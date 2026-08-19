"""
Data handling utilities: upload parsing, profiling, dataset health score,
AI-style rule recommendations, cleaning operations (missing values, duplicates,
outliers, encoding, scaling, date/text parsing), snapshots, undo & reset capabilities.
"""
import os
import json
import pickle
import uuid
import chardet
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer, KNNImputer
from sklearn.preprocessing import (
    LabelEncoder, OneHotEncoder, OrdinalEncoder,
    StandardScaler, MinMaxScaler, RobustScaler
)
from datetime import datetime

def _project_path(project_dir):
    os.makedirs(project_dir, exist_ok=True)
    return project_dir


def save_df(project_dir, df, name="df.pkl"):
    with open(os.path.join(_project_path(project_dir), name), "wb") as f:
        pickle.dump(df, f)


def load_df(project_dir, name="df.pkl"):
    path = os.path.join(_project_path(project_dir), name)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def save_state(project_dir, state):
    with open(os.path.join(_project_path(project_dir), "state.json"), "w") as f:
        json.dump(state, f, default=str)


def load_state(project_dir):
    path = os.path.join(_project_path(project_dir), "state.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def detect_encoding(file_bytes):
    try:
        result = chardet.detect(file_bytes[:100000])
        return result.get("encoding") or "utf-8"
    except Exception:
        return "utf-8"


def read_uploaded_file(file_storage):
    """Parse an uploaded CSV, Excel, or TSV FileStorage into a DataFrame safely."""
    filename = file_storage.filename
    ext = filename.rsplit(".", 1)[-1].lower()

    if ext in ("xlsx", "xls"):
        df = pd.read_excel(file_storage)
    else:
        raw = file_storage.read()
        encoding = detect_encoding(raw)
        try:
            sample = raw[:5000].decode(encoding, errors="ignore")
        except Exception:
            sample = raw[:5000].decode("utf-8", errors="ignore")

        delimiter = ","
        for cand in [",", ";", "\t", "|"]:
            if sample.count(cand) > sample.count(delimiter):
                delimiter = cand
        from io import BytesIO
        try:
            df = pd.read_csv(BytesIO(raw), encoding=encoding, sep=delimiter)
        except Exception:
            df = pd.read_csv(BytesIO(raw), encoding="latin1", sep=delimiter)

    # Clean column names (strip whitespace and unprintable characters)
    df.columns = [str(c).strip() for c in df.columns]
    return df


def basic_file_info(df, filename):
    mem_bytes = df.memory_usage(deep=True).sum()
    mem_formatted = f"{mem_bytes / (1024*1024):.2f} MB" if mem_bytes > 1024*1024 else f"{mem_bytes / 1024:.1f} KB"
    return {
        "filename": filename,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "memory_usage": mem_formatted,
        "memory_kb": round(mem_bytes / 1024, 2),
    }


def column_types(df):
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    bool_cols = df.select_dtypes(include=["bool"]).columns.tolist()
    numeric = [c for c in numeric if c not in bool_cols]
    datetime_cols = []
    categorical = []
    
    for c in df.columns:
        if c in numeric or c in bool_cols:
            continue
        try:
            is_dt = np.issubdtype(df[c].dtype, np.datetime64)
        except TypeError:
            is_dt = False
        if is_dt:
            datetime_cols.append(c)
            continue
        # Sniff date strings
        if df[c].dtype == object or pd.api.types.is_string_dtype(df[c]):
            sample = df[c].dropna().astype(str).head(20)
            if len(sample) > 0:
                parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
                if parsed.notna().mean() >= 0.75:
                    datetime_cols.append(c)
                    continue
        categorical.append(c)
        
    return {
        "numeric": numeric,
        "categorical": categorical,
        "boolean": bool_cols,
        "datetime": datetime_cols,
    }


def count_outliers(df, column, method="iqr"):
    """Count outliers in a numeric column using specified method"""
    if column not in df.columns or not pd.api.types.is_numeric_dtype(df[column]):
        return 0
    s = df[column].dropna()
    if len(s) < 5:
        return 0
    if method == "iqr":
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0:
            return 0
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        return int(((s < lower) | (s > upper)).sum())
    elif method == "zscore":
        std = s.std(ddof=0)
        if std == 0:
            return 0
        z = (s - s.mean()) / std
        return int((z.abs() > 3).sum())
    return 0


def dataset_health_score(df):
    """0-100 health score based on dataset quality metrics."""
    score = 100.0
    n_rows, n_cols = df.shape
    n_cells = n_rows * n_cols
    if n_cells == 0:
        return 0.0

    # Missing values penalty (up to -40)
    missing_ratio = df.isna().sum().sum() / n_cells
    score -= missing_ratio * 40.0

    # Duplicate rows penalty (up to -20)
    dup_ratio = df.duplicated().sum() / max(n_rows, 1)
    score -= dup_ratio * 20.0

    # Constant columns penalty (up to -15)
    const_cols = sum(df[c].nunique(dropna=False) <= 1 for c in df.columns)
    score -= (const_cols / max(n_cols, 1)) * 15.0

    # High cardinality text penalty (up to -15)
    obj_cols = df.select_dtypes(include="object").columns
    high_card = sum(df[c].nunique() > 0.9 * n_rows and n_rows > 20 for c in obj_cols)
    score -= (high_card / max(n_cols, 1)) * 15.0

    # Outlier penalty for numeric columns (up to -10)
    num_cols = df.select_dtypes(include=[np.number]).columns
    if len(num_cols) > 0:
        total_outliers = sum(count_outliers(df, c, "iqr") for c in num_cols)
        outlier_ratio = total_outliers / (n_rows * len(num_cols))
        score -= min(10.0, outlier_ratio * 50.0)

    return max(0.0, min(100.0, round(score, 1)))


def profile_dataset(df):
    types = column_types(df)
    numeric = types["numeric"]

    missing = df.isna().sum()
    missing_pct = (missing / len(df) * 100).round(2) if len(df) > 0 else missing

    desc = {}
    if numeric:
        desc = df[numeric].describe().round(3).to_dict()

    corr = {}
    if len(numeric) >= 2:
        corr_df = df[numeric].corr(numeric_only=True).round(3)
        corr = corr_df.to_dict()

    outlier_counts = {}
    for col in numeric:
        outlier_counts[col] = count_outliers(df, col, "iqr")

    profile = {
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "dtypes": {c: str(df[c].dtype) for c in df.columns},
        "missing_counts": {c: int(missing[c]) for c in df.columns},
        "missing_pct": {c: float(missing_pct[c]) for c in df.columns},
        "total_missing_cells": int(missing.sum()),
        "duplicate_rows": int(df.duplicated().sum()),
        "unique_counts": {c: int(df[c].nunique(dropna=True)) for c in df.columns},
        "outlier_counts": outlier_counts,
        "total_outliers": sum(outlier_counts.values()),
        "column_types": types,
        "describe": desc,
        "correlation": corr,
        "health_score": dataset_health_score(df),
    }
    return profile


def ai_recommendations(df, profile):
    """Rule-based recommendations engine used as fallback."""
    recs = []
    warnings = []
    types = profile["column_types"]
    n = profile["shape"]["rows"]

    id_cols, const_cols, high_card_cols, high_corr_pairs = [], [], [], []

    for c in df.columns:
        uniq = profile["unique_counts"][c]
        if uniq <= 1:
            const_cols.append(c)
        if n > 0 and uniq >= 0.95 * n and uniq > 20:
            id_cols.append(c)
        elif c in types["categorical"] and n > 0 and uniq > 0.5 * n and uniq > 30:
            high_card_cols.append(c)

    if profile["correlation"]:
        corr_df = pd.DataFrame(profile["correlation"])
        cols = corr_df.columns.tolist()
        for i, a in enumerate(cols):
            for b in cols[i + 1:]:
                val = corr_df.loc[a, b]
                if pd.notna(val) and abs(val) >= 0.85:
                    high_corr_pairs.append((a, b, round(float(val), 3)))

    for c in id_cols:
        recs.append(f"Remove '{c}' — identifier column with near-unique values.")
    for c in const_cols:
        recs.append(f"Remove '{c}' — constant column with zero variance.")
    for c in high_card_cols:
        recs.append(f"High cardinality in '{c}' — use target/ordinal encoding.")
    for a, b, v in high_corr_pairs[:5]:
        warnings.append(f"'{a}' and '{b}' are highly correlated (r={v}) — consider dropping one.")

    for c in df.columns:
        pct = profile["missing_pct"][c]
        if 0 < pct <= 5:
            recs.append(f"Fill missing values in '{c}' using median/mode ({pct}% missing).")
        elif 5 < pct <= 40:
            recs.append(f"'{c}' has {pct}% missing — consider KNN imputation.")
        elif pct > 40:
            warnings.append(f"'{c}' missing {pct}% values — consider dropping column.")

    for c in types["categorical"]:
        uniq = profile["unique_counts"][c]
        if 2 <= uniq <= 15 and c not in high_card_cols:
            recs.append(f"One-Hot Encode '{c}' ({uniq} categories).")
        elif uniq > 15:
            recs.append(f"Label/Ordinal Encode '{c}' due to higher cardinality.")

    if len(types["numeric"]) > 0:
        recs.append("Apply StandardScaler or RobustScaler to numeric features.")

    # Target selection heuristic
    suggested_target = None
    candidates = [c for c in df.columns if c not in id_cols and c not in const_cols]
    for c in reversed(candidates):
        uniq = profile["unique_counts"][c]
        if 2 <= uniq <= max(20, int(0.2 * n)):
            suggested_target = c
            break
    if suggested_target is None and candidates:
        suggested_target = candidates[-1]

    task_hint = "classification"
    imbalance_note = None
    if suggested_target:
        uniq = profile["unique_counts"][suggested_target]
        if suggested_target in types["numeric"] and uniq > 20:
            task_hint = "regression"
        else:
            task_hint = "classification"
            vc = df[suggested_target].value_counts(normalize=True)
            if len(vc) > 0 and (vc.iloc[0] > 0.8):
                imbalance_note = f"Target '{suggested_target}' is imbalanced ({round(vc.iloc[0]*100,1)}% majority class)."

    return {
        "recommendations": recs,
        "warnings": warnings,
        "id_columns": id_cols,
        "constant_columns": const_cols,
        "high_cardinality_columns": high_card_cols,
        "high_correlation_pairs": high_corr_pairs,
        "suggested_target": suggested_target,
        "suggested_task": task_hint,
        "imbalance_note": imbalance_note,
    }


# ---------------- Manual Cleaning Operations ----------------

def apply_missing_value_strategy(df, column, strategy):
    df = df.copy()
    if column not in df.columns:
        return df
    if strategy == "drop_rows":
        df = df[df[column].notna()]
    elif strategy == "drop_column":
        df = df.drop(columns=[column])
    elif strategy in ("mean", "median"):
        if pd.api.types.is_numeric_dtype(df[column]):
            imp = SimpleImputer(strategy=strategy)
            df[[column]] = imp.fit_transform(df[[column]])
    elif strategy == "mode":
        mode_val = df[column].mode(dropna=True)
        fill_val = mode_val.iloc[0] if len(mode_val) else "Unknown"
        df[column] = df[column].fillna(fill_val)
    elif strategy in ("constant", "unknown", "missing"):
        fill_val = 0 if pd.api.types.is_numeric_dtype(df[column]) else "Missing"
        df[column] = df[column].fillna(fill_val)
    elif strategy == "knn":
        if pd.api.types.is_numeric_dtype(df[column]):
            imp = KNNImputer(n_neighbors=5)
            df[[column]] = imp.fit_transform(df[[column]])
    return df


def remove_duplicates(df):
    return df.drop_duplicates().reset_index(drop=True)


def handle_outliers(df, column, method="iqr"):
    df = df.copy()
    if column not in df.columns or not pd.api.types.is_numeric_dtype(df[column]):
        return df
    if method == "iqr":
        q1, q3 = df[column].quantile([0.25, 0.75])
        iqr = q3 - q1
        if iqr > 0:
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            df = df[(df[column] >= lower) & (df[column] <= upper)]
    elif method == "zscore":
        std = df[column].std(ddof=0)
        if std > 0:
            z = (df[column] - df[column].mean()) / std
            df = df[z.abs() <= 3]
    elif method == "isolation_forest":
        from sklearn.ensemble import IsolationForest
        if len(df) > 10:
            iso = IsolationForest(contamination=0.05, random_state=42)
            mask = iso.fit_predict(df[[column]].fillna(df[column].median())) == 1
            df = df[mask]
    return df.reset_index(drop=True)


def encode_column(df, column, method="onehot"):
    df = df.copy()
    if column not in df.columns:
        return df
    if method == "label":
        le = LabelEncoder()
        df[column] = le.fit_transform(df[column].astype(str))
    elif method == "onehot":
        dummies = pd.get_dummies(df[column].astype(str), prefix=column, drop_first=False)
        df = pd.concat([df.drop(columns=[column]), dummies], axis=1)
    elif method == "ordinal":
        oe = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)
        df[column] = oe.fit_transform(df[[column]].astype(str))
    return df


