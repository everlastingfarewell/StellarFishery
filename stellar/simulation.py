"""Fixed-step Vulkan height field. World distances are metres and forces are newtons."""
from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import numpy as np
import wgpu

from .config import DT, DX, MASS, N, ROOT, SPEED
from .platform import platform_profile

# glslc input for the height field, and the bytecode built from it by
# scripts/build-spv.py for platforms without a shader compiler.
WAVE_SOURCE = ROOT / "shaders" / "wave.comp"
PREBUILT = ROOT / "data" / "water.spv"


def shader_binary():
    """SPIR-V for the height-field kernel, compiled now or read from `data/`."""
    if not platform_profile()["wgsl"] and PREBUILT.is_file():
        return PREBUILT.read_bytes()

    roots = sorted(Path("C:/VulkanSDK").glob("*/Bin"), reverse=True)
    if "VULKAN_SDK" in os.environ:
        roots.insert(0, Path(os.environ["VULKAN_SDK"]) / "Bin")

    def executable(name):
        return shutil.which(name) or next((r / (name+".exe") for r in roots
                                           if (r / (name+".exe")).is_file()), None)

    glslc = executable("glslc")
    if not glslc:
        if PREBUILT.is_file():
            return PREBUILT.read_bytes()
        raise RuntimeError("Install the Vulkan SDK to provide glslc, or run "
                           "scripts/build-spv.py to create data/water.spv")

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "wave.spv"
        subprocess.run([glslc, WAVE_SOURCE, "-o", out], check=True)
        if spirv_val := executable("spirv-val"):
            subprocess.run([spirv_val, out], check=True)
        return out.read_bytes()


@dataclass
class Contact:
    x: float
    z: float
    radius: float
    momentum: tuple  # impulse for an impact, constant force for a contact with duration
    start: float
    duration: float = 0


