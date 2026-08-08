"""Run tools/eval_kb.py with PMOS_EMBEDDINGS_* loaded from the user registry (setx).

Keeps the key out of the command line and visible output. On non-Windows systems
export the variables in your shell instead. Usage:

    python tools/eval_kb_api.py
"""
import os, subprocess, sys

names = ["PMOS_EMBEDDINGS_URL", "PMOS_EMBEDDINGS_KEY", "PMOS_EMBEDDINGS_MODEL"]
missing = [n for n in names if not os.environ.get(n)]

if missing and os.name == "nt":
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            for n in list(missing):
                try:
                    v, _ = winreg.QueryValueEx(k, n)
                    os.environ[n] = v
                    missing.remove(n)
                except FileNotFoundError:
                    pass
    except OSError:
        pass

if missing:
    print("missing embeddings env vars:", ", ".join(missing), file=sys.stderr)
    sys.exit(1)

print("embeddings env loaded (key hidden); running eval_kb.py with API vectors")
here = os.path.dirname(os.path.abspath(__file__))
sys.exit(subprocess.run([sys.executable, os.path.join(here, "eval_kb.py")]).returncode)
