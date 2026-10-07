"""
database.py - Municipal GIS Encroachment Detection System
Extended database with:
  - 4 roles: admin | gis_officer | surveyor | viewer
  - EvidenceFile: file attachments linked to encroachment cases
  - Notification: in-app alerts
  - Extended ParcelRecord: village, mandal, district, state
  - Extended EncroachmentRecord: case_id, assigned_officer, verification fields
  - OTPToken: password-reset tokens
"""

from __future__ import annotations
import bcrypt
import secrets
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# ────────────────────────────────────────────────────────────────
#  ROLE CONSTANTS
# ────────────────────────────────────────────────────────────────
ROLE_ADMIN      = "admin"
ROLE_GIS_OFFICER = "gis_officer"
ROLE_SURVEYOR   = "surveyor"
ROLE_VIEWER     = "viewer"

# Backward-compatible alias
ROLE_USER = ROLE_VIEWER

# Roles that can write/modify data
WRITE_ROLES = {ROLE_ADMIN, ROLE_GIS_OFFICER}
# Roles that can verify encroachments
VERIFY_ROLES = {ROLE_ADMIN, ROLE_GIS_OFFICER, ROLE_SURVEYOR}


class User(UserMixin, db.Model):
    """Application user — roles: admin | gis_officer | surveyor | viewer."""
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False, index=True)
    email         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name     = db.Column(db.String(150), nullable=False, default="")
    role          = db.Column(db.String(20),  nullable=False, default=ROLE_VIEWER)
    is_active     = db.Column(db.Boolean,     default=True,  nullable=False)
    phone         = db.Column(db.String(30),  nullable=True)
    department    = db.Column(db.String(120), nullable=True)
    created_at    = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    last_login    = db.Column(db.DateTime,    nullable=True)

    # ── password helpers ──────────────────────────────────────────
    def set_password(self, plain: str) -> None:
        """Hash and store password. Never stores plain text."""
        self.password_hash = bcrypt.hashpw(
            plain.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, plain: str) -> bool:
        try:
            return bcrypt.checkpw(plain.encode("utf-8"),
                                  self.password_hash.encode("utf-8"))
        except Exception:
            return False

    # ── role helpers ──────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def can_write(self) -> bool:
        """Admin and GIS Officer can create/edit/delete records."""
        return self.role in WRITE_ROLES

    @property
    def can_verify(self) -> bool:
        """Admin, GIS Officer, Surveyor can verify/reject encroachments."""
        return self.role in VERIFY_ROLES

    @property
    def role_display(self) -> str:
        labels = {
            ROLE_ADMIN:       "Administrator",
            ROLE_GIS_OFFICER: "GIS Officer",
            ROLE_SURVEYOR:    "Surveyor",
            ROLE_VIEWER:      "Viewer",
        }
        return labels.get(self.role, self.role.replace("_", " ").title())

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "username":    self.username,
            "email":       self.email,
            "full_name":   self.full_name,
            "role":        self.role,
            "role_display": self.role_display,
            "is_active":   self.is_active,
            "phone":       self.phone,
            "department":  self.department,
            "can_write":   self.can_write,
            "can_verify":  self.can_verify,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
            "last_login":  self.last_login.isoformat()  if self.last_login  else None,
        }


