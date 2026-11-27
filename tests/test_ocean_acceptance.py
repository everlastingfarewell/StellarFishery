"""Reproduce open-water and optics checks with the production Vulkan renderer."""
from pathlib import Path

import numpy as np
from PIL import Image
from rendercanvas.offscreen import RenderCanvas

from examples.demo import Scene
from stellar.config import DT, N
from stellar.simulation import Contact
from stellar.spectrum import LENGTHS, SIZE, seeds

OUT=Path(__file__).resolve().parent.parent/"captures"/"ocean"


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    canvas=RenderCanvas(size=(480,320),pixel_ratio=1)
    scene=Scene(canvas)
    canvas.request_draw(scene.draw)
    water=scene.water

    def frame():
        return Image.fromarray(np.asarray(canvas.draw()).copy()).convert("RGB")

    def film(name,frames):
        frames[0].save(OUT/(name+".webp"),save_all=True,append_images=frames[1:],duration=90,
                       lossless=True,loop=0)

    def foam():
        data=water.q.read_texture({"texture":water.foam_images[water.phase]},
                                  {"bytes_per_row":N*4},(N,N,1))
        return np.frombuffer(data,np.float32).reshape(N,N)

    def reset():
        water.recenter(5000,5000)
        water.recenter(0,0)
        water.tick=0
        scene.spectrum.tick=None
        scene.camera.target[:]=0
        scene.camera.pitch=.73
        scene.camera.yaw=.55

    water.advance(13*DT)
    scene.spectrum.update()
    gpu=np.frombuffer(water.q.read_buffer(scene.spectrum.field),np.float32).reshape(3,SIZE,SIZE,8)
    for i,(seed,length) in enumerate(zip(seeds(3.5,.7,12000,4),LENGTHS)):
        k=np.fft.fftfreq(SIZE)*SIZE*2*np.pi/length
        kx,kz=np.meshgrid(k,k)
        km=np.hypot(kx,kz)
        a=seed*np.exp(-1j*np.sqrt(9.81*km)*water.tick*DT)
        neg=(-np.arange(SIZE))%SIZE
        h=a+a[np.ix_(neg,neg)].conj()
        for channel,factor in [(1,1),(0,1j*kx/np.maximum(km,1e-12)),(2,1j*kz/np.maximum(km,1e-12)),
                               (4,1j*kx),(5,1j*kz)]:
            ref=np.fft.ifft2(h*factor)*SIZE**2
            assert np.abs(ref.imag).max()<1e-6
            np.testing.assert_allclose(ref.real,gpu[i,:,:,channel],atol=2e-6)

    # Every interior triangle edge has two owners, including each coarse/fine join.
    tri=scene.triangles
    edges=np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]])
    unique,counts=np.unique(np.sort(edges,axis=1),axis=0,return_counts=True)
    assert counts.max()==2 and (counts==1).sum()==4*64
    # Locate a crest in the central mesh and sample that same world point after scrolling.
    xs=np.linspace(.13,2.13,11)
    profile=[scene.sample(x,.23) for x in xs]
    crest_x=xs[np.argmax(profile)]
    crest_y=max(profile)
    water.recenter(.75,0)
    np.testing.assert_allclose(scene.sample(crest_x,.23),crest_y,atol=2e-5)
    frames=[]
    for x in np.linspace(-1,36,38):
        scene.camera.target[0]=x
        scene.camera.pitch=.22
        water.recenter(x,0)
        frames.append(frame())
    film("frozen-crossing",frames)

    for wind in [False,True]:
        reset()
        scene.preset(wind)
        water.pending.append(Contact(0,0,.45,(0,-24,0),0))
        frames=[]
        for _ in range(25):
            water.advance(3*DT)
            frames.append(frame())
        film("wind-impact" if wind else "calm-impact",frames)
        if not wind:
            baseline=water.field()
        else:
            np.testing.assert_array_equal(water.field(),baseline)

    reset()
    scene.camera.pitch=.28
    frames=[]
    for i in range(38):
        scene.camera.yaw=.5+i*.055
        scene.sun_angle=-2.0+i*.09
        water.advance(3*DT)
        frames.append(frame())
    film("rock-reflection-and-backlight",frames)
    scene.camera.yaw=.55
    scene.camera.target[:]=[14,0,0]
    scene.camera.pitch=.16
    scene.sun_angle=-2.1
    water.recenter(14,0)
    scene.spectrum.swell=True
    scene.spectrum.configure(speed=8)
    frames=[]
    for _ in range(28):
        water.advance(3*DT)
        frames.append(frame())
    film("backlit-swell",frames)
    scene.spectrum.swell=False
    scene.preset(True)
    water.recenter(0,0)
    water.advance(10*DT)
    scene.camera.pitch=.88
    scene.camera.target[:]=[-1,0,0]
    frame().save(OUT/"shallow-deep-stones.png")
    print("Wind shoreline peak foam",foam().max())
    assert foam().max()>0
    reset()
    scene.preset(False)
    water.recenter(24,0)
    water.advance(DT)
    assert foam().max()==0
    # Converging contact velocity induces a short-lived offshore whitecap.
    for x,kick in [(23.6,240),(24.4,-240)]:
        water.pending.append(Contact(x,0,.45,(kick,0,0),water.tick*DT))
    scene.camera.target[0]=24
    scene.camera.distance=4
    frames=[]
    for i in range(100):
        water.advance(4*DT)
        if i==9:
            peak=foam().max()
        if i%3==0:
            frames.append(frame())
    film("advected-whitecap",frames)
    print("Offshore whitecap early / late",peak,foam().max())
    assert 0<foam().max()<peak
    canvas.set_logical_size(320,240)
    assert frame().size==(320,240)
    canvas.close()


def main():
    run()


if __name__=="__main__":
    main()