class Water:
    """128 x 128 height field advanced by a damped wave equation in compute.

    `readback` (in ticks) is how many steps have been read back to the host.
    Platforms without host readback get a RuntimeError: every step needs it.
    Picking and buoyancy use the same triangles that `field()` describes, so a
    platform without host readback cannot answer either of them.
    """

    def __init__(self):
        from .platform import request_device

        if not platform_profile()["readback"]:
            raise RuntimeError(
                "this platform cannot read simulation results back (see "
                "docs/brick.md), so the height field cannot be stepped or queried")
        self.adapter, self.device = request_device()
        d = self.device
        self.q = d.queue
        self.readback = 0
        usage = (wgpu.TextureUsage.STORAGE_BINDING | wgpu.TextureUsage.TEXTURE_BINDING |
                 wgpu.TextureUsage.COPY_SRC | wgpu.TextureUsage.COPY_DST)
        self.images = [d.create_texture(size=(N,N,1), format=f, usage=usage)
                       for f in ("r32float","r32float","rg32float")]
        self.params = d.create_buffer(size=32, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.pipeline = d.create_compute_pipeline(layout="auto", compute={
            "module": d.create_shader_module(code=shader_binary()), "entry_point":"main"})
        self.capacity = 0
        self.reserve(1)
        self.origin = np.array([-N//2, -N//2])
        self.phase = self.tick = self.consumed = 0
        self.after_step = None
        self.foam_images = []
        self.pending = []
        self.remainder = 0.

    def reserve(self, count):
        if count <= self.capacity:
            return
        self.capacity = 1 << (count-1).bit_length()
        self.events = self.device.create_buffer(size=32*self.capacity,
            usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_DST)
        self.groups = []
        for phase in range(2):
            resources = [self.images[i].create_view() for i in (phase,1-phase,2)]
            resources.extend([{"buffer":self.params}, {"buffer":self.events}])
            self.groups.append(self.device.create_bind_group(layout=self.pipeline.get_bind_group_layout(0),
                entries=[{"binding":i,"resource":v} for i,v in enumerate(resources)]))

    def recenter(self, x, z):
        origin = np.floor(np.array([x,z])/DX).astype(int)-N//2
        # Clear exposed world columns/rows in physical ring order in both histories and flow.
        for axis, delta in enumerate(origin-self.origin):
            length = min(abs(int(delta)), N)
            if not length:
                continue
            first = int(origin[axis] if delta < 0 else origin[axis]+N-length) % N
            for start, size in ((first,min(length,N-first)), (0,max(0,first+length-N))):
                if not size:
                    continue
                ox,oz,w,h = (start,0,size,N) if axis == 0 else (0,start,N,size)
                for i, image in enumerate(self.images+self.foam_images):
                    stride = w * (8 if i == 2 else 4)
                    self.q.write_texture({"texture":image,"origin":(ox,oz,0)}, bytes(h*stride),
                                         {"bytes_per_row":stride}, (w,h,1))
        self.origin = origin

    def record(self, event, impulse, time):
        center = np.array([event.x,event.z])
        lo = np.maximum(self.origin, np.ceil((center-event.radius)/DX).astype(int))
        hi = np.minimum(self.origin+N-1, np.floor((center+event.radius)/DX).astype(int))
        x,z = [np.arange(a,b+1,dtype=np.float32)*DX-c for a,b,c in zip(lo,hi,center)]
        weights = np.maximum(0,1-(x[:,None]**2+z**2)/event.radius**2)**2
        total = weights.sum()
        if total > 0:
            return (*center,event.radius,1/total,*impulse,time)

    def step(self):
        """Advance one fixed tick and consume the contacts that fall inside it."""
        start, end = self.tick*DT, (self.tick+1)*DT
        remaining, records = [], []
        for event in self.pending:
            if event.start >= end-1e-12:
                remaining.append(event)
                continue
            impulse = np.asarray(event.momentum)
            if event.duration:
                stop = event.start+event.duration
                impulse = impulse * max(0,min(end,stop)-max(start,event.start))
                if stop > end+1e-12:
                    remaining.append(event)
            else:
                self.consumed += 1
            record = self.record(event,impulse,start)
            if record:
                records.append(record)
        self.pending = remaining
        self.reserve(max(1,len(records)))
        if records:
            self.q.write_buffer(self.events,0,np.asarray(records,dtype="<f4"))
        self.q.write_buffer(self.params,0,struct.pack("<4i4f",*self.origin,N,len(records),
            DX,DT,(SPEED*DT/DX)**2,MASS))
        encoder = self.device.create_command_encoder()
        compute = encoder.begin_compute_pass()
        compute.set_pipeline(self.pipeline)
        compute.set_bind_group(0,self.groups[self.phase])
        compute.dispatch_workgroups(math.ceil(N/16),math.ceil(N/16))
        compute.end()
        self.q.submit([encoder.finish()])
        self.phase ^= 1
        self.tick += 1
        if self.after_step:
            self.after_step()

    def advance(self, seconds):
        """Advance as many whole ticks as `seconds` covers."""
        self.remainder += seconds
        while self.remainder >= DT-1e-12:
            self.step()
            self.remainder -= DT

    def field(self, index=None):
        """World-aligned height (NaN-free copy) of a history image, latest by default."""
        i = self.phase if index is None else index
        channels = 2 if i==2 else 1
        data = self.q.read_texture({"texture":self.images[i]},
                                   {"bytes_per_row":N*channels*4}, (N,N,1))
        shape = (N,N,2) if channels==2 else (N,N)
        self.readback = self.tick
        return np.roll(np.frombuffer(data,np.float32).reshape(shape),
                       tuple(-self.origin[::-1]),axis=(0,1))

    def pick(self, eye, ray):
        """World-space hit of `ray` against the height field, or None.

        Intersects the exact two triangles per cell used by the indexed draw.
        """
        h = self.field()
        x,z = (np.arange(N-1) + self.origin[:,None])*DX
        hits = []
        for upper in (False,True):
            base = h[1:,1:] if upper else h[:-1,:-1]
            sx = (h[1:,1:]-h[1:,:-1] if upper else h[:-1,1:]-base)/DX
            sz = (h[1:,1:]-h[:-1,1:] if upper else h[1:,:-1]-base)/DX
            with np.errstate(divide="ignore",invalid="ignore"):
                t = (base-eye[1]+sx*(eye[0]-x-upper*DX)
                     +sz*(eye[2]-z[:,None]-upper*DX))/(ray[1]-sx*ray[0]-sz*ray[2])
                u = (eye[0]+t*ray[0]-x)/DX
                v = (eye[2]+t*ray[2]-z[:,None])/DX
                inside = (t>=0)&(u>=0)&(v>=0)&(u<=1)&(v<=1)
                inside &= (u+v>=1) if upper else (u+v<=1)
            if inside.any():
                hits.append(t[inside].min())
        return eye+min(hits)*ray if hits else None

    def sample(self, x, z):
        """Height for a buoyancy probe on the current rendered triangles."""
        local = np.array([x,z])/DX-self.origin
        if np.any(local < 0) or np.any(local > N-1):
            return None
        i,j = np.minimum(np.floor(local).astype(int),N-2)
        u,v = local-[i,j]
        h = self.field()
        if u+v <= 1:
            return (1-u-v)*h[j,i]+u*h[j,i+1]+v*h[j+1,i]
        return (u+v-1)*h[j+1,i+1]+(1-u)*h[j+1,i]+(1-v)*h[j,i+1]
