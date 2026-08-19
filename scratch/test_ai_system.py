import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import json
import time
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from app import app, db
from utils import ai_utils as au
from utils import data_utils as du
from utils import ml_utils as mu

def run_tests():
    print("="*70)
    print("MODELFLOW GEMINI-FIRST + ENGINE FALLBACK ARCHITECTURE REGRESSION SUITE")
    print("="*70)

    test_results = []
    test_user_id = "test_user_reg_123"

    db.users.update_one(
        {"_id": test_user_id},
        {"$set": {"email": "regression@modelflow.ai", "name": "Regression Tester"}},
        upsert=True
    )

    app.config["TESTING"] = True

    # -------------------------------------------------------------------------
    # PART 1: STANDARD FLOW (GEMINI ACTIVE)
    # -------------------------------------------------------------------------
    print("\n--- PART 1: TESTING STANDARD FLOW (GEMINI ACTIVE) ---")

    with app.test_client() as client:
        def set_authenticated(sess):
            sess["_user_id"] = test_user_id
            sess["_fresh"] = True

        def auth_post(url, json_data):
            with client.session_transaction() as sess:
                set_authenticated(sess)
            return client.post(url, json=json_data)

        def auth_get(url):
            with client.session_transaction() as sess:
                set_authenticated(sess)
            return client.get(url)

        # 1. Gemini Initializer & Key
        try:
            api_key = os.getenv("GEMINI_API_KEY")
            client_sdk = au.get_gemini_client()
            test_results.append(("1. Gemini SDK & API Key Initializer", "PASS", "google-genai Client initialized cleanly"))
        except Exception as e:
            test_results.append(("1. Gemini SDK & API Key Initializer", "FAIL", str(e)))

        # 2. Dataset Profiling & Gemini Recommendations
        try:
            df_sample = pd.DataFrame({
                "age": [25, 30, 45, 50, 22, 38, 41, 29],
                "income": [50000, 60000, 80000, 95000, 42000, 71000, 78000, 56000],
                "purchased": [0, 1, 1, 1, 0, 1, 1, 0]
            })
            profile_sample = du.profile_dataset(df_sample)
            recs, provider = au.get_ai_recommendations_with_fallback(df_sample, profile_sample)
            test_results.append(("2. Gemini Dataset Profiling & Strategy", "PASS", f"Provider: {provider}"))
        except Exception as e:
            test_results.append(("2. Gemini Dataset Profiling & Strategy", "FAIL", str(e)))

        # 3. Gemini Data Cleaning Strategy
        try:
            c_strategy, c_provider = au.get_cleaning_strategy_with_fallback(df_sample, profile_sample)
            test_results.append(("3. Gemini Cleaning Strategy", "PASS", f"Provider: {c_provider}, Imputation: {c_strategy.get('imputation_strategy')}"))
        except Exception as e:
            test_results.append(("3. Gemini Cleaning Strategy", "FAIL", str(e)))

        # 4. Gemini Training Strategy
        try:
            t_strategy, t_provider = au.get_training_strategy_with_fallback(df_sample, profile_sample, "purchased", "classification")
            test_results.append(("4. Gemini Training Strategy", "PASS", f"Provider: {t_provider}, Top Model: {t_strategy.get('primary_model_recommendation')}"))
        except Exception as e:
            test_results.append(("4. Gemini Training Strategy", "FAIL", str(e)))

        # 5. AI Chat & Memory ("My name is Muhammad" -> "What is my name?")
        try:
            res1 = auth_post("/api/ai/chat", {"message": "My name is Muhammad."})
            c_id = res1.get_json().get("conversation_id")
            time.sleep(1)
            res2 = auth_post("/api/ai/chat", {"message": "What is my name?", "conversation_id": c_id})
            d2 = res2.get_json()
            if res2.status_code == 200 and "Muhammad" in d2.get("response", ""):
                test_results.append(("5. AI Chat Memory Retention", "PASS", "Recalled 'Muhammad' from chat memory"))
            else:
                test_results.append(("5. AI Chat Memory Retention", "FAIL", str(d2)))
        except Exception as e:
            test_results.append(("5. AI Chat Memory Retention", "FAIL", str(e)))

        # 6. ModelFlow Engine AutoML Training Execution
        try:
            X = df_sample[["age", "income"]]
            y = df_sample["purchased"]
            X_tr, X_te, y_tr, y_te = mu.train_test_split_data(X, y, test_size=0.2, task="classification")
            lb_df, fitted, extras, best_model_name = mu.run_automl(X_tr, X_te, y_tr, y_te, task="classification", model_names=["Random Forest", "Logistic Regression"])
            top_acc = lb_df.iloc[0]["Accuracy"]
            test_results.append(("6. ModelFlow Engine AutoML Training", "PASS", f"Trained {len(lb_df)} models, Top Model: {best_model_name}, Top Accuracy: {top_acc*100:.1f}%"))

        except Exception as e:
            test_results.append(("6. ModelFlow Engine AutoML Training", "FAIL", str(e)))



    # -------------------------------------------------------------------------
    # PART 2: MANDATORY GEMINI FAILURE SIMULATION (REQUIREMENT #19)
    # -------------------------------------------------------------------------
    print("\n--- PART 2: TESTING SIMULATED GEMINI FAILURE & ENGINE FALLBACK ---")
    original_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "INVALID_SIMULATED_KEY_FOR_TESTING"

    try:
        # 7. Simulated Failure: Dataset Profiling Strategy
        recs_fb, prov_fb = au.get_ai_recommendations_with_fallback(df_sample, profile_sample)
        if prov_fb == "ModelFlow Engine Fallback" and "suggested_models" in recs_fb:
            test_results.append(("7. [Fallback Test] Dataset Profiling Strategy", "PASS", f"Fallback engaged seamlessly: {prov_fb}"))
        else:
            test_results.append(("7. [Fallback Test] Dataset Profiling Strategy", "FAIL", f"Unexpected provider: {prov_fb}"))
    except Exception as e:
        test_results.append(("7. [Fallback Test] Dataset Profiling Strategy", "FAIL", str(e)))

    try:
        # 8. Simulated Failure: Cleaning Strategy
        clean_fb, c_prov_fb = au.get_cleaning_strategy_with_fallback(df_sample, profile_sample)
        if c_prov_fb == "ModelFlow Engine Fallback" and "imputation_strategy" in clean_fb:
            test_results.append(("8. [Fallback Test] Cleaning Strategy", "PASS", f"Fallback engaged: {c_prov_fb}"))
        else:
            test_results.append(("8. [Fallback Test] Cleaning Strategy", "FAIL", f"Unexpected: {c_prov_fb}"))
    except Exception as e:
        test_results.append(("8. [Fallback Test] Cleaning Strategy", "FAIL", str(e)))

    try:
        # 9. Simulated Failure: Training Strategy
        train_fb, t_prov_fb = au.get_training_strategy_with_fallback(df_sample, profile_sample, "purchased", "classification")
        if t_prov_fb == "ModelFlow Engine Fallback" and "recommended_algorithms" in train_fb:
            test_results.append(("9. [Fallback Test] Training Strategy", "PASS", f"Fallback engaged: {t_prov_fb}"))
        else:
            test_results.append(("9. [Fallback Test] Training Strategy", "FAIL", f"Unexpected: {t_prov_fb}"))
    except Exception as e:
        test_results.append(("9. [Fallback Test] Training Strategy", "FAIL", str(e)))

    try:
        # 10. Simulated Failure: Error Explanation
        err_fb, e_prov_fb = au.explain_error_with_fallback("ValueError: Target variable contains missing values", "Dataset Cleaning")
        if e_prov_fb == "ModelFlow Engine Fallback" and "plain_english_explanation" in err_fb:
            test_results.append(("10. [Fallback Test] Error Explanation", "PASS", f"Fallback explanation generated: {e_prov_fb}"))
        else:
            test_results.append(("10. [Fallback Test] Error Explanation", "FAIL", f"Unexpected: {e_prov_fb}"))
    except Exception as e:
        test_results.append(("10. [Fallback Test] Error Explanation", "FAIL", str(e)))

    # Restore Gemini API Key
    if original_key:
        os.environ["GEMINI_API_KEY"] = original_key

    # Print Summary Table
    print("\n" + "="*70)
    print("FINAL REGRESSION & FALLBACK TEST RESULTS TABLE")
    print("="*70)
    for title, result, details in test_results:
        print(f"[{result}] {title}\n  -> {details}")
    print("="*70)

if __name__ == "__main__":
    run_tests()
