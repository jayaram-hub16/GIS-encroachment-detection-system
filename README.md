# Municipal GIS Encroachment Detection System

An AI-powered geospatial platform for real-time cadastral verification, land-use classification, and legal audit enforcement.

## 🌐 Live Demo
**Production URL:** https://municipal-gis-system.onrender.com

## 🏗️ Tech Stack
- **Backend:** Python 3.x + Flask 3.0 + Flask-Login + Flask-SQLAlchemy
- **Database:** PostgreSQL (production) / SQLite (local)
- **GIS Engine:** Shapely 2.0 (polygon intersection & difference)
- **ML Classifier:** Scikit-Learn (NDVI/NDBI spectral classification)
- **Frontend:** HTML5 + CSS3 + Vanilla JS + Leaflet.js
- **Maps:** Google Satellite, Hybrid, OSM tiles via Leaflet
- **Auth:** Bcrypt password hashing + Flask-Login sessions

## 🔐 Default Credentials
| Role | Username | Password |
|------|----------|----------|
| Admin | `admin` | `Admin@1234` |
| Viewer | `surveyor` | `Survey@1234` |

> Public users can self-register at `/signup` — always assigned Viewer role.

## 🚀 Production Deployment (Render.com)

### Method 1: render.yaml (Automatic)
1. Fork/push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo → Render reads `render.yaml` automatically
4. Done! Includes free PostgreSQL database.

### Method 2: Manual Web Service
1. Go to [render.com](https://render.com) → New → Web Service
2. Connect GitHub repo
3. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn run_app:app --workers=2 --timeout=120`
   - **Environment:** Python 3
4. Add Environment Variables:
   - `SECRET_KEY` = (generate random string)
   - `HTTPS` = `true`
   - `DATABASE_URL` = (from Render PostgreSQL Add-On)

## 💻 Local Development
```bash
pip install -r requirements.txt
python run_app.py
```
Visit: http://127.0.0.1:5000

## 📋 Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask session encryption key |
| `DATABASE_URL` | Yes (prod) | PostgreSQL connection string |
| `HTTPS` | Yes (prod) | Set to `true` for secure cookies |
| `PORT` | No | Server port (default: 5000) |

## 🔒 Security Features
- Bcrypt password hashing (never plaintext)
- Server-side RBAC: Admin-only POST/PUT/DELETE (HTTP 403 for unauthorized)
- Immutable append-only audit log
- CSRF-safe session cookies (HttpOnly, SameSite=Lax, Secure=True in production)

## 📊 API Endpoints
| Method | Endpoint | Access |
|--------|----------|--------|
| GET | /api/parcels | Authenticated |
| POST | /api/parcels | Admin only |
| PUT | /api/parcels/:id | Admin only |
| DELETE | /api/parcels/:id | Admin only |
| GET | /api/db/encroachments | Authenticated |
| POST | /api/scan | Admin only |
| GET | /api/audit-logs | Admin only |
| GET | /api/dashboard-stats | Authenticated |
| GET | /api/me | Authenticated |
