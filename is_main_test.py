
import sys

print(f"Hello from is_main_test.py!", file=sys.stderr)
print(f"__name__ = '{__name__}'", file=sys.stderr)
sys.stderr.flush()

if __name__ == "__main__":
    print("This is being run as the main script!", file=sys.stderr)
    sys.stderr.flush()
else:
    print("This is being imported as a module!", file=sys.stderr)
    sys.stderr.flush()