def scale_columns(df, columns, method="standard"):
    df = df.copy()
    columns = [c for c in columns if c in df.columns and pd.api.types.is_numeric_dtype(df[c])]
    if not columns or method == "none":
        return df
    scaler = {"standard": StandardScaler(), "minmax": MinMaxScaler(), "robust": RobustScaler()}.get(method)
    if scaler is None:
        return df
    df[columns] = scaler.fit_transform(df[columns])
    return df


# ---------------- Advanced Auto Dataset Cleaning System ----------------

def auto_clean(df, profile=None):
    """
    Comprehensive Automated Data Cleaning System
    Returns (cleaned_df, cleaning_report)
    """
    if profile is None:
        profile = profile_dataset(df)

    df_clean = df.copy()
    health_before = dataset_health_score(df_clean)

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [],
        "before": {
            "rows": len(df_clean),
            "columns": len(df_clean.columns),
            "missing_values": int(df_clean.isna().sum().sum()),
            "duplicate_rows": int(df_clean.duplicated().sum()),
            "health_score": health_before
        },
        "after": {}
    }

    # Step 1: Remove Duplicate Rows
    dup_count = int(df_clean.duplicated().sum())
    if dup_count > 0:
        before_rows = len(df_clean)
        df_clean = remove_duplicates(df_clean)
        report["steps"].append({
            "step": 1,
            "action": "Remove Duplicates",
            "icon": "fas fa-copy",
            "description": f"Removed {dup_count} duplicate rows.",
            "impact": f"-{dup_count} rows"
        })

    # Step 2: Remove Constant & Zero-Variance Columns
    const_cols = [c for c in df_clean.columns if df_clean[c].nunique(dropna=False) <= 1]
    if const_cols:
        df_clean = df_clean.drop(columns=const_cols)
        report["steps"].append({
            "step": 2,
            "action": "Drop Constant Columns",
            "icon": "fas fa-minus-circle",
            "description": f"Dropped {len(const_cols)} constant columns with zero variance: {', '.join(const_cols[:5])}",
            "impact": f"-{len(const_cols)} columns"
        })

    # Step 3: Handle Date / Time Columns & Extract Features
    types_now = column_types(df_clean)
    for col in types_now["datetime"]:
        if col in df_clean.columns:
            dt_series = pd.to_datetime(df_clean[col], errors="coerce", format="mixed")
            if dt_series.notna().sum() > 0:
                df_clean[f"{col}_year"] = dt_series.dt.year.fillna(-1).astype(int)
                df_clean[f"{col}_month"] = dt_series.dt.month.fillna(-1).astype(int)
                df_clean[f"{col}_day"] = dt_series.dt.day.fillna(-1).astype(int)
                df_clean[f"{col}_dayofweek"] = dt_series.dt.dayofweek.fillna(-1).astype(int)
                df_clean = df_clean.drop(columns=[col])
                report["steps"].append({
                    "step": 3,
                    "action": "Datetime Feature Engineering",
                    "icon": "fas fa-calendar-alt",
                    "description": f"Parsed date column '{col}' into year, month, day, and dayofweek features.",
                    "impact": f"Transformed '{col}'"
                })

    # Step 4: Missing Values Imputation & Severe Missing Column Dropping
    types_now = column_types(df_clean)
    for col in list(df_clean.columns):
        missing_count = int(df_clean[col].isna().sum())
        if missing_count == 0:
            continue

        missing_pct = (missing_count / len(df_clean)) * 100
        if missing_pct > 50.0:
            df_clean = df_clean.drop(columns=[col])
            report["steps"].append({
                "step": 4,
                "action": "Drop High-Missing Column",
                "icon": "fas fa-trash-alt",
                "description": f"Dropped column '{col}' due to excessive missing values ({missing_pct:.1f}% missing).",
                "impact": f"Dropped '{col}'"
            })
        elif col in types_now["numeric"]:
            median_val = df_clean[col].median()
            df_clean[col] = df_clean[col].fillna(median_val)
            report["steps"].append({
                "step": 4,
                "action": "Impute Numeric Missing",
                "icon": "fas fa-calculator",
                "description": f"Imputed {missing_count} missing values in '{col}' using median ({median_val:.2f}).",
                "impact": f"Fixed {missing_count} cells"
            })
        else:
            mode_val = df_clean[col].mode(dropna=True)
            fill_val = mode_val.iloc[0] if len(mode_val) > 0 else "Missing"
            df_clean[col] = df_clean[col].fillna(fill_val)
            report["steps"].append({
                "step": 4,
                "action": "Impute Categorical Missing",
                "icon": "fas fa-font",
                "description": f"Imputed {missing_count} missing values in '{col}' using mode ('{fill_val}').",
                "impact": f"Fixed {missing_count} cells"
            })

    # Step 5: Handle Outliers in Numeric Features (IQR Filter)
    types_now = column_types(df_clean)
    for col in types_now["numeric"]:
        if len(df_clean) > 20:
            q1, q3 = df_clean[col].quantile([0.25, 0.75])
            iqr = q3 - q1
            if iqr > 0:
                lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
                outliers = ((df_clean[col] < lower) | (df_clean[col] > upper)).sum()
                if 0 < outliers <= 0.05 * len(df_clean):  # Only clip if extreme (< 5% of dataset)
                    df_clean[col] = df_clean[col].clip(lower, upper)
                    report["steps"].append({
                        "step": 5,
                        "action": "Clip Numeric Outliers",
                        "icon": "fas fa-compress-alt",
                        "description": f"Clipped {outliers} extreme outliers in '{col}' to IQR bounds [{lower:.2f}, {upper:.2f}].",
                        "impact": f"Clipped {outliers} values"
                    })

    # Calculate final health score & summary
    health_after = dataset_health_score(df_clean)
    report["after"] = {
        "rows": len(df_clean),
        "columns": len(df_clean.columns),
        "missing_values": int(df_clean.isna().sum().sum()),
        "duplicate_rows": int(df_clean.duplicated().sum()),
        "health_score": health_after
    }
    report["summary"] = {
        "rows_removed": report["before"]["rows"] - report["after"]["rows"],
        "columns_changed": report["before"]["columns"] - report["after"]["columns"],
        "missing_fixed": report["before"]["missing_values"] - report["after"]["missing_values"],
        "health_improvement": round(health_after - health_before, 1)
    }

    return df_clean, report