class OTPToken(db.Model):
    """Secure password-reset / OTP tokens. Auto-expires after 15 minutes."""
    __tablename__ = "otp_tokens"

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token      = db.Column(db.String(64), unique=True, nullable=False, index=True)
    purpose    = db.Column(db.String(30), nullable=False, default="password_reset")
    attempts   = db.Column(db.Integer, default=0)
    used       = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=False)

    user = db.relationship("User", backref="otp_tokens")

    @classmethod
    def create(cls, user_id: int, purpose: str = "password_reset", ttl_minutes: int = 15):
        """Create a new secure token, invalidating previous ones for same user+purpose."""
        # Invalidate existing tokens
        cls.query.filter_by(user_id=user_id, purpose=purpose, used=False).update({"used": True})
        token = cls(
            user_id    = user_id,
            token      = secrets.token_urlsafe(48),
            purpose    = purpose,
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
        )
        db.session.add(token)
        return token

    @property
    def is_valid(self) -> bool:
        return (
            not self.used
            and self.attempts < 5
            and datetime.now(timezone.utc) < self.expires_at
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "purpose": self.purpose,
            "used": self.used,
            "attempts": self.attempts,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class ParcelRecord(db.Model):
    """Persistent cadastral parcel record — extended with location hierarchy."""
    __tablename__ = "parcel_records"

    id                  = db.Column(db.Integer, primary_key=True)
    parcel_id           = db.Column(db.String(60), unique=True, nullable=False, index=True)
    survey_number       = db.Column(db.String(60), nullable=False)
    sub_division        = db.Column(db.String(60), default="")
    owner_name          = db.Column(db.String(150), nullable=False)
    owner_type          = db.Column(db.String(50),  nullable=False, default="PRIVATE_CITIZEN")
    deed_number         = db.Column(db.String(80),  nullable=False, default="")
    tax_id              = db.Column(db.String(80),  nullable=False, default="")
    contact_email       = db.Column(db.String(120), default="")
    contact_phone       = db.Column(db.String(30),  default="")
    # Location hierarchy
    zone_name           = db.Column(db.String(120), default="")
    village             = db.Column(db.String(120), default="")
    mandal              = db.Column(db.String(120), default="")
    district            = db.Column(db.String(120), default="")
    state               = db.Column(db.String(80),  default="")
    # Land details
    registered_land_use = db.Column(db.String(40),  nullable=False, default="RESIDENTIAL")
    land_category       = db.Column(db.String(80),  default="")
    area_sqm            = db.Column(db.Float, default=0.0)
    max_coverage_ratio  = db.Column(db.Float, default=0.65)
    setback_meters      = db.Column(db.Float, default=2.5)
    market_rate_per_sqm = db.Column(db.Float, default=12000.0)
    # Coordinates
    latitude            = db.Column(db.Float, nullable=True)
    longitude           = db.Column(db.Float, nullable=True)
    geometry_geojson    = db.Column(db.Text,  nullable=True)   # GeoJSON polygon string
    # Dates
    registration_date   = db.Column(db.String(20), default="")
    survey_date         = db.Column(db.String(20), default="")
    # Status
    status              = db.Column(db.String(30), default="ACTIVE")
    data_source         = db.Column(db.String(120), default="")
    notes               = db.Column(db.Text, default="")
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                    onupdate=lambda: datetime.now(timezone.utc))
    created_by          = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id":                  self.id,
            "parcel_id":           self.parcel_id,
            "survey_number":       self.survey_number,
            "sub_division":        self.sub_division,
            "owner_name":          self.owner_name,
            "owner_type":          self.owner_type,
            "deed_number":         self.deed_number,
            "tax_id":              self.tax_id,
            "contact_email":       self.contact_email,
            "contact_phone":       self.contact_phone,
            "zone_name":           self.zone_name,
            "village":             self.village,
            "mandal":              self.mandal,
            "district":            self.district,
            "state":               self.state,
            "registered_land_use": self.registered_land_use,
            "land_category":       self.land_category,
            "area_sqm":            self.area_sqm,
            "max_coverage_ratio":  self.max_coverage_ratio,
            "setback_meters":      self.setback_meters,
            "market_rate_per_sqm": self.market_rate_per_sqm,
            "latitude":            self.latitude,
            "longitude":           self.longitude,
            "geometry_geojson":    self.geometry_geojson,
            "registration_date":   self.registration_date,
            "survey_date":         self.survey_date,
            "status":              self.status,
            "data_source":         self.data_source,
            "notes":               self.notes,
            "created_at":          self.created_at.isoformat() if self.created_at else None,
            "updated_at":          self.updated_at.isoformat() if self.updated_at else None,
        }


