"""
run_app.py - Municipal GIS Encroachment Detection System
Auth    : Flask-Login (session-based) + OTP password-reset
AuthZ   : 4 roles — admin | gis_officer | surveyor | viewer
          All mutation APIs guarded server-side.
Features: RBAC, GIS analysis, parcel CRUD, encroachment case management,
          evidence uploads, notifications, audit logging, CSV/JSON export.
"""

from __future__ import annotations
import os, re, uuid, socket, json, csv
from datetime import datetime, timezone
from functools import wraps
from io import StringIO, BytesIO
from pathlib import Path

from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, session, send_file, abort
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from werkzeug.utils import secure_filename

from database import (
    db, User, ParcelRecord, EncroachmentRecord, AuditLog,
    EvidenceFile, Notification, OTPToken,
    ROLE_USER, ROLE_ADMIN, ROLE_GIS_OFFICER, ROLE_SURVEYOR, ROLE_VIEWER,
    audit, notify, init_db,
)
from core.models import (
    MunicipalSurveyRegistry, DisputeStatus, LandUseType, OwnerType,
)
from core.classifier       import LandCoverClassifier
from core.detector         import EncroachmentDetector
from core.dataset_generator import build_default_municipal_dataset
from core.report_generator  import MunicipalReportGenerator

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  FLASK APP CONFIG
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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

# File upload configuration
_upload_folder = os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads"))
os.makedirs(_upload_folder, exist_ok=True)
app.config["UPLOAD_FOLDER"]        = _upload_folder
app.config["MAX_CONTENT_LENGTH"]   = int(os.environ.get("UPLOAD_MAX_MB", 50)) * 1024 * 1024
ALLOWED_IMAGE_EXT  = {"jpg", "jpeg", "png", "gif", "webp", "tif", "tiff"}
ALLOWED_GEO_EXT    = {"geojson", "json", "kml", "kmz", "zip", "gpkg"}
ALLOWED_DOC_EXT    = {"pdf", "csv", "xlsx", "xls", "txt"}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXT | ALLOWED_GEO_EXT | ALLOWED_DOC_EXT


init_db(app)

login_manager = LoginManager(app)
login_manager.login_view         = "login_page"
login_manager.login_message      = "Please log in to access the system."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(uid: str):
    return db.session.get(User, int(uid))


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ROLE-BASED DECORATORS  (server-side enforcement)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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




def write_required(fn):
    """Allows admin OR gis_officer to modify data. Returns 403 for surveyor/viewer."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"status": "error", "message": "Authentication required.", "code": 401}), 401
        if not current_user.can_write:
            return jsonify({"status": "error",
                            "message": "Write access required (admin or GIS officer).", "code": 403}), 403
        return fn(*args, **kwargs)
    return login_required(wrapper)


def verify_required(fn):
    """Allows admin, gis_officer, or surveyor to verify/reject encroachment cases."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"status": "error", "message": "Authentication required.", "code": 401}), 401
        if not current_user.can_verify:
            return jsonify({"status": "error",
                            "message": "Verification access required.", "code": 403}), 403
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  GIS IN-MEMORY STATE  (unchanged from original)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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


# Lazy init â€” populated on first request to avoid OOM on cloud startup
gis_state: MunicipalAppState | None = None


def get_gis_state() -> MunicipalAppState:
    """Return the global GIS state, initialising it on first call."""
    global gis_state
    if gis_state is None:
        gis_state = MunicipalAppState()
    return gis_state


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  HELPERS
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  AUTH ROUTES â€” PUBLIC
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
    """Public self-registration â€” always creates ROLE_USER accounts."""
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  PAGE ROUTES
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
    """Public network connect page â€” shows QR code + URL for all devices."""
    return render_template("connect.html", host_ip=get_host_ip())


@app.route("/")
@login_required
def index():
    """GIS map â€” accessible to both roles."""
    return render_template("index.html", user=current_user)


@app.route("/dashboard")
@login_required
def dashboard():
    """Smart redirect: admins â†’ admin dashboard, users â†’ user dashboard."""
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  CURRENT USER API
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/api/me", methods=["GET"])
@login_required
def get_me():
    return jsonify({"status": "success", "user": current_user.to_dict()})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  USER MANAGEMENT APIS  â€” ADMIN ONLY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/api/users", methods=["GET"])
