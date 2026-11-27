"""Compatibility entry point for the original Brick deployment."""
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    env = dict(os.environ, PYTHONPATH=f"{root}:{root}/vendor", OPENBLAS_NUM_THREADS="1")
    os.execve(sys.executable, [sys.executable, "-m", "stellar.handheld", *sys.argv[1:]], env)
