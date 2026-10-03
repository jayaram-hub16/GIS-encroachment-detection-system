"""
run_app.py - Municipal GIS Encroachment Detection Web Application.
Authentication : Flask-Login (session-based).
Authorisation  : ROLE_USER (read-only) | ROLE_ADMIN (full CRUD).
All mutation APIs are guarded server-side with admin_required().
Public self-registration is supported via /signup.
Audit log captures every admin action.
"""

from __future__ import annotations
import os, re, uuid
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, session
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)

from database import (
    db, User, ParcelRecord, EncroachmentRecord, AuditLog,
    ROLE_USER, ROLE_ADMIN, audit, init_db,
)
from core.models import (
    MunicipalSurveyRegistry, DisputeStatus, LandUseType, OwnerType,
)
from core.classifier       import LandCoverClassifier
from core.detector         import EncroachmentDetector
from core.dataset_generator import build_default_municipal_dataset
from core.report_generator  import MunicipalReportGenerator

# ══════════════════════════════════════════════════════════════════
#  FLASK APP CONFIG
# ══════════════════════════════════════════════════════════════════

app = Flask(__name__, template_folder="templates", static_folder="static")

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Fix Render/Heroku DATABASE_URL: they provide postgres:// but SQLAlchemy needs postgresql://
_raw_db_url = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'municipal.db')}")
if _raw_db_url.startswith("postgres://"):
    _raw_db_url = _raw_db_url.replace("postgres://", "postgresql://", 1)

app.config["SECRET_KEY"]                 = os.environ.get("SECRET_KEY", "muni-gis-rbac-secret-2026")
app.config["SQLALCHEMY_DATABASE_URI"]    = _raw_db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SESSION_COOKIE_HTTPONLY"]    = True
app.config["SESSION_COOKIE_SAMESITE"]    = "Lax"
app.config["SESSION_COOKIE_SECURE"]      = os.environ.get("HTTPS", "false").lower() == "true"

init_db(app)

login_manager = LoginManager(app)
login_manager.login_view         = "login_page"
login_manager.login_message      = "Please log in to access the system."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(uid: str):
    return db.session.get(User, int(uid))


# ══════════════════════════════════════════════════════════════════
#  ROLE-BASED DECORATORS  (server-side enforcement)
# ══════════════════════════════════════════════════════════════════

def admin_required(fn):
    """
    Decorator: rejects non-admin callers with 403 JSON.
    Applied on every mutation API (POST / PUT / DELETE).
    A regular user sending requests manually will always get:
        {"status": "error", "message": "Admin access required.", "code": 403}
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"status": "error", "message": "Authentication required.", "code": 401}), 401
        if not current_user.is_admin:
            return jsonify({"status": "error", "message": "Admin access required.", "code": 403}), 403
        return fn(*args, **kwargs)
    return login_required(wrapper)


def admin_page_required(fn):
    """Decorator for HTML pages: redirects non-admins to user dashboard."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            return redirect(url_for("user_dashboard"))
        return fn(*args, **kwargs)
    return wrapper


# ══════════════════════════════════════════════════════════════════
#  GIS IN-MEMORY STATE  (unchanged from original)
# ══════════════════════════════════════════════════════════════════

class MunicipalAppState:
    def __init__(self):
        self.classifier = LandCoverClassifier()
        self.registry: MunicipalSurveyRegistry = build_default_municipal_dataset(self.classifier)
        self.detector   = EncroachmentDetector(self.registry)
        self.report_gen = MunicipalReportGenerator(self.registry)
        self.detector.run_detection_scan()

    def reset(self):
        self.registry   = build_default_municipal_dataset(self.classifier)
        self.detector   = EncroachmentDetector(self.registry)
        self.report_gen = MunicipalReportGenerator(self.registry)
        self.detector.run_detection_scan()