class EncroachmentRecord(db.Model):
    """Persistent encroachment case — extended with case workflow fields."""
    __tablename__ = "encroachment_records"

    id                  = db.Column(db.Integer, primary_key=True)
    # Case ID: ENC-YYYY-000001
    flag_id             = db.Column(db.String(60), unique=True, nullable=False, index=True)
    encroachment_type   = db.Column(db.String(60), nullable=False)
    severity            = db.Column(db.String(20), nullable=False)
    detection_method    = db.Column(db.String(60), default="GIS_ANALYSIS")
    violator_name       = db.Column(db.String(150), default="")
    violator_parcel_id  = db.Column(db.String(60),  default="")
    affected_parcel_id  = db.Column(db.String(60),  nullable=False, default="")
    affected_owner      = db.Column(db.String(150), default="")
    affected_land_use   = db.Column(db.String(40),  default="")
    # Location
    village             = db.Column(db.String(120), default="")
    mandal              = db.Column(db.String(120), default="")
    district            = db.Column(db.String(120), default="")
    latitude            = db.Column(db.Float, nullable=True)
    longitude           = db.Column(db.Float, nullable=True)
    geometry_geojson    = db.Column(db.Text, nullable=True)
    # Metrics
    encroached_area_sqm = db.Column(db.Float, default=0.0)
    encroachment_pct    = db.Column(db.Float, default=0.0)
    estimated_penalty   = db.Column(db.Float, default=0.0)
    confidence          = db.Column(db.Float, default=0.0)
    # Status workflow: DETECTED -> PENDING_VERIFICATION -> VERIFIED | REJECTED
    status              = db.Column(db.String(40), default="DETECTED", index=True)
    # Verification
    assigned_officer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_by_id      = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    verified_at         = db.Column(db.DateTime, nullable=True)
    officer_remarks     = db.Column(db.Text, default="")
    action_taken        = db.Column(db.Text, default="")
    recommended_action  = db.Column(db.Text, default="")
    notes               = db.Column(db.Text, default="")
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                    onupdate=lambda: datetime.now(timezone.utc))

    assigned_officer = db.relationship("User", foreign_keys=[assigned_officer_id],
                                       backref="assigned_cases")
    verified_by      = db.relationship("User", foreign_keys=[verified_by_id],
                                       backref="verified_cases")
    evidence_files   = db.relationship("EvidenceFile", backref="case",
                                       cascade="all, delete-orphan", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id":                  self.id,
            "flag_id":             self.flag_id,
            "encroachment_type":   self.encroachment_type,
            "severity":            self.severity,
            "detection_method":    self.detection_method,
            "violator_name":       self.violator_name,
            "violator_parcel_id":  self.violator_parcel_id,
            "affected_parcel_id":  self.affected_parcel_id,
            "affected_owner":      self.affected_owner,
            "affected_land_use":   self.affected_land_use,
            "village":             self.village,
            "mandal":              self.mandal,
            "district":            self.district,
            "latitude":            self.latitude,
            "longitude":           self.longitude,
            "geometry_geojson":    self.geometry_geojson,
            "encroached_area_sqm": self.encroached_area_sqm,
            "encroachment_pct":    self.encroachment_pct,
            "estimated_penalty":   self.estimated_penalty,
            "confidence":          self.confidence,
            "status":              self.status,
            "assigned_officer_id": self.assigned_officer_id,
            "assigned_officer":    self.assigned_officer.full_name if self.assigned_officer else None,
            "verified_by_id":      self.verified_by_id,
            "verified_by":         self.verified_by.full_name if self.verified_by else None,
            "verified_at":         self.verified_at.isoformat() if self.verified_at else None,
            "officer_remarks":     self.officer_remarks,
            "action_taken":        self.action_taken,
            "recommended_action":  self.recommended_action,
            "notes":               self.notes,
            "evidence_count":      self.evidence_files.count() if self.evidence_files else 0,
            "created_at":          self.created_at.isoformat() if self.created_at else None,
            "updated_at":          self.updated_at.isoformat() if self.updated_at else None,
        }


