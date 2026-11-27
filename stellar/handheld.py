"""CPU spectral ocean for the stock TrimUI framebuffer."""
import argparse
import math
import os
import select
import struct
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .waves import LENGTHS, SIZE, seeds
from dataclasses import dataclass


BEACH_SLOPE = math.tan(math.radians(10))
SEABED_SLOPE = math.tan(math.radians(15))
MAX_BEACH_HEIGHT = 4.0
SHORE_SPACING = 24.0
SHORE_OFFSETS = np.random.default_rng(419).uniform(-3, 3, 64).astype(np.float32) - 6


def shore_segment(z):
    segment = np.floor(np.asarray(z) / SHORE_SPACING).astype(np.int64)
    left = SHORE_OFFSETS[segment % len(SHORE_OFFSETS)]
    right = SHORE_OFFSETS[(segment + 1) % len(SHORE_OFFSETS)]
    gradient = (right - left) / SHORE_SPACING
    shore = left + gradient * (np.asarray(z) - segment * SHORE_SPACING)
    return shore, gradient


def bottom_height(x, z=0):
    shore, gradient = shore_segment(z)
    offshore = np.asarray(x) - shore
    slope = np.where(offshore >= 0, SEABED_SLOPE, BEACH_SLOPE)
    return np.minimum(-slope * offshore / np.sqrt(1 + gradient * gradient), MAX_BEACH_HEIGHT)


def terrain_hit(camera, down, right, forward=None, limit=250):
    """Intersect planar shore/seabed facets with shared polygon edges."""
    if forward is None:
        forward = np.zeros_like(down)
    end_z = camera.z + forward * limit
    first = math.floor(min(camera.z, float(end_z.min())) / SHORE_SPACING)
    last = math.floor(max(camera.z, float(end_z.max())) / SHORE_SPACING)
    hit = np.full(down.shape, np.inf, dtype=np.float32)
    for segment in range(first, last + 1):
        start_z = segment * SHORE_SPACING
        shore, gradient = shore_segment(start_z)
        offset = camera.x - shore - gradient * (camera.z - start_z)
        for offshore, slope in ((False, BEACH_SLOPE), (True, SEABED_SLOPE)):
            slope /= math.sqrt(1 + gradient * gradient)
            denominator = down - slope * (right - gradient * forward)
            travel = (camera.height + slope * offset) / np.where(abs(denominator) > 1e-8, denominator, 1e-8)
            z = camera.z + travel * forward
            side = offset + travel * (right - gradient * forward)
            valid = ((travel > 0) & (travel <= limit) & (z >= start_z)
                     & (z <= start_z + SHORE_SPACING) & ((side >= 0) if offshore else
                     ((side <= 0) & (-slope * side <= MAX_BEACH_HEIGHT))))
            hit = np.minimum(hit, np.where(valid, travel, np.inf))
    # Inland plateau uses the same height cap as camera collision.
    travel = (camera.height - MAX_BEACH_HEIGHT) / np.where(abs(down) > 1e-8, down, 1e-8)
    plateau = bottom_height(camera.x + right * travel, camera.z + forward * travel)
    valid = (travel > 0) & (travel <= limit) & (plateau >= MAX_BEACH_HEIGHT)
    hit = np.minimum(hit, np.where(valid, travel, np.inf))
    return hit


def caustic_strength(depth, distance):
    # Linear fades reach zero so invisible texture reads can stop.
    depth = np.asarray(depth, dtype=np.float16)
    distance = np.asarray(distance, dtype=np.float16)
    return np.clip((np.float16(16) - depth) / np.float16(14), 0, 1) * np.clip(
        (np.float16(18.2) - distance) / np.float16(15.4), 0, 1)


def sand_grain(x, z):
    # Cached world-space coarse albedo, requiring no texture samples.
    return 0.88 + 0.12 * ((np.floor(x * 9) * 13 + np.floor(z * 9) * 7) % 17) / 16


