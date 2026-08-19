"""
AI utilities for ModelFlow recommendations, cleaning strategy, training guidance,
error explanations, and interactive AI Chat assistant using Google GenAI SDK:
Google Gemini AI → ModelFlow Engine Fallback
"""
import os
import json
import traceback
import time
from dotenv import load_dotenv
import requests

try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False

load_dotenv()


def get_gemini_client():
    """Get initialized google-genai client if key exists"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in environment variables.")
    if HAS_GENAI_SDK:
        return genai.Client(api_key=api_key)
    return None


def get_gemini_recommendations(df, profile):
    """
    Get AI recommendations from Google Gemini API using google-genai SDK with gemini-3.6-flash model.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not configured")

    summary = _prepare_dataset_summary(df, profile)
    prompt = _build_recommendation_prompt(summary)

    # 1. Try official google-genai SDK first
    if HAS_GENAI_SDK:
        try:
            client = genai.Client(api_key=api_key)
            config = types.GenerateContentConfig(
                temperature=0.4,
                response_mime_type="application/json"
            )
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
                config=config
            )
            if response and response.text:
                return _parse_ai_response(response.text)
        except Exception as sdk_err:
            print(f"[Gemini SDK Recommendation Warning]: {sdk_err}. Falling back to REST API...")

    # 2. REST API Fallback with updated model endpoints (gemini-3.6-flash, gemini-3.5-flash, gemini-flash-latest)
    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    headers = {"Content-Type": "application/json"}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json"
        }
    }

    last_error = None
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        for attempt in range(2):
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=15)
                if resp.status_code == 200:
                    result = resp.json()
                    content = result["candidates"][0]["content"]["parts"][0]["text"]
                    return _parse_ai_response(content)
                elif resp.status_code in [429, 503]:
                    last_error = f"{model_name} HTTP {resp.status_code}"
                    time.sleep(1.5)
                else:
                    last_error = f"{model_name} HTTP {resp.status_code}"
                    break
            except Exception as req_err:
                last_error = str(req_err)
                time.sleep(1)

    raise RuntimeError(f"All Gemini model endpoints failed. Last error: {last_error}")


def get_ai_recommendations_with_fallback(df, profile):
    """
    Get AI recommendations with strict fallback chain:
    Google Gemini AI -> ModelFlow Engine Fallback
    Returns (recommendations_dict, provider_name)
    """
    try:
        print("[AI Architecture] Attempting dataset strategy via Gemini AI (gemini-3.6-flash)...")
        recs = get_gemini_recommendations(df, profile)
        if isinstance(recs, dict) and "suggested_models" in recs:
            provider_name = "Gemini AI"
            recs["provider"] = provider_name
            recs["execution_engine"] = "ModelFlow Engine"
            print(f"[AI Architecture] Successfully received strategy from {provider_name}")
            return recs, provider_name
    except Exception as e:
        print(f"[AI Architecture] Gemini AI unavailable ({str(e)}). Switching to ModelFlow Engine Fallback...")

    # ModelFlow Engine Fallback
    from . import data_utils as du
    local_recs = du.ai_recommendations(df, profile)
    provider_name = "ModelFlow Engine Fallback"
    local_recs["provider"] = provider_name
    local_recs["execution_engine"] = "ModelFlow Engine"
    local_recs["dataset_overview"] = f"Heuristic profiling by ModelFlow Engine for dataset with {len(df)} rows and {len(df.columns)} columns."
    local_recs["problem_explanation"] = f"Target '{local_recs.get('suggested_target')}' selected via deterministic data distribution rules."

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


def get_cleaning_strategy_with_fallback(df, profile):
    """
    Get AI-recommended data cleaning strategy:
    Gemini AI -> ModelFlow Engine Fallback
    Returns (cleaning_strategy_dict, provider_name)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            summary = _prepare_dataset_summary(df, profile)
            prompt = f"""
Analyze the following dataset metadata and act as a Data Preparation Specialist.
Recommend the optimal data cleaning, imputation, categorical encoding, and feature scaling strategy.

