"""
ML utilities: model zoo, train/test split, AutoML leaderboard,
metrics, feature importance, and prediction helpers.
"""
import time
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression, LinearRegression
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.svm import SVC, SVR
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.naive_bayes import GaussianNB
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    confusion_matrix, roc_curve, precision_recall_curve,
    mean_absolute_error, mean_squared_error, r2_score,
    mean_absolute_percentage_error,
)

try:
    from xgboost import XGBClassifier, XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    from lightgbm import LGBMClassifier, LGBMRegressor
    HAS_LGBM = True
except ImportError:
    HAS_LGBM = False


def detect_task_type(y):
    if pd.api.types.is_numeric_dtype(y) and y.nunique() > 20:
        return "regression"
    return "classification"


def get_model_zoo(task):
    zoo = {}
    if task == "classification":
        zoo["Logistic Regression"] = LogisticRegression(max_iter=2000)
        zoo["Decision Tree"] = DecisionTreeClassifier(random_state=42)
        zoo["Random Forest"] = RandomForestClassifier(n_estimators=200, random_state=42)
        zoo["KNN"] = KNeighborsClassifier()
        zoo["Naive Bayes"] = GaussianNB()
        zoo["SVM"] = SVC(probability=True)
        if HAS_XGB:
            zoo["XGBoost"] = XGBClassifier(eval_metric="logloss", random_state=42)
        if HAS_LGBM:
            zoo["LightGBM"] = LGBMClassifier(random_state=42, verbose=-1)
    else:
        zoo["Linear Regression"] = LinearRegression()
        zoo["Decision Tree"] = DecisionTreeRegressor(random_state=42)
        zoo["Random Forest"] = RandomForestRegressor(n_estimators=200, random_state=42)
        zoo["KNN"] = KNeighborsRegressor()
        zoo["SVR"] = SVR()
        if HAS_XGB:
            zoo["XGBoost"] = XGBRegressor(random_state=42)
        if HAS_LGBM:
            zoo["LightGBM"] = LGBMRegressor(random_state=42, verbose=-1)
    return zoo


def recommend_model(task, n_rows, n_features):
    """Simple heuristic 'AI model recommendation'."""
    if task == "classification":
        if n_rows < 2000:
            model, reason = "Random Forest", "Small dataset — Random Forest handles limited data robustly without heavy tuning."
        elif n_features > 50:
            model, reason = "LightGBM" if HAS_LGBM else "Random Forest", "Many features — gradient boosting handles high dimensionality efficiently."
        else:
            model, reason = "XGBoost" if HAS_XGB else "Random Forest", "Balanced dataset size — gradient boosting typically gives strong accuracy."
        expected = "78% - 92%"
    else:
        if n_rows < 2000:
            model, reason = "Random Forest", "Small dataset — tree ensembles generalize well without much tuning."
        else:
            model, reason = "XGBoost" if HAS_XGB else "Random Forest", "Larger dataset — gradient boosting usually minimizes error best."
        expected = "R² 0.65 - 0.90"
    confidence = round(min(95, 60 + max(0, 30 - n_features)), 1)
    return {
        "model": model,
        "confidence": confidence,
        "reason": reason,
        "expected_range": expected,
        "estimated_time_sec": round(max(1, n_rows * n_features / 50000), 1),
    }


def train_test_split_data(X, y, test_size=0.2, shuffle=True, random_state=42, stratify_flag=False, task="classification"):
    stratify = y if (stratify_flag and task == "classification" and y.nunique() > 1) else None
    return train_test_split(X, y, test_size=test_size, shuffle=shuffle, random_state=random_state, stratify=stratify)


def _safe_proba(model, X):
    try:
        proba = model.predict_proba(X)
        if proba.shape[1] == 2:
            return proba[:, 1]
        return proba
    except Exception:
        return None


