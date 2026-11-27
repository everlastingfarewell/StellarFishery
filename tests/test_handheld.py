"""CPU-only checks for handheld joystick controls and camera projection."""
import math
import struct
import unittest

import numpy as np

from stellar.handheld import Camera, Ocean, Stick


class HandheldTests(unittest.TestCase):
    def test_camera_movement_and_dead_zone(self):
        camera = Camera()
        camera.move([2000, -2000, 2000, -2000], 0.1)
        self.assertEqual(camera, Camera())
        camera.move([0, -32768, 0, 0], 0.1)
        self.assertAlmostEqual(camera.z, -11.4)
        camera.move([32767, 0, 0, 0], 0.1)
        self.assertAlmostEqual(camera.x, 0.6)
        camera = Camera(yaw=math.pi / 2)
        camera.move([0, -32768, 0, 0], 0.1)
        self.assertAlmostEqual(camera.x, 0.6)
        self.assertAlmostEqual(camera.z, -12)

    def test_diagonal_speed_and_time_steps(self):
        camera = Camera()
        camera.move([32767, -32768, 0, 0], 0.1)
        self.assertAlmostEqual(math.hypot(camera.x, camera.z + 12), 0.6)
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
            camera = Camera()
            r1, l1 = mapping.index(311), mapping.index(310)
            stick.event(struct.pack("=IhBB", 0, 1, 0x81, r1))
            camera.move([0] * 4, 0.1, stick.vertical)
            self.assertAlmostEqual(camera.height, 4.3)
            stick.event(struct.pack("=IhBB", 0, 1, 1, l1))
            self.assertEqual(stick.vertical, 0)
            stick.event(struct.pack("=IhBB", 0, 0, 1, r1))
            for _ in range(20):
                camera.move([0] * 4, 0.1, stick.vertical)
            self.assertEqual(camera.height, 0.5)
            stick.event(struct.pack("=IhBB", 0, 0, 1, l1))
            self.assertEqual(stick.vertical, 0)
        ocean = Ocean.for_display(1024, 768)
        baseline = np.asarray(ocean.frame(1))
        ocean.camera.height = 8
        raised = np.asarray(ocean.frame(1))
        self.assertFalse(np.array_equal(raised, baseline))
        self.assertTrue(np.isfinite(ocean.haze).all())
        ocean.camera.height = 4
        np.testing.assert_array_equal(ocean.frame(1), baseline)


if __name__ == "__main__":
    unittest.main()