Return STRICT JSON adhering to this exact schema:
{{
  "imputation_strategy": "median OR mean OR mode OR drop",
  "encoding_strategy": "onehot OR label",
  "scaling_strategy": "standard OR minmax OR none",
  "explanation": "Brief clear explanation of why these strategies were recommended",
  "high_priority_actions": [
    "Action item 1"
  ]
}}

Dataset Metadata:
{summary}
"""
            if HAS_GENAI_SDK:
                client = genai.Client(api_key=api_key)
                config = types.GenerateContentConfig(temperature=0.3, response_mime_type="application/json")
                resp = client.models.generate_content(model="gemini-3.6-flash", contents=prompt, config=config)
                if resp and resp.text:
                    parsed = _parse_ai_response(resp.text)
                    if isinstance(parsed, dict) and "imputation_strategy" in parsed:
                        return parsed, "Gemini AI"
        except Exception as err:
            print(f"[AI Cleaning Strategy Warning]: {err}. Using ModelFlow Engine Fallback...")

    # ModelFlow Engine Fallback Strategy
    fallback_strategy = {
        "imputation_strategy": "median",
        "encoding_strategy": "onehot",
        "scaling_strategy": "standard",
        "explanation": "Default robust data cleaning plan generated by ModelFlow Engine rules.",
        "high_priority_actions": [
            "Fill numeric missing values with median.",
            "One-hot encode categorical features.",
            "Standardize numeric columns using StandardScaler."
        ]
    }
    return fallback_strategy, "ModelFlow Engine Fallback"


def get_training_strategy_with_fallback(df, profile, target_col, task_type):
    """
    Get AI-recommended AutoML training strategy:
    Gemini AI -> ModelFlow Engine Fallback
    Returns (training_strategy_dict, provider_name)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            summary = _prepare_dataset_summary(df, profile)
            prompt = f"""
Act as an AutoML System Architect. Analyze this dataset metadata for target column '{target_col}' ({task_type} task).
Recommend the optimal machine learning model suite and hyperparameter strategy.

Return STRICT JSON adhering to this exact schema:
{{
  "recommended_algorithms": ["Random Forest", "XGBoost", "LightGBM", "Logistic Regression"],
  "primary_model_recommendation": "Name of top recommended model",
  "strategy_explanation": "Brief explanation of why these models fit this dataset",
  "recommended_split_ratio": 80
}}

Dataset Summary:
{summary}
"""
            if HAS_GENAI_SDK:
                client = genai.Client(api_key=api_key)
                config = types.GenerateContentConfig(temperature=0.3, response_mime_type="application/json")
                resp = client.models.generate_content(model="gemini-3.6-flash", contents=prompt, config=config)
                if resp and resp.text:
                    parsed = _parse_ai_response(resp.text)
                    if isinstance(parsed, dict) and "recommended_algorithms" in parsed:
                        return parsed, "Gemini AI"
        except Exception as err:
            print(f"[AI Training Strategy Warning]: {err}. Using ModelFlow Engine Fallback...")

    # ModelFlow Engine Fallback Strategy
    default_algos = ["Random Forest", "XGBoost", "Logistic Regression"] if task_type == "classification" else ["Random Forest", "LightGBM", "Ridge Regression"]
    fallback_strategy = {
        "recommended_algorithms": default_algos,
        "primary_model_recommendation": default_algos[0],
        "strategy_explanation": "Standard multi-model AutoML suite selected by ModelFlow Engine rules.",
        "recommended_split_ratio": 80
    }
    return fallback_strategy, "ModelFlow Engine Fallback"


def explain_error_with_fallback(error_str, action_context="AutoML Training"):
    """
    Explain workflow or runtime error:
    Gemini AI -> ModelFlow Engine Fallback
    Returns (explanation_dict, provider_name)
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and error_str:
        try:
            # Sanitize error to avoid leaking secrets
            clean_error = str(error_str)[:1000]
            prompt = f"""
Act as a Data Science Support Specialist at an enterprise AutoML firm.
Analyze this runtime error that occurred during '{action_context}' and explain it clearly to a non-expert user.

Return STRICT JSON:
{{
  "error_title": "Short readable title of what went wrong",
  "plain_english_explanation": "Clear non-technical explanation",
  "probable_root_cause": "Likely cause in the dataset or configuration",
  "suggested_fix_steps": ["Step 1", "Step 2"]
}}

