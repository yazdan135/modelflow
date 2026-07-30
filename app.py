import os
import io
import json
import uuid
import shutil
import traceback
from datetime import datetime
from functools import wraps
import numpy as np
import pandas as pd
import bcrypt
from flask import (
    Flask, render_template, request, redirect, url_for, session,
    send_file, jsonify, flash, Response, stream_with_context
)
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

from utils import data_utils as du
from utils import ml_utils as mu
from utils import viz_utils as vu
from utils import report_utils as ru
from utils import ai_utils as au

# Load environment variables
load_dotenv()

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_ROOT, "user_data")
os.makedirs(DATA_DIR, exist_ok=True)

app = Flask(__name__)
app.url_map.strict_slashes = False
app.config["TEMPLATES_AUTO_RELOAD"] = True

ATLAS_MONGO_URI = "mongodb+srv://shoppro271_db_user:LOG81tNMvqpFeiCT@automl.5bfoz9h.mongodb.net/automl_app?retryWrites=true&w=majority&tls=true&tlsAllowInvalidCertificates=true"
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL") or "admin@yazdan.com").strip().lower()
ADMIN_PASSWORD = (os.getenv("ADMIN_PASSWORD") or "yazdan243").strip()

mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri or "<db_password>" in mongo_uri or "<password>" in mongo_uri or "localhost" in mongo_uri:
    mongo_uri = ATLAS_MONGO_URI
elif mongo_uri.endswith("/") and not mongo_uri.startswith("mongodb+srv://"):
    mongo_uri += "automl_app"

if "tls=" not in mongo_uri and "ssl=" not in mongo_uri and "mongodb+srv://" in mongo_uri:
    sep = "&" if "?" in mongo_uri else "?"
    mongo_uri += f"{sep}tls=true&tlsAllowInvalidCertificates=true"

app.config["MONGO_URI"] = mongo_uri
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-very-insecure-change-me")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200MB

# Initialize MongoDB
try:
    mongo = PyMongo(app)
    db = mongo.db
    if db is None and hasattr(mongo, "cx") and mongo.cx is not None:
        db = mongo.cx.get_database("automl_app")
    if hasattr(mongo, "cx") and mongo.cx is not None:
        mongo.cx.admin.command('ping')
except Exception as mongo_err:
    print(f"WARNING: Initial MongoDB connection failed ({mongo_err}). Connecting with Atlas TLS configuration...")
    app.config["MONGO_URI"] = ATLAS_MONGO_URI
    mongo = PyMongo(app)
    db = mongo.db
    if db is None and hasattr(mongo, "cx") and mongo.cx is not None:
        db = mongo.cx.get_database("automl_app")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"

# Initialize OAuth for Google
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.email = user_data["email"]
        self.name = user_data["name"]
        self.provider = user_data.get("provider", "local")
        self.picture = user_data.get("picture")
        self.is_admin = user_data.get("is_admin", False) or (self.email.lower() == ADMIN_EMAIL)
        self.has_submitted_feedback = user_data.get("has_submitted_feedback", False)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
            flash("Admin privilege required to access this section.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated_function

@login_manager.user_loader
def load_user(user_id):
    user_data = db.users.find_one({"_id": user_id})
    if user_data:
        return User(user_data)
    return None

def get_user_dir(user_id):
    user_dir = os.path.join(DATA_DIR, user_id)
    os.makedirs(user_dir, exist_ok=True)
    return user_dir

def get_project_dir(user_id, project_id):
    project_dir = os.path.join(get_user_dir(user_id), project_id)
    os.makedirs(project_dir, exist_ok=True)
    return project_dir

def get_current_project():
    if "project_id" not in session:
        return None
    project_id = session["project_id"]
    if not current_user.is_authenticated:
        return None
    return db.projects.find_one({"_id": project_id, "user_id": current_user.id})

def set_current_project(project_id):
    session["project_id"] = project_id

def create_new_project(user_id, project_name=None):
    if not project_name:
        count = db.projects.count_documents({"user_id": user_id}) + 1
        project_name = f"AutoML Project #{count}"
    project_id = str(uuid.uuid4())
    project = {
        "_id": project_id,
        "user_id": user_id,
        "name": project_name,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "state": {}
    }
    db.projects.insert_one(project)
    get_project_dir(user_id, project_id)
    log_user_activity(user_id, project_id, "project", f"Created new workspace project '{project_name}'")
    return project

def update_project_state(project_id, state):
    db.projects.update_one(
        {"_id": project_id},
        {"$set": {"state": state, "updated_at": datetime.utcnow()}}
    )

def get_user_projects(user_id):
    return list(db.projects.find({"user_id": user_id}).sort("updated_at", -1))

def log_user_activity(user_id, project_id, action_type, description, metadata=None):
    try:
        activity = {
            "user_id": str(user_id),
            "project_id": str(project_id) if project_id else None,
            "action_type": action_type,
            "description": description,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow()
        }
        db.activities.insert_one(activity)
    except Exception as e:
        print(f"Error logging activity: {e}")

def get_user_analytics_data(user_id):
    user_doc = db.users.find_one({"_id": str(user_id)}) or {}
    created_at = user_doc.get("created_at") or datetime.utcnow()

    projects = list(db.projects.find({"user_id": str(user_id)}).sort("updated_at", -1))
    total_projects = len(projects)

    all_scores = []
    trained_models = []
    algo_counts = {}
    task_counts = {}
    history_events = []
    score_timeline = []
    total_datasets_uploaded = 0

    # Fetch recorded activities from MongoDB
    db_activities = list(db.activities.find({"user_id": str(user_id)}).sort("timestamp", -1))
    for act in db_activities:
        history_events.append({
            "timestamp": act.get("timestamp"),
            "action_type": act.get("action_type", "general"),
            "description": act.get("description", ""),
            "project_id": act.get("project_id"),
            "metadata": act.get("metadata", {})
        })

    # Iterate user projects to dynamically aggregate trained models & stats
    for proj in projects:
        pid = proj["_id"]
        pname = proj.get("name", "Project")
        p_created = proj.get("created_at", datetime.utcnow())
        p_updated = proj.get("updated_at", datetime.utcnow())
        
        pdir = os.path.join(DATA_DIR, str(user_id), pid)
        state = du.load_state(pdir) if os.path.exists(pdir) else proj.get("state", {})

        if state.get("file_info"):
            total_datasets_uploaded += 1

        task = state.get("task")
        if task:
            task_counts[task] = task_counts.get(task, 0) + 1

        leaderboard = state.get("leaderboard", [])
        for entry in leaderboard:
            model_name = entry.get("Model", "Unknown")
            algo_counts[model_name] = algo_counts.get(model_name, 0) + 1
            
            score_val = None
            for key in ["Accuracy", "F1", "R2", "Score", "precision", "recall"]:
                if key in entry and entry[key] is not None and entry[key] != "—":
                    try:
                        score_val = float(entry[key])
                        break
                    except (ValueError, TypeError):
                        pass
            
            if score_val is not None:
                all_scores.append(score_val)
                date_str = p_updated.strftime("%Y-%m-%d %H:%M") if isinstance(p_updated, datetime) else str(p_updated)[:16]
                score_timeline.append({
                    "date": date_str,
                    "score": score_val,
                    "model_info": f"{model_name} ({pname})"
                })

            trained_models.append({
                "project_name": pname,
                "project_id": pid,
                "model_name": model_name,
                "task": task or "N/A",
                "score": score_val,
                "is_best": (model_name == state.get("best_model")),
                "updated_at": p_updated
            })

        # Synthesize fallback activity logs if activity table is empty
        if not db_activities:
            history_events.append({
                "timestamp": p_created,
                "action_type": "project",
                "description": f"Created workspace project '{pname}'",
                "project_id": pid,
                "metadata": {}
            })
            if state.get("file_info"):
                fname = state["file_info"].get("filename", "dataset")
                history_events.append({
                    "timestamp": p_updated,
                    "action_type": "dataset",
                    "description": f"Uploaded dataset '{fname}' into project '{pname}'",
                    "project_id": pid,
                    "metadata": state["file_info"]
                })
            if leaderboard:
                best_m = state.get("best_model", "Model")
                history_events.append({
                    "timestamp": p_updated,
                    "action_type": "training",
                    "description": f"Trained {len(leaderboard)} models in '{pname}'. Top model: {best_m}",
                    "project_id": pid,
                    "metadata": {"models_trained": len(leaderboard), "best_model": best_m}
                })

    history_events.sort(key=lambda x: x.get("timestamp") if isinstance(x.get("timestamp"), datetime) else datetime.min, reverse=True)

    min_score = min(all_scores) if all_scores else 0.0
    max_score = max(all_scores) if all_scores else 0.0
    avg_score = (sum(all_scores) / len(all_scores)) if all_scores else 0.0
    total_models_trained = len(trained_models)

    return {
        "user_info": {
            "name": user_doc.get("name", "User"),
            "email": user_doc.get("email", ""),
            "provider": user_doc.get("provider", "local"),
            "picture": user_doc.get("picture"),
            "created_at": created_at,
        },
        "stats": {
            "total_projects": total_projects,
            "total_models_trained": total_models_trained,
            "total_datasets_uploaded": total_datasets_uploaded,
            "min_score": min_score,
            "max_score": max_score,
            "avg_score": avg_score,
            "total_activities": len(history_events)
        },
        "algo_counts": algo_counts,
        "task_counts": task_counts,
        "trained_models": trained_models,
        "history_events": history_events,
        "score_timeline": sorted(score_timeline, key=lambda x: str(x["date"]))
    }

def require_project():
    project = get_current_project()
    if not project:
        projects = get_user_projects(current_user.id)
        if projects:
            project = projects[0]
            set_current_project(project["_id"])
        else:
            return None, None
    project_dir = get_project_dir(current_user.id, project["_id"])
    df = du.load_df(project_dir)
    return project, df

@app.errorhandler(Exception)
def handle_error(e):
    tb = traceback.format_exc()
    print(tb)
    return render_template("error.html", error=str(e), traceback=tb), 500

def is_google_configured():
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    return (
        client_id is not None
        and client_secret is not None
        and not client_id.startswith("your-")
        and not client_secret.startswith("your-")
    )

# Auth Routes
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        name = request.form.get("name")
        
        if not email or not password or not name:
            flash("Please fill all fields", "danger")
            return redirect(url_for("signup"))
        
        existing_user = db.users.find_one({"email": email.lower()})
        if existing_user:
            flash("Email already registered. Please log in instead.", "warning")
            return redirect(url_for("login"))
        
        hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        user_id = str(uuid.uuid4())
        db.users.insert_one({
            "_id": user_id,
            "email": email.lower(),
            "password": hashed,
            "name": name,
            "provider": "local"
        })
        
        user_data = db.users.find_one({"_id": user_id})
        user = User(user_data)
        login_user(user)
        flash("Account created successfully! Welcome to AutoML Studio!", "success")
        return redirect(url_for("index"))
        
    return render_template("signup.html", google_configured=is_google_configured())

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        if not email or not password:
            flash("Please fill all fields", "danger")
            return redirect(url_for("login"))
        
        # Special check for Admin Credentials
        if email.lower() == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            admin_user = db.users.find_one({"email": ADMIN_EMAIL})
            if not admin_user:
                hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode('utf-8'), bcrypt.gensalt())
                admin_id = str(uuid.uuid4())
                db.users.insert_one({
                    "_id": admin_id,
                    "email": ADMIN_EMAIL,
                    "password": hashed,
                    "name": "Platform Admin",
                    "provider": "local",
                    "is_admin": True,
                    "created_at": datetime.utcnow()
                })
                admin_user = db.users.find_one({"_id": admin_id})
            
            user = User(admin_user)
            login_user(user)
            flash("Welcome to the Admin Control Panel!", "success")
            return redirect(url_for("admin_dashboard"))

        user_data = db.users.find_one({"email": email.lower(), "provider": "local"})
        if not user_data:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
        
        if bcrypt.checkpw(password.encode('utf-8'), user_data["password"]):
            user = User(user_data)
            login_user(user)
            flash("Logged in successfully!", "success")
            if user.is_admin:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("index"))
        else:
            flash("Invalid email or password.", "danger")
            return redirect(url_for("login"))
        
    return render_template("login.html", google_configured=is_google_configured())