@login_required
def get_users():
    """List users â€” admin sees all; regular users see only themselves."""
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
    â€” role changes are silently ignored for non-admins.
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  PARCEL CRUD APIs
#  GET  â†’ authenticated users (read)
#  POST/PUT/DELETE â†’ ADMIN ONLY  (server-side enforcement)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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
@admin_required                        # â† ADMIN ONLY â€” enforced server-side
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
@admin_required                        # â† ADMIN ONLY
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
@admin_required                        # â† ADMIN ONLY
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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  ENCROACHMENT CRUD APIs
#  GET  â†’ authenticated users
#  POST/PUT/DELETE â†’ ADMIN ONLY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  AUDIT LOG API  â€” ADMIN ONLY
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  DASHBOARD STATS API
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

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

    gis_metrics = get_gis_state().registry.get_metrics_summary()

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


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  EXISTING GIS APIs  (all login_required; GIS scan = admin_required)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

@app.route("/api/cadastre", methods=["GET"])
@login_required
def get_cadastre():
    return jsonify(get_gis_state().registry.get_parcels_geojson())


@app.route("/api/structures", methods=["GET"])
@login_required
def get_structures():
    return jsonify(get_gis_state().registry.get_structures_geojson())


@app.route("/api/encroachments", methods=["GET"])
@login_required
def get_encroachments():
    return jsonify(get_gis_state().registry.get_encroachments_geojson())


@app.route("/api/stats", methods=["GET"])
@login_required
def get_stats():
    return jsonify(get_gis_state().registry.get_metrics_summary())


@app.route("/api/scan", methods=["POST"])
@admin_required
def run_scan():
    flags = get_gis_state().detector.run_detection_scan()
    audit(current_user, "SCAN", "system",
          detail=f"GIS scan â€” {len(flags)} flags detected", ip=client_ip())
    db.session.commit()
    return jsonify({
        "status": "success",
        "flags_detected": len(flags),
        "encroachments":  get_gis_state().registry.get_encroachments_geojson(),
        "stats":          get_gis_state().registry.get_metrics_summary(),
    })


@app.route("/api/notice/<flag_id>", methods=["GET"])
@login_required
def get_legal_notice(flag_id: str):
    try:
        notice = get_gis_state().report_gen.generate_legal_notice(flag_id)
        return jsonify({"status": "success", "notice": notice})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 404


@app.route("/api/audit-report", methods=["GET"])
@login_required
def get_full_audit():
    return jsonify(get_gis_state().report_gen.generate_full_audit_report())


@app.route("/api/analyze-custom-polygon", methods=["POST"])
@login_required
def analyze_custom_polygon():
    data   = request.get_json() or {}
    coords = data.get("coordinates")
    if not coords or len(coords) < 3:
        return jsonify({"status": "error", "message": "Invalid polygon."}), 400
    result = get_gis_state().detector.analyze_arbitrary_polygon(coords, data.get("claimed_parcel_id"))
    return jsonify({"status": "success", "analysis": result})


@app.route("/api/classify-spectral-sample", methods=["POST"])
@login_required
def classify_sample():
    data = request.get_json() or {}
    result = get_gis_state().classifier.classify_spectral_profile(
        float(data.get("red", 0.25)), float(data.get("green", 0.22)),
        float(data.get("blue", 0.20)), float(data.get("nir", 0.28)),
        float(data.get("swir", 0.40)), float(data.get("texture_variance", 0.14))
    )
    return jsonify({"status": "success", "result": result})


@app.route("/api/classifier-diagnostics", methods=["GET"])
@login_required
def classifier_diagnostics():
    return jsonify(get_gis_state().classifier.get_model_diagnostics())


@app.route("/api/update-flag-status", methods=["POST"])
@admin_required
def update_flag_status():
    data     = request.get_json() or {}
    flag_id  = data.get("flag_id")
    new_status = data.get("status")
    flag = get_gis_state().registry.encroachment_flags.get(flag_id)
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
    get_gis_state().reset()
    audit(current_user, "RESET", "system", detail="GIS cadastre reset to baseline", ip=client_ip())
    db.session.commit()
    return jsonify({"status": "success", "message": "Municipal cadastre reset to baseline state."})


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  STARTUP (only used when running directly: python run_app.py)
#  In production, gunicorn imports `app` from this module directly.
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•



