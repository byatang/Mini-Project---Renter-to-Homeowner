"""Both scripts must open with the disclaimer, word for word.

The API keys are blanked for these runs, so nothing calls FRED or Gemini: the rate falls
back to the default and the AI step reports "unavailable".
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from renters import DISCLAIMER

PROJECT = Path(__file__).parent
EXACT = "Educational tool, not personalized financial advice. Rates shown are not guaranteed."


def test_disclaimer_text_is_exact():
    assert DISCLAIMER == EXACT


@pytest.mark.parametrize("script", ["demo.py", "advisor.py"])
def test_script_prints_disclaimer_first(script):
    env = {**os.environ, "GEMINI_API_KEY": "", "FRED_API_KEY": "", "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run([sys.executable, script], cwd=PROJECT, env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == EXACT
