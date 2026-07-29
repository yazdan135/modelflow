
import sys
print("Testing imports with detailed logging...")
print("Python executable:", sys.executable)

print("\n--- 1. Testing basic dependencies ---")
try:
    import pandas as pd
    print("✓ pandas", pd.__version__)
except Exception as e:
    print("✗ pandas:", type(e).__name__, str(e))
try:
    import numpy as np
    print("✓ numpy", np.__version__)
except Exception as e:
    print("✗ numpy:", type(e).__name__, str(e))
try:
    import plotly
    print("✓ plotly", plotly.__version__)
except Exception as e:
    print("✗ plotly:", type(e).__name__, str(e))
try:
    import requests
    print("✓ requests", requests.__version__)
except Exception as e:
    print("✗ requests:", type(e).__name__, str(e))

print("\n--- 2. Testing our utils ---")
try:
    from utils import data_utils as du
    print("✓ data_utils imported")
except Exception as e:
    print("✗ data_utils:", type(e).__name__)
    import traceback
    print(traceback.format_exc())
try:
    from utils import viz_utils as vu
    print("✓ viz_utils imported")
except Exception as e:
    print("✗ viz_utils:", type(e).__name__)
    import traceback
    print(traceback.format_exc())
try:
    from utils import ai_utils as au
    print("✓ ai_utils imported")
except Exception as e:
    print("✗ ai_utils:", type(e).__name__)
    import traceback
    print(traceback.format_exc())

print("\n--- 3. Testing app.py import ---")
try:
    import app
    print("✓ app imported successfully")
except Exception as e:
    print("✗ app import failed:", type(e).__name__, str(e))
    import traceback
    print(traceback.format_exc())
