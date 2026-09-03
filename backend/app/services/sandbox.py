import os
import sys
import io
import base64
import logging
import subprocess
import tempfile
import textwrap

logger = logging.getLogger(__name__)

SANDBOX_PRELUDE = """
import builtins
_ORIG_IMPORT = builtins.__import__

_BLOCKED = {'os', 'subprocess', 'socket', 'shutil', 'sys', 'importlib', 'ctypes', 'multiprocessing', 'signal', 'pty', 'fcntl', 'posix', 'resource', 'termios'}

def _safe_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top in _BLOCKED:
        raise ImportError(f"Module '{name}' is blocked in sandbox for security reasons.")
    # Allow matplotlib for charts
    if name.startswith('matplotlib'):
        pass
    return _ORIG_IMPORT(name, *args, **kwargs)

builtins.__import__ = _safe_import

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
"""

CAPTURE_WRAPPER = """
import io, base64, sys, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# Capture stdout/stderr
_OUTPUT = io.StringIO()
_ERRORS = io.StringIO()
sys.stdout = _OUTPUT
sys.stderr = _ERRORS
_orig_show = plt.show
def _capture_show(*args, **kwargs):
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode('utf-8')
    _CAPTURED_CHARTS.append(b64)
    buf.close()
    plt.close('all')
plt.show = _capture_show

_CAPTURED_CHARTS = []

import numpy as np
import pandas as pd
import json

# Load data if provided
_DATA = None
if __DATA_PATH__:
    import pandas as pd
    path = __DATA_PATH__
    if path.endswith('.csv'):
        _DATA = pd.read_csv(path)
    elif path.endswith(('.xlsx', '.xls')):
        _DATA = pd.read_excel(path)
"""


def run_python(code: str, data_path: str = None) -> dict:
    """
    Execute Python code in a sandboxed subprocess.
    Returns dict with: stdout, stderr, charts (list of base64 PNG strings), error
    """
    # Build the full script
    script = SANDBOX_PRELUDE
    script += CAPTURE_WRAPPER.replace("__DATA_PATH__", repr(data_path) if data_path else "None")
    script += "\n"
    script += code
    script += "\n"
    script += """
_RESULT = {"stdout": _OUTPUT.getvalue(), "stderr": _ERRORS.getvalue(), "charts": _CAPTURED_CHARTS, "error": None}
print("__SANDBOX_RESULT__" + json.dumps(_RESULT, ensure_ascii=False))
"""

    script = textwrap.dedent(script)

    with tempfile.TemporaryDirectory() as tmpdir:
        script_path = os.path.join(tmpdir, "script.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script)

        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=tmpdir,
                env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
            )
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "",
                "charts": [],
                "error": "Code execution timed out (30 seconds limit).",
            }
        except Exception as e:
            logger.error(f"Sandbox error: {e}")
            return {
                "stdout": "",
                "stderr": "",
                "charts": [],
                "error": f"Sandbox execution error: {str(e)}",
            }

    # Parse the output
    stdout = result.stdout
    stderr = result.stderr

    # Try to extract the JSON result
    import json
    marker = "__SANDBOX_RESULT__"
    charts = []
    error = None

    if marker in stdout:
        idx = stdout.index(marker)
        json_str = stdout[idx + len(marker):].strip()
        output_before = stdout[:idx]
        try:
            parsed = json.loads(json_str)
            output_before = parsed.get("stdout", output_before)
            stderr = parsed.get("stderr", stderr) or stderr
            charts = parsed.get("charts", [])
            error = parsed.get("error")
        except json.JSONDecodeError:
            error = "Failed to parse sandbox result."

        stdout = output_before

    if result.returncode != 0 and not error:
        error = stderr or f"Process exited with code {result.returncode}"

    return {
        "stdout": stdout.strip(),
        "stderr": stderr.strip() if stderr else "",
        "charts": charts,
        "error": error,
    }
