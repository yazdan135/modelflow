
import sys
from app import app

print("Starting ModelFlow AI server via run.py...", file=sys.stderr)
sys.stderr.flush()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)