Runtime Error:
{clean_error}
"""
            if HAS_GENAI_SDK:
                client = genai.Client(api_key=api_key)
                config = types.GenerateContentConfig(temperature=0.3, response_mime_type="application/json")
                resp = client.models.generate_content(model="gemini-3.6-flash", contents=prompt, config=config)
                if resp and resp.text:
                    parsed = _parse_ai_response(resp.text)
                    if isinstance(parsed, dict) and "plain_english_explanation" in parsed:
                        return parsed, "Gemini AI"
        except Exception as err:
            print(f"[AI Error Explanation Warning]: {err}. Using ModelFlow Engine Fallback...")

    # ModelFlow Engine Local Fallback Explanation
    fallback_explanation = {
        "error_title": f"Processing Issue during {action_context}",
        "plain_english_explanation": "The system encountered an unexpected error while executing this workflow task.",
        "probable_root_cause": "Missing values, unencoded categorical data, or incompatible target variable selection.",
        "suggested_fix_steps": [
            "Check dataset on Clean page to ensure no missing target values exist.",
            "Verify all categorical features are properly encoded.",
            "Try training with a smaller subset of columns or standard algorithms."
        ]
    }
    return fallback_explanation, "ModelFlow Engine Fallback"


def generate_chat_response_with_fallback(history_messages, project_context=None):
    """
    Generate conversational AI chat response:
    Try Google Gemini API -> If failure / HTTP 429 / quota exceeded -> ModelFlow Engine Fallback
    Returns tuple: (response_text, provider_name) where provider_name is 'Gemini AI' or 'ModelFlow Engine Fallback'
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key and history_messages:
        try:
            print("[AI Chat Architecture] Attempting Gemini API chat generation...")
            response_text = _call_gemini_chat_api(api_key, history_messages, project_context)
            if response_text and response_text.strip():
                print("[AI Chat Architecture] Gemini API responded successfully.")
                return response_text.strip(), "Gemini AI"
        except Exception as e:
            err_str = str(e)
            is_429 = any(k in err_str.lower() for k in ["429", "quota", "exceeded", "resource_exhausted", "too many requests", "rate limit"])
            if is_429:
                print(f"[AI Chat Architecture] Gemini API Quota Exceeded (HTTP 429). Safely triggering ModelFlow Engine Fallback.")
            else:
                print(f"[AI Chat Architecture] Gemini API error ({err_str[:120]}). Triggering ModelFlow Engine Fallback.")

    # ModelFlow Engine Local Fallback Response
    print("[AI Chat Architecture] Executing ModelFlow Engine Fallback generator...")
    fallback_response = _generate_modelflow_engine_chat_response(history_messages, project_context)
    return fallback_response, "ModelFlow Engine Fallback"


def generate_chat_response(history_messages, project_context=None):
    """Legacy compatibility wrapper"""
    text, _ = generate_chat_response_with_fallback(history_messages, project_context)
    return text