def evaluate_classification(y_true, y_pred, y_proba=None):
    metrics = {
        "Accuracy": round(accuracy_score(y_true, y_pred), 4),
        "Precision": round(precision_score(y_true, y_pred, average="weighted", zero_division=0), 4),
        "Recall": round(recall_score(y_true, y_pred, average="weighted", zero_division=0), 4),
        "F1": round(f1_score(y_true, y_pred, average="weighted", zero_division=0), 4),
    }
    if y_proba is not None and len(np.unique(y_true)) == 2:
        try:
            metrics["ROC_AUC"] = round(roc_auc_score(y_true, y_proba), 4)
        except Exception:
            metrics["ROC_AUC"] = None
    else:
        metrics["ROC_AUC"] = None
    return metrics


def evaluate_regression(y_true, y_pred):
    return {
        "MAE": round(mean_absolute_error(y_true, y_pred), 4),
        "MSE": round(mean_squared_error(y_true, y_pred), 4),
        "RMSE": round(np.sqrt(mean_squared_error(y_true, y_pred)), 4),
        "R2": round(r2_score(y_true, y_pred), 4),
        "MAPE": round(mean_absolute_percentage_error(y_true, y_pred) * 100, 4) if (y_true != 0).all() else None,
    }


def run_automl(X_train, X_test, y_train, y_test, task, model_names=None, progress_callback=None):
    """Train selected (or all) models, return leaderboard + fitted models + curves."""
    zoo = get_model_zoo(task)
    if model_names:
        zoo = {k: v for k, v in zoo.items() if k in model_names}

    leaderboard = []
    fitted = {}
    extras = {}
    total_models = len(zoo)

    for idx, (name, model) in enumerate(zoo.items(), 1):
        if progress_callback:
            progress_callback({
                "stage": "train_start",
                "model": name,
                "index": idx,
                "total": total_models
            })
        start = time.time()
        try:
            model.fit(X_train, y_train)
        except Exception as e:
            leaderboard.append({"Model": name, "Error": str(e)})
            if progress_callback:
                progress_callback({
                    "stage": "train_error",
                    "model": name,
                    "index": idx,
                    "total": total_models,
                    "error": str(e)
                })
            continue
        elapsed = round(time.time() - start, 3)

        if progress_callback:
            progress_callback({
                "stage": "evaluating",
                "model": name,
                "index": idx,
                "total": total_models
            })

        y_pred = model.predict(X_test)

        row = {"Model": name, "Training_Time_sec": elapsed}
        if task == "classification":
            proba = _safe_proba(model, X_test)
            metrics = evaluate_classification(y_test, y_pred, proba)
            row.update(metrics)
            cm = confusion_matrix(y_test, y_pred).tolist()
            extras[name] = {"confusion_matrix": cm}
            if proba is not None and len(np.unique(y_test)) == 2:
                fpr, tpr, _ = roc_curve(y_test, proba)
                prec, rec, _ = precision_recall_curve(y_test, proba)
                extras[name]["roc"] = {"fpr": fpr.tolist(), "tpr": tpr.tolist()}
                extras[name]["pr"] = {"precision": prec.tolist(), "recall": rec.tolist()}
        else:
            metrics = evaluate_regression(y_test, y_pred)
            row.update(metrics)
            extras[name] = {
                "y_true": np.asarray(y_test).tolist(),
                "y_pred": np.asarray(y_pred).tolist(),
                "residuals": (np.asarray(y_test) - np.asarray(y_pred)).tolist(),
            }

        leaderboard.append(row)
        fitted[name] = model

        if progress_callback:
            metric_str = f"Accuracy: {metrics.get('Accuracy') * 100:.1f}%" if (task == "classification" and metrics.get('Accuracy') is not None) else (f"R²: {metrics.get('R2')}" if metrics.get('R2') is not None else "Complete")
            progress_callback({
                "stage": "train_complete",
                "model": name,
                "index": idx,
                "total": total_models,
                "metrics": metrics,
                "summary": metric_str
            })

    lb_df = pd.DataFrame(leaderboard)
    if task == "classification" and "Accuracy" in lb_df.columns:
        lb_df = lb_df.sort_values("Accuracy", ascending=False)
    elif "R2" in lb_df.columns:
        lb_df = lb_df.sort_values("R2", ascending=False)

    best_model_name = lb_df.iloc[0]["Model"] if len(lb_df) else None
    return lb_df, fitted, extras, best_model_name