# ══════════════════════════════════════════════════════════════════════════════
#  PASSWORD RESET / OTP ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Step 1: request a reset token via email."""
    if current_user.is_authenticated:
        return redirect(url_for("user_dashboard"))

    message = None
    error   = None
    if request.method == "POST":
        identifier = (request.form.get("identifier", "") or "").strip()
        if not identifier:
            error = "Please enter your email or username."
        else:
            user = User.query.filter(
                (User.email == identifier.lower()) | (User.username == identifier)
            ).first()
            # Always show the same message (don't reveal if account exists)
            message = "If an account exists, a reset code has been sent to the registered email."
            if user and user.is_active:
                with app.app_context():
                    token = OTPToken.create(user.id, purpose="password_reset", ttl_minutes=15)
                    db.session.commit()
                # Try to send email if MAIL_SERVER is configured
                _send_reset_email(user, token.token)
                audit(user, "PASSWORD_RESET_REQUESTED", "user",
                      resource_id=user.id,
                      detail=f"Password reset requested for {user.email}",
                      ip=client_ip())
                db.session.commit()
    return render_template("forgot_password.html", message=message, error=error)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    """Step 2: set new password using the token."""
    if current_user.is_authenticated:
        return redirect(url_for("user_dashboard"))

    record = OTPToken.query.filter_by(token=token, purpose="password_reset").first()
    if not record or not record.is_valid:
        return render_template("reset_password.html", token=token,
                               error="This reset link is invalid or has expired. Please request a new one.")

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if password != confirm:
            error = "Passwords do not match."
        elif (pwd_err := validate_password(password)):
            error = pwd_err
        else:
            record.attempts += 1
            record.used = True
            user = db.session.get(User, record.user_id)
            if not user:
                error = "User account not found."
            else:
                user.set_password(password)
                audit(user, "PASSWORD_RESET", "user",
                      resource_id=user.id, detail="Password reset via token", ip=client_ip())
                db.session.commit()
                return render_template("reset_password.html", token=token, success=True)

        record.attempts += 1
        db.session.commit()

    return render_template("reset_password.html", token=token, error=error)


@app.route("/api/change-password", methods=["POST"])
@login_required
def change_password():
    """Authenticated users change their own password."""
    data        = request.get_json() or {}
    current_pw  = data.get("current_password", "")
    new_pw      = data.get("new_password", "")
    confirm_pw  = data.get("confirm_password", "")

    if not current_pw or not new_pw:
        return jsonify({"status": "error", "message": "Current and new password are required."}), 400
    if not current_user.check_password(current_pw):
        return jsonify({"status": "error", "message": "Current password is incorrect."}), 400
    if new_pw != confirm_pw:
        return jsonify({"status": "error", "message": "New passwords do not match."}), 400
    if (pwd_err := validate_password(new_pw)):
        return jsonify({"status": "error", "message": pwd_err}), 400

    current_user.set_password(new_pw)
    audit(current_user, "PASSWORD_CHANGED", "user",
          resource_id=current_user.id, detail="User changed own password", ip=client_ip())
    db.session.commit()
    return jsonify({"status": "success", "message": "Password updated successfully."})