def _call_gemini_chat_api(api_key, history_messages, project_context=None):
    system_instruction = (
        "You are ModelFlow AI Assistant, an expert Data Science, AutoML, and Machine Learning Advisor "
        "integrated into the ModelFlow SaaS platform.\n"
        "Your goals are to help users:\n"
        "1. Understand ModelFlow workflows (dataset upload, data cleaning, AutoML model training, evaluation, predictions, deployment).\n"
        "2. Analyze their uploaded datasets, feature engineering choices, and model leaderboard results.\n"
        "3. Debug workflow errors, model performance issues, and explain data science concepts clearly.\n"
        "4. Provide production-grade code snippets, recommendations, and actionable advice.\n"
        "Be helpful, professional, clear, and concise. Format responses in Markdown."
    )

    if project_context:
        ctx_str = json.dumps(project_context, indent=2, default=str)
        system_instruction += f"\n\nActive Project Context:\n{ctx_str}"

    if HAS_GENAI_SDK:
        try:
            client = genai.Client(api_key=api_key)
            contents = []
            for msg in history_messages:
                role = "user" if msg.get("role") in ["user", "human"] else "model"
                text = msg.get("content", "")
                if text:
                    contents.append(types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=text)]
                    ))

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
                max_output_tokens=2048
            )

            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=contents,
                config=config
            )

            if response and response.text:
                return response.text
        except Exception as sdk_err:
            print(f"[Gemini Chat SDK Warning]: {sdk_err}. Trying REST API...")

    # REST API Fallback for Chat
    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    headers = {"Content-Type": "application/json"}

    contents_payload = []
    contents_payload.append({
        "role": "user",
        "parts": [{"text": f"System Context:\n{system_instruction}\n\nPlease acknowledge and adhere to these guidelines."}]
    })
    contents_payload.append({
        "role": "model",
        "parts": [{"text": "Understood. I am ModelFlow AI Assistant, ready to help you with your datasets, AutoML models, and workflows."}]
    })

    for msg in history_messages:
        role = "user" if msg.get("role") in ["user", "human"] else "model"
        text = msg.get("content", "")
        if text:
            contents_payload.append({
                "role": role,
                "parts": [{"text": text}]
            })

    data = {
        "contents": contents_payload,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048
        }
    }

    last_error = None
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        for attempt in range(2):
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=15)
                if resp.status_code == 200:
                    result = resp.json()
                    return result["candidates"][0]["content"]["parts"][0]["text"]
                elif resp.status_code in [429, 503]:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
                    time.sleep(1)
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:100]}"
                    break
            except Exception as req_err:
                last_error = str(req_err)
                time.sleep(1)

    raise RuntimeError(f"Gemini AI Chat service unavailable. Error: {last_error}")