def run_automl_stream(X_train, X_test, y_train, y_test, task, model_names=None):
    """Generator yielding step events during training, finishing with final result dict."""
    zoo = get_model_zoo(task)
    if model_names:
        zoo = {k: v for k, v in zoo.items() if k in model_names}

    leaderboard = []
    fitted = {}
    extras = {}
    total_models = len(zoo)

    for idx, (name, model) in enumerate(zoo.items(), 1):
        yield {
            "stage": "train_start",
            "model": name,
            "index": idx,
            "total": total_models
        }
        start = time.time()
        try:
            model.fit(X_train, y_train)
        except Exception as e:
            leaderboard.append({"Model": name, "Error": str(e)})
            yield {
                "stage": "train_error",
                "model": name,
                "index": idx,
                "total": total_models,
                "error": str(e)
            }
            continue
        elapsed = round(time.time() - start, 3)

        yield {
            "stage": "evaluating",
            "model": name,
            "index": idx,
            "total": total_models
        }

        y_pred = model.predict(X_test)
        row = {"Model": name, "Training_Time_sec": elapsed}

        if task == "classification":
            proba = _safe_proba(model, X_test)
            metrics = evaluate_classification(y_test, y_pred, proba)
            row.update(metrics)
            cm = confusion_matrix(y_test, y_pred).tolist()
            extras[name] = {"confusion_matrix": cm}
            if proba is not None and len(np.unique(y_test)) == 2:
                fpr, tpr, _ = roc_curve(y_test, proba)
                prec, rec, _ = precision_recall_curve(y_test, proba)
                extras[name]["roc"] = {"fpr": fpr.tolist(), "tpr": tpr.tolist()}
                extras[name]["pr"] = {"precision": prec.tolist(), "recall": rec.tolist()}
        else:
            metrics = evaluate_regression(y_test, y_pred)
            row.update(metrics)
            extras[name] = {
                "y_true": np.asarray(y_test).tolist(),
                "y_pred": np.asarray(y_pred).tolist(),
                "residuals": (np.asarray(y_test) - np.asarray(y_pred)).tolist(),
            }

        leaderboard.append(row)
        fitted[name] = model

        metric_str = f"Accuracy: {metrics.get('Accuracy') * 100:.1f}%" if (task == "classification" and metrics.get('Accuracy') is not None) else (f"R²: {metrics.get('R2')}" if metrics.get('R2') is not None else "Complete")
        yield {
            "stage": "train_complete",
            "model": name,
            "index": idx,
            "total": total_models,
            "metrics": metrics,
            "summary": metric_str
        }

    lb_df = pd.DataFrame(leaderboard)
    if task == "classification" and "Accuracy" in lb_df.columns:
        lb_df = lb_df.sort_values("Accuracy", ascending=False)
    elif "R2" in lb_df.columns:
        lb_df = lb_df.sort_values("R2", ascending=False)

    best_model_name = lb_df.iloc[0]["Model"] if len(lb_df) else None
    yield {
        "stage": "result",
        "lb_df": lb_df,
        "fitted": fitted,
        "extras": extras,
        "best_model_name": best_model_name
    }


def get_feature_importance(model, feature_names):
    importance = None
    if hasattr(model, "feature_importances_"):
        importance = model.feature_importances_
    elif hasattr(model, "coef_"):
        coef = model.coef_
        importance = np.abs(coef[0]) if coef.ndim > 1 else np.abs(coef)
    if importance is None:
        return None
    pairs = sorted(zip(feature_names, importance), key=lambda x: x[1], reverse=True)
    return pairs[:20]


def save_model_bundle(path, model, feature_columns, target_column, task, scaler=None, encoders=None):
    bundle = {
        "model": model,
        "feature_columns": feature_columns,
        "target_column": target_column,
        "task": task,
        "scaler": scaler,
        "encoders": encoders or {},
    }
    joblib.dump(bundle, path)


def load_model_bundle(path):
    return joblib.load(path)
