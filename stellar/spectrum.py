"""Directional JONSWAP density and separable Vulkan inverse FFT."""
import numpy as np
import wgpu

from .config import SHADERS
from .platform import prebuilt, shader_module

SIZE = 32
LENGTHS = (256., 32., 4.)


def seeds(speed, direction, fetch, spread):
    rng = np.random.default_rng(1729)
    bands = []
    for band, length in enumerate(LENGTHS):
        dk = 2*np.pi/length
        x,z = np.meshgrid(np.fft.fftfreq(SIZE)*SIZE*dk,np.fft.fftfreq(SIZE)*SIZE*dk)
        k = np.maximum(np.hypot(x,z),1e-12)
        omega = np.sqrt(9.81*k)
        peak = 22*(9.81**2/(max(speed,0.01)*fetch))**(1/3)
        sigma = np.where(omega<peak,0.07,0.09)
        gamma = 3.3**np.exp(-0.5*((omega-peak)/(sigma*peak))**2)
        alpha = 0.076*(max(speed,0.01)**2/(fetch*9.81))**0.22
        spectrum = alpha*9.81**2/omega**5*np.exp(-1.25*(peak/omega)**4)*gamma
        theta = np.arctan2(z,x)-direction
        angles = np.arange(2048)*2*np.pi/2048
        norm = np.maximum(0,np.cos(angles))**spread
        angular = np.maximum(0,np.cos(theta))**spread/(2*np.pi*norm.mean())
        def fade(low, high):
            t = np.clip((k-low)/(high-low),0,1)
            return t*t*(3-2*t)
        a,b = fade(.20,.35),fade(1.6,2.8)
        weight = (1-a,a-b,b)[band]
        variance = spectrum*angular*weight*dk**2*omega/(2*k*k)
        phase = (rng.normal(size=k.shape)+1j*rng.normal(size=k.shape))*np.sqrt(variance/4)
        phase[0,0]=0
        phase[SIZE//2,:]=phase[:,SIZE//2]=0
        bands.append(phase*bool(speed))
    return np.stack(bands).astype(np.complex64)


class Spectrum:
    def __init__(self, water):
        d = water.device
        self.water = water
        self.swell = False
        self.speed = 3.5
        storage = wgpu.BufferUsage.STORAGE
        self.seed = d.create_buffer(size=3*SIZE**2*8,usage=storage|wgpu.BufferUsage.COPY_DST)
        self.clock = d.create_buffer(size=16,usage=wgpu.BufferUsage.UNIFORM|wgpu.BufferUsage.COPY_DST)
        temp = d.create_buffer(size=3*SIZE**2*7*8,usage=storage)
        self.field = d.create_buffer(size=3*SIZE**2*32,usage=storage|wgpu.BufferUsage.COPY_SRC)
        self.passes = []
        module = shader_module(d, "spectrum.spv", (SHADERS/"fft.wgsl").read_text(),
                               prebuilt("spectrum.spv"))
        for entry, resources in [("rows",{0:self.seed,1:self.clock,2:temp}),
                                 ("columns",{3:temp,4:self.field})]:
            p=d.create_compute_pipeline(layout="auto",compute={"module":module,"entry_point":entry})
            group=d.create_bind_group(layout=p.get_bind_group_layout(0),entries=[
                {"binding":i,"resource":{"buffer":buf}} for i,buf in resources.items()])
            self.passes.append((p,group))
        self.configure()

    def configure(self,speed=3.5,direction=0.7,fetch=12000,spread=4):
        self.speed = speed
        self.water.q.write_buffer(self.seed,0,seeds(speed,direction,fetch,spread))
        self.tick = None

    def update(self):
        w = self.water
        if self.tick == w.tick:
            return
        from .config import DT
        w.q.write_buffer(self.clock,0,np.array([DT*w.tick,0.16 if self.swell and self.speed else 0.,0,0],np.float32))
        enc = w.device.create_command_encoder()
        for pipeline,group in self.passes:
            p = enc.begin_compute_pass()
            p.set_pipeline(pipeline)
            p.set_bind_group(0,group)
            p.dispatch_workgroups(SIZE,3)
            p.end()
        w.q.submit([enc.finish()])
        self.tick = w.tick
