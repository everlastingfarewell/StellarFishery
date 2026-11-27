"""CPU-only checks for handheld joystick controls and camera projection."""
import math
import struct
import unittest
from unittest.mock import patch

import numpy as np

from stellar.handheld import Camera, Ocean, Stick, bottom_height, terrain_hit, shore_segment, caustic_strength


class HandheldTests(unittest.TestCase):
    def test_camera_movement_and_dead_zone(self):
        camera = Camera()
        camera.move([2000, -2000, 2000, -2000], 0.1)
        self.assertEqual(camera, Camera())
        camera.move([0, -32768, 0, 0], 0.1)
        self.assertAlmostEqual(camera.z, -11.1)
        camera.move([32767, 0, 0, 0], 0.1)
        self.assertAlmostEqual(camera.x, 0.9)
        camera = Camera(yaw=math.pi / 2)
        camera.move([0, -32768, 0, 0], 0.1)
        self.assertAlmostEqual(camera.x, 0.9)
        self.assertAlmostEqual(camera.z, -12)

    def test_diagonal_speed_and_time_steps(self):
        camera = Camera()
        camera.move([32767, -32768, 0, 0], 0.1)
        self.assertAlmostEqual(math.hypot(camera.x, camera.z + 12), 0.9)
        fine, coarse = Camera(), Camera()
        for _ in range(20):
            fine.move([0, -32768, 0, 0], 0.05)
        for _ in range(10):
            coarse.move([0, -32768, 0, 0], 0.1)
        self.assertAlmostEqual(fine.z, coarse.z)

    def test_look_direction_and_limits(self):
        camera = Camera()
        camera.move([0, 0, 32767, -32768], 0.1)
        self.assertGreater(camera.yaw, 0)
        self.assertGreater(camera.pitch, 0)
        for _ in range(100):
            camera.move([0, 0, 32767, -32768], 0.1)
        self.assertEqual(camera.pitch, 1.2)
        self.assertLessEqual(abs(camera.yaw), math.pi)

    def test_axis_mapping_initialization_and_exit(self):
        for mapping in (bytes([16, 17, 0, 1, 3, 4]), bytes([0, 1, 2, 5, 16, 17])):
            stick = Stick(mapping)
            for slot, index in enumerate(stick.indices):
                self.assertFalse(stick.event(struct.pack("=IhBB", 0, -12345, 0x82, index)))
                self.assertEqual(stick.values[slot], -12345)
                stick.event(struct.pack("=IhBB", 0, 0, 2, index))
                self.assertEqual(stick.values[slot], 0)
            self.assertFalse(stick.event(struct.pack("=IhBB", 0, 1, 0x81, 6)))
            self.assertTrue(stick.event(struct.pack("=IhBB", 0, 1, 1, 6)))
        with self.assertRaises(RuntimeError):
            Stick(bytes([0, 1]))

    def test_projection_tracks_camera(self):
        ocean = Ocean.for_display(1024, 768)
        baseline = np.asarray(ocean.frame(1))
        sky_pixels = ocean.sky.sum()
        for camera in (Camera(x=4), Camera(z=0), Camera(yaw=0.5), Camera(pitch=0.4)):
            ocean.camera = camera
            frame = np.asarray(ocean.frame(1))
            self.assertEqual(frame.shape, (144, 192, 3))
            self.assertFalse(np.array_equal(frame, baseline))
        self.assertGreater(ocean.sky.sum(), sky_pixels)
        for pitch in (-1.2, 1.2):
            ocean.camera.pitch = pitch
            ocean.frame(1)
            self.assertTrue(np.isfinite(ocean.haze).all())
        ocean.camera = Camera()
        np.testing.assert_array_equal(ocean.frame(1), baseline)

    def test_height_buttons_and_projection(self):
        # Include a reordered map to catch reliance on fixed button indices.
        for mapping in ((304, 305, 307, 308, 310, 311, 314, 315), (311, 304, 310)):
            stick = Stick(bytes([0, 1, 3, 4]), mapping)
            camera = Camera(x=8, height=-0.5)
            r1, l1 = mapping.index(311), mapping.index(310)
            stick.event(struct.pack("=IhBB", 0, 1, 0x81, r1))
            camera.move([0] * 4, 0.1, stick.vertical)
            self.assertAlmostEqual(camera.height, -0.05)
            stick.event(struct.pack("=IhBB", 0, 1, 1, l1))
            self.assertEqual(stick.vertical, 0)
            stick.event(struct.pack("=IhBB", 0, 0, 1, r1))
            for _ in range(20):
                camera.move([0] * 4, 0.1, stick.vertical)
            self.assertAlmostEqual(camera.height, float(bottom_height(camera.x, camera.z)) + 1.6)
            stick.event(struct.pack("=IhBB", 0, 0, 1, l1))
            self.assertEqual(stick.vertical, 0)
        ocean = Ocean.for_display(1024, 768)
        baseline = np.asarray(ocean.frame(1))
        ocean.camera.height = 0.3
        raised = np.asarray(ocean.frame(1))
        self.assertFalse(np.array_equal(raised, baseline))
        self.assertTrue(np.isfinite(ocean.haze).all())
        ocean.camera.height = 4
        np.testing.assert_array_equal(ocean.frame(1), baseline)

    def test_bounded_height_crosses_surface(self):
        ocean = Ocean.for_display(1024, 768)
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            for height in (0.01, 0, -0.01, -4, -10000, 10000):
                ocean.camera.height = height
                ocean.frame(1)
                self.assertTrue(np.isfinite(ocean.haze).all())
                self.assertTrue(((ocean.haze >= 0) & (ocean.haze <= 1)).all())
        camera = Camera(height=10000)
        camera.move([0] * 4, 0.1, 1)
        self.assertAlmostEqual(camera.height, 0.8)

    def test_shoulders_do_not_exit_at_legacy_indices(self):
        stick = Stick(bytes([0, 1, 3, 4]), (304, 305, 307, 308, 314, 315, 310, 311))
        self.assertFalse(stick.event(struct.pack("=IhBB", 0, 1, 1, 7)))
        self.assertEqual(stick.vertical, 1)

    def test_underwater_skips_surface_work_and_resumes(self):
        ocean = Ocean.for_display(1024, 768)
        ocean.camera.x = 8
        baseline = np.asarray(ocean.frame(1))
        self.assertIsNone(ocean.caustics)
        ocean.camera.height = -2
        with patch("numpy.fft.ifft2", side_effect=AssertionError("Underwater FFT")), \
             patch("numpy.exp", side_effect=AssertionError("Underwater exponential")):
            first = np.asarray(ocean.frame(1))
            second = np.asarray(ocean.frame(4))
        self.assertFalse(np.array_equal(first, second))
        self.assertEqual(ocean.caustics.shape, (128, 128))
        self.assertEqual(ocean.caustics.dtype, np.uint8)
        self.assertEqual(ocean.underwater_base.dtype, np.float16)
        self.assertEqual(ocean.caustic_u.dtype, np.float16)
        ocean.camera.height = 4
        with patch.object(ocean, "underwater_frame", side_effect=AssertionError("Above-water caustics")):
            np.testing.assert_array_equal(ocean.frame(1), baseline)

    def test_underwater_projection_and_deep_fog(self):
        ocean = Ocean.for_display(1024, 768)
        ocean.camera.x = 8
        ocean.camera.height = -2
        baseline = np.asarray(ocean.frame(1))
        ocean.camera.x += 2
        self.assertFalse(np.array_equal(ocean.frame(1), baseline))
        ocean.camera.height = -10000
        ocean.camera.x = 2000
        deep = np.asarray(ocean.frame(1))
        self.assertLess(deep.mean(), baseline.mean())
        self.assertFalse(ocean.caustic_pixels.any())
        np.testing.assert_array_equal(deep, ocean.frame(8))
        for height in (-0.0001, -6, -6.0001, -10000):
            for pitch in (-1.2, 0, 1.2):
                ocean.camera.height, ocean.camera.pitch = height, pitch
                with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
                    frame = np.asarray(ocean.frame(1e8))
                self.assertEqual(frame.shape, (144, 192, 3))
                self.assertTrue(np.isfinite(ocean.underwater_base).all())

    def test_bottom_clearance_and_shore(self):
        camera = Camera(x=0, height=-100)
        camera.move([0] * 4, 0.1, -1)
        self.assertAlmostEqual(camera.height - bottom_height(camera.x, camera.z), 1.6)
        for _ in range(100):
            camera.move([-32768, 0, 0, 0], 0.1, -1)
            self.assertGreaterEqual(camera.height - bottom_height(camera.x, camera.z), 1.6 - 1e-6)
            self.assertLessEqual(camera.height, max(0.8, float(bottom_height(camera.x, camera.z)) + 1.6))
        shore, _ = shore_segment(0)
        self.assertEqual(bottom_height(shore), 0)
        self.assertGreater(bottom_height(-10), 0)
        self.assertEqual(bottom_height(-100), 4)
        self.assertLess(bottom_height(20), bottom_height(0))
        for x in (-100, -20, 0, 20):
            camera = Camera(x=x, height=10)
            hit = terrain_hit(camera, np.array([1.0]), np.array([0.0]))[0]
            self.assertAlmostEqual(10 - hit, bottom_height(x, camera.z), places=4)


    def test_facet_angles_and_caustic_fade(self):
        for z in (-57, 5, 39):
            shore, _ = shore_segment(z)
            for x, angle in ((shore - 8, 10), (shore + 8, 15)):
                dx = (bottom_height(x + 0.01, z) - bottom_height(x, z)) / 0.01
                dz = (bottom_height(x, z + 0.01) - bottom_height(x, z)) / 0.01
                self.assertAlmostEqual(math.degrees(math.atan(math.hypot(dx, dz))), angle, places=3)
        self.assertNotEqual(shore_segment(5)[0], shore_segment(39)[0])
        fade = caustic_strength(np.array([2, 8, 16]), np.array([4, 4, 4]))
        self.assertTrue(np.all(np.diff(fade) < 0))
        self.assertEqual(fade[-1], 0)
        self.assertEqual(caustic_strength(2, 18.2), 0)

    def test_walk_onshore_and_return_to_water(self):
        camera = Camera()
        start_x = camera.x
        for _ in range(30):
            camera.move([-32768, 0, 0, 0], 0.1, -1)
        self.assertAlmostEqual(camera.x, start_x - 27)
        self.assertGreater(bottom_height(camera.x, camera.z), 0)
        self.assertAlmostEqual(camera.height, bottom_height(camera.x, camera.z) + 1.6)
        for _ in range(40):
            camera.move([32767, 0, 0, 0], 0.1)
        self.assertAlmostEqual(camera.x, start_x + 9)
        self.assertLessEqual(camera.height, 0.8)
        for _ in range(20):
            camera.move([0] * 4, 0.1, -1)
        self.assertLess(camera.height, 0)
        self.assertGreaterEqual(camera.height, bottom_height(camera.x, camera.z) + 1.6 - 1e-6)


if __name__ == "__main__":
    unittest.main()
