"""
AI utilities for recommendations with automatic fallback provider chain:
Kimi (Moonshot) → Gemini → ModelFlow AI
"""
import os
import json
import traceback
from dotenv import load_dotenv
import requests

load_dotenv()


def get_kimi_recommendations(df, profile):
    """
    Get AI recommendations from Kimi (Moonshot) API
    """
    api_key = os.getenv("KIMI_API_KEY") or "sk-l2VaraztNvwMgKofXXuaHzkxz915S04MM7K425msu4keResS"
    if not api_key:
        raise ValueError("KIMI_API_KEY not configured")

    summary = _prepare_dataset_summary(df, profile)
    prompt = _build_recommendation_prompt(summary)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "moonshot-v1-8k",
        "messages": [
            {
                "role": "system",
                "content": "You are an expert Data Scientist and AutoML Specialist at an enterprise AI firm (Vertex AI / DataRobot standard). Return strictly valid JSON."
            },
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
        "response_format": {"type": "json_object"}
    }

    response = requests.post(
        "https://api.moonshot.cn/v1/chat/completions",
        headers=headers,
        json=data,
        timeout=15
    )
    response.raise_for_status()
    result = response.json()
    content = result["choices"][0]["message"]["content"]
    return _parse_ai_response(content)


def get_gemini_recommendations(df, profile):
    """
    Get AI recommendations from Gemini API
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    summary = _prepare_dataset_summary(df, profile)
    prompt = _build_recommendation_prompt(summary)

    # Try gemini-2.0-flash or fallback gemini-1.5-flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5,
            "responseMimeType": "application/json"
        }
    }

    response = requests.post(url, headers=headers, json=data, timeout=15)
    if response.status_code != 200:
        # Fallback to gemini-1.5-flash if 2.0 returns issue
        url_15 = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        response = requests.post(url_15, headers=headers, json=data, timeout=15)
    
    response.raise_for_status()
    result = response.json()
    content = result["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_ai_response(content)


def _prepare_dataset_summary(df, profile):
    """Prepare a detailed concise summary of the dataset for AI prompts"""
    types = profile.get("column_types", {})
    summary = {
        "shape": profile.get("shape", {"rows": len(df), "columns": len(df.columns)}),
        "health_score": profile.get("health_score", 100),
        "column_types": {
            "numeric_count": len(types.get("numeric", [])),
            "categorical_count": len(types.get("categorical", [])),
            "datetime_count": len(types.get("datetime", [])),
            "boolean_count": len(types.get("boolean", []))
        },
        "duplicate_rows": profile.get("duplicate_rows", 0),
        "columns_detail": []
    }

    for col in df.columns[:30]:  # Cap columns to avoid token overflow
        summary["columns_detail"].append({
            "name": col,
            "dtype": str(df[col].dtype),
            "unique_count": profile.get("unique_counts", {}).get(col, df[col].nunique()),
            "missing_count": profile.get("missing_counts", {}).get(col, df[col].isna().sum()),
            "missing_pct": profile.get("missing_pct", {}).get(col, 0.0)
        })

    return json.dumps(summary, indent=2)


def _build_recommendation_prompt(summary_json):
    """Build structured prompt for AI recommendations"""
    return f"""
Analyze the following dataset metadata and act as an expert AutoML Engineer.
Provide comprehensive, production-ready machine learning recommendations.

Return STRICT JSON adhering to this exact schema:
{{
  "dataset_overview": "Summary explanation of the dataset quality and predictive potential",
  "suggested_target": "best_candidate_target_column_name",
  "suggested_task": "classification OR regression",
  "problem_explanation": "Detailed explanation of why this target and task were selected",
  "recommendations": [
    {{
      "text": "Specific actionable recommendation",
      "category": "cleaning OR encoding OR scaling OR modeling OR feature_engineering",
      "priority": "high OR medium OR low"
    }}
  ],
  "warnings": [
    "Critical dataset quality warning if any"
  ],
  "suggested_models": [
    {{
      "model": "Model Name (e.g. Random Forest, XGBoost, LightGBM, Logistic Regression, Ridge Regression)",
      "confidence": 92.5,
      "expected_performance": "e.g. 94-96% Accuracy or 0.88-0.92 R² Score",
      "advantages": ["Advantage 1", "Advantage 2"],
      "disadvantages": ["Disadvantage 1"],
      "preprocessing": ["Specific preprocessing step required"],
      "hyperparameters": {{
        "n_estimators": 200,
        "max_depth": 10,
        "learning_rate": 0.05
      }}
    }}
  ],
  "preprocessing_suggestions": [
    "Actionable feature engineering suggestion"
  ],
  "imbalance_note": "Note regarding class distribution or continuous variance"
}}