def _send_reset_email(user, token: str) -> None:
    """Send a password-reset email if MAIL_SERVER env var is configured."""
    mail_server = os.environ.get("MAIL_SERVER", "")
    if not mail_server:
        print(f"[MAIL] MAIL_SERVER not configured. Token for {user.email}: {token}")
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        base_url = os.environ.get("APP_BASE_URL", "http://localhost:5000")
        reset_url = f"{base_url}/reset-password/{token}"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Municipal GIS — Password Reset"
        msg["From"]    = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@municipal.gov")
        msg["To"]      = user.email

        body_html = f"""
        <html><body>
        <p>Hello {user.full_name or user.username},</p>
        <p>A password reset was requested for your Municipal GIS account.</p>
        <p><a href="{reset_url}">Click here to reset your password</a></p>
        <p>This link expires in 15 minutes. If you did not request this, ignore this email.</p>
        <p>Reset link: {reset_url}</p>
        </body></html>"""

        msg.attach(MIMEText(body_html, "html"))

        port = int(os.environ.get("MAIL_PORT", 587))
        with smtplib.SMTP(mail_server, port) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(os.environ.get("MAIL_USERNAME", ""), os.environ.get("MAIL_PASSWORD", ""))
            smtp.sendmail(msg["From"], user.email, msg.as_string())
        print(f"[MAIL] Reset email sent to {user.email}")
    except Exception as exc:
        print(f"[MAIL] Failed to send email: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
#  NOTIFICATION APIs
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/notifications", methods=["GET"])
@login_required
def get_notifications():
    """Get current user's notifications."""
    page      = request.args.get("page", 1, type=int)
    per_page  = min(request.args.get("per_page", 20, type=int), 100)
    unread_only = request.args.get("unread_only", "false").lower() == "true"

    q = Notification.query.filter_by(user_id=current_user.id)
    if unread_only:
        q = q.filter_by(is_read=False)
    q = q.order_by(Notification.created_at.desc())
    total  = q.count()
    items  = q.offset((page - 1) * per_page).limit(per_page).all()
    unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({
        "status":  "success",
        "total":   total,
        "unread":  unread,
        "page":    page,
        "items":   [n.to_dict() for n in items],
    })


@app.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required
def mark_notification_read(nid: int):
    n = Notification.query.filter_by(id=nid, user_id=current_user.id).first()
    if not n:
        return jsonify({"status": "error", "message": "Not found."}), 404
    n.is_read = True
    db.session.commit()
    return jsonify({"status": "success"})


@app.route("/api/notifications/mark-all-read", methods=["POST"])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"status": "success"})


