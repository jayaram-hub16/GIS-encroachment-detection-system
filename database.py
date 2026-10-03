"""
database.py - SQLite Database Models for Municipal GIS System.
Supports: User (user|admin roles), ParcelRecord, EncroachmentRecord, AuditLog.
Passwords hashed with bcrypt. Roles enforced on every mutation API.
"""

from __future__ import annotations
import bcrypt
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()


# ────────────────────────────────────────────────────────────────
#  ROLE CONSTANTS  (source of truth — never hard-code strings)
# ────────────────────────────────────────────────────────────────
ROLE_USER  = "user"
ROLE_ADMIN = "admin"


class User(UserMixin, db.Model):
    """Application user — roles: 'user' (read-only) | 'admin' (full access)."""
    __tablename__ = "users"

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80),  unique=True, nullable=False, index=True)
    email         = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name     = db.Column(db.String(150), nullable=False, default="")
    role          = db.Column(db.String(20),  nullable=False, default=ROLE_USER)
    is_active     = db.Column(db.Boolean,     default=True,  nullable=False)
    created_at    = db.Column(db.DateTime,    default=lambda: datetime.now(timezone.utc))
    last_login    = db.Column(db.DateTime,    nullable=True)

    # ── password helpers ──────────────────────────────────────────
    def set_password(self, plain: str) -> None:
        """Hash and persist password. Never stores plain text."""
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

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "username":   self.username,
            "email":      self.email,
            "full_name":  self.full_name,
            "role":       self.role,
            "is_active":  self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat()  if self.last_login  else None,
        }


class ParcelRecord(db.Model):
    """Persistent cadastral parcel record."""
    __tablename__ = "parcel_records"

    id                  = db.Column(db.Integer, primary_key=True)
    parcel_id           = db.Column(db.String(60), unique=True, nullable=False, index=True)
    survey_number       = db.Column(db.String(60), nullable=False)
    owner_name          = db.Column(db.String(150), nullable=False)
    owner_type          = db.Column(db.String(50),  nullable=False, default="PRIVATE_CITIZEN")
    deed_number         = db.Column(db.String(80),  nullable=False, default="")
    tax_id              = db.Column(db.String(80),  nullable=False, default="")
    contact_email       = db.Column(db.String(120), default="")
    contact_phone       = db.Column(db.String(30),  default="")
    zone_name           = db.Column(db.String(120), default="")
    registered_land_use = db.Column(db.String(40),  nullable=False, default="RESIDENTIAL")
    area_sqm            = db.Column(db.Float, default=0.0)
    max_coverage_ratio  = db.Column(db.Float, default=0.65)
    setback_meters      = db.Column(db.Float, default=2.5)
    market_rate_per_sqm = db.Column(db.Float, default=12000.0)
    latitude            = db.Column(db.Float, nullable=True)
    longitude           = db.Column(db.Float, nullable=True)
    registration_date   = db.Column(db.String(20), default="")
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
            "owner_name":          self.owner_name,
            "owner_type":          self.owner_type,
            "deed_number":         self.deed_number,
            "tax_id":              self.tax_id,
            "contact_email":       self.contact_email,
            "contact_phone":       self.contact_phone,
            "zone_name":           self.zone_name,
            "registered_land_use": self.registered_land_use,
            "area_sqm":            self.area_sqm,
            "max_coverage_ratio":  self.max_coverage_ratio,
            "setback_meters":      self.setback_meters,
            "market_rate_per_sqm": self.market_rate_per_sqm,
            "latitude":            self.latitude,
            "longitude":           self.longitude,
            "registration_date":   self.registration_date,
            "notes":               self.notes,
            "created_at":          self.created_at.isoformat() if self.created_at else None,
            "updated_at":          self.updated_at.isoformat() if self.updated_at else None,
        }