Dataset Metadata:
{summary_json}
"""


def _parse_ai_response(content):
    """Parse AI response string safely to JSON dict"""
    if not content:
        raise ValueError("Empty AI response")
    
    # Direct parse
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Clean markdown formatting if present
    content_clean = content.strip()
    if "```json" in content_clean:
        start = content_clean.find("```json") + 7
        end = content_clean.rfind("```")
        content_clean = content_clean[start:end].strip()
    elif "```" in content_clean:
        start = content_clean.find("```") + 3
        end = content_clean.rfind("```")
        content_clean = content_clean[start:end].strip()

    return json.loads(content_clean)


def get_ai_recommendations_with_fallback(df, profile):
    """
    Get AI recommendations with strict fallback provider chain:
    Kimi AI → Gemini AI → ModelFlow AI
    Returns (recommendations_dict, provider_name)
    """
    providers = [
        ("Kimi AI", get_kimi_recommendations),
        ("Gemini AI", get_gemini_recommendations)
    ]

    for provider_name, provider_func in providers:
        try:
            print(f"[AI Fallback System] Attempting recommendations via {provider_name}...")
            recs = provider_func(df, profile)
            if isinstance(recs, dict) and "suggested_models" in recs:
                recs["provider"] = provider_name
                print(f"[AI Fallback System] Successfully received recommendations from {provider_name}")
                return recs, provider_name
        except Exception as e:
            print(f"[AI Fallback System] {provider_name} unavailable or failed: {str(e)}")
            continue

    # Final fallback to ModelFlow AI
    print("[AI Fallback System] Engaging ModelFlow AI...")
    from . import data_utils as du
    local_recs = du.ai_recommendations(df, profile)
    provider_name = "ModelFlow AI"
    local_recs["provider"] = provider_name
    local_recs["dataset_overview"] = f"Heuristic analysis performed by ModelFlow AI for dataset with {len(df)} rows and {len(df.columns)} columns."
    local_recs["problem_explanation"] = f"Target '{local_recs.get('suggested_target')}' selected based on unique value distribution and data types."

    # Structure local suggested models to match AI format
    target = local_recs.get("suggested_target", "target")
    task = local_recs.get("suggested_task", "classification")

    if task == "classification":
        models = [
            {
                "model": "Random Forest Classifier",
                "confidence": 88.0,
                "expected_performance": "85% - 93% Accuracy",
                "advantages": ["Handles non-linear patterns", "Resilient to outliers", "Feature importance insights"],
                "disadvantages": ["Larger memory footprint"],
                "preprocessing": ["Impute missing numeric values", "One-hot encode categorical features"],
                "hyperparameters": {"n_estimators": 100, "max_depth": 12, "random_state": 42}
            },
            {
                "model": "XGBoost Classifier",
                "confidence": 92.0,
                "expected_performance": "88% - 96% Accuracy",
                "advantages": ["State-of-the-art gradient boosting", "Handles missing values implicitly"],
                "disadvantages": ["Requires hyperparameter tuning"],
                "preprocessing": ["Label encode categorical target & features"],
                "hyperparameters": {"n_estimators": 150, "learning_rate": 0.08, "max_depth": 6}
            },
            {
                "model": "Logistic Regression",
                "confidence": 78.0,
                "expected_performance": "78% - 85% Accuracy",
                "advantages": ["Highly interpretable", "Fast training and inference"],
                "disadvantages": ["Assumes linear decision boundary"],
                "preprocessing": ["StandardScaler numerical features"],
                "hyperparameters": {"C": 1.0, "solver": "lbfgs", "max_iter": 1000}
            }
        ]
    else:
        models = [
            {
                "model": "Random Forest Regressor",
                "confidence": 86.0,
                "expected_performance": "0.80 - 0.90 R² Score",
                "advantages": ["Non-parametric", "Handles non-linear relationships"],
                "disadvantages": ["Cannot extrapolate beyond training range"],
                "preprocessing": ["Impute missing values with median"],
                "hyperparameters": {"n_estimators": 100, "max_depth": 10, "random_state": 42}
            },
            {
                "model": "LightGBM Regressor",
                "confidence": 91.0,
                "expected_performance": "0.84 - 0.93 R² Score",
                "advantages": ["Extremely fast", "Low memory consumption"],
                "disadvantages": ["Can overfit small datasets"],
                "preprocessing": ["Encode object columns"],
                "hyperparameters": {"n_estimators": 200, "learning_rate": 0.05, "num_leaves": 31}
            },
            {
                "model": "Ridge Regression",
                "confidence": 75.0,
                "expected_performance": "0.70 - 0.82 R² Score",
                "advantages": ["L2 Regularization prevents overfitting", "Interpretable weights"],
                "disadvantages": ["Linear assumptions"],
                "preprocessing": ["StandardScaler features"],
                "hyperparameters": {"alpha": 1.0}
            }
        ]

    local_recs["suggested_models"] = models
    local_recs["preprocessing_suggestions"] = [
        "Check for missing values and fill using median or mode.",
        "Apply One-Hot encoding to low-cardinality categorical variables.",
        "Apply StandardScaler to numeric features for linear models."
    ]
    return local_recs, provider_name