@dataclass
class Camera:
    x: float = 0.0
    z: float = -12.0
    yaw: float = 0.0
    pitch: float = 0.0
    height: float = 0.8

    def move(self, axes, seconds, vertical=0):
        # Linux joystick values are negative when pushed up or left.
        values = np.clip(np.asarray(axes, dtype=float) / 32767, -1, 1)
        values = np.sign(values) * np.maximum(np.abs(values) - 0.15, 0) / 0.85
        left_x, left_y, right_x, right_y = values
        seconds = min(max(seconds, 0), 0.1)
        self.height += vertical * 4.5 * seconds
        self.yaw = (self.yaw + right_x * 1.4 * seconds + math.pi) % (2 * math.pi) - math.pi
        self.pitch = float(np.clip(self.pitch - right_y * seconds, -1.2, 1.2))
        length = max(1.0, math.hypot(left_x, left_y))
        sideways, forward = left_x / length, -left_y / length
        self.x += (sideways * math.cos(self.yaw) + forward * math.sin(self.yaw)) * 9 * seconds
        self.z += (forward * math.cos(self.yaw) - sideways * math.sin(self.yaw)) * 9 * seconds
        self.constrain()

    def constrain(self):
        floor = float(bottom_height(self.x, self.z)) + 1.6
        # Shallow water and land require head clearance above the sea-level
        # cap. Follow the terrain there without restricting horizontal travel.
        ceiling = max(0.8, floor)
        self.height = min(ceiling, max(self.height, floor))


class Stick:
    def __init__(self, axis_map, button_map=()):
        # JSIOCGAXMAP reports ABS codes in joystick-event index order.
        pairs = ((0, 1, 3, 4), (0, 1, 2, 5))
        codes = next((pair for pair in pairs if all(code in axis_map for code in pair)), None)
        if codes is None:
            raise RuntimeError(f"Cannot identify both analog sticks in axis map {list(axis_map)}")
        self.indices = tuple(axis_map.index(code) for code in codes)
        self.values = [0, 0, 0, 0]
        # BTN_TL and BTN_TR identify L1 and R1 independently of event order.
        self.shoulders = tuple(button_map.index(code) if code in button_map else None for code in (310, 311))
        self.pressed = [False, False]

    @property
    def vertical(self):
        return int(self.pressed[1]) - int(self.pressed[0])

    def event(self, packet):
        _, value, kind, number = struct.unpack("=IhBB", packet)
        if kind & 0x7f == 2 and number in self.indices:
            self.values[self.indices.index(number)] = value
        if kind & 0x7f == 1 and number in self.shoulders:
            self.pressed[self.shoulders.index(number)] = bool(value)
        # Initialization events establish axis state, but never trigger exit.
        return kind == 1 and value != 0 and number in (6, 7) and number not in self.shoulders