# ══════════════════════════════════════════════════════════════════════════════
#  ENCROACHMENT VERIFICATION WORKFLOW
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/db/encroachments/<int:rid>/verify", methods=["POST"])
@verify_required
def verify_encroachment(rid: int):
    """Verify or reject an encroachment case."""
    rec = db.session.get(EncroachmentRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404

    data    = request.get_json() or {}
    action  = data.get("action", "").upper()  # VERIFY or REJECT
    remarks = sanitize(data.get("remarks", ""), 1000)

    if action not in ("VERIFY", "REJECT"):
        return jsonify({"status": "error", "message": "action must be VERIFY or REJECT."}), 400

    new_status = "VERIFIED" if action == "VERIFY" else "REJECTED"
    rec.status           = new_status
    rec.verified_by_id   = current_user.id
    rec.verified_at      = datetime.now(timezone.utc)
    rec.officer_remarks  = remarks
    rec.updated_at       = datetime.now(timezone.utc)

    audit(current_user, f"ENCROACHMENT_{action}D", "encroachment",
          resource_id=rid,
          detail=f"Case {rec.flag_id} -> {new_status}. Remarks: {remarks[:200]}",
          ip=client_ip())

    # Notify assigned officer
    if rec.assigned_officer_id:
        notify(
            user_id     = rec.assigned_officer_id,
            title       = f"Case {rec.flag_id} {new_status}",
            message     = f"Case {rec.flag_id} has been {new_status.lower()} by {current_user.full_name}. {remarks}",
            notif_type  = "SUCCESS" if action == "VERIFY" else "WARNING",
            resource    = "encroachment",
            resource_id = rid,
        )

    db.session.commit()
    return jsonify({"status": "success", "encroachment": rec.to_dict()})


@app.route("/api/db/encroachments/<int:rid>/assign", methods=["POST"])
@write_required
def assign_encroachment(rid: int):
    """Assign an encroachment case to an officer."""
    rec = db.session.get(EncroachmentRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Record not found."}), 404

    data        = request.get_json() or {}
    officer_id  = data.get("officer_id")

    if officer_id:
        officer = db.session.get(User, int(officer_id))
        if not officer:
            return jsonify({"status": "error", "message": "Officer not found."}), 404
        rec.assigned_officer_id = officer.id
        rec.status = "PENDING_VERIFICATION"
        rec.updated_at = datetime.now(timezone.utc)

        # Notify the officer
        notify(
            user_id     = officer.id,
            title       = f"Case {rec.flag_id} assigned to you",
            message     = f"Encroachment case {rec.flag_id} ({rec.encroachment_type}) has been assigned to you for verification.",
            notif_type  = "INFO",
            resource    = "encroachment",
            resource_id = rid,
        )
    else:
        rec.assigned_officer_id = None

    audit(current_user, "CASE_ASSIGNED", "encroachment", resource_id=rid,
          detail=f"Case {rec.flag_id} assigned to officer_id={officer_id}",
          ip=client_ip())
    db.session.commit()
    return jsonify({"status": "success", "encroachment": rec.to_dict()})


# ══════════════════════════════════════════════════════════════════════════════
#  EVIDENCE FILE UPLOAD & MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_file_type(ext: str) -> str:
    ext = ext.lower()
    if ext in ALLOWED_IMAGE_EXT: return "image"
    if ext in ALLOWED_GEO_EXT:   return "geodata"
    return "document"


@app.route("/api/evidence", methods=["POST"])
@login_required
def upload_evidence():
    """Upload evidence file and link to an encroachment case."""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file provided."}), 400

    f           = request.files["file"]
    case_id     = request.form.get("case_id", type=int)
    description = sanitize(request.form.get("description", ""), 500)
    ev_type     = sanitize(request.form.get("evidence_type", "GENERAL"), 30).upper()

    if not f or not f.filename:
        return jsonify({"status": "error", "message": "Empty filename."}), 400
    if not case_id:
        return jsonify({"status": "error", "message": "case_id is required."}), 400

    rec = db.session.get(EncroachmentRecord, case_id)
    if not rec:
        return jsonify({"status": "error", "message": "Encroachment case not found."}), 404

    if not _allowed_file(f.filename):
        return jsonify({"status": "error",
                        "message": f"File type not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}), 400

    orig_name = secure_filename(f.filename)
    ext       = orig_name.rsplit(".", 1)[1].lower()
    new_name  = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], new_name)

    try:
        f.save(save_path)
        size = os.path.getsize(save_path)
    except Exception as exc:
        return jsonify({"status": "error", "message": f"Failed to save file: {exc}"}), 500

    ev = EvidenceFile(
        case_id         = case_id,
        filename        = new_name,
        original_name   = orig_name,
        file_type       = _get_file_type(ext),
        mime_type       = f.mimetype,
        file_size_bytes = size,
        file_path       = save_path,
        description     = description,
        evidence_type   = ev_type,
        uploaded_by_id  = current_user.id,
    )
    db.session.add(ev)
    db.session.flush()

    audit(current_user, "EVIDENCE_UPLOADED", "evidence", resource_id=ev.id,
          detail=f"File '{orig_name}' uploaded for case {rec.flag_id}", ip=client_ip())
    db.session.commit()
    return jsonify({"status": "success", "evidence": ev.to_dict()}), 201


@app.route("/api/evidence/<int:eid>", methods=["DELETE"])
@write_required
def delete_evidence(eid: int):
    ev = db.session.get(EvidenceFile, eid)
    if not ev:
        return jsonify({"status": "error", "message": "Not found."}), 404
    try:
        if os.path.exists(ev.file_path):
            os.remove(ev.file_path)
    except Exception:
        pass
    audit(current_user, "EVIDENCE_DELETED", "evidence", resource_id=eid,
          detail=f"Deleted evidence file '{ev.original_name}'", ip=client_ip())
    db.session.delete(ev)
    db.session.commit()
    return jsonify({"status": "success"})


@app.route("/api/evidence/<int:eid>/download")
@login_required
def download_evidence(eid: int):
    ev = db.session.get(EvidenceFile, eid)
    if not ev:
        abort(404)
    if not os.path.exists(ev.file_path):
        return jsonify({"status": "error", "message": "File not found on server."}), 404
    return send_file(ev.file_path, as_attachment=True, download_name=ev.original_name)


@app.route("/api/evidence/<int:eid>/preview")
@login_required
def preview_evidence(eid: int):
    ev = db.session.get(EvidenceFile, eid)
    if not ev or ev.file_type != "image":
        abort(404)
    if not os.path.exists(ev.file_path):
        abort(404)
    return send_file(ev.file_path, mimetype=ev.mime_type or "image/jpeg")


@app.route("/api/db/encroachments/<int:rid>/evidence", methods=["GET"])
@login_required
def get_case_evidence(rid: int):
    rec = db.session.get(EncroachmentRecord, rid)
    if not rec:
        return jsonify({"status": "error", "message": "Case not found."}), 404
    files = EvidenceFile.query.filter_by(case_id=rid).order_by(EvidenceFile.created_at.desc()).all()
    return jsonify({"status": "success", "evidence": [e.to_dict() for e in files]})


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT APIs  (CSV / GeoJSON)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/export/parcels.csv")
@login_required
def export_parcels_csv():
    records = ParcelRecord.query.order_by(ParcelRecord.created_at.desc()).all()
    si = StringIO()
    w  = csv.DictWriter(si, fieldnames=[
        "parcel_id", "survey_number", "sub_division", "owner_name", "owner_type",
        "village", "mandal", "district", "state", "zone_name",
        "registered_land_use", "area_sqm", "latitude", "longitude",
        "registration_date", "survey_date", "status", "created_at",
    ])
    w.writeheader()
    for r in records:
        d = r.to_dict()
        w.writerow({k: d.get(k, "") for k in w.fieldnames})
    si.seek(0)
    buf = BytesIO(si.read().encode("utf-8-sig"))  # utf-8-sig = Excel-compatible BOM
    buf.seek(0)
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                     download_name="parcels_export.csv")


@app.route("/api/export/encroachments.csv")
@login_required
def export_encroachments_csv():
    records = EncroachmentRecord.query.order_by(EncroachmentRecord.created_at.desc()).all()
    si = StringIO()
    w  = csv.DictWriter(si, fieldnames=[
        "flag_id", "encroachment_type", "severity", "detection_method",
        "affected_parcel_id", "affected_owner", "village", "mandal", "district",
        "encroached_area_sqm", "estimated_penalty", "confidence",
        "status", "assigned_officer", "verified_by", "verified_at",
        "officer_remarks", "action_taken", "created_at",
    ])
    w.writeheader()
    for r in records:
        d = r.to_dict()
        w.writerow({k: d.get(k, "") for k in w.fieldnames})
    si.seek(0)
    buf = BytesIO(si.read().encode("utf-8-sig"))
    buf.seek(0)
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                     download_name="encroachments_export.csv")