class EncroachmentRecord(db.Model):
    """Persistent encroachment violation record."""
    __tablename__ = "encroachment_records"

    id                  = db.Column(db.Integer, primary_key=True)
    flag_id             = db.Column(db.String(60), unique=True, nullable=False, index=True)
    encroachment_type   = db.Column(db.String(60), nullable=False)
    severity            = db.Column(db.String(20), nullable=False)
    violator_name       = db.Column(db.String(150), default="")
    violator_parcel_id  = db.Column(db.String(60),  default="")
    affected_parcel_id  = db.Column(db.String(60),  nullable=False, default="")
    affected_owner      = db.Column(db.String(150), default="")
    affected_land_use   = db.Column(db.String(40),  default="")
    encroached_area_sqm = db.Column(db.Float, default=0.0)
    estimated_penalty   = db.Column(db.Float, default=0.0)
    confidence          = db.Column(db.Float, default=0.0)
    status              = db.Column(db.String(40), default="DETECTED")
    recommended_action  = db.Column(db.Text, default="")
    latitude            = db.Column(db.Float, nullable=True)
    longitude           = db.Column(db.Float, nullable=True)
    notes               = db.Column(db.Text, default="")
    created_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at          = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                                    onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id":                  self.id,
            "flag_id":             self.flag_id,
            "encroachment_type":   self.encroachment_type,
            "severity":            self.severity,
            "violator_name":       self.violator_name,
            "violator_parcel_id":  self.violator_parcel_id,
            "affected_parcel_id":  self.affected_parcel_id,
            "affected_owner":      self.affected_owner,
            "affected_land_use":   self.affected_land_use,
            "encroached_area_sqm": self.encroached_area_sqm,
            "estimated_penalty":   self.estimated_penalty,
            "confidence":          self.confidence,
            "status":              self.status,
            "recommended_action":  self.recommended_action,
            "latitude":            self.latitude,
            "longitude":           self.longitude,
            "notes":               self.notes,
            "created_at":          self.created_at.isoformat() if self.created_at else None,
            "updated_at":          self.updated_at.isoformat() if self.updated_at else None,
        }


class AuditLog(db.Model):
    """
    Immutable audit trail for all admin mutations.
    Entries are NEVER updated or deleted — append-only.
    """
    __tablename__ = "audit_logs"

    id          = db.Column(db.Integer, primary_key=True)
    actor_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_name  = db.Column(db.String(100), nullable=False, default="")   # snapshot — survives user deletion
    action      = db.Column(db.String(60),  nullable=False)               # CREATED | UPDATED | DELETED | LOGIN | ...
    resource    = db.Column(db.String(60),  nullable=False, default="")   # parcel | encroachment | user | system
    resource_id = db.Column(db.String(100), nullable=True)                # record PK or identifier
    detail      = db.Column(db.Text, default="")                          # human-readable summary
    ip_address  = db.Column(db.String(60),  nullable=True)
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
#  AUDIT HELPER
# ────────────────────────────────────────────────────────────────

def audit(actor, action: str, resource: str, resource_id=None,
          detail: str = "", ip: str = None) -> None:
    """Append one immutable audit-log entry and flush (no commit needed here)."""
    entry = AuditLog(
        actor_id    = actor.id   if actor else None,
        actor_name  = (actor.username or actor.email) if actor else "system",
        action      = action,
        resource    = resource,
        resource_id = str(resource_id) if resource_id is not None else None,
        detail      = detail[:1000],
        ip_address  = ip,
    )
    db.session.add(entry)
    # caller is responsible for db.session.commit()


# ────────────────────────────────────────────────────────────────
#  DB INIT
# ────────────────────────────────────────────────────────────────

def init_db(app) -> None:
    """
    Initialise tables (idempotent via create_all) and seed default accounts.
    Safe to call on every startup — skips seeding if users already exist.
    """
    db.init_app(app)
    with app.app_context():
        db.create_all()
        try:
            if User.query.count() == 0:
                admin = User(
                    username  = "admin",
                    email     = "admin@municipal.gov",
                    full_name = "Municipal Administrator",
                    role      = ROLE_ADMIN,
                    is_active = True,
                )
                admin.set_password("Admin@1234")
                db.session.add(admin)

                user = User(
                    username  = "surveyor",
                    email     = "surveyor@municipal.gov",
                    full_name = "Survey Officer",
                    role      = ROLE_USER,
                    is_active = True,
                )
                user.set_password("Survey@1234")
                db.session.add(user)
                db.session.commit()
                print("[DB] Seeded: admin / Admin@1234  &  surveyor / Survey@1234")
            else:
                print(f"[DB] Ready — {User.query.count()} user(s).")
        except Exception as exc:
            db.session.rollback()
            print(f"[DB] Seed skipped ({exc})")