class Ocean:
    @classmethod
    def for_display(cls, width, height):
        return cls(192, round(192 * height / width))

    def display_frame(self, seconds, size):
        return self.frame(seconds).resize(size, Image.Resampling.NEAREST)

    def __init__(self, width, height):
        self.camera = Camera()
        self.view = None
        self.caustics = None
        row, col = np.indices((height, width), dtype=np.float32)
        self.ray_down = (row / height - 0.26) * 0.82
        self.ray_right = (col - width / 2) / height * 0.82
        k = np.fft.fftfreq(SIZE) * SIZE * 2 * np.pi
        self.modes = seeds(5, 0.7, 12000, 4)
        self.slopes = []
        self.omega = []
        for length in LENGTHS:
            kx, kz = np.meshgrid(k / length, k / length)
            self.slopes.append(1j * np.stack((kx, kz)))
            self.omega.append(np.sqrt(9.81 * np.hypot(kx, kz)))
        self.update_view()

    def update_view(self):
        camera = self.camera
        camera.constrain()
        view = (camera.x, camera.z, camera.yaw, camera.pitch, camera.height)
        if view == self.view:
            return
        self.view = view
        # Intersect the view rays with the horizontal ocean plane.
        down = self.ray_down * math.cos(camera.pitch) - math.sin(camera.pitch)
        forward = math.cos(camera.pitch) + self.ray_down * math.sin(camera.pitch)
        if camera.height < 0:
            self.update_underwater_view(down, forward)
            return
        # Below the plane, upward rays intersect water. Keep ray travel
        # positive so haze remains bounded on either side of the surface.
        toward_water = down if camera.height >= 0 else -down
        self.sky = toward_water <= 0
        distance = abs(camera.height) / np.maximum(toward_water, 0.001)
        x = camera.x + (self.ray_right * math.cos(camera.yaw) + forward * math.sin(camera.yaw)) * distance
        z = camera.z + (forward * math.cos(camera.yaw) - self.ray_right * math.sin(camera.yaw)) * distance
        self.depth = np.clip(-bottom_height(x, z), 0, 6)
        self.haze = np.exp(-distance / 95)
        self.sky_color = np.stack((133 - 96*down, 171 - 46*down, 192 - 38*down), axis=-1)
        right = self.ray_right * math.cos(camera.yaw) + forward * math.sin(camera.yaw)
        world_forward = forward * math.cos(camera.yaw) - self.ray_right * math.sin(camera.yaw)
        land_distance = terrain_hit(camera, down, right, world_forward)
        land_x = camera.x + right * np.minimum(land_distance, 10000)
        self.land = np.isfinite(land_distance) & ((land_distance < distance) | self.sky)
        land_z = camera.z + (forward * math.cos(camera.yaw) - self.ray_right * math.sin(camera.yaw)) * np.minimum(land_distance, 10000)
        grain = sand_grain(land_x, land_z)
        self.land_color = grain[..., None] * np.array((186, 169, 126), dtype=np.float32)
        land_fog = np.clip(land_distance / 250, 0, 1)[..., None]
        self.land_color = self.land_color * (1 - land_fog) + self.sky_color * land_fog
        self.samples = []
        for length in LENGTHS:
            u, v = (x % length) * SIZE / length, (z % length) * SIZE / length
            i, j = np.floor(u).astype(int), np.floor(v).astype(int)
            self.samples.append((i % SIZE, j % SIZE, (u-i).astype(np.float32), (v-j).astype(np.float32)))

    def update_underwater_view(self, down, forward):
        """Cache curved seabed intersections and the flat water ceiling."""
        if self.caustics is None:
            with Image.open(Path(__file__).with_name("caustics.png")) as texture:
                self.caustics = np.asarray(texture.convert("L")).copy()
        camera = self.camera
        right = self.ray_right * math.cos(camera.yaw) + forward * math.sin(camera.yaw)
        world_forward = forward * math.cos(camera.yaw) - self.ray_right * math.sin(camera.yaw)
        bed_distance = terrain_hit(camera, down, right, world_forward, limit=32)
        ceiling_distance = -camera.height / np.maximum(-down, 0.001)
        ceiling = down < 0
        bed = np.isfinite(bed_distance) & (~ceiling | (bed_distance < ceiling_distance))
        distance = np.where(bed, bed_distance, np.where(ceiling, ceiling_distance, 32))
        # Linear distance fog and a single depth tint replace optical integration.
        # World projection stays float32; UV, color and fog work uses float16.
        fog = np.clip((distance - 2) / 26, 0, 1).astype(np.float16)
        depth = np.float16(min(-camera.height / 40, 1))
        self.underwater_fog_color = np.array((9, 57, 68), dtype=np.float16) * (1 - depth * np.float16(0.8))
        self.underwater_base = np.empty((*down.shape, 3), dtype=np.float16)
        self.underwater_base[:] = np.array((48, 119, 127), dtype=np.float16)
        self.underwater_base[bed] = np.array((112, 142, 111), dtype=np.float16)
        ground_x = camera.x + right * np.minimum(bed_distance, 32)
        ground_z = camera.z + (forward * math.cos(camera.yaw) - self.ray_right * math.sin(camera.yaw)) * np.minimum(bed_distance, 32)
        self.underwater_base[bed] *= sand_grain(ground_x[bed], ground_z[bed]).astype(np.float16)[:, None]
        self.underwater_base *= np.array((1 - depth * np.float16(0.8), 1 - depth * np.float16(0.4),
                                          1 - depth * np.float16(0.2)), dtype=np.float16)
        self.underwater_base *= (1 - fog[..., None])
        self.underwater_fog = fog[..., None] * self.underwater_fog_color
        strength = caustic_strength(np.clip(-bottom_height(ground_x, ground_z), 0, 1000), np.minimum(distance, 32))
        self.caustic_pixels = bed & (fog < 1) & (strength > 0)
        self.caustic_fade = strength[self.caustic_pixels]
        travel = distance[self.caustic_pixels]
        x = camera.x + (self.ray_right[self.caustic_pixels] * math.cos(camera.yaw)
                        + forward[self.caustic_pixels] * math.sin(camera.yaw)) * travel
        z = camera.z + (forward[self.caustic_pixels] * math.cos(camera.yaw)
                        - self.ray_right[self.caustic_pixels] * math.sin(camera.yaw)) * travel
        self.caustic_u = ((x % 6) / 6).astype(np.float16)
        self.caustic_v = ((z % 6) / 6).astype(np.float16)

    def underwater_frame(self, seconds):
        # Exactly one nearest texture lookup per visible seabed pixel.
        height, width = self.caustics.shape
        u = (self.caustic_u + np.float16((seconds * 0.025) % 1)) % np.float16(1)
        v = (self.caustic_v + np.float16((seconds * 0.018) % 1)) % np.float16(1)
        pattern = self.caustics[(v * height).astype(np.intp), (u * width).astype(np.intp)]
        factor = 1 + (np.float16(-0.22) + pattern.astype(np.float16) * np.float16(0.8 / 255)) * self.caustic_fade
        color = self.underwater_base.copy()
        color[self.caustic_pixels] *= factor[:, None]
        color += self.underwater_fog
        return Image.fromarray(np.clip(color, 0, 255).astype(np.uint8))

    def frame(self, seconds):
        self.update_view()
        if self.camera.height < 0:
            return self.underwater_frame(seconds)
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
        color[self.land] = self.land_color[self.land]
        return Image.fromarray(np.clip(color, 0, 255).astype(np.uint8))