@app.route("/api/export/encroachments.geojson")
@login_required
def export_encroachments_geojson():
    records = EncroachmentRecord.query.filter(
        EncroachmentRecord.latitude.isnot(None)
    ).all()
    features = []
    for r in records:
        props = r.to_dict()
        props.pop("geometry_geojson", None)
        geom = None
        if r.geometry_geojson:
            try:
                geom = json.loads(r.geometry_geojson)
            except Exception:
                pass
        if not geom and r.latitude and r.longitude:
            geom = {"type": "Point", "coordinates": [r.longitude, r.latitude]}
        if geom:
            features.append({"type": "Feature", "geometry": geom, "properties": props})
    geojson = {"type": "FeatureCollection", "features": features}
    buf = BytesIO(json.dumps(geojson, indent=2).encode("utf-8"))
    buf.seek(0)
    return send_file(buf, mimetype="application/geo+json", as_attachment=True,
                     download_name="encroachments.geojson")


# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL SEARCH API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/search", methods=["GET"])
@login_required
def global_search():
    """Cross-entity search: parcels, encroachments, users (admin only)."""
    q_str    = request.args.get("q", "").strip()
    if len(q_str) < 2:
        return jsonify({"status": "error", "message": "Query must be at least 2 characters."}), 400

    like = f"%{q_str}%"
    results = {}

    parcels = ParcelRecord.query.filter(
        ParcelRecord.parcel_id.ilike(like)     |
        ParcelRecord.survey_number.ilike(like) |
        ParcelRecord.owner_name.ilike(like)    |
        ParcelRecord.village.ilike(like)       |
        ParcelRecord.mandal.ilike(like)        |
        ParcelRecord.district.ilike(like)
    ).limit(10).all()
    results["parcels"] = [r.to_dict() for r in parcels]

    enc = EncroachmentRecord.query.filter(
        EncroachmentRecord.flag_id.ilike(like)        |
        EncroachmentRecord.violator_name.ilike(like)  |
        EncroachmentRecord.affected_owner.ilike(like) |
        EncroachmentRecord.affected_parcel_id.ilike(like) |
        EncroachmentRecord.village.ilike(like)        |
        EncroachmentRecord.district.ilike(like)
    ).limit(10).all()
    results["encroachments"] = [r.to_dict() for r in enc]

    if current_user.is_admin:
        users = User.query.filter(
            User.username.ilike(like) |
            User.full_name.ilike(like) |
            User.email.ilike(like)
        ).limit(10).all()
        results["users"] = [u.to_dict() for u in users]

    return jsonify({"status": "success", "query": q_str, "results": results})