@app.route("/login/google")
def login_google():
    if not is_google_configured():
        flash("Google login is not configured.", "danger")
        return redirect(url_for("login"))
    redirect_uri = url_for("authorize_google", _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/callback/google")
def authorize_google():
    if not is_google_configured():
        flash("Google login is not configured.", "danger")
        return redirect(url_for("login"))
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    if not user_info:
        userinfo_endpoint = google.server_metadata.get('userinfo_endpoint', 'https://openidconnect.googleapis.com/v1/userinfo')
        resp = google.get(userinfo_endpoint)
        user_info = resp.json()
    
    email = user_info["email"]
    name = user_info.get("name", email.split("@")[0])
    picture = user_info.get("picture")
    
    user_data = db.users.find_one({"email": email.lower()})
    if not user_data:
        user_id = str(uuid.uuid4())
        db.users.insert_one({
            "_id": user_id,
            "email": email.lower(),
            "name": name,
            "provider": "google",
            "picture": picture
        })
        user_data = db.users.find_one({"_id": user_id})
    else:
        update_data = {"name": name}
        if picture:
            update_data["picture"] = picture
        db.users.update_one({"_id": user_data["_id"]}, {"$set": update_data})
        user_data = db.users.find_one({"_id": user_data["_id"]})
    
    user = User(user_data)
    login_user(user)
    flash("Logged in with Google successfully!", "success")
    return redirect(url_for("index"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("login"))

@app.route("/landing", methods=["GET"])
def landing():
    return render_template("landing.html")

# Dynamic SaaS Dashboard & Project Routes
@app.route("/", methods=["GET"])
def index():
    if not current_user.is_authenticated:
        return render_template("landing.html")
    projects = get_user_projects(current_user.id)
    current_project = get_current_project()

    if not current_project and projects:
        current_project = projects[0]
        set_current_project(current_project["_id"])

    kpis = {
        "dataset_name": "No Dataset Uploaded",
        "rows": 0,
        "columns": 0,
        "missing_cells": 0,
        "missing_pct": 0.0,
        "duplicate_rows": 0,
        "total_outliers": 0,
        "health_score": 0.0,
        "memory_usage": "0 KB",
        "problem_type": "Not configured",
        "best_model": "None",
        "best_score": "—",
        "workflow_step": 1,
        "models_trained_count": 0,
    }

    state = {}
    profile = {}
    ai = {}
    leaderboard = []

    if current_project:
        project_dir = get_project_dir(current_user.id, current_project["_id"])
        state = du.load_state(project_dir)
        df = du.load_df(project_dir)

        if df is not None:
            profile = du.profile_dataset(df)
            state["profile"] = profile
            file_info = state.get("file_info") or du.basic_file_info(df, "dataset.csv")
            ai = state.get("ai") or {}
            leaderboard = state.get("leaderboard", [])

            kpis["dataset_name"] = file_info.get("filename", "dataset.csv")
            kpis["rows"] = profile.get("shape", {}).get("rows", len(df))
            kpis["columns"] = profile.get("shape", {}).get("columns", len(df.columns))
            kpis["missing_cells"] = profile.get("total_missing_cells", int(df.isna().sum().sum()))
            kpis["missing_pct"] = round((kpis["missing_cells"] / max(kpis["rows"] * kpis["columns"], 1)) * 100, 1)
            kpis["duplicate_rows"] = profile.get("duplicate_rows", int(df.duplicated().sum()))
            kpis["total_outliers"] = profile.get("total_outliers", 0)
            kpis["health_score"] = profile.get("health_score", du.dataset_health_score(df))
            kpis["memory_usage"] = file_info.get("memory_usage", "0 KB")

            if state.get("best_model"):
                kpis["workflow_step"] = 5
            elif state.get("cleaning_log") or state.get("cleaning_report"):
                kpis["workflow_step"] = 3
            elif profile:
                kpis["workflow_step"] = 2
            else:
                kpis["workflow_step"] = 1

            if state.get("task"):
                kpis["problem_type"] = state["task"].title()

            if leaderboard:
                kpis["models_trained_count"] = len(leaderboard)
                kpis["best_model"] = state.get("best_model", leaderboard[0].get("Model", "None"))
                best_row = leaderboard[0]
                metric_name = "Accuracy" if state.get("task") == "classification" else "R2"
                val = best_row.get(metric_name) or best_row.get("Score")
                if val is not None and val != "—":
                    kpis["best_score"] = f"{float(val)*100:.1f}%" if metric_name == "Accuracy" else f"{float(val):.3f}"

    return render_template(
        "projects.html",
        projects=projects,
        current_project=current_project,
        kpis=kpis,
        state=state,
        profile=profile,
        ai=ai,
        leaderboard=leaderboard,
        columns=list(df.columns) if (current_project and 'df' in locals() and df is not None) else [],
        feature_columns=state.get("feature_columns", []) if current_project else []
    )

@app.route("/new-project", methods=["GET", "POST"])
@login_required
def new_project():
    if request.method == "POST":
        project_name = request.form.get("project_name")
        project = create_new_project(current_user.id, project_name)
        set_current_project(project["_id"])
        flash(f"New project workspace '{project['name']}' created successfully!", "success")
        return redirect(url_for("upload_page"))
    return render_template("new_project.html")

@app.route("/switch-project/<project_id>", methods=["GET"])
@login_required
def switch_project(project_id):
    project = db.projects.find_one({"_id": project_id, "user_id": current_user.id})
    if not project:
        flash("Project not found!", "danger")
        return redirect(url_for("index"))
    set_current_project(project_id)
    flash(f"Switched active project to '{project['name']}'!", "success")
    return redirect(url_for("index"))

@app.route("/delete-project/<project_id>", methods=["POST", "GET"])
@login_required
def delete_project(project_id):
    project = db.projects.find_one({"_id": project_id, "user_id": current_user.id})
    if not project:
        flash("Project not found or access denied.", "danger")
        return redirect(url_for("index"))

    project_name = project.get("name", "Project")

    # Delete project document from DB
    db.projects.delete_one({"_id": project_id, "user_id": current_user.id})

    # Delete project directory from disk
    project_dir = os.path.join(DATA_DIR, current_user.id, project_id)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir, ignore_errors=True)

    # Reset or update active session project if deleted project was active
    if session.get("project_id") == project_id:
        session.pop("project_id", None)
        remaining_projects = get_user_projects(current_user.id)
        if remaining_projects:
            set_current_project(remaining_projects[0]["_id"])

    flash(f"Project '{project_name}' deleted successfully!", "success")
    return redirect(url_for("index"))

@app.route("/rename-project/<project_id>", methods=["POST", "GET"])
@login_required
def rename_project(project_id):
    project = db.projects.find_one({"_id": project_id, "user_id": current_user.id})
    if not project:
        flash("Project not found or access denied.", "danger")
        return redirect(url_for("index"))

    new_name = request.form.get("project_name", "").strip()
    if not new_name:
        flash("Project name cannot be empty.", "warning")
        return redirect(url_for("index"))

    db.projects.update_one(
        {"_id": project_id, "user_id": current_user.id},
        {"$set": {"name": new_name, "updated_at": datetime.utcnow()}}
    )

    flash(f"Project name updated to '{new_name}' successfully!", "success")
    return redirect(url_for("index"))

@app.route("/upload-page", methods=["GET"])
@login_required
def upload_page():
    project = get_current_project()
    if not project:
        projects = get_user_projects(current_user.id)
        if projects:
            project = projects[0]
            set_current_project(project["_id"])
        else:
            flash("Please create your first project workspace to start dataset upload & model training.", "info")
            return redirect(url_for("new_project"))
    state = project.get("state", {})
    return render_template("index.html", state=state, current_project=project)

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    project = get_current_project()
    if not project:
        projects = get_user_projects(current_user.id)
        if projects:
            project = projects[0]
            set_current_project(project["_id"])
        else:
            flash("Please create a project workspace first before uploading datasets.", "warning")
            return redirect(url_for("new_project"))

    project_dir = get_project_dir(current_user.id, project["_id"])
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("Please choose a CSV, TSV, or Excel file.", "danger")
        return redirect(url_for("upload_page"))

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("csv", "xlsx", "xls", "tsv"):
        flash("Only .csv, .xlsx, .xls, and .tsv files are supported.", "danger")
        return redirect(url_for("upload_page"))

    df = du.read_uploaded_file(file)
    du.save_df(project_dir, df)
    du.save_df(project_dir, df, name="original.pkl")

    info = du.basic_file_info(df, file.filename)
    profile = du.profile_dataset(df)

    state = {
        "file_info": info,
        "profile": profile,
        "cleaning_log": [],
        "target": None,
        "task": None
    }
    du.save_state(project_dir, state)
    update_project_state(project["_id"], state)
    
    du.create_cleaning_snapshot(project_dir, df, "Initial raw upload")
    log_user_activity(current_user.id, project["_id"], "dataset", f"Uploaded dataset '{file.filename}' ({info['rows']} rows, {info['columns']} columns)", metadata=info)

    flash(f"Uploaded '{file.filename}' successfully — {info['rows']} rows, {info['columns']} columns ({info['memory_usage']}).", "success")
    return redirect(url_for("explore"))

@app.route("/explore")
@login_required
def explore():
    project, df = require_project()
    if not project:
        flash("Please create a project workspace first.", "info")
        return redirect(url_for("new_project"))
    if df is None:
        flash("Please upload a dataset first.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])

    profile = du.profile_dataset(df)
    ai, provider = au.get_ai_recommendations_with_fallback(df, profile)
    state = du.load_state(project_dir)
    state["profile"] = profile
    state["ai"] = ai
    state["ai_provider"] = provider
    du.save_state(project_dir, state)
    update_project_state(project["_id"], state)

    preview = df.head(100).to_html(classes="table table-sm table-striped table-hover align-middle text-xs font-mono", index=False, na_rep="—")
    return render_template("explore.html", profile=profile, ai=ai, provider=provider, preview=preview,
                            file_info=state.get("file_info", {}), columns=list(df.columns), state=state, current_project=project)

@app.route("/clean", methods=["GET", "POST"])
@login_required
def clean():
    project, df = require_project()
    if not project:
        flash("Please create a project workspace first.", "info")
        return redirect(url_for("new_project"))
    if df is None:
        flash("Please upload a dataset first.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])

    state = du.load_state(project_dir)
    log = state.get("cleaning_log", [])

    if request.method == "POST":
        action = request.form.get("action")
        try:
            if action == "auto_clean":
                profile = du.profile_dataset(df)
                df, report = du.auto_clean(df, profile)
                state["cleaning_report"] = report
                log.append(f"Auto-Clean performed (Health score improved to {report['after']['health_score']})")
                du.create_cleaning_snapshot(project_dir, df, "Auto-Clean pipeline")
                flash("Auto-Clean completed successfully!", "success")

            elif action == "missing":
                column = request.form["column"]
                strategy = request.form["strategy"]
                df = du.apply_missing_value_strategy(df, column, strategy)
                log.append(f"Missing values in '{column}' handled via {strategy}.")
                du.create_cleaning_snapshot(project_dir, df, f"Missing values: {column} ({strategy})")
                flash(f"Imputed missing values in '{column}'.", "success")

            elif action == "duplicates":
                before = len(df)
                df = du.remove_duplicates(df)
                log.append(f"Removed {before - len(df)} duplicate rows.")
                du.create_cleaning_snapshot(project_dir, df, "Removed duplicates")
                flash(f"Removed {before - len(df)} duplicate rows.", "success")

            elif action == "outliers":
                column = request.form["column"]
                method = request.form["method"]
                before = len(df)
                df = du.handle_outliers(df, column, method)
                log.append(f"Outliers removed from '{column}' via {method} ({before - len(df)} rows dropped).")
                du.create_cleaning_snapshot(project_dir, df, f"Outliers: {column} ({method})")
                flash(f"Handled outliers in '{column}'.", "success")

            elif action == "encode":
                column = request.form["column"]
                method = request.form["method"]
                df = du.encode_column(df, column, method)
                log.append(f"Encoded '{column}' using {method}.")
                du.create_cleaning_snapshot(project_dir, df, f"Encoded: {column} ({method})")
                flash(f"Encoded column '{column}'.", "success")

            elif action == "scale":
                method = request.form["method"]
                numeric_cols = du.column_types(df)["numeric"]
                df = du.scale_columns(df, numeric_cols, method)
                log.append(f"Scaled numeric columns using {method}.")
                du.create_cleaning_snapshot(project_dir, df, f"Scaled features ({method})")
                flash(f"Scaled numeric features using {method}.", "success")

            elif action == "drop_column":
                column = request.form["column"]
                if column in df.columns:
                    df = df.drop(columns=[column])
                    log.append(f"Dropped column '{column}'.")
                    du.create_cleaning_snapshot(project_dir, df, f"Dropped {column}")
                    flash(f"Dropped column '{column}'.", "info")

            elif action == "reset":
                df, msg = du.reset_to_original(project_dir)
                flash(msg, "info")
                return redirect(url_for("clean"))

            elif action == "undo":
                df, msg = du.undo_last_cleaning(project_dir)
                if df is None:
                    flash(msg, "warning")
                else:
                    log = state.get("cleaning_log", [])
                    if log:
                        log.pop()
                    state["cleaning_log"] = log
                    flash(msg, "success")

            du.save_df(project_dir, df)
            profile_new = du.profile_dataset(df)
            state["profile"] = profile_new
            state["cleaning_log"] = log
            state["file_info"]["rows"] = len(df)
            state["file_info"]["columns"] = len(df.columns)
            du.save_state(project_dir, state)
            update_project_state(project["_id"], state)

        except Exception as e:
            flash(f"Could not apply cleaning step: {e}", "danger")
        return redirect(url_for("clean"))

    profile = du.profile_dataset(df)
    state["profile"] = profile
    du.save_state(project_dir, state)

    types = du.column_types(df)
    preview = df.head(50).to_html(classes="table table-sm table-striped table-hover align-middle text-xs font-mono", index=False, na_rep="—")
    cleaning_report = state.get("cleaning_report")
    history = state.get("cleaning_history", [])

    return render_template(
        "clean.html",
        profile=profile,
        types=types,
        preview=preview,
        log=log,
        history=history,
        state=state,
        current_project=project,
        cleaning_report=cleaning_report
    )

@app.route("/visualize")
@login_required
def visualize():
    project, df = require_project()
    if not project:
        flash("Please create a project workspace first.", "info")
        return redirect(url_for("new_project"))
    if df is None:
        flash("Please upload a dataset first.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])
    state = du.load_state(project_dir)
    types = du.column_types(df)
    return render_template("visualize.html", types=types, columns=list(df.columns), state=state, current_project=project)

@app.route("/api/chart")
@login_required
def api_chart():
    project, df = require_project()
    if df is None:
        return jsonify({"error": "no dataset loaded"}), 400
    kind = request.args.get("kind", "histogram")
    col = request.args.get("column")
    col2 = request.args.get("column2")
    dark_mode = request.args.get("dark_mode", "true").lower() == "true"
    types = du.column_types(df)

    if not col and len(df.columns) > 0:
        col = df.columns[0]
    if kind == "scatter" and not col2 and len(df.columns) > 1:
        col2 = df.columns[1] if df.columns[1] != col else df.columns[0]

    try:
        if kind == "histogram":
            fig = vu.histogram(df, col, dark_mode=dark_mode)
        elif kind == "bar":
            fig = vu.bar_chart(df, col, dark_mode=dark_mode)
        elif kind == "box":
            fig = vu.box_plot(df, col, col2, dark_mode=dark_mode)
        elif kind == "violin":
            fig = vu.violin_plot(df, col, col2, dark_mode=dark_mode)
        elif kind == "correlation":
            fig = vu.correlation_heatmap(df, types["numeric"], dark_mode=dark_mode)
        elif kind == "missing":
            fig = vu.missing_bar(df, dark_mode=dark_mode)
        elif kind == "scatter":
            fig = vu.scatter_plot(df, col, col2, dark_mode=dark_mode)
        elif kind == "pie":
            fig = vu.pie_chart(df, col, dark_mode=dark_mode)
        else:
            return jsonify({"error": f"unknown chart type '{kind}'"}), 400
        return fig.to_json(engine="json"), 200, {"Content-Type": "application/json"}
    except Exception as e:
        return jsonify({"error": f"Chart rendering failed: {str(e)}"}), 500

@app.route("/train", methods=["GET", "POST"])
@login_required
def train():
    project, df = require_project()
    if not project:
        flash("Please create a project workspace first before training models.", "warning")
        return redirect(url_for("new_project"))
    if df is None:
        flash("Please upload a dataset first before training models.", "warning")
        return redirect(url_for("upload_page"))

    project_dir = get_project_dir(current_user.id, project["_id"])
    state = du.load_state(project_dir)

    if request.method == "POST":
        target = request.form["target"]
        split = float(request.form.get("split", 0.2))
        shuffle = request.form.get("shuffle", "on") == "on"
        stratify_flag = request.form.get("stratify", "off") == "on"
        model_choice = request.form.getlist("models")
        train_all = request.form.get("train_all") == "on"

        work_df = df.copy()
        task = mu.detect_task_type(work_df[target])

        feature_df = work_df.drop(columns=[target])
        cat_cols = du.column_types(feature_df)["categorical"] + du.column_types(feature_df)["datetime"]
        for c in cat_cols:
            feature_df = du.encode_column(feature_df, c, "onehot" if feature_df[c].nunique() <= 15 else "label")

        feature_df = feature_df.select_dtypes(include=[np.number, "bool"])
        feature_df = feature_df.fillna(feature_df.median(numeric_only=True))

        y = work_df[target]
        if task == "classification" and not pd.api.types.is_numeric_dtype(y):
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder()
            y = pd.Series(le.fit_transform(y.astype(str)), index=y.index)
            class_labels = le.classes_.tolist()
        else:
            class_labels = sorted(y.dropna().unique().tolist()) if task == "classification" else None

        combined = pd.concat([feature_df, y.rename("__target__")], axis=1).dropna()
        feature_df = combined.drop(columns="__target__")
        y = combined["__target__"]

        X_train, X_test, y_train, y_test = mu.train_test_split_data(
            feature_df, y, test_size=split, shuffle=shuffle,
            stratify_flag=stratify_flag, task=task
        )

        model_names = None if train_all else (model_choice or None)
        lb_df, fitted, extras, best_name = mu.run_automl(X_train, X_test, y_train, y_test, task, model_names)

        du.save_df(project_dir, feature_df, name="feature_df.pkl")
        du.save_df(project_dir, X_test, name="X_test.pkl")
        du.save_df(project_dir, y_test, name="y_test.pkl")

        import pickle
        with open(os.path.join(project_dir, "fitted_models.pkl"), "wb") as f:
            pickle.dump(fitted, f)
        with open(os.path.join(project_dir, "extras.pkl"), "wb") as f:
            pickle.dump(extras, f)

        state["target"] = target
        state["task"] = task
        state["class_labels"] = class_labels
        state["feature_columns"] = feature_df.columns.tolist()
        state["leaderboard"] = lb_df.to_dict(orient="records")
        state["best_model"] = best_name
        du.save_state(project_dir, state)
        update_project_state(project["_id"], state)

        if best_name:
            best_model_obj = fitted[best_name]
            model_path = os.path.join(project_dir, "best_model.pkl")
            mu.save_model_bundle(model_path, best_model_obj, feature_df.columns.tolist(), target, task)

        log_user_activity(current_user.id, project["_id"], "training", f"Trained AutoML pipeline with {len(lb_df)} models. Top selected model: '{best_name}'", metadata={"best_model": best_name, "task": task, "models_count": len(lb_df)})

        flash(f"AutoML training complete! Best model selected: {best_name}", "success")
        return redirect(url_for("results"))

    profile = du.profile_dataset(df)
    ai = state.get("ai") or du.ai_recommendations(df, profile)
    zoo_class = list(mu.get_model_zoo("classification").keys())
    zoo_reg = list(mu.get_model_zoo("regression").keys())
    return render_template("train.html", columns=list(df.columns), ai=ai,
                            zoo_class=zoo_class, zoo_reg=zoo_reg, state=state, current_project=project)

@app.route("/train_stream", methods=["POST"])
@login_required
def train_stream():
    project, df = require_project()
    if not project or df is None:
        return jsonify({"error": "No active project or dataset loaded."}), 400

    project_dir = get_project_dir(current_user.id, project["_id"])
    state = du.load_state(project_dir)

    target = request.form.get("target")
    split = float(request.form.get("split", 0.2))
    shuffle = request.form.get("shuffle", "on") == "on"
    stratify_flag = request.form.get("stratify", "off") == "on"
    model_choice = request.form.getlist("models")
    train_all = request.form.get("train_all") == "on"

    def generate_events():
        def make_sse(pct, msg, model_name="", log_entry=""):
            payload = {
                "percent": int(pct),
                "message": msg,
                "model": model_name,
                "log": log_entry
            }
            return f"data: {json.dumps(payload)}\n\n"

        yield make_sse(5, "Initializing AutoML dataset pipeline...", log_entry="[INIT] Dataset loaded and objective verified.")

        work_df = df.copy()
        task = mu.detect_task_type(work_df[target])

        yield make_sse(8, "Encoding categorical features & handling missing values...", log_entry=f"[PREPROCESS] Task auto-detected as '{task.upper()}'. Encoding columns...")

        feature_df = work_df.drop(columns=[target])
        cat_cols = du.column_types(feature_df)["categorical"] + du.column_types(feature_df)["datetime"]
        for c in cat_cols:
            feature_df = du.encode_column(feature_df, c, "onehot" if feature_df[c].nunique() <= 15 else "label")

        feature_df = feature_df.select_dtypes(include=[np.number, "bool"])
        feature_df = feature_df.fillna(feature_df.median(numeric_only=True))

        y = work_df[target]
        if task == "classification" and not pd.api.types.is_numeric_dtype(y):
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder()
            y = pd.Series(le.fit_transform(y.astype(str)), index=y.index)
            class_labels = le.classes_.tolist()
        else:
            class_labels = sorted(y.dropna().unique().tolist()) if task == "classification" else None

        combined = pd.concat([feature_df, y.rename("__target__")], axis=1).dropna()
        feature_df = combined.drop(columns="__target__")
        y = combined["__target__"]

        yield make_sse(15, f"Splitting data into Training & Testing sets ({int((1-split)*100)}% Train / {int(split*100)}% Test)...", log_entry="[DATA] Data split completed.")

        X_train, X_test, y_train, y_test = mu.train_test_split_data(
            feature_df, y, test_size=split, shuffle=shuffle,
            stratify_flag=stratify_flag, task=task
        )

        model_names = None if train_all else (model_choice or None)
        lb_df = None
        fitted = {}
        extras = {}
        best_name = None

        for evt in mu.run_automl_stream(X_train, X_test, y_train, y_test, task, model_names):
            if evt.get("stage") == "result":
                lb_df = evt["lb_df"]
                fitted = evt["fitted"]
                extras = evt["extras"]
                best_name = evt["best_model_name"]
            else:
                m_name = evt.get("model", "")
                idx = evt.get("index", 1)
                tot = evt.get("total", 1)
                stage = evt.get("stage")

                pct_start = 15 + int(((idx - 1) / tot) * 70)
                pct_mid = 15 + int(((idx - 0.5) / tot) * 70)
                pct_end = 15 + int((idx / tot) * 70)

                if stage == "train_start":
                    yield make_sse(pct_start, f"Training Model [{idx}/{tot}]: {m_name}...", model_name=m_name, log_entry=f"⚡ [{idx}/{tot}] Fitting model '{m_name}' on training split...")
                elif stage == "evaluating":
                    yield make_sse(pct_mid, f"Evaluating accuracy & cross-validation metrics for {m_name}...", model_name=m_name, log_entry=f"📊 Computing performance metrics for '{m_name}'...")
                elif stage == "train_complete":
                    summary = evt.get("summary", "")
                    yield make_sse(pct_end, f"Completed {m_name}! {summary}", model_name=m_name, log_entry=f"✔ [{idx}/{tot}] '{m_name}' trained. Score: {summary}")
                elif stage == "train_error":
                    yield make_sse(pct_end, f"Error in {m_name}", model_name=m_name, log_entry=f"⚠️ [{idx}/{tot}] Error training '{m_name}': {evt.get('error')}")

        yield make_sse(90, "Evaluating AutoML leaderboard & selecting optimal model...", log_entry=f"🏆 Winner Model selected: '{best_name}'")

        du.save_df(project_dir, feature_df, name="feature_df.pkl")
        du.save_df(project_dir, X_test, name="X_test.pkl")
        du.save_df(project_dir, y_test, name="y_test.pkl")

        import pickle
        with open(os.path.join(project_dir, "fitted_models.pkl"), "wb") as f:
            pickle.dump(fitted, f)
        with open(os.path.join(project_dir, "extras.pkl"), "wb") as f:
            pickle.dump(extras, f)

        state["target"] = target
        state["task"] = task
        state["class_labels"] = class_labels
        state["feature_columns"] = feature_df.columns.tolist()
        state["leaderboard"] = lb_df.to_dict(orient="records") if lb_df is not None else []
        state["best_model"] = best_name
        du.save_state(project_dir, state)
        update_project_state(project["_id"], state)

        if best_name and best_name in fitted:
            best_model_obj = fitted[best_name]
            model_path = os.path.join(project_dir, "best_model.pkl")
            mu.save_model_bundle(model_path, best_model_obj, feature_df.columns.tolist(), target, task)

        log_user_activity(current_user.id, project["_id"], "training", f"Trained AutoML pipeline. Top model: '{best_name}'", metadata={"best_model": best_name, "task": task})

        yield make_sse(98, "Saving model pipeline & preparing results...", log_entry="💾 Saved fitted models & artifacts to workspace.")

        final_payload = {
            "percent": 100,
            "message": f"Training Complete! Top Model: {best_name}",
            "model": best_name,
            "log": "🚀 Redirecting to results dashboard...",
            "redirect": url_for("results")
        }
        yield f"data: {json.dumps(final_payload)}\n\n"

    return Response(stream_with_context(generate_events()), mimetype="text/event-stream")

@app.route("/results")
@login_required
def results():
    project, df = require_project()
    if not project:
        flash("Please create a project workspace first.", "info")
        return redirect(url_for("new_project"))
    if df is None:
        flash("Please upload a dataset first.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])
    state = du.load_state(project_dir)
    if "leaderboard" not in state:
        flash("Train a model first.", "warning")
        return redirect(url_for("train"))

    leaderboard = state["leaderboard"]
    task = state["task"]
    best_model = state["best_model"]

    best_row = next((r for r in leaderboard if r.get("Model") == best_model), (leaderboard[0] if leaderboard else {}))

    overall_score = None
    if task == "classification" and leaderboard:
        total = 0
        count = 0
        for metric in ["Accuracy", "Precision", "Recall", "F1"]:
            val = best_row.get(metric)
            if val is not None and val != "—":
                total += float(val)
                count += 1
        if count > 0:
            overall_score = round((total / count) * 100, 2)
    elif task == "regression" and leaderboard:
        val = best_row.get("R2")
        if val is not None and val != "—":
            overall_score = round(float(val), 4)

    import pickle
    with open(os.path.join(project_dir, "extras.pkl"), "rb") as f:
        extras = pickle.load(f)
    with open(os.path.join(project_dir, "fitted_models.pkl"), "rb") as f:
        fitted = pickle.load(f)

    best_extras = extras.get(best_model, {})
    best_obj = fitted.get(best_model)
    feature_cols = state.get("feature_columns", [])

    charts = {}
    if task == "classification":
        charts["leaderboard"] = vu.leaderboard_bar(pd.DataFrame(leaderboard), "Accuracy").to_json()
        if "confusion_matrix" in best_extras:
            labels = state.get("class_labels")
            labels = [str(l) for l in labels] if labels else None
            charts["confusion_matrix"] = vu.confusion_matrix_fig(best_extras["confusion_matrix"], labels).to_json()
        if "roc" in best_extras:
            charts["roc"] = vu.roc_curve_fig(best_extras["roc"]["fpr"], best_extras["roc"]["tpr"], None).to_json()
        if "pr" in best_extras:
            charts["pr"] = vu.pr_curve_fig(best_extras["pr"]["precision"], best_extras["pr"]["recall"]).to_json()
    else:
        charts["leaderboard"] = vu.leaderboard_bar(pd.DataFrame(leaderboard), "R2").to_json()
        if "y_true" in best_extras:
            charts["actual_vs_predicted"] = vu.actual_vs_predicted(best_extras["y_true"], best_extras["y_pred"]).to_json()
        if "residuals" in best_extras:
            charts["residuals"] = vu.residual_plot(best_extras["y_pred"], best_extras["residuals"]).to_json()

    fi = mu.get_feature_importance(best_obj, feature_cols) if best_obj is not None else None
    charts["feature_importance"] = vu.feature_importance_fig(fi).to_json()

    show_feedback_modal = not getattr(current_user, "has_submitted_feedback", False)

    return render_template(
        "results.html",
        leaderboard=leaderboard,
        task=task,
        best_model=best_model,
        best_row=best_row,
        charts=charts,
        state=state,
        overall_score=overall_score,
        current_project=project,
        show_feedback_modal=show_feedback_modal
    )

@app.route("/predict", methods=["GET", "POST"])
@login_required
def predict():
    project, df = require_project()
    if not project:
        flash("Please create a project workspace first.", "info")
        return redirect(url_for("new_project"))
    if df is None:
        flash("Please upload a dataset first.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])
    state = du.load_state(project_dir)
    if "best_model" not in state:
        flash("Train a model first.", "warning")
        return redirect(url_for("train"))

    feature_cols = state.get("feature_columns", [])
    prediction = None
    batch_download = None

    if request.method == "POST":
        model_path = os.path.join(project_dir, "best_model.pkl")
        bundle = mu.load_model_bundle(model_path)
        model = bundle["model"]

        if "single_submit" in request.form:
            row = {}
            for col in feature_cols:
                val = request.form.get(col, "0")
                try:
                    row[col] = float(val)
                except ValueError:
                    row[col] = 0.0
            X = pd.DataFrame([row])[feature_cols]
            pred = model.predict(X)[0]
            prediction = pred
        elif "batch_file" in request.files:
            file = request.files["batch_file"]
            if file and file.filename:
                batch_df = du.read_uploaded_file(file)
                X = batch_df.reindex(columns=feature_cols, fill_value=0)
                X = X.apply(pd.to_numeric, errors="coerce").fillna(0)
                preds = model.predict(X)
                batch_df["prediction"] = preds
                out_path = os.path.join(project_dir, "predictions.csv")
                batch_df.to_csv(out_path, index=False)
                batch_download = True
                flash(f"Batch prediction complete for {len(batch_df)} rows.", "success")

    return render_template("predict.html", feature_columns=feature_cols,
                            prediction=prediction, batch_download=batch_download,
                            task=state.get("task"), state=state, current_project=project)

@app.route("/download/<what>")
@login_required
def download(what):
    project, df = require_project()
    if df is None:
        flash("No dataset in session.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])

    files = {
        "model": ("best_model.pkl", "application/octet-stream"),
        "predictions": ("predictions.csv", "text/csv"),
    }
    if what == "metrics":
        state = du.load_state(project_dir)
        lb = pd.DataFrame(state.get("leaderboard", []))
        buf = io.BytesIO()
        buf.write(lb.to_csv(index=False).encode())
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name="metrics.csv", mimetype="text/csv")
    if what == "feature_list":
        state = du.load_state(project_dir)
        buf = io.BytesIO(json.dumps(state.get("feature_columns", []), indent=2).encode())
        return send_file(buf, as_attachment=True, download_name="feature_list.json", mimetype="application/json")
    if what == "requirements":
        reqs = ("flask\nflask-pymongo\nflask-login\nauthlib\nbcrypt\npython-dotenv\npandas\nnumpy\nscikit-learn\nxgboost\nlightgbm\njoblib\nplotly\nreportlab\nopenpyxl\n")
        buf = io.BytesIO(reqs.encode())
        return send_file(buf, as_attachment=True, download_name="requirements.txt", mimetype="text/plain")

    if what in files:
        fname, mime = files[what]
        path = os.path.join(project_dir, fname)
        if not os.path.exists(path):
            flash("File not available yet.", "warning")
            return redirect(url_for("results"))
        return send_file(path, as_attachment=True, download_name=fname, mimetype=mime)

    flash("Unknown file requested.", "danger")
    return redirect(url_for("results"))

@app.route("/api/v1/predict", methods=["POST"])
@login_required
def api_v1_predict():
    try:
        project, df = require_project()
        if not project:
            return jsonify({"error": "No project active"}), 400
        project_dir = get_project_dir(current_user.id, project["_id"])
        state = du.load_state(project_dir)

        if "best_model" not in state:
            return jsonify({"error": "No trained model found. Please train a model first."}), 400

        model_path = os.path.join(project_dir, "best_model.pkl")
        if not os.path.exists(model_path):
            return jsonify({"error": "Model bundle file missing."}), 404

        bundle = mu.load_model_bundle(model_path)
        model = bundle["model"]
        feature_cols = state.get("feature_columns", [])
        task = state.get("task", "classification")

        data = request.get_json(silent=True) or request.form.to_dict()
        if data and "inputs" in data and isinstance(data["inputs"], dict):
            inputs = data["inputs"]
        elif data:
            inputs = data
        else:
            inputs = {}

        row = {}
        for col in feature_cols:
            val = inputs.get(col, 0)
            try:
                row[col] = float(val)
            except (ValueError, TypeError):
                row[col] = 0.0

        X = pd.DataFrame([row])[feature_cols]

        raw_pred = model.predict(X)[0]
        if hasattr(raw_pred, "item"):
            prediction_val = raw_pred.item()
        else:
            prediction_val = raw_pred

        probabilities = None
        if task == "classification" and hasattr(model, "predict_proba"):
            try:
                probs = model.predict_proba(X)[0]
                labels = state.get("class_labels")
                if labels and len(labels) == len(probs):
                    probabilities = {str(k): round(float(v), 4) for k, v in zip(labels, probs)}
                else:
                    probabilities = {f"Class {i}": round(float(v), 4) for i, v in enumerate(probs)}
            except Exception:
                probabilities = None

        return jsonify({
            "success": True,
            "prediction": prediction_val,
            "probabilities": probabilities,
            "task": task,
            "model_name": state.get("best_model", "Best Model"),
            "target": state.get("target")
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Prediction failed: {str(e)}"}), 500


@app.route("/api/quick_train", methods=["POST"])
@login_required
def api_quick_train():
    try:
        project, df = require_project()
        if not project or df is None:
            return jsonify({"error": "No project or dataset active. Please upload a dataset first."}), 400

        project_dir = get_project_dir(current_user.id, project["_id"])
        state = du.load_state(project_dir)

        target = request.form.get("target") or (request.json.get("target") if (request.is_json and request.json) else None)
        if not target or target not in df.columns:
            return jsonify({"error": f"Valid target column selection is required (received '{target}')."}), 400

        split_val = request.form.get("split", 0.2) if not request.is_json else request.json.get("split", 0.2)
        try:
            split = float(split_val)
        except (ValueError, TypeError):
            split = 0.2

        work_df = df.copy()
        task = mu.detect_task_type(work_df[target])

        feature_df = work_df.drop(columns=[target])
        cat_cols = du.column_types(feature_df)["categorical"] + du.column_types(feature_df)["datetime"]
        for c in cat_cols:
            feature_df = du.encode_column(feature_df, c, "onehot" if feature_df[c].nunique() <= 15 else "label")

        feature_df = feature_df.select_dtypes(include=[np.number, "bool"])
        feature_df = feature_df.fillna(feature_df.median(numeric_only=True))

        y = work_df[target]
        if task == "classification" and not pd.api.types.is_numeric_dtype(y):
            from sklearn.preprocessing import LabelEncoder
            le = LabelEncoder()
            y = pd.Series(le.fit_transform(y.astype(str)), index=y.index)
            class_labels = le.classes_.tolist()
        else:
            class_labels = sorted(y.dropna().unique().tolist()) if task == "classification" else None

        combined = pd.concat([feature_df, y.rename("__target__")], axis=1).dropna()
        feature_df = combined.drop(columns="__target__")
        y = combined["__target__"]

        X_train, X_test, y_train, y_test = mu.train_test_split_data(
            feature_df, y, test_size=split, shuffle=True,
            stratify_flag=False, task=task
        )

        lb_df, fitted, extras, best_name = mu.run_automl(X_train, X_test, y_train, y_test, task, model_names=None)

        du.save_df(project_dir, feature_df, name="feature_df.pkl")
        du.save_df(project_dir, X_test, name="X_test.pkl")
        du.save_df(project_dir, y_test, name="y_test.pkl")

        import pickle
        with open(os.path.join(project_dir, "fitted_models.pkl"), "wb") as f:
            pickle.dump(fitted, f)
        with open(os.path.join(project_dir, "extras.pkl"), "wb") as f:
            pickle.dump(extras, f)

        state["target"] = target
        state["task"] = task
        state["class_labels"] = class_labels
        state["feature_columns"] = feature_df.columns.tolist()
        state["leaderboard"] = lb_df.to_dict(orient="records")
        state["best_model"] = best_name
        state["deployed"] = True
        du.save_state(project_dir, state)
        update_project_state(project["_id"], state)

        if best_name:
            best_model_obj = fitted[best_name]
            model_path = os.path.join(project_dir, "best_model.pkl")
            mu.save_model_bundle(model_path, best_model_obj, feature_df.columns.tolist(), target, task)

        return jsonify({
            "success": True,
            "best_model": best_name,
            "task": task,
            "leaderboard": state["leaderboard"],
            "feature_columns": feature_df.columns.tolist(),
            "message": f"AutoML training complete! '{best_name}' model auto-deployed successfully."
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Quick training failed: {str(e)}"}), 500

@app.route("/report")
@login_required
def report():
    project, df = require_project()
    if df is None:
        flash("Please upload a dataset first.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])
    state = du.load_state(project_dir)
    if "leaderboard" not in state:
        flash("Train a model first to include performance in the report.", "warning")
        return redirect(url_for("train"))

    profile = state.get("profile") or du.profile_dataset(df)
    ai = state.get("ai") or du.ai_recommendations(df, profile)
    leaderboard = state.get("leaderboard", [])
    best_model = state.get("best_model")
    best_row = next((r for r in leaderboard if r.get("Model") == best_model), {})

    ctx = {
        "project_name": project.get("name", "AutoML Studio Report"),
        "dataset_name": state.get("file_info", {}).get("filename", "dataset"),
        "target_column": state.get("target"),
        "task": state.get("task"),
        "health_score": profile.get("health_score"),
        "profile": profile,
        "recommendations": ai.get("recommendations", []),
        "warnings": ai.get("warnings", []),
        "leaderboard": leaderboard,
        "best_model": best_model,
        "best_metrics": best_row,
    }
    ctx["conclusion"] = ru.generate_conclusion(ctx)

    out_path = os.path.join(project_dir, "report.pdf")
    ru.build_report(out_path, ctx)
    return send_file(out_path, as_attachment=True, download_name=f"AutoML_Report_{project.get('name', 'project')}.pdf", mimetype="application/pdf")

@app.route("/deploy")
@login_required
def deploy():
    project, df = require_project()
    if not project:
        flash("Please create a project workspace first.", "info")
        return redirect(url_for("new_project"))
    if df is None:
        flash("Please upload a dataset first.", "warning")
        return redirect(url_for("upload_page"))
    project_dir = get_project_dir(current_user.id, project["_id"])
    state = du.load_state(project_dir)
    feature_cols = state.get("feature_columns", [])
    target = state.get("target", "target")
    snippet = f'''import joblib
import pandas as pd
from flask import Flask, request, jsonify

app = Flask(__name__)
bundle = joblib.load("model.pkl")
model = bundle["model"]
FEATURE_COLUMNS = {feature_cols}

@app.route("/predict", methods=["POST"])
def predict():
    payload = request.get_json()
    X = pd.DataFrame([payload]).reindex(columns=FEATURE_COLUMNS, fill_value=0)
    pred = model.predict(X)[0]
    return jsonify({{"prediction": pred if not hasattr(pred, "item") else pred.item()}})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
'''
    return render_template("deploy.html", snippet=snippet, feature_cols=feature_cols, target=target, state=state, current_project=project)

@app.route("/code")
@login_required
def code():
    project = get_current_project()
    project_dir = get_project_dir(current_user.id, project["_id"]) if project else None
    state = du.load_state(project_dir) if project_dir else {}
    default_code = '''# Welcome to AutoML Code Playground!
# You have access to:
# - pandas as pd
# - numpy as np
# - Your active dataset as 'df'
# - All utils modules (du, mu, vu, ru, au)

import pandas as pd
import numpy as np

print("Hello from AutoML SaaS Platform!")
if df is not None:
    print(f"Active dataset shape: {df.shape[0]} rows, {df.shape[1]} columns")
    print("\nDataset Summary Head:")
    print(df.head())
else:
    print("No dataset uploaded yet — navigate to Upload step.")
'''
    return render_template("code.html", state=state, default_code=default_code, current_project=project)

@app.route("/api/execute", methods=["POST"])
@login_required
def execute_code():
    project = get_current_project()
    project_dir = get_project_dir(current_user.id, project["_id"]) if project else None
    data = request.json
    code = data.get("code", "")
    try:
        df = du.load_df(project_dir) if project_dir else None
        exec_globals = {
            "pd": pd,
            "np": np,
            "df": df,
            "du": du,
            "mu": mu,
            "vu": vu,
            "ru": ru,
            "au": au,
        }
        output_buffer = io.StringIO()
        import sys
        old_stdout = sys.stdout
        sys.stdout = output_buffer
        
        exec(code, exec_globals)
        
        sys.stdout = old_stdout
        output = output_buffer.getvalue()
        if not output:
            output = "Code executed successfully (no stdout produced)"
        return jsonify({"success": True, "output": output})
    except Exception as e:
        import sys
        sys.stdout = old_stdout
        return jsonify({"success": False, "output": f"Error: {str(e)}\n{traceback.format_exc()}"})

@app.route("/analytics")
@login_required
def analytics():
    project = get_current_project()
    analytics_data = get_user_analytics_data(current_user.id)
    
    charts = {}
    charts["algo_pie"] = vu.user_algorithm_pie(analytics_data["algo_counts"]).to_json()
    charts["task_donut"] = vu.user_task_donut(analytics_data["task_counts"]).to_json()
    charts["score_timeline"] = vu.user_score_history_line(analytics_data["score_timeline"]).to_json()
    charts["score_range"] = vu.user_score_range_bar(
        analytics_data["stats"]["min_score"],
        analytics_data["stats"]["avg_score"],
        analytics_data["stats"]["max_score"]
    ).to_json()

    return render_template(
        "analytics.html",
        data=analytics_data,
        charts=charts,
        current_project=project
    )

@app.route("/api/feedback", methods=["POST"])
@login_required
def submit_feedback():
    try:
        data = request.get_json(silent=True) or request.form.to_dict()
        rating = int(data.get("rating", 5))
        category = data.get("category", "General Experience")
        comment = data.get("comment", "").strip()
        project_id = session.get("project_id")

        feedback_doc = {
            "user_id": current_user.id,
            "user_name": current_user.name,
            "user_email": current_user.email,
            "rating": rating,
            "category": category,
            "comment": comment,
            "project_id": project_id,
            "timestamp": datetime.utcnow()
        }
        db.feedbacks.insert_one(feedback_doc)
        db.users.update_one({"_id": current_user.id}, {"$set": {"has_submitted_feedback": True}})
        log_user_activity(current_user.id, project_id, "feedback", f"Submitted {rating}-star model training feedback", metadata={"rating": rating, "category": category})

        return jsonify({"success": True, "message": "Thank you for your valuable feedback!"})
    except Exception as e:
        return jsonify({"error": f"Failed to record feedback: {str(e)}"}), 500

@app.route("/support", methods=["GET", "POST"])
@login_required
def support():
    project = get_current_project()
    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        category = request.form.get("category", "General Question")
        message = request.form.get("message", "").strip()

        if not subject or not message:
            flash("Please enter both subject and message details.", "warning")
            return redirect(url_for("support"))

        msg_doc = {
            "user_id": current_user.id,
            "user_name": current_user.name,
            "user_email": current_user.email,
            "subject": subject,
            "category": category,
            "message": message,
            "status": "unread",
            "timestamp": datetime.utcnow()
        }
        db.messages.insert_one(msg_doc)
        log_user_activity(current_user.id, session.get("project_id"), "support", f"Sent support ticket to admin: '{subject}'")

        flash("Your message has been sent to the Admin! We will review it shortly.", "success")
        return redirect(url_for("support"))

    user_messages = list(db.messages.find({"user_id": current_user.id}).sort("timestamp", -1))
    return render_template("support.html", messages=user_messages, current_project=project)

@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    all_users = list(db.users.find().sort("created_at", -1))
    all_projects = list(db.projects.find().sort("updated_at", -1))
    all_feedbacks = list(db.feedbacks.find().sort("timestamp", -1))
    all_messages = list(db.messages.find().sort("timestamp", -1))
    all_activities = list(db.activities.find().sort("timestamp", -1).limit(100))

    user_stats = []
    total_models_all = 0
    for u in all_users:
        uid = str(u["_id"])
        u_projects = [p for p in all_projects if p.get("user_id") == uid]
        models_count = 0
        for p in u_projects:
            pdir = os.path.join(DATA_DIR, uid, p["_id"])
            p_state = du.load_state(pdir) if os.path.exists(pdir) else p.get("state", {})
            models_count += len(p_state.get("leaderboard", []))
        
        total_models_all += models_count
        user_stats.append({
            "user_id": uid,
            "name": u.get("name", "User"),
            "email": u.get("email", ""),
            "provider": u.get("provider", "local"),
            "created_at": u.get("created_at"),
            "projects_count": len(u_projects),
            "models_count": models_count
        })

    unread_messages = sum(1 for m in all_messages if m.get("status") == "unread")

    kpis = {
        "total_users": len(all_users),
        "total_projects": len(all_projects),
        "total_models": total_models_all,
        "total_feedbacks": len(all_feedbacks),
        "unread_messages": unread_messages
    }

    return render_template(
        "admin.html",
        kpis=kpis,
        users=user_stats,
        feedbacks=all_feedbacks,
        messages=all_messages,
        activities=all_activities,
        current_project=get_current_project()
    )

@app.route("/admin/message/<msg_id>/<action>", methods=["POST", "GET"])
@login_required
@admin_required
def admin_message_action(msg_id, action):
    from bson.objectid import ObjectId
    try:
        query = {"_id": ObjectId(msg_id)} if len(str(msg_id)) == 24 else {"_id": msg_id}
    except Exception:
        query = {"_id": msg_id}

    if action == "read":
        db.messages.update_one(query, {"$set": {"status": "read"}})
        flash("Support message marked as read.", "success")
    elif action == "resolve":
        db.messages.update_one(query, {"$set": {"status": "resolved"}})
        flash("Support message marked as resolved.", "success")
    elif action == "delete":
        db.messages.delete_one(query)
        flash("Support message deleted.", "info")

    return redirect(url_for("admin_dashboard"))

@app.route("/reset")
@login_required
def reset():
    session.pop("project_id", None)
    flash("Session reset. Select or create a project to continue.", "info")
    return redirect(url_for("index"))

if __name__ == "__main__":
    import sys
    print("="*50, file=sys.stderr)
    print("Starting ModelFlow Enterprise AI Platform...", file=sys.stderr)
    print("Host: 0.0.0.0, Port: 5050", file=sys.stderr)
    print("="*50, file=sys.stderr)
    sys.stderr.flush()
    
    try:
        app.run(debug=False, host="0.0.0.0", port=5050)
    except Exception as e:
        print(f"ERROR in app.run(): {str(e)}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)
        sys.exit(1)