gis_state = MunicipalAppState()


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def sanitize(val, max_len: int = 200) -> str:
    if not isinstance(val, str):
        val = str(val)
    val = val.strip()[:max_len]
    val = re.sub(r"[<>\"']", "", val)
    return val


def client_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr or "")


def validate_password(pwd: str) -> str | None:
    """Return error string or None if valid."""
    if len(pwd) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", pwd):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"[0-9]", pwd):
        return "Password must contain at least one number."
    return None


# ══════════════════════════════════════════════════════════════════
#  AUTH ROUTES — PUBLIC
# ══════════════════════════════════════════════════════════════════

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard") if current_user.is_admin else url_for("user_dashboard"))

    error = None
    if request.method == "POST":
        identifier = sanitize(request.form.get("identifier", ""), 120)
        password   = request.form.get("password", "")

        if not identifier or not password:
            error = "Email / username and password are required."
        else:
            user = User.query.filter(
                (User.email == identifier) | (User.username == identifier)
            ).first()

            if user and user.is_active and user.check_password(password):
                login_user(user, remember=request.form.get("remember") == "on")
                user.last_login = datetime.now(timezone.utc)
                audit(user, "LOGIN", "system", detail="User logged in", ip=client_ip())
                db.session.commit()
                dest = url_for("admin_dashboard") if user.is_admin else url_for("user_dashboard")
                return redirect(request.args.get("next") or dest)
            elif user and not user.is_active:
                error = "Your account has been deactivated. Contact an administrator."
            else:
                error = "Invalid credentials. Please check your email/username and password."

    return render_template("login.html", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup_page():
    """Public self-registration — always creates ROLE_USER accounts."""
    if current_user.is_authenticated:
        return redirect(url_for("user_dashboard"))

    error = success = None
    if request.method == "POST":
        username  = sanitize(request.form.get("username", ""), 80)
        email     = sanitize(request.form.get("email", ""), 120).lower()
        full_name = sanitize(request.form.get("full_name", ""), 150)
        password  = request.form.get("password", "")
        confirm   = request.form.get("confirm_password", "")

        if not username or not email or not password:
            error = "Username, email, and password are required."
        elif password != confirm:
            error = "Passwords do not match."
        elif (pwd_err := validate_password(password)):
            error = pwd_err
        elif User.query.filter(
            (User.username == username) | (User.email == email)
        ).first():
            error = "Username or email is already registered."
        else:
            new_user = User(
                username  = username,
                email     = email,
                full_name = full_name,
                role      = ROLE_USER,   # NEVER allow self-upgrading to admin
                is_active = True,
            )
            new_user.set_password(password)
            db.session.add(new_user)
            audit(new_user, "SIGNUP", "user",
                  resource_id=username,
                  detail=f"New user registered: {username}",
                  ip=client_ip())
            db.session.commit()
            success = "Account created! You can now log in."

    return render_template("signup.html", error=error, success=success)


@app.route("/logout")
@login_required
def logout():
    audit(current_user, "LOGOUT", "system", detail="User logged out", ip=client_ip())
    db.session.commit()
    logout_user()
    session.clear()
    return redirect(url_for("login_page"))


# ══════════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ══════════════════════════════════════════════════════════════════

import socket

def get_host_ip() -> str:
    """Get the best local IP address for LAN access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.route("/connect")
def connect_page():
    """Public network connect page — shows QR code + URL for all devices."""
    return render_template("connect.html", host_ip=get_host_ip())


@app.route("/")
@login_required
def index():
    """GIS map — accessible to both roles."""
    return render_template("index.html", user=current_user)


@app.route("/dashboard")
@login_required
def dashboard():
    """Smart redirect: admins → admin dashboard, users → user dashboard."""
    if current_user.is_admin:
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/admin")
@admin_page_required
def admin_dashboard():
    """Admin-only management dashboard."""
    return render_template("dashboard.html", user=current_user)


@app.route("/user-dashboard")
@login_required
def user_dashboard():
    """Read-only dashboard for regular users."""
    return render_template("user_dashboard.html", user=current_user)


# ══════════════════════════════════════════════════════════════════
#  CURRENT USER API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/me", methods=["GET"])
@login_required
def get_me():
    return jsonify({"status": "success", "user": current_user.to_dict()})


# ══════════════════════════════════════════════════════════════════
#  USER MANAGEMENT APIS  — ADMIN ONLY
# ══════════════════════════════════════════════════════════════════

@app.route("/api/users", methods=["GET"])
@login_required
def get_users():
    """List users — admin sees all; regular users see only themselves."""
    if current_user.is_admin:
        page     = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 25, type=int), 100)
        search   = request.args.get("search", "").strip()
        q        = User.query
        if search:
            like = f"%{search}%"
            q = q.filter(
                User.username.ilike(like) | User.email.ilike(like) | User.full_name.ilike(like)
            )
        q = q.order_by(User.created_at.desc())
        total   = q.count()
        records = q.offset((page - 1) * per_page).limit(per_page).all()
        return jsonify({
            "status": "success",
            "total":  total, "page": page, "per_page": per_page,
            "pages":  (total + per_page - 1) // per_page,
            "users":  [u.to_dict() for u in records],
        })
    # Regular users: only self
    return jsonify({"status": "success", "users": [current_user.to_dict()]})


@app.route("/api/users", methods=["POST"])
@admin_required
def create_user():
    """Admin creates a new user. Role can be set by admin only."""
    data      = request.get_json() or {}
    username  = sanitize(data.get("username", ""), 80)
    email     = sanitize(data.get("email", ""), 120).lower()
    full_name = sanitize(data.get("full_name", ""), 150)
    role      = data.get("role", ROLE_USER)
    password  = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"status": "error", "message": "Username, email, and password are required."}), 400
    if (pwd_err := validate_password(password)):
        return jsonify({"status": "error", "message": pwd_err}), 400
    if role not in (ROLE_USER, ROLE_ADMIN):
        role = ROLE_USER
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({"status": "error", "message": "Username or email already exists."}), 409

    user = User(username=username, email=email, full_name=full_name, role=role, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    audit(current_user, "CREATED", "user", resource_id=user.id,
          detail=f"Created user '{username}' with role '{role}'", ip=client_ip())
    db.session.commit()
    return jsonify({"status": "success", "user": user.to_dict()}), 201


@app.route("/api/users/<int:uid>", methods=["GET"])
@login_required
def get_user(uid: int):
    """Admin sees any user; regular user sees only self."""
    if not current_user.is_admin and current_user.id != uid:
        return jsonify({"status": "error", "message": "Access denied.", "code": 403}), 403
    user = db.session.get(User, uid)
    if not user:
        return jsonify({"status": "error", "message": "User not found."}), 404
    return jsonify({"status": "success", "user": user.to_dict()})


@app.route("/api/users/<int:uid>", methods=["PUT"])
@login_required
def update_user(uid: int):
    """
    Admin may update any field (incl. role/active).
    Regular users may only update their own full_name and password
    — role changes are silently ignored for non-admins.
    """
    if not current_user.is_admin and current_user.id != uid:
        return jsonify({"status": "error", "message": "Access denied.", "code": 403}), 403

    user = db.session.get(User, uid)
    if not user:
        return jsonify({"status": "error", "message": "User not found."}), 404

    data    = request.get_json() or {}
    changes = []

    if "full_name" in data:
        user.full_name = sanitize(data["full_name"], 150)
        changes.append("full_name")

    # Only admin can change email, role, active status
    if current_user.is_admin:
        if "email" in data:
            user.email = sanitize(data["email"], 120).lower()
            changes.append("email")
        if "role" in data and data["role"] in (ROLE_USER, ROLE_ADMIN):
            if user.id == current_user.id and data["role"] != ROLE_ADMIN:
                return jsonify({"status": "error",
                                "message": "Cannot demote yourself from admin."}), 400
            user.role = data["role"]
            changes.append("role")
        if "is_active" in data:
            user.is_active = bool(data["is_active"])
            changes.append("is_active")

    if "password" in data and data["password"]:
        if (pwd_err := validate_password(data["password"])):
            return jsonify({"status": "error", "message": pwd_err}), 400
        user.set_password(data["password"])
        changes.append("password")

    audit(current_user, "UPDATED", "user", resource_id=uid,
          detail=f"Updated fields: {', '.join(changes)}", ip=client_ip())
    db.session.commit()
    return jsonify({"status": "success", "user": user.to_dict()})


@app.route("/api/users/<int:uid>", methods=["DELETE"])
@admin_required
def delete_user(uid: int):
    if current_user.id == uid:
        return jsonify({"status": "error", "message": "Cannot delete your own account."}), 400
    user = db.session.get(User, uid)
    if not user:
        return jsonify({"status": "error", "message": "User not found."}), 404
    uname = user.username
    audit(current_user, "DELETED", "user", resource_id=uid,
          detail=f"Deleted user '{uname}'", ip=client_ip())
    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "success", "message": f"User '{uname}' deleted."})


# ══════════════════════════════════════════════════════════════════
#  PARCEL CRUD APIs
#  GET  → authenticated users (read)
#  POST/PUT/DELETE → ADMIN ONLY  (server-side enforcement)
# ══════════════════════════════════════════════════════════════════

@app.route("/api/parcels", methods=["GET"])
@login_required
def get_parcels_db():
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search   = request.args.get("search", "").strip()
    land_use = request.args.get("land_use", "").strip()
    owner_t  = request.args.get("owner_type", "").strip()
    sort_by  = request.args.get("sort_by", "created_at")
    sort_dir = request.args.get("sort_dir", "desc")

    q = ParcelRecord.query
    if search:
        like = f"%{search}%"
        q = q.filter(
            ParcelRecord.owner_name.ilike(like) | ParcelRecord.survey_number.ilike(like) |
            ParcelRecord.parcel_id.ilike(like)  | ParcelRecord.zone_name.ilike(like) |
            ParcelRecord.deed_number.ilike(like)
        )
    if land_use: q = q.filter(ParcelRecord.registered_land_use == land_use)
    if owner_t:  q = q.filter(ParcelRecord.owner_type == owner_t)

    col = getattr(ParcelRecord, sort_by, ParcelRecord.created_at)
    q   = q.order_by(col.asc() if sort_dir == "asc" else col.desc())

    total   = q.count()
    records = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "status": "success", "total": total, "page": page,
        "per_page": per_page, "pages": (total + per_page - 1) // per_page,
        "parcels": [r.to_dict() for r in records],
    })


@app.route("/api/parcels", methods=["POST"])
@admin_required                        # ← ADMIN ONLY — enforced server-side
def create_parcel():
    data = request.get_json() or {}
    for field in ("survey_number", "owner_name", "registered_land_use"):
        if not str(data.get(field, "")).strip():
            return jsonify({"status": "error", "message": f"'{field}' is required."}), 400

    parcel_id = sanitize(data.get("parcel_id", ""), 60) or f"PARCEL-{uuid.uuid4().hex[:8].upper()}"
    if ParcelRecord.query.filter_by(parcel_id=parcel_id).first():
        return jsonify({"status": "error", "message": "Parcel ID already exists."}), 409

    try:
        rec = ParcelRecord(
            parcel_id           = parcel_id,
            survey_number       = sanitize(data.get("survey_number", ""), 60),
            owner_name          = sanitize(data.get("owner_name", ""), 150),
            owner_type          = data.get("owner_type", "PRIVATE_CITIZEN"),
            deed_number         = sanitize(data.get("deed_number", ""), 80),
            tax_id              = sanitize(data.get("tax_id", ""), 80),
            contact_email       = sanitize(data.get("contact_email", ""), 120),
            contact_phone       = sanitize(data.get("contact_phone", ""), 30),
            zone_name           = sanitize(data.get("zone_name", ""), 120),
            registered_land_use = data.get("registered_land_use", "RESIDENTIAL"),
            area_sqm            = float(data.get("area_sqm") or 0),
            max_coverage_ratio  = float(data.get("max_coverage_ratio") or 0.65),
            setback_meters      = float(data.get("setback_meters") or 2.5),
            market_rate_per_sqm = float(data.get("market_rate_per_sqm") or 12000),
            latitude            = float(data["latitude"])  if data.get("latitude")  else None,
            longitude           = float(data["longitude"]) if data.get("longitude") else None,
            registration_date   = sanitize(data.get("registration_date", ""), 20),
            notes               = sanitize(data.get("notes", ""), 1000),
            created_by          = current_user.id,
        )
        db.session.add(rec)
        db.session.flush()
        audit(current_user, "CREATED", "parcel", resource_id=rec.id,
              detail=f"Parcel '{parcel_id}' owner='{rec.owner_name}'", ip=client_ip())
        db.session.commit()
        return jsonify({"status": "success", "parcel": rec.to_dict()}), 201
    except (ValueError, TypeError) as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Invalid data: {e}"}), 400


@app.route("/api/parcels/<int:rid>", methods=["GET"])
@login_required
def get_parcel_detail(rid: int):
    rec = db.session.get(ParcelRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404
    return jsonify({"status": "success", "parcel": rec.to_dict()})


@app.route("/api/parcels/<int:rid>", methods=["PUT"])
@admin_required                        # ← ADMIN ONLY
def update_parcel(rid: int):
    rec = db.session.get(ParcelRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404

    data = request.get_json() or {}
    try:
        str_fields = {
            "survey_number": 60, "owner_name": 150, "owner_type": 50,
            "deed_number": 80, "tax_id": 80, "contact_email": 120,
            "contact_phone": 30, "zone_name": 120, "registered_land_use": 40,
            "registration_date": 20, "notes": 1000,
        }
        for f, maxlen in str_fields.items():
            if f in data:
                setattr(rec, f, sanitize(data[f], maxlen))

        for f in ("area_sqm", "max_coverage_ratio", "setback_meters", "market_rate_per_sqm"):
            if f in data:
                setattr(rec, f, float(data[f] or 0))

        for f in ("latitude", "longitude"):
            if f in data:
                setattr(rec, f, float(data[f]) if data[f] else None)

        rec.updated_at = datetime.now(timezone.utc)
        audit(current_user, "UPDATED", "parcel", resource_id=rid,
              detail=f"Updated parcel ID={rid}", ip=client_ip())
        db.session.commit()
        return jsonify({"status": "success", "parcel": rec.to_dict()})
    except (ValueError, TypeError) as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Invalid data: {e}"}), 400


@app.route("/api/parcels/<int:rid>", methods=["DELETE"])
@admin_required                        # ← ADMIN ONLY
def delete_parcel(rid: int):
    rec = db.session.get(ParcelRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404
    pid = rec.parcel_id
    audit(current_user, "DELETED", "parcel", resource_id=rid,
          detail=f"Deleted parcel '{pid}' owner='{rec.owner_name}'", ip=client_ip())
    db.session.delete(rec)
    db.session.commit()
    return jsonify({"status": "success", "message": f"Parcel '{pid}' deleted."})


# ══════════════════════════════════════════════════════════════════
#  ENCROACHMENT CRUD APIs
#  GET  → authenticated users
#  POST/PUT/DELETE → ADMIN ONLY
# ══════════════════════════════════════════════════════════════════

@app.route("/api/db/encroachments", methods=["GET"])
@login_required
def get_db_encroachments():
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search   = request.args.get("search", "").strip()
    severity = request.args.get("severity", "").strip()
    status_f = request.args.get("status", "").strip()

    q = EncroachmentRecord.query
    if search:
        like = f"%{search}%"
        q = q.filter(
            EncroachmentRecord.flag_id.ilike(like) |
            EncroachmentRecord.violator_name.ilike(like) |
            EncroachmentRecord.affected_owner.ilike(like)
        )
    if severity: q = q.filter(EncroachmentRecord.severity == severity)
    if status_f: q = q.filter(EncroachmentRecord.status   == status_f)

    q     = q.order_by(EncroachmentRecord.created_at.desc())
    total = q.count()
    recs  = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "status": "success", "total": total, "page": page,
        "per_page": per_page, "pages": (total + per_page - 1) // per_page,
        "encroachments": [r.to_dict() for r in recs],
    })


@app.route("/api/db/encroachments", methods=["POST"])
@admin_required
def create_db_encroachment():
    data = request.get_json() or {}
    for field in ("encroachment_type", "severity", "affected_parcel_id"):
        if not str(data.get(field, "")).strip():
            return jsonify({"status": "error", "message": f"'{field}' is required."}), 400

    flag_id = f"ENC-DB-{uuid.uuid4().hex[:8].upper()}"
    try:
        rec = EncroachmentRecord(
            flag_id             = flag_id,
            encroachment_type   = data.get("encroachment_type", ""),
            severity            = data.get("severity", "MEDIUM"),
            violator_name       = sanitize(data.get("violator_name", ""), 150),
            violator_parcel_id  = sanitize(data.get("violator_parcel_id", ""), 60),
            affected_parcel_id  = sanitize(data.get("affected_parcel_id", ""), 60),
            affected_owner      = sanitize(data.get("affected_owner", ""), 150),
            affected_land_use   = data.get("affected_land_use", "RESIDENTIAL"),
            encroached_area_sqm = float(data.get("encroached_area_sqm") or 0),
            estimated_penalty   = float(data.get("estimated_penalty") or 0),
            confidence          = float(data.get("confidence") or 0.9),
            status              = data.get("status", "DETECTED"),
            recommended_action  = sanitize(data.get("recommended_action", ""), 1000),
            latitude            = float(data["latitude"])  if data.get("latitude")  else None,
            longitude           = float(data["longitude"]) if data.get("longitude") else None,
            notes               = sanitize(data.get("notes", ""), 1000),
        )
        db.session.add(rec)
        db.session.flush()
        audit(current_user, "CREATED", "encroachment", resource_id=rec.id,
              detail=f"Flag '{flag_id}' type={rec.encroachment_type}", ip=client_ip())
        db.session.commit()
        return jsonify({"status": "success", "encroachment": rec.to_dict()}), 201
    except (ValueError, TypeError) as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Invalid data: {e}"}), 400


@app.route("/api/db/encroachments/<int:rid>", methods=["GET"])
@login_required
def get_db_encroachment(rid: int):
    rec = db.session.get(EncroachmentRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404
    return jsonify({"status": "success", "encroachment": rec.to_dict()})


@app.route("/api/db/encroachments/<int:rid>", methods=["PUT"])
@admin_required
def update_db_encroachment(rid: int):
    rec = db.session.get(EncroachmentRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404

    data = request.get_json() or {}
    try:
        for f in ("encroachment_type", "severity", "violator_name", "violator_parcel_id",
                  "affected_parcel_id", "affected_owner", "affected_land_use",
                  "status", "recommended_action", "notes"):
            if f in data:
                setattr(rec, f, sanitize(str(data[f]), 1000))
        for f in ("encroached_area_sqm", "estimated_penalty", "confidence"):
            if f in data:
                setattr(rec, f, float(data[f] or 0))
        for f in ("latitude", "longitude"):
            if f in data:
                setattr(rec, f, float(data[f]) if data[f] else None)

        rec.updated_at = datetime.now(timezone.utc)
        audit(current_user, "UPDATED", "encroachment", resource_id=rid,
              detail=f"Updated encroachment ID={rid}", ip=client_ip())
        db.session.commit()
        return jsonify({"status": "success", "encroachment": rec.to_dict()})
    except (ValueError, TypeError) as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Invalid data: {e}"}), 400


@app.route("/api/db/encroachments/<int:rid>", methods=["DELETE"])
@admin_required
def delete_db_encroachment(rid: int):
    rec = db.session.get(EncroachmentRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404
    audit(current_user, "DELETED", "encroachment", resource_id=rid,
          detail=f"Deleted flag '{rec.flag_id}'", ip=client_ip())
    db.session.delete(rec)
    db.session.commit()
    return jsonify({"status": "success", "message": "Encroachment record deleted."})


# ══════════════════════════════════════════════════════════════════
#  AUDIT LOG API  — ADMIN ONLY
# ══════════════════════════════════════════════════════════════════

@app.route("/api/audit-logs", methods=["GET"])
@admin_required
def get_audit_logs():
    page     = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 30, type=int), 100)
    search   = request.args.get("search", "").strip()
    action_f = request.args.get("action", "").strip()
    resource_f = request.args.get("resource", "").strip()

    q = AuditLog.query
    if search:
        like = f"%{search}%"
        q = q.filter(
            AuditLog.actor_name.ilike(like) | AuditLog.detail.ilike(like)
        )
    if action_f:   q = q.filter(AuditLog.action   == action_f)
    if resource_f: q = q.filter(AuditLog.resource  == resource_f)

    q     = q.order_by(AuditLog.created_at.desc())
    total = q.count()
    logs  = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "status": "success", "total": total, "page": page,
        "per_page": per_page, "pages": (total + per_page - 1) // per_page,
        "logs": [l.to_dict() for l in logs],
    })


# ══════════════════════════════════════════════════════════════════
#  DASHBOARD STATS API
# ══════════════════════════════════════════════════════════════════

@app.route("/api/dashboard-stats", methods=["GET"])
@login_required
def dashboard_stats():
    from sqlalchemy import func
    total_parcels       = ParcelRecord.query.count()
    total_encroachments = EncroachmentRecord.query.count()
    total_users         = User.query.count() if current_user.is_admin else None

    sev_rows    = db.session.query(EncroachmentRecord.severity, func.count()).group_by(EncroachmentRecord.severity).all()
    status_rows = db.session.query(EncroachmentRecord.status,   func.count()).group_by(EncroachmentRecord.status).all()

    recent_parcels = [r.to_dict() for r in ParcelRecord.query.order_by(ParcelRecord.created_at.desc()).limit(5).all()]
    recent_enc     = [r.to_dict() for r in EncroachmentRecord.query.order_by(EncroachmentRecord.created_at.desc()).limit(5).all()]

    gis_metrics = gis_state.registry.get_metrics_summary()

    payload = {
        "status": "success",
        "db_stats": {
            "total_parcels":       total_parcels,
            "total_encroachments": total_encroachments,
            "total_users":         total_users,
            "severity_breakdown":  {r[0]: r[1] for r in sev_rows},
            "status_breakdown":    {r[0]: r[1] for r in status_rows},
        },
        "gis_stats":            gis_metrics,
        "recent_parcels":       recent_parcels,
        "recent_encroachments": recent_enc,
    }
    return jsonify(payload)


# ══════════════════════════════════════════════════════════════════
#  EXISTING GIS APIs  (all login_required; GIS scan = admin_required)
# ══════════════════════════════════════════════════════════════════

@app.route("/api/cadastre", methods=["GET"])
@login_required
def get_cadastre():
    return jsonify(gis_state.registry.get_parcels_geojson())


@app.route("/api/structures", methods=["GET"])
@login_required
def get_structures():
    return jsonify(gis_state.registry.get_structures_geojson())


@app.route("/api/encroachments", methods=["GET"])
@login_required
def get_encroachments():
    return jsonify(gis_state.registry.get_encroachments_geojson())


@app.route("/api/stats", methods=["GET"])
@login_required
def get_stats():
    return jsonify(gis_state.registry.get_metrics_summary())


@app.route("/api/scan", methods=["POST"])
@admin_required
def run_scan():
    flags = gis_state.detector.run_detection_scan()
    audit(current_user, "SCAN", "system",
          detail=f"GIS scan — {len(flags)} flags detected", ip=client_ip())
    db.session.commit()
    return jsonify({
        "status": "success",
        "flags_detected": len(flags),
        "encroachments":  gis_state.registry.get_encroachments_geojson(),
        "stats":          gis_state.registry.get_metrics_summary(),
    })


@app.route("/api/notice/<flag_id>", methods=["GET"])
@login_required
def get_legal_notice(flag_id: str):
    try:
        notice = gis_state.report_gen.generate_legal_notice(flag_id)
        return jsonify({"status": "success", "notice": notice})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 404


@app.route("/api/audit-report", methods=["GET"])
@login_required
def get_full_audit():
    return jsonify(gis_state.report_gen.generate_full_audit_report())


@app.route("/api/analyze-custom-polygon", methods=["POST"])
@login_required
def analyze_custom_polygon():
    data   = request.get_json() or {}
    coords = data.get("coordinates")
    if not coords or len(coords) < 3:
        return jsonify({"status": "error", "message": "Invalid polygon."}), 400
    result = gis_state.detector.analyze_arbitrary_polygon(coords, data.get("claimed_parcel_id"))
    return jsonify({"status": "success", "analysis": result})


@app.route("/api/classify-spectral-sample", methods=["POST"])
@login_required
def classify_sample():
    data = request.get_json() or {}
    result = gis_state.classifier.classify_spectral_profile(
        float(data.get("red", 0.25)), float(data.get("green", 0.22)),
        float(data.get("blue", 0.20)), float(data.get("nir", 0.28)),
        float(data.get("swir", 0.40)), float(data.get("texture_variance", 0.14))
    )
    return jsonify({"status": "success", "result": result})


@app.route("/api/classifier-diagnostics", methods=["GET"])
@login_required
def classifier_diagnostics():
    return jsonify(gis_state.classifier.get_model_diagnostics())


@app.route("/api/update-flag-status", methods=["POST"])
@admin_required
def update_flag_status():
    data     = request.get_json() or {}
    flag_id  = data.get("flag_id")
    new_status = data.get("status")
    flag = gis_state.registry.encroachment_flags.get(flag_id)
    if not flag:
        return jsonify({"status": "error", "message": "Flag not found."}), 404
    try:
        flag.status = DisputeStatus(new_status)
        audit(current_user, "UPDATED", "gis_flag", resource_id=flag_id,
              detail=f"Status -> {new_status}", ip=client_ip())
        db.session.commit()
        return jsonify({"status": "success", "flag": flag.to_dict()})
    except ValueError:
        return jsonify({"status": "error", "message": f"Invalid status: {new_status}"}), 400


@app.route("/api/reset", methods=["POST"])
@admin_required
def reset_dataset():
    gis_state.reset()
    audit(current_user, "RESET", "system", detail="GIS cadastre reset to baseline", ip=client_ip())
    db.session.commit()
    return jsonify({"status": "success", "message": "Municipal cadastre reset to baseline state."})


# ══════════════════════════════════════════════════════════════════
#  STARTUP (only used when running directly: python run_app.py)
#  In production, gunicorn imports `app` from this module directly.
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Municipal GIS System -> http://127.0.0.1:{port}")
    print("[*] Default credentials -> admin / Admin@1234  |  surveyor / Survey@1234")
    print("[*] Signup page -> /signup  |  Connect page -> /connect")
    app.run(host="0.0.0.0", port=port, debug=False)
