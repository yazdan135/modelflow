"""
ModelFlow Dev v2.0-LR — Data Models & Storage Architecture
Enterprise Machine Learning Development Platform Core Models
"""

import os
import json
import time
import uuid
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user_data", "v2_workspace")
os.makedirs(DATA_DIR, exist_ok=True)

STORE_FILE = os.path.join(DATA_DIR, "v2_store.json")


def generate_uuid(prefix=""):
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def get_default_store():
    ws_id = "ws_default_01"
    proj_1 = "proj_churn_analytics"
    proj_2 = "proj_fraud_detection"

    return {
        "workspaces": {
            ws_id: {
                "id": ws_id,
                "name": "Acme AI Engineering Corp",
                "plan": "Enterprise Scale",
                "version": "v2.0-LR",
                "created_at": "2026-08-01 10:00:00",
                "members": [
                    {"id": "usr_01", "name": "Yazdan Khan", "email": "yazdan@acme.ai", "role": "Owner", "avatar": "YK"},
                    {"id": "usr_02", "name": "Sarah Chen", "email": "sarah.chen@acme.ai", "role": "Admin", "avatar": "SC"},
                    {"id": "usr_03", "name": "Alex Rivera", "email": "alex.r@acme.ai", "role": "ML Engineer", "avatar": "AR"},
                    {"id": "usr_04", "name": "Elena Rostova", "email": "elena@acme.ai", "role": "Data Analyst", "avatar": "ER"},
                    {"id": "usr_05", "name": "David Miller", "email": "david.m@acme.ai", "role": "Viewer", "avatar": "DM"},
                    {"id": "usr_06", "name": "Rachel Green", "email": "rachel@acme.ai", "role": "Billing Manager", "avatar": "RG"}
                ],
                "api_keys": [
                    {"id": "key_01", "name": "Production Deploy Key", "prefix": "mf_live_98a7...", "created": "2026-08-01", "status": "Active"},
                    {"id": "key_02", "name": "CI/CD Pipeline Key", "prefix": "mf_test_41b2...", "created": "2026-08-02", "status": "Active"}
                ],
                "activities": [
                    {"timestamp": "10 mins ago", "user": "Alex Rivera", "action": "Promoted model v2.1 to Production in Customer Churn Predictor"},
                    {"timestamp": "45 mins ago", "user": "Sarah Chen", "action": "Created Dataset Version v1.2 (Cleaned Telecom Features)"},
                    {"timestamp": "2 hours ago", "user": "Yazdan Khan", "action": "Logged Experiment run #48 (XGBoost Hyperparameter Tuning)"}
                ]
            }
        },
        "projects": {
            proj_1: {
                "id": proj_1,
                "workspace_id": ws_id,
                "name": "Customer Churn Predictor",
                "slug": "customer-churn-predictor",
                "description": "Enterprise customer retention model predicting subscription churn with 94.2% ROC-AUC.",
                "tags": ["Classification", "Customer Success", "Production"],
                "created_at": "2026-08-01 11:30:00",
                "owner": "Yazdan Khan"
            },
            proj_2: {
                "id": proj_2,
                "workspace_id": ws_id,
                "name": "Financial Fraud Detector",
                "slug": "financial-fraud-detector",
                "description": "Real-time transaction anomaly detection pipeline trained on credit card event streams.",
                "tags": ["Anomaly Detection", "Finance", "High Throughput"],
                "created_at": "2026-08-02 09:15:00",
                "owner": "Alex Rivera"
            }
        },
        "datasets": {
            "ds_churn_v1": {
                "id": "ds_churn_v1",
                "project_id": proj_1,
                "name": "Telecom Customer Churn Master",
                "source": "CSV Upload",
                "owner": "Sarah Chen",
                "tags": ["Behavioral", "Cleaned"],
                "current_version": "v1.2",
                "created_at": "2026-08-01 12:00:00",
                "versions": [
                    {
                        "version": "v1.0",
                        "records": 7043,
                        "columns": 21,
                        "size": "1.4 MB",
                        "created_at": "2026-08-01 12:00:00",
                        "quality_score": "88%",
                        "changes": "Initial raw dataset ingestion from database dump."
                    },
                    {
                        "version": "v1.2",
                        "records": 7043,
                        "columns": 24,
                        "size": "1.6 MB",
                        "created_at": "2026-08-02 10:30:00",
                        "quality_score": "98%",
                        "changes": "Imputed missing TotalCharges, encoded Contract tenure, added SMOTE balance."
                    }
                ],
                "schema": [
                    {"column": "customerID", "type": "Categorical", "missing": 0, "sample": "7590-VHVEG"},
                    {"column": "tenure", "type": "Numeric", "missing": 0, "sample": "1"},
                    {"column": "MonthlyCharges", "type": "Numeric", "missing": 0, "sample": "29.85"},
                    {"column": "TotalCharges", "type": "Numeric", "missing": 0, "sample": "29.85"},
                    {"column": "Churn", "type": "Target (Binary)", "missing": 0, "sample": "No"}
                ]
            }
        },
        "experiments": {
            "exp_run_01": {
                "id": "exp_run_01",
                "project_id": proj_1,
                "name": "XGBoost Hyperparameter Sweep #48",
                "dataset_version": "v1.2",
                "algorithm": "XGBoost Classifier",
                "problem_type": "Binary Classification",
                "status": "COMPLETED",
                "created_at": "2026-08-02 14:20:00",
                "duration": "42.8s",
                "metrics": {"accuracy": 0.924, "precision": 0.912, "recall": 0.905, "f1_score": 0.908, "roc_auc": 0.942},
                "hyperparams": {"n_estimators": 250, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.8},
                "artifacts": ["model.pkl", "feature_importance.json", "confusion_matrix.png"]
            },
            "exp_run_02": {
                "id": "exp_run_02",
                "project_id": proj_1,
                "name": "LightGBM Gradient Boosting #47",
                "dataset_version": "v1.2",
                "algorithm": "LightGBM Classifier",
                "problem_type": "Binary Classification",
                "status": "COMPLETED",
                "created_at": "2026-08-02 13:10:00",
                "duration": "28.1s",
                "metrics": {"accuracy": 0.911, "precision": 0.898, "recall": 0.890, "f1_score": 0.894, "roc_auc": 0.928},
                "hyperparams": {"num_leaves": 31, "learning_rate": 0.08, "n_estimators": 200},
                "artifacts": ["model.pkl", "metrics.json"]
            }
        },
        "models": {
            "mod_churn_v2": {
                "id": "mod_churn_v2",
                "project_id": proj_1,
                "name": "Churn Predictor XGBoost",
                "version": "v2.1",
                "experiment_id": "exp_run_01",
                "approval_status": "APPROVED",
                "created_at": "2026-08-02 15:00:00",
                "metrics": {"accuracy": "92.4%", "f1_score": "90.8%", "roc_auc": "0.942"},
                "model_card": {
                    "intended_use": "Predict customer subscription churn probabilities for account management teams.",
                    "primary_features": ["Contract Type", "Tenure Months", "Monthly Charges", "Total Tickets"],
                    "bias_eval": "Evaluated across regional demographics with sub-2% variance."
                },
                "feature_importance": [
                    {"feature": "Contract_Month_to_Month", "importance": 0.34},
                    {"feature": "Tenure_Months", "importance": 0.28},
                    {"feature": "MonthlyCharges", "importance": 0.18},
                    {"feature": "TechSupport_No", "importance": 0.12},
                    {"feature": "TotalCharges", "importance": 0.08}
                ]
            }
        },
        "deployments": {
            "dep_churn_prod": {
                "id": "dep_churn_prod",
                "project_id": proj_1,
                "name": "Production Churn REST API",
                "environment": "PRODUCTION",
                "endpoint_url": "/api/v2/deployments/dep_churn_prod/predict",
                "active_model_id": "mod_churn_v2",
                "active_model_version": "v2.1",
                "auth_key": "mf_live_98ab76cd43",
                "rate_limit": "1000 Req/Min",
                "health_status": "HEALTHY",
                "created_at": "2026-08-02 15:30:00",
                "stats": {
                    "total_requests": 142850,
                    "avg_latency_ms": 18.4,
                    "error_rate": "0.02%",
                    "uptime": "99.99%"
                }
            }
        },
        "prediction_logs": [
            {
                "id": "log_101",
                "deployment_id": "dep_churn_prod",
                "project_id": proj_1,
                "model_version": "v2.1",
                "timestamp": "2026-08-03 16:15:22",
                "inputs": {"tenure": 3, "MonthlyCharges": 89.50, "Contract": "Month-to-month"},
                "prediction": "CHURN_LIKELY",
                "confidence": "87.4%",
                "latency_ms": 16.2,
                "status": "SUCCESS",
                "user": "API Key: mf_live_98a7..."
            },
            {
                "id": "log_102",
                "deployment_id": "dep_churn_prod",
                "project_id": proj_1,
                "model_version": "v2.1",
                "timestamp": "2026-08-03 16:18:05",
                "inputs": {"tenure": 48, "MonthlyCharges": 45.10, "Contract": "Two year"},
                "prediction": "RETAINED",
                "confidence": "96.1%",
                "latency_ms": 14.8,
                "status": "SUCCESS",
                "user": "API Key: mf_live_98a7..."
            }
        ],
        "knowledge_hub": [
            {
                "id": "kn_01",
                "project_id": proj_1,
                "title": "Architecture Decision: XGBoost vs Neural Net",
                "category": "Decisions",
                "author": "Yazdan Khan",
                "date": "2026-08-02",
                "content": "Selected XGBoost v2.1 due to superior tabular performance (+2.4% ROC-AUC over MLP) and sub-20ms inference latency constraint."
            },
            {
                "id": "kn_02",
                "project_id": proj_1,
                "title": "Dataset Imputation Strategy for TotalCharges",
                "category": "Notes",
                "author": "Sarah Chen",
                "date": "2026-08-01",
                "content": "Missing TotalCharges for zero-tenure accounts are imputed using tenure * MonthlyCharges product rule rather than global mean."
            }
        ],
        "files": [
            {"id": "fl_01", "project_id": proj_1, "name": "churn_training_v1.2.csv", "type": "Dataset", "size": "1.6 MB", "uploaded_at": "2026-08-02"},
            {"id": "fl_02", "project_id": proj_1, "name": "xgboost_model_v2.1.pkl", "type": "Model Weight", "size": "4.2 MB", "uploaded_at": "2026-08-02"},
            {"id": "fl_03", "project_id": proj_1, "name": "model_card_v2.1.pdf", "type": "Report", "size": "340 KB", "uploaded_at": "2026-08-02"}
        ]
    }


def load_store():
    if not os.path.exists(STORE_FILE):
        store = get_default_store()
        save_store(store)
        return store
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        store = get_default_store()
        save_store(store)
        return store


def save_store(store):
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
