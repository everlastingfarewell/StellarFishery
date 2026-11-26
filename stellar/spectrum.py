"""Directional JONSWAP density and separable Vulkan inverse FFT."""
import numpy as np
import wgpu

from .config import SHADERS
from .platform import prebuilt, shader_module

from .waves import SIZE, LENGTHS, seeds


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
