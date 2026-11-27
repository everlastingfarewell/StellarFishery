"""Interactive ocean demo: orbit camera, sun controls and water impacts."""
import math
import time

import numpy as np

from stellar.config import DT
from stellar.renderer import OceanRenderer
from stellar.simulation import Contact


class Camera:
    """Orbit camera looking at the water from about ten metres away."""

    def __init__(self):
        self.target = np.zeros(3)
        self.yaw, self.pitch, self.distance = 0.55, 0.73, 10.0

    def basis(self):
        """Eye position, right and up vectors, view direction for the current orbit."""
        s, c = math.sin(self.yaw), math.cos(self.yaw)
        back = np.array([s * math.cos(self.pitch), math.sin(self.pitch), c * math.cos(self.pitch)])
        right = np.array([c, 0, -s])
        return self.target + self.distance * back, right, np.cross(back, right), -back

    def ray(self, x, y, size):
        """Ray through a pointer position, for picking the surface."""
        width, height = size
        eye, right, up, forward = self.basis()
        direction = forward + 0.5 * ((2*x-width)*right + (height-2*y)*up)/height
        return eye.copy(), direction / np.linalg.norm(direction)


class Scene(OceanRenderer):
    """The ocean renderer with the demo camera and input handling attached."""

    def __init__(self, canvas):
        super().__init__(canvas, Camera())


def main():
    """Open the interactive window; returns when the window is closed."""
    from rendercanvas.glfw import RenderCanvas, loop
    canvas = RenderCanvas(size=(960,640),title="StellarFishery | Open water",update_mode="continuous")
    scene = Scene(canvas)
    water, camera = scene.water, scene.camera
    keys = set()
    press = last = None
    previous = time.perf_counter()

    @canvas.add_event_handler("pointer_down","pointer_up","pointer_move","key_down","key_up")
    def input_event(e):
        nonlocal press,last
        kind = e["event_type"]
        if kind.startswith("key"):
            if kind=="key_down" and e["key"].lower()=="g" and "g" not in keys:
                scene.spectrum.swell=not scene.spectrum.swell
                scene.spectrum.tick=None
            if kind=="key_down" and e["key"] in ("1","2"):
                scene.preset(e["key"]=="2")
            (keys.add if kind=="key_down" else keys.discard)(e["key"].lower())
            return
        x,y = e["x"],e["y"]
        if kind=="pointer_down" and e["button"]==1:
            press = (*camera.ray(x,y,canvas.get_logical_size()),time.perf_counter())
        elif kind=="pointer_up" and e["button"]==1 and press:
            eye,ray,started = press
            hit = scene.pick(eye,ray)
            if hit is not None:
                strength = 4 + 20*min(1.0,time.perf_counter()-started)
                water.pending.append(Contact(hit[0],hit[2],0.45,(0,-strength,0),water.tick*DT))
            press = None
        elif kind=="pointer_move" and last:
            dx,dy = x-last[0],y-last[1]
            if 2 in e["buttons"]:
                camera.yaw -= dx*0.008
                camera.pitch = np.clip(camera.pitch+dy*0.008,0.1,1.52)
            if 3 in e["buttons"]:
                camera.distance = np.clip(camera.distance*math.exp(np.clip(dy*0.012,-3,3)),2,30)
        last = x,y

    def frame():
        nonlocal previous
        now = time.perf_counter()
        elapsed, previous = now-previous, now
        _,right,_,_ = camera.basis()
        motion = right*(int("d" in keys)-int("a" in keys))
        motion += np.array([right[2],0,-right[0]])*(int("w" in keys)-int("s" in keys))
        camera.target += motion/max(1,np.linalg.norm(motion))*3*elapsed
        scene.sun_angle += elapsed*(int("e" in keys)-int("q" in keys))
        water.recenter(*camera.target[[0,2]])
        water.advance(elapsed)
        scene.draw()
    canvas.request_draw(frame)
    loop.run()


if __name__ == "__main__":
    main()
