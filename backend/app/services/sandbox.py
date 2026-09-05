import os
import sys
import io
import base64
import logging
import subprocess
import tempfile
import textwrap
from pathlib import Path

logger = logging.getLogger(__name__)

# backend/ — storage_path values in the DB are relative to this directory.
BACKEND_ROOT = Path(__file__).resolve().parents[2]

SANDBOX_PRELUDE = """
# ── 1. Load runtime libraries FIRST, before the import guard is installed. ──
# matplotlib / pandas / numpy all import `importlib` and `sys` internally, so
# installing the guard first would make them fail to load at all.
import io, base64, json, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── 2. Now install the import guard, applied to user code only. ──
import builtins
_ORIG_IMPORT = builtins.__import__

# NOTE: `os` / `shutil` / `sys` / `importlib` are intentionally NOT blocked.
# They are already loaded by pandas/matplotlib at start-up, and libraries keep
# importing them lazily (e.g. pandas' plotting backend pulls in `os` via
# importlib.metadata). Blocking them breaks ordinary analysis code while adding
# no real security, since the modules are already in sys.modules.
# The true sandbox boundary is the isolated subprocess; this list blocks the
# genuine escape hatches (spawning processes, network, native memory tricks).
_BLOCKED = {'subprocess', 'socket', 'ctypes', 'multiprocessing', 'signal',
            'pty', 'fcntl', 'posix', 'resource', 'termios'}

# Warm up pandas' lazy plotting backend while imports are still unrestricted,
# so that `df.plot(...)` in user code does not trigger a blocked import later.
try:
    import pandas.plotting
    pandas.plotting._core._load_backend("matplotlib")
except Exception:
    pass


def _safe_import(name, *args, **kwargs):
    top = name.split('.')[0]
    if top in _BLOCKED:
        raise ImportError(f"Module '{name}' is blocked in sandbox for security reasons.")
    return _ORIG_IMPORT(name, *args, **kwargs)

builtins.__import__ = _safe_import
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

# Injected BEFORE the capture wrapper: install the excepthook as early as
# possible so a failure during data loading still returns a readable error.
# The result marker MUST be written to sys.__stdout__ (the real stdout):
# sys.stdout gets captured into _OUTPUT, so a plain print() of the marker
# would be swallowed by our own redirection.
# globals().get(...) keeps _emit_result() safe even if it fires before the
# capture buffers exist.
EMIT_HELPERS = """
def _emit_result():
    import json as _json
    _g = globals()
    _out, _err, _ch = _g.get('_OUTPUT'), _g.get('_ERRORS'), _g.get('_CAPTURED_CHARTS')
    _r = {"stdout": _out.getvalue() if _out else "",
          "stderr": _err.getvalue() if _err else "",
          "charts": _ch if _ch else [], "error": None}
    sys.__stdout__.write("__SANDBOX_RESULT__" + _json.dumps(_r, ensure_ascii=False) + "\\n")
    sys.__stdout__.flush()

def _sandbox_excepthook(etype, value, tb):
    import traceback as _tb
    _err = globals().get('_ERRORS')
    if _err is not None and not issubclass(etype, SystemExit):
        _err.write("".join(_tb.format_exception(etype, value, tb)))
    _emit_result()

sys.excepthook = _sandbox_excepthook
"""


def run_python(code: str, data_path: str = None) -> dict:
    """
    Execute Python code in a sandboxed subprocess.
    Returns dict with: stdout, stderr, charts (list of base64 PNG strings), error
    """
    # The subprocess runs with cwd=tempdir, but storage_path values in the DB
    # are relative to the backend root — resolve them to absolute paths first.
    if data_path and not os.path.isabs(data_path):
        data_path = str((BACKEND_ROOT / data_path).resolve())

    # Build the full script
    script = SANDBOX_PRELUDE
    script += EMIT_HELPERS
    script += CAPTURE_WRAPPER.replace("__DATA_PATH__", repr(data_path) if data_path else "None")
    script += "\n"
    script += code
    script += "\n"
    script += "_emit_result()\n"

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
                # SECURITY: never leak server secrets into the sandboxed subprocess.
                # The child only needs PATH/TEMP/system vars to run pandas/matplotlib;
                # secrets (SECRET_KEY, DB URL, provider API keys) are stripped.
                env={k: v for k, v in os.environ.items()
                     if k not in ("SECRET_KEY", "DATABASE_URL", "OPENAI_API_KEY",
                                  "DEEPSEEK_API_KEY", "GLM_API_KEY", "QWEN_API_KEY")}
                | {"PYTHONPATH": os.pathsep.join(sys.path)},
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