# ---------------- Snapshot & Undo / Reset Utilities ----------------

def create_cleaning_snapshot(project_dir, df, description=""):
    """Save a timestamped dataframe snapshot for step-by-step undo"""
    snapshot_id = str(uuid.uuid4())
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snapshot_filename = f"snapshot_{snapshot_id}.pkl"
    save_df(project_dir, df, name=snapshot_filename)

    state = load_state(project_dir)
    history = state.get("cleaning_history", [])
    history.append({
        "id": snapshot_id,
        "timestamp": timestamp,
        "description": description,
        "snapshot_file": snapshot_filename,
        "rows": len(df),
        "columns": len(df.columns)
    })
    state["cleaning_history"] = history
    save_state(project_dir, state)
    return snapshot_id


def undo_last_cleaning(project_dir):
    """Revert dataset to the previous cleaning snapshot"""
    state = load_state(project_dir)
    history = state.get("cleaning_history", [])

    if len(history) < 2:
        return None, "No previous cleaning operation to undo."

    # Remove last snapshot entry
    last_snapshot = history.pop()
    prev_snapshot = history[-1]

    # Load dataframe from previous snapshot
    prev_df = load_df(project_dir, name=prev_snapshot["snapshot_file"])
    if prev_df is None:
        return None, "Previous snapshot file could not be read."

    # Save as current dataframe
    save_df(project_dir, prev_df)

    # Clean up last snapshot file
    last_path = os.path.join(_project_path(project_dir), last_snapshot["snapshot_file"])
    if os.path.exists(last_path):
        try:
            os.remove(last_path)
        except OSError:
            pass

    state["cleaning_history"] = history
    save_state(project_dir, state)
    return prev_df, f"Successfully undone: restored snapshot '{prev_snapshot['description']}' ({prev_snapshot['rows']} rows, {prev_snapshot['columns']} cols)."


def reset_to_original(project_dir):
    """Reset dataset to initial uploaded raw state"""
    original_df = load_df(project_dir, name="original.pkl")
    if original_df is None:
        return None, "Original dataset file not found."

    save_df(project_dir, original_df)

    state = load_state(project_dir)
    state["cleaning_history"] = []
    state["cleaning_log"] = []
    state["cleaning_report"] = None
    save_state(project_dir, state)

    # Save baseline initial snapshot
    create_cleaning_snapshot(project_dir, original_df, "Initial raw dataset")
    return original_df, f"Dataset successfully reset to original state ({len(original_df)} rows, {len(original_df.columns)} columns)."