class EvidenceFile(db.Model):
    """Evidence files attached to encroachment cases."""
    __tablename__ = "evidence_files"

    id              = db.Column(db.Integer, primary_key=True)
    case_id         = db.Column(db.Integer, db.ForeignKey("encroachment_records.id"),
                                nullable=False, index=True)
    filename        = db.Column(db.String(255), nullable=False)
    original_name   = db.Column(db.String(255), nullable=False)
    file_type       = db.Column(db.String(50),  nullable=False)   # image|geojson|document|etc
    mime_type       = db.Column(db.String(100), nullable=True)
    file_size_bytes = db.Column(db.Integer, default=0)
    file_path       = db.Column(db.String(500), nullable=False)
    description     = db.Column(db.Text, default="")
    evidence_type   = db.Column(db.String(60), default="GENERAL")  # BEFORE|AFTER|ANNOTATED|SURVEY
    uploaded_by_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at      = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])

    def to_dict(self) -> dict:
        return {
            "id":             self.id,
            "case_id":        self.case_id,
            "filename":       self.filename,
            "original_name":  self.original_name,
            "file_type":      self.file_type,
            "mime_type":      self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "description":    self.description,
            "evidence_type":  self.evidence_type,
            "uploaded_by":    self.uploaded_by.full_name if self.uploaded_by else None,
            "created_at":     self.created_at.isoformat() if self.created_at else None,
            "download_url":   f"/api/evidence/{self.id}/download",
            "preview_url":    f"/api/evidence/{self.id}/preview" if self.file_type == "image" else None,
        }


class Notification(db.Model):
    """In-app notifications for users."""
    __tablename__ = "notifications"

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title       = db.Column(db.String(200), nullable=False)
    message     = db.Column(db.Text, default="")
    notif_type  = db.Column(db.String(40), default="INFO")  # INFO|SUCCESS|WARNING|ERROR
    resource    = db.Column(db.String(60), nullable=True)
    resource_id = db.Column(db.String(100), nullable=True)
    is_read     = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", backref="notifications")

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "title":       self.title,
            "message":     self.message,
            "notif_type":  self.notif_type,
            "resource":    self.resource,
            "resource_id": self.resource_id,
            "is_read":     self.is_read,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    """
    Immutable audit trail. Entries are NEVER updated or deleted — append-only.
    """
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer, primary_key=True)
    actor_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_name  = db.Column(db.String(100), nullable=False, default="")
    action      = db.Column(db.String(60),  nullable=False)
    resource    = db.Column(db.String(60),  nullable=False, default="")
    resource_id = db.Column(db.String(100), nullable=True)
    detail      = db.Column(db.Text, default="")
    ip_address  = db.Column(db.String(60),  nullable=True)
    user_agent  = db.Column(db.String(300), nullable=True)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "actor_id":    self.actor_id,
            "actor_name":  self.actor_name,
            "action":      self.action,
            "resource":    self.resource,
            "resource_id": self.resource_id,
            "detail":      self.detail,
            "ip_address":  self.ip_address,
            "created_at":  self.created_at.isoformat() if self.created_at else None,
        }


# ────────────────────────────────────────────────────────────────
#  HELPERS
# ────────────────────────────────────────────────────────────────

def audit(actor, action: str, resource: str, resource_id=None,
          detail: str = "", ip: str = None, ua: str = None) -> None:
    """Append one immutable audit-log entry (caller must commit)."""
    entry = AuditLog(
        actor_id    = actor.id   if actor else None,
        actor_name  = (actor.username or actor.email) if actor else "system",
        action      = action,
        resource    = resource,
        resource_id = str(resource_id) if resource_id is not None else None,
        detail      = detail[:1000],
        ip_address  = ip,
        user_agent  = (ua or "")[:300],
    )
    db.session.add(entry)


def notify(user_id: int, title: str, message: str = "",
           notif_type: str = "INFO", resource: str = None,
           resource_id: str = None) -> None:
    """Create an in-app notification (caller must commit)."""
    n = Notification(
        user_id     = user_id,
        title       = title[:200],
        message     = message[:2000],
        notif_type  = notif_type,
        resource    = resource,
        resource_id = str(resource_id) if resource_id is not None else None,
    )
    db.session.add(n)