def run(frames, initial_height=0.8):
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
        ocean = Ocean.for_display(width, height)
        ocean.camera.height = initial_height
        with mmap.mmap(fb.fileno(), stride * geometry()[3], access=mmap.ACCESS_WRITE) as display:
            stick = os.open("/dev/input/js0", os.O_RDONLY | os.O_NONBLOCK)
            start = time.monotonic()
            count = 0
            try:
                axis_count = fcntl.ioctl(stick, 0x80016a11, bytes(1))[0]
                axis_map = fcntl.ioctl(stick, 0x80406a32, bytes(64))[:axis_count]
                button_count = fcntl.ioctl(stick, 0x80016a12, bytes(1))[0]
                button_map = struct.unpack("=512H", fcntl.ioctl(stick, 0x84006a34, bytes(1024)))[:button_count]
                controls = Stick(axis_map, button_map)
                print(f"Stick axes LX/LY/RX/RY: {controls.indices}", flush=True)
                print(f"Height buttons L1/R1: {controls.shoulders}", flush=True)
                previous = start
                while frames == 0 or count < frames:
                    while select.select([stick], [], [], 0)[0]:
                        if controls.event(os.read(stick, 8)):
                            return
                    now = time.monotonic()
                    ocean.camera.move(controls.values, now - previous, controls.vertical)
                    previous = now
                    image = ocean.display_frame(now-start, (width, height))
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


def window(height=0.8):
    import tkinter as tk
    from PIL import ImageTk

    root = tk.Tk()
    root.title("StellarFishery — Brick Pro handheld renderer")
    root.resizable(False, False)
    label = tk.Label(root, borderwidth=0)
    label.pack()
    root.bind("<Escape>", lambda event: root.destroy())
    ocean = Ocean.for_display(1024, 768)
    ocean.camera.height = height
    start = time.monotonic()

    def update():
        label.image = ImageTk.PhotoImage(ocean.display_frame(time.monotonic() - start, (1024, 768)))
        label.configure(image=label.image)
        root.after(16, update)

    update()
    root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--frames", type=int, default=0, help="stop after this many frames (0 runs continuously)")
    mode.add_argument("--preview", metavar="PNG", help="save one Brick-sized PNG on this computer")
    mode.add_argument("--window", action="store_true", help="animate the handheld renderer in a desktop window")
    parser.add_argument("--time", type=float, metavar="SECONDS", help="preview time in seconds (default 0)")
    parser.add_argument("--height", type=float, default=0.8, metavar="METRES",
                        help="initial camera height; negative values start underwater")
    args = parser.parse_args()
    if args.time is not None and (not args.preview or not math.isfinite(args.time) or args.time < 0):
        parser.error("--time requires --preview and a finite, nonnegative value")
    if args.frames < 0:
        parser.error("--frames must be nonnegative")
    if not math.isfinite(args.height):
        parser.error("--height must be finite")
    if args.preview:
        size = (1024, 768)
        ocean = Ocean.for_display(*size)
        ocean.camera.height = args.height
        ocean.display_frame(args.time or 0, size).save(args.preview, format="PNG")
    elif args.window:
        window(args.height)
    else:
        run(args.frames, args.height)
