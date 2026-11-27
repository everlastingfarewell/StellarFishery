"""Offline bake of a periodic caustics tile; never run by the renderer."""
from pathlib import Path

import numpy as np
from PIL import Image


def bake():
    size = 128
    rng = np.random.default_rng(719)
    points = rng.uniform(0, 1, (24, 2))
    y, x = np.indices((size, size), dtype=np.float32) / size
    distances = []
    for px, py in points:
        dx = (x - px + 0.5) % 1 - 0.5
        dy = (y - py + 0.5) % 1 - 0.5
        distances.append(np.hypot(dx, dy))
    nearest = np.partition(distances, 1, axis=0)[:2]
    # Soft bright cell boundaries form a seamless, pre-baked light network.
    ridge = np.exp(-((nearest[1] - nearest[0]) / 0.012) ** 2)
    tile = Image.fromarray(np.round(ridge * 255).astype(np.uint8))
    tile.save(Path(__file__).resolve().parents[1] / "stellar" / "caustics.png")


if __name__ == "__main__":
    bake()
