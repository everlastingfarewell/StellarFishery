"""CPU spectral ocean for the stock TrimUI framebuffer."""
import argparse
import os
import select
import struct
import time

import numpy as np
from PIL import Image

from .waves import LENGTHS, SIZE, seeds


class Ocean:
    def __init__(self, width, height):
        row, col = np.indices((height, width), dtype=np.float32)
        # View rays cross a horizontal ocean from a camera four metres up.
        down = (row / height - 0.26) * 0.82
        self.sky = down <= 0
        distance = 4 / np.maximum(down, 0.001)
        x = (col - width / 2) / height * 0.82 * distance
        z = distance - 12
        self.depth = np.clip(0.32 * (x + 6), 0, 6)
        self.haze = np.exp(-distance / 95)
        self.sky_color = np.stack((133 - 96*down, 171 - 46*down, 192 - 38*down), axis=-1)
        self.samples = []
        k = np.fft.fftfreq(SIZE) * SIZE * 2 * np.pi
        self.modes = seeds(5, 0.7, 12000, 4)
        self.slopes = []
        self.omega = []
        for length in LENGTHS:
            u, v = x * SIZE / length, z * SIZE / length
            i, j = np.floor(u).astype(int), np.floor(v).astype(int)
            self.samples.append((i % SIZE, j % SIZE, (u-i).astype(np.float32), (v-j).astype(np.float32)))
            kx, kz = np.meshgrid(k / length, k / length)
            self.slopes.append(1j * np.stack((kx, kz)))
            self.omega.append(np.sqrt(9.81 * np.hypot(kx, kz)))

    def frame(self, seconds):
        slopes = np.zeros((2, *self.depth.shape), dtype=np.float32)
        for mode, omega, gradient, sample in zip(self.modes, self.omega, self.slopes, self.samples):
            phased = mode * np.exp(-1j * omega * seconds)
            # Twice the real part includes the conjugate modes used by fft.wgsl.
            field = 2 * np.fft.ifft2(gradient * phased, norm="forward").real.astype(np.float32)
            i, j, u, v = sample
            right, below = (i+1) % SIZE, (j+1) % SIZE
            top = field[:, j, i]*(1-u) + field[:, j, right]*u
            bottom = field[:, below, i]*(1-u) + field[:, below, right]*u
            slopes += top*(1-v) + bottom*v
        sx, sz = slopes
        light = np.clip(0.46 + 2*sx + sz, 0, 1)
        shallow = np.exp(-self.depth * 0.85)
        glint = np.maximum(0, light - 0.72)**2 * 1100
        water = np.stack((9+56*shallow+23*light, 46+85*shallow+58*light,
                          61+36*shallow+61*light), axis=-1) + glint[..., None]
        water[self.depth == 0] = (186, 169, 126)
        color = water*self.haze[..., None] + self.sky_color*(1-self.haze[..., None])
        color[self.sky] = self.sky_color[self.sky]
        return Image.fromarray(np.clip(color, 0, 255).astype(np.uint8))


def run(frames):
    import fcntl
    import mmap

    with open("/dev/fb0", "r+b", buffering=0) as fb:
        def geometry():
            return struct.unpack_from("=13I", fcntl.ioctl(fb, 0x4600, bytes(160)))
        width, height, _, _, _, _, bits, _, red, red_bits, _, green, green_bits = geometry()
        if (bits, red, red_bits, green, green_bits) != (32, 16, 8, 8, 8):
            raise RuntimeError("Expected the TG4040 32-bit framebuffer")
        with open("/sys/class/graphics/fb0/stride") as source:
            stride = int(source.read())
        ocean = Ocean(192, round(192 * height / width))
        with mmap.mmap(fb.fileno(), stride * geometry()[3], access=mmap.ACCESS_WRITE) as display:
            stick = os.open("/dev/input/js0", os.O_RDONLY | os.O_NONBLOCK)
            start = time.monotonic()
            count = 0
            try:
                while frames == 0 or count < frames:
                    while select.select([stick], [], [], 0)[0]:
                        _, value, kind, button = struct.unpack("=IhBB", os.read(stick, 8))
                        if kind == 1 and value and button in (6, 7):
                            return
                    image = ocean.frame(time.monotonic()-start).resize((width, height), Image.Resampling.NEAREST)
                    raw = image.convert("RGBA").tobytes("raw", "BGRA")
                    x, y = geometry()[4:6]
                    offset = y * stride + x * 4
                    if stride == width * 4:
                        display[offset:offset+len(raw)] = raw
                    else:
                        for row in range(height):
                            pos = offset + row * stride
                            display[pos:pos+width*4] = raw[row*width*4:(row+1)*width*4]
                    count += 1
            finally:
                os.close(stick)
            print(f"{count} frames in {time.monotonic()-start:.2f}s", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", type=int, default=0, help="stop after this many frames (0 runs continuously)")
    run(parser.parse_args().frames)