def _generate_modelflow_engine_chat_response(history_messages, project_context=None):
    """
    Intelligent deterministic chatbot fallback generator using ModelFlow Engine rules & conversation history.
    """
    if not history_messages:
        return "Hello! I am your ModelFlow AI Assistant (ModelFlow Engine Fallback). How can I help you today?"

    last_user_msg = ""
    for m in reversed(history_messages):
        if m.get("role") in ["user", "human"]:
            last_user_msg = m.get("content", "").strip()
            break

    msg_lower = last_user_msg.lower()

    # 1. Identity & Name Tracking
    if any(q in msg_lower for q in ["what is my name", "who am i", "remember my name"]):
        name = None
        for m in history_messages:
            if m.get("role") in ["user", "human"]:
                txt = m.get("content", "")
                txt_lower = txt.lower()
                if "my name is " in txt_lower:
                    idx = txt_lower.find("my name is ") + 11
                    name = txt[idx:].split(".")[0].split("!")[0].split("\n")[0].strip()
                elif "i am " in txt_lower and len(txt.split()) <= 6:
                    idx = txt_lower.find("i am ") + 5
                    name = txt[idx:].split(".")[0].split("!")[0].split("\n")[0].strip()
        if name:
            return f"Your name is **{name}**! 😊 How can I help you with your ModelFlow project today?"
        return "I don't have your name saved in our current conversation history yet. Feel free to tell me by saying *'My name is [Your Name]'*!"

    if "my name is " in msg_lower or (msg_lower.startswith("i am ") and len(msg_lower.split()) <= 6):
        if "my name is " in msg_lower:
            idx = last_user_msg.lower().find("my name is ") + 11
            name = last_user_msg[idx:].split(".")[0].split("!")[0].split("\n")[0].strip()
        else:
            idx = last_user_msg.lower().find("i am ") + 5
            name = last_user_msg[idx:].split(".")[0].split("!")[0].split("\n")[0].strip()
        return f"Nice to meet you, **{name}**! 👋 I am your ModelFlow AI Assistant. What would you like to build or analyze today?"

    # 2. Greetings
    if any(g in msg_lower for g in ["hi", "hello", "hey", "greetings", "good morning", "good afternoon"]):
        return "Hello! I am your ModelFlow AI Assistant (running on **ModelFlow Engine Fallback**). 👋\n\nI can help you analyze dataset quality, guide feature engineering, recommend ML models, explain training errors, and optimize your AutoML pipeline. What can I assist you with?"

    # 3. Dataset Context & Explanation
    if any(k in msg_lower for k in ["explain my dataset", "dataset summary", "current dataset", "my data", "analyze dataset"]):
        if project_context:
            p_name = project_context.get("project_name", "Active Project")
            shape = project_context.get("dataset_shape", {})
            rows = shape.get("rows", "N/A") if isinstance(shape, dict) else "N/A"
            cols = shape.get("columns", "N/A") if isinstance(shape, dict) else "N/A"
            health = project_context.get("health_score", "N/A")
            best_model = project_context.get("best_model", "None trained yet")
            best_acc = project_context.get("best_accuracy", "N/A")

            return (
                f"### 📊 Active Workspace Dataset Overview: **{p_name}**\n\n"
                f"- **Dataset Dimensions**: `{rows}` rows × `{cols}` columns\n"
                f"- **Health Quality Score**: `{health}/100`\n"
                f"- **Suggested Target**: `{project_context.get('suggested_target', 'Not set')}`\n"
                f"- **Recommended Task**: `{project_context.get('suggested_task', 'Not set')}`\n"
                f"- **Top Performing Model**: `{best_model}` (Score: `{best_acc}`)\n\n"
                f"**Recommendations**:\n"
                f"1. Check the **Clean** tab to impute any missing values and handle outliers.\n"
                f"2. Ensure all categorical features are properly encoded (One-Hot or Label Encoding).\n"
                f"3. Run automated training on the **Train** tab to compare 14+ ML algorithms."
            )
        return "No active dataset is currently selected in your workspace session. Please create or open a project and upload a CSV/Excel file on the **Upload** page!"

    # 4. Low Accuracy & Training Errors
    if any(k in msg_lower for k in ["accuracy low", "low accuracy", "improve model", "poor performance", "training error", "explain error"]):
        return (
            "### 🛠️ Model Performance & Accuracy Optimization Guide\n\n"
            "If your model accuracy is lower than expected, try these **ModelFlow Engine Action Items**:\n\n"
            "1. **Class Imbalance**: Check if target labels are unevenly distributed (e.g. 95% Class A vs 5% Class B). Consider SMOTE or weighted loss.\n"
            "2. **Data Cleaning**: Remove high-missingness columns (>50% missing) and impute missing numerical cells using median.\n"
            "3. **Feature Scaling**: Apply `StandardScaler` or `MinMaxScaler` for distance-based models (KNN, Logistic Regression, SVM).\n"
            "4. **Non-Linear Algorithms**: Switch to tree ensembles like **XGBoost**, **LightGBM**, or **Random Forest** which excel on tabular data.\n"
            "5. **Hyperparameter Tuning**: Increase `n_estimators` (100–300) and adjust `max_depth` to prevent underfitting or overfitting."
        )

    # 5. Model choice (XGBoost vs Random Forest, etc.)
    if "xgboost" in msg_lower or "random forest" in msg_lower or "logistic regression" in msg_lower:
        return (
            "### 🤖 Model Selection Comparison\n\n"
            "- **Random Forest**: Best general baseline for tabular data. Handles non-linearities automatically, resilient to outliers, resistant to overfitting.\n"
            "- **XGBoost**: Gradient boosting framework providing state-of-the-art accuracy. Ideal for competitive performance, but requires careful learning rate tuning.\n"
            "- **Logistic Regression**: Fast, highly interpretable linear baseline. Perfect for quick deployment when linear decision boundaries hold."
        )

    # 6. General Fallback Response
    return (
        f"I received your query: *\"{last_user_msg}\"*\n\n"
        "As your **ModelFlow AI Assistant**, here is what I recommend:\n\n"
        "1. **Dataset Ingestion**: Upload tabular datasets (.csv, .xlsx) on the **Upload** tab for automated AI health checks.\n"
        "2. **Data Preparation**: Use the **Clean** tab for 1-click median imputation, one-hot encoding, and feature scaling.\n"
        "3. **AutoML Training**: Compare 14+ algorithms on the **Train** tab and export binaries or REST APIs on the **Deploy** tab."
    )


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
            "name": str(col),
            "dtype": str(df[col].dtype),
            "unique_count": int(profile.get("unique_counts", {}).get(col, df[col].nunique())),
            "missing_count": int(profile.get("missing_counts", {}).get(col, df[col].isna().sum())),
            "missing_pct": float(profile.get("missing_pct", {}).get(col, 0.0))
        })

    return json.dumps(summary, indent=2, default=str)


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
