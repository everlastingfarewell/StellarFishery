"""Run the fixed-camera Vulkan acceptance replay. Outputs are measured in metres."""
from pathlib import Path
import csv

import numpy as np
from PIL import Image
from rendercanvas.offscreen import RenderCanvas

from examples.demo import Scene
from stellar.config import DT, DX, MASS, N
from stellar.simulation import Contact, Water

OUT = Path(__file__).resolve().parent.parent / "captures"


def verify_contacts():
    water = Water()
    for x,z in [(0,0), (water.origin[0]*DX,water.origin[1]*DX)]:
        water.recenter(x+40,z+40)
        water.recenter(0,0)
        water.pending.append(Contact(x,z,0.45,(3,-24,0),water.tick*DT))
        water.step()
        h = water.field()
        np.testing.assert_allclose(h.sum()*MASS/DT,-24,rtol=2e-6)
        np.testing.assert_allclose(water.field(2)[:,:,0].sum()*MASS,3,rtol=2e-6)
        if x == 0:
            depression = h.min()
            assert -0.026 < depression < -0.020, depression
            np.testing.assert_allclose(water.sample(0,0),depression)
        water.recenter(DX,0)
        np.testing.assert_array_equal(water.field()[:,:-1],h[:,1:])
        assert not water.field()[:,-1].any()
    water.recenter(100,100)
    water.pending.append(Contact(100,100,0.45,(60,0,0),water.tick*DT+DT/2,DT))
    water.step()
    np.testing.assert_allclose(water.field(2)[:,:,0].sum()*MASS,0.5,rtol=1e-5)
    water.step()
    assert not water.pending
    np.testing.assert_allclose(water.field(2)[:,:,0].sum()*MASS,0.5*(1+np.exp(-0.65*DT)),rtol=1e-5)
    return depression


def replay(name, starts, fps):
    canvas = RenderCanvas(size=(384,256), pixel_ratio=1)
    scene = Scene(canvas)
    scene.preset(False)
    canvas.request_draw(scene.draw)
    water = scene.water
    water.pending.extend(Contact(0,0,0.45,(0,-24,0),t) for t in starts)
    frames, fields, rows = [], [], []
    axis = (np.arange(N)-N//2)*DX
    radius = np.hypot(axis[:,None],axis)
    for frame in range(1,6*fps+1):
        water.advance(1/fps)
        assert water.consumed == sum(t < water.tick*DT-1e-10 for t in starts)
        image = canvas.draw()
        if frame % (fps//10):
            continue
        frames.append(Image.fromarray(np.asarray(image).copy()).convert("RGB"))
        h = water.field()
        fields.append(h)
        line = h[N//2,N//2:]
        ring = np.argmax(np.abs(line))*DX
        rows.append((name,fps,water.tick,water.tick*DT,h.min(),np.abs(h).max(),ring,
                     np.abs(h[radius<2]).max(),np.abs(h[radius>7]).max(),water.consumed))
    frames[0].save(OUT/f"{name}-{fps}fps.webp",save_all=True,append_images=frames[1:],
                   duration=100,loop=0,lossless=True)
    canvas.close()
    return fields,rows


def main():
    OUT.mkdir(exist_ok=True)
    print("First-step center height:",verify_contacts())
    with (OUT/"measurements.csv").open("w",newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["case","fps","tick","seconds","minimum_m","peak_abs_m","peak_radius_positive_x_m",
                         "inner_2m_peak_m","outer_7m_peak_m","impacts_consumed"])
        for name,starts in [("single",[0]),("burst",[0,0.012,0.17,0.32])]:
            baseline = None
            for fps in (30,60):
                fields,rows = replay(name,starts,fps)
                writer.writerows(rows)
                if baseline is not None:
                    np.testing.assert_array_equal(fields,baseline)
                baseline = fields
            print(name,"identical fields at all 60 shared samples")


if __name__ == "__main__":
    main()