# ══════════════════════════════════════════════════════════════════════════════
#  ENHANCED DASHBOARD STATS API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/dashboard-stats-v2", methods=["GET"])
@login_required
def dashboard_stats_v2():
    """Enhanced stats for dashboard KPI cards and charts."""
    from sqlalchemy import func
    total_parcels       = ParcelRecord.query.count()
    total_area_sqm      = db.session.query(func.sum(ParcelRecord.area_sqm)).scalar() or 0
    total_encroachments = EncroachmentRecord.query.count()
    total_users         = User.query.count() if current_user.is_admin else None

    # Status breakdown
    status_rows = db.session.query(
        EncroachmentRecord.status, func.count()
    ).group_by(EncroachmentRecord.status).all()
    status_breakdown = {r[0]: r[1] for r in status_rows}

    # Severity breakdown
    sev_rows = db.session.query(
        EncroachmentRecord.severity, func.count()
    ).group_by(EncroachmentRecord.severity).all()
    severity_breakdown = {r[0]: r[1] for r in sev_rows}

    # Type breakdown (top 6)
    type_rows = db.session.query(
        EncroachmentRecord.encroachment_type, func.count()
    ).group_by(EncroachmentRecord.encroachment_type).order_by(func.count().desc()).limit(6).all()
    type_breakdown = {r[0]: r[1] for r in type_rows}

    # Recent 30-day trend (encroachments by day)
    from datetime import timedelta
    thirty_ago = datetime.now(timezone.utc) - timedelta(days=30)
    trend_rows = db.session.query(
        func.date(EncroachmentRecord.created_at), func.count()
    ).filter(EncroachmentRecord.created_at >= thirty_ago
    ).group_by(func.date(EncroachmentRecord.created_at)).all()
    trend = {str(r[0]): r[1] for r in trend_rows}

    recent_enc = [r.to_dict() for r in
                  EncroachmentRecord.query.order_by(
                      EncroachmentRecord.created_at.desc()).limit(8).all()]
    recent_parcels = [r.to_dict() for r in
                      ParcelRecord.query.order_by(
                          ParcelRecord.created_at.desc()).limit(5).all()]

    gis_metrics = {}
    try:
        gis_metrics = get_gis_state().registry.get_metrics_summary()
    except Exception:
        pass

    return jsonify({
        "status": "success",
        "db_stats": {
            "total_parcels":         total_parcels,
            "total_area_sqm":        round(total_area_sqm, 2),
            "total_encroachments":   total_encroachments,
            "detected":              status_breakdown.get("DETECTED", 0),
            "pending_verification":  status_breakdown.get("PENDING_VERIFICATION", 0),
            "verified":              status_breakdown.get("VERIFIED", 0),
            "rejected":              status_breakdown.get("REJECTED", 0),
            "total_users":           total_users,
            "severity_breakdown":    severity_breakdown,
            "type_breakdown":        type_breakdown,
            "status_breakdown":      status_breakdown,
            "trend_30d":             trend,
        },
        "gis_stats":            gis_metrics,
        "recent_parcels":       recent_parcels,
        "recent_encroachments": recent_enc,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  PROFILE PAGES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/profile")
@login_required
def profile_page():
    """User profile/settings page."""
    return render_template("profile.html", user=current_user)


# ══════════════════════════════════════════════════════════════════════════════
#  UTILITY — allowed roles list (for admin user creation form)
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/roles", methods=["GET"])
@login_required
def get_roles():
    roles = [
        {"value": ROLE_ADMIN,       "label": "Administrator",  "description": "Full system access"},
        {"value": ROLE_GIS_OFFICER, "label": "GIS Officer",    "description": "Manage parcels, verify cases"},
        {"value": ROLE_SURVEYOR,    "label": "Surveyor",       "description": "Field surveys, verify cases"},
        {"value": ROLE_VIEWER,      "label": "Viewer",         "description": "Read-only access"},
    ]
    return jsonify({"status": "success", "roles": roles})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Municipal GIS System -> http://127.0.0.1:{port}")
    print("[*] Default credentials -> admin / Admin@1234  |  surveyor / Survey@1234")
    print("[*] Signup page -> /signup  |  Connect page -> /connect")
    app.run(host="0.0.0.0", port=port, debug=False)