# ────────────────────────────────────────────────────────────────
#  DB INIT (idempotent — safe to call on every startup)
# ────────────────────────────────────────────────────────────────

def init_db(app) -> None:
    """
    Initialise tables with create_all (additive — does not drop existing columns).
    Safely adds missing columns to existing SQLite / PostgreSQL tables.
    Seeds default admin account ONLY when the users table is empty.
    """
    db.init_app(app)
    with app.app_context():
        db.create_all()
        try:
            from sqlalchemy import inspect, text
            with db.engine.connect() as conn:
                inspector = inspect(db.engine)
                table_names = inspector.get_table_names()

                if "users" in table_names:
                    user_cols = {c["name"] for c in inspector.get_columns("users")}
                    for col_name, col_type in [("phone", "VARCHAR(30)"), ("department", "VARCHAR(120)")]:
                        if col_name not in user_cols:
                            conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                            conn.commit()

                if "parcel_records" in table_names:
                    parcel_cols = {c["name"] for c in inspector.get_columns("parcel_records")}
                    for col_name, col_type in [
                        ("sub_division", "VARCHAR(60)"), ("village", "VARCHAR(120)"),
                        ("mandal", "VARCHAR(120)"), ("district", "VARCHAR(120)"),
                        ("state", "VARCHAR(80)"), ("land_category", "VARCHAR(80)"),
                        ("geometry_geojson", "TEXT"), ("survey_date", "VARCHAR(20)"),
                        ("status", "VARCHAR(30)"), ("data_source", "VARCHAR(120)"),
                    ]:
                        if col_name not in parcel_cols:
                            conn.execute(text(f"ALTER TABLE parcel_records ADD COLUMN {col_name} {col_type}"))
                            conn.commit()

                if "encroachment_records" in table_names:
                    enc_cols = {c["name"] for c in inspector.get_columns("encroachment_records")}
                    for col_name, col_type in [
                        ("detection_method", "VARCHAR(60)"), ("village", "VARCHAR(120)"),
                        ("mandal", "VARCHAR(120)"), ("district", "VARCHAR(120)"),
                        ("geometry_geojson", "TEXT"), ("encroachment_pct", "FLOAT"),
                        ("assigned_officer_id", "INTEGER"), ("verified_by_id", "INTEGER"),
                        ("verified_at", "DATETIME"), ("officer_remarks", "TEXT"),
                        ("action_taken", "TEXT"),
                    ]:
                        if col_name not in enc_cols:
                            conn.execute(text(f"ALTER TABLE encroachment_records ADD COLUMN {col_name} {col_type}"))
                            conn.commit()

            if User.query.count() == 0:
                import os
                # Admin password from env or random-generated (never hardcoded in prod)
                admin_pw = os.environ.get("ADMIN_INITIAL_PASSWORD", "")
                if not admin_pw:
                    # Generate a secure random password on first run
                    admin_pw = secrets.token_urlsafe(16)
                    print(f"[DB] Generated admin password (set ADMIN_INITIAL_PASSWORD to override): {admin_pw}")

                admin = User(
                    username   = "admin",
                    email      = os.environ.get("ADMIN_EMAIL", "admin@municipal.gov"),
                    full_name  = "Municipal Administrator",
                    role       = ROLE_ADMIN,
                    department = "Administration",
                    is_active  = True,
                )
                admin.set_password(admin_pw)
                db.session.add(admin)
                db.session.commit()
                print(f"[DB] Admin account created. Username: admin")
            else:
                # Migrate existing users: map old 'user' role -> 'viewer'
                updated = User.query.filter_by(role="user").update({"role": ROLE_VIEWER})
                if updated:
                    db.session.commit()
                    print(f"[DB] Migrated {updated} user(s): 'user' -> 'viewer'")
                print(f"[DB] Ready — {User.query.count()} user(s).")
        except Exception as exc:
            db.session.rollback()
            print(f"[DB] Init error ({exc})")
