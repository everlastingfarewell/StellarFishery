"""Paths, grid constants and platform helpers shared by every module."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path(__file__).resolve().parent
SHADERS = ROOT / "shaders"
SPV = ROOT / "spv"
DATA = ROOT / "data"
PLATFORM_FILE = DATA / "platform.npy"

# Surface grid: metres, seconds and newtons throughout the project.
N, DX, SPEED = 128, 0.125, 3.0
DT = 0.4 * DX / SPEED
MASS = 1000 * DX**2 * 0.08
DENSITY = 1000.0
CONTACT_THICKNESS = 0.08
