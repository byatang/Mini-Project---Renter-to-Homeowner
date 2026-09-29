"""Hook 3: run the test suite after any file edit. Skip quietly if there are no tests.

Passing tests -> a one-line note. Failing tests -> exit code 2, so Claude sees the
failures and fixes them before moving on.
"""

import json
import os
import subprocess
import sys

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.join(os.path.dirname(__file__), "..", "..")
SKIP_DIRS = {".venv", ".git", "__pycache__", ".pytest_cache", "node_modules"}


def has_tests():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if any(f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")) for f in files):
            return True
    return False


def main():
    json.load(sys.stdin)  # the edit details; not needed, but read so the pipe closes cleanly
    if not has_tests():
        return

    venv_python = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    python = venv_python if os.path.exists(venv_python) else sys.executable
    result = subprocess.run([python, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
                            cwd=ROOT, capture_output=True, text=True, timeout=110)
    lines = result.stdout.strip().splitlines()
    summary = lines[-1] if lines else "no output"

    if result.returncode in (0, 5):  # 5 = pytest found no tests
        print(json.dumps({"systemMessage": f"Tests after edit: {summary}"}))
        return
    print("Tests FAILED after this edit:\n" + "\n".join(lines[-40:]) + result.stderr[-2000:],
          file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
