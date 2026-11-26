import numpy as np
import wgpu

from .config import DX, N, SHADERS
from .mesh import rings
from .platform import platform_profile, prebuilt, shader_module
from .simulation import Water
from .spectrum import Spectrum

# Shader modules: the WGSL files renderer.py joins into one module, the entry
# points used, and their prebuilt SPIR-V (spv/, built by scripts/build-spv.py)
# for platforms without a WGSL compiler.
MODULES = {
    "screen": (("camera.wgsl", "bathymetry.wgsl", "opaque.wgsl"),
               ("fullscreen", "opaque")),
    "sea": (("camera.wgsl", "bathymetry.wgsl", "ocean.wgsl", "surface.wgsl"),
            ("vertex", "fragment", "probe")),
    "foam": (("bathymetry.wgsl", "ocean.wgsl", "foam.wgsl"), ("foam",)),
}
# Entry points that only exist where the host can read simulation results back.
NEEDS_READBACK = (("sea", "probe"),)


def available(name, entry_point):
    """Whether this platform can build `entry_point` of the module `name`."""
    profile = platform_profile()
    if not profile["wgsl"] and not profile["spirv"]:
        return False
    if (name, entry_point) in NEEDS_READBACK and not profile["readback"]:
        return False
    return True


def shader(device, name, entry_point=None):
    """The shader module for `name`, checking that `entry_point` is usable.

    Without a WGSL compiler the module comes from the prebuilt `spv/<name>.spv`
    built by tools/build-spv.py.
    """
    if entry_point is not None and not available(name, entry_point):
        raise RuntimeError(f"{name}.{entry_point} is not available on this platform")
    if not platform_profile()["wgsl"]:
        return shader_module(device, f"{name}.spv", None, prebuilt(f"{name}.spv"))
    code = "\n".join((SHADERS / f).read_text() for f in MODULES[name][0])
    return shader_module(device, name, code)


def group(device,pipeline,resources):
    """Bind group 0 for `resources`, holding buffer or texture views by binding."""
    return device.create_bind_group(layout=pipeline.get_bind_group_layout(0),entries=[
        {"binding":i,"resource":{"buffer":r} if isinstance(r,wgpu.GPUBuffer) else r}
        for i,r in resources.items()])


class OceanRenderer:
    """Draws the ocean, its opaque shore and the foam that follows the waves."""

    def __init__(self,canvas,camera):
        self.canvas,self.camera,self.water=canvas,camera,Water()
        w=self.water
        d=w.device
        self.spectrum=Spectrum(w)
        self.wind=True
        self.sun_angle=-1.95
        self.context=canvas.get_context("wgpu")
        fmt=self.context.get_preferred_format(w.adapter)
        self.context.configure(device=d,format=fmt)
        self.camera_buffer=d.create_buffer(size=96,usage=wgpu.BufferUsage.UNIFORM|wgpu.BufferUsage.COPY_DST)
        screen=shader(d,"screen")
        self.opaque=d.create_render_pipeline(layout="auto",vertex={"module":screen,"entry_point":"fullscreen"},
            fragment={"module":screen,"entry_point":"opaque","targets":[{"format":v} for v in (fmt,"rgba8unorm","r32float")]})
        self.background=group(d,self.opaque,{0:self.camera_buffer})
        sea=shader(d,"sea","vertex")
        self.surface=d.create_render_pipeline(layout="auto",vertex={"module":sea,"entry_point":"vertex"},
            fragment={"module":sea,"entry_point":"fragment","targets":[{"format":fmt}]},
            depth_stencil={"format":"depth24plus","depth_write_enabled":True,"depth_compare":"less"})
        self.probe=(d.create_compute_pipeline(layout="auto",compute={
            "module":shader(d,"sea","probe"),"entry_point":"probe"})
            if available("sea","probe") else None)
        coords,self.triangles=rings()
        self.count=len(coords)
        self.coords=d.create_buffer_with_data(data=coords,usage=wgpu.BufferUsage.STORAGE)
        self.indices=d.create_buffer_with_data(data=self.triangles,usage=wgpu.BufferUsage.INDEX)
        self.points=d.create_buffer(size=len(coords)*16,usage=wgpu.BufferUsage.STORAGE|wgpu.BufferUsage.COPY_SRC)
        foam=shader(d,"foam","foam")
        self.foam=d.create_compute_pipeline(layout="auto",compute={"module":foam,"entry_point":"foam"})
        usage=wgpu.TextureUsage.TEXTURE_BINDING|wgpu.TextureUsage.STORAGE_BINDING|wgpu.TextureUsage.COPY_DST|wgpu.TextureUsage.COPY_SRC
        w.foam_images=[d.create_texture(size=(N,N,1),format="r32float",usage=usage) for _ in range(2)]
        self.foam_groups=[]
        self.geometry=[]
        self.probes=[]
        for i in range(2):
            field=self.spectrum.field
            wet=w.foam_images[i].create_view()
            h=w.images[i].create_view()
            self.foam_groups.append(group(d,self.foam,{0:w.params,1:h,2:w.images[2].create_view(),
                3:w.foam_images[1-i].create_view(),4:wet,5:field,8:self.spectrum.clock}))
            geom={0:self.camera_buffer,1:h,2:wet,5:field,6:self.coords,8:self.spectrum.clock}
            self.geometry.append(geom)
            if self.probe is not None:
                self.probes.append(group(d,self.probe,{**geom,7:self.points}))
        self.size=None
        w.after_step=self.advance_foam

    def preset(self,wind):
        """Switch between zero background energy and the low-wind sea."""
        self.wind=wind
        self.spectrum.configure(speed=3.5 if wind else 0)

    def advance_foam(self):
        """Evolve the spectral field and advect the foam after each simulation tick."""
        self.spectrum.update()
        w=self.water
        enc=w.device.create_command_encoder()
        p=enc.begin_compute_pass()
        p.set_pipeline(self.foam)
        p.set_bind_group(0,self.foam_groups[w.phase])
        p.dispatch_workgroups(N//16,N//16)
        p.end()
        w.q.submit([enc.finish()])

    def uniforms(self,width,height):
        """Upload the camera, sun and grid uniforms for this frame."""
        eye,right,up,forward=self.camera.basis()
        sun=np.array([np.cos(self.sun_angle),.32,np.sin(self.sun_angle)])
        data=[*eye,float(self.wind),*right,2*height/width,*up,2,*forward,0,*self.water.origin,DX,N,*sun/np.linalg.norm(sun),0]
        self.water.q.write_buffer(self.camera_buffer,0,np.asarray(data,np.float32))
        self.spectrum.update()

    def pick(self,eye,ray):
        """World-space surface hit along `ray`, or None when the platform cannot read back."""
        w=self.water
        if self.probe is None or not platform_profile()["readback"]:
            return w.pick(eye,ray)
        self.uniforms(*self.canvas.get_physical_size())
        enc=w.device.create_command_encoder()
        p=enc.begin_compute_pass()
        p.set_pipeline(self.probe)
        p.set_bind_group(0,self.probes[w.phase])
        p.dispatch_workgroups((self.count+63)//64)
        p.end()
        w.q.submit([enc.finish()])
        points=np.frombuffer(w.q.read_buffer(self.points),np.float32).reshape(-1,4)[:,:3]
        a,b,c=points[self.triangles].transpose(1,0,2)
        e1,e2=b-a,c-a
        cross=np.cross(ray,e2)
        det=(e1*cross).sum(axis=1)
        delta=eye-a
        q=np.cross(delta,e1)
        with np.errstate(divide="ignore",invalid="ignore"):
            u=(delta*cross).sum(axis=1)/det
            v=(q*ray).sum(axis=1)/det
            t=(q*e2).sum(axis=1)/det
        valid=(abs(det)>1e-9)&(u>=0)&(v>=0)&(u+v<=1)&(t>=0)
        if valid.any():
            return eye+t[valid].min()*ray

    def sample(self,x,z):
        """Height of the surface above (x, z) for buoyancy probes."""
        hit=self.pick(np.array([x,1000.,z]),np.array([0.,-1.,0.]))
        return None if hit is None else hit[1]

    def resize(self,size):
        d=self.water.device
        def view(fmt,usage):
            return d.create_texture(size=(*size,1),format=fmt,usage=usage).create_view()
        usage=wgpu.TextureUsage.RENDER_ATTACHMENT
        self.depth=view("depth24plus",usage)
        self.color,self.linear=[view(fmt,usage|wgpu.TextureUsage.TEXTURE_BINDING) for fmt in ("rgba8unorm","r32float")]
        self.groups=[group(d,self.surface,{**g,3:self.color,4:self.linear}) for g in self.geometry]
        self.size=size

    def draw(self):
        tex=self.context.get_current_texture()
        size=tex.size[:2]
        if size!=self.size:
            self.resize(size)
        self.uniforms(*size)
        enc=self.water.device.create_command_encoder()
        display=tex.create_view()
        def attachment(v,load):
            return {"view":v,"load_op":load,"store_op":"store","clear_value":(0,0,0,0),"resolve_target":None}
        p=enc.begin_render_pass(color_attachments=[attachment(v,"clear") for v in (display,self.color,self.linear)])
        p.set_pipeline(self.opaque)
        p.set_bind_group(0,self.background)
        p.draw(3)
        p.end()
        p=enc.begin_render_pass(color_attachments=[attachment(display,"load")],depth_stencil_attachment={
            "view":self.depth,"depth_load_op":"clear","depth_store_op":"discard","depth_clear_value":1})
        p.set_pipeline(self.surface)
        p.set_bind_group(0,self.groups[self.water.phase])
        p.set_index_buffer(self.indices,"uint32")
        p.draw_indexed(self.triangles.size)
        p.end()
        self.water.q.submit([enc.finish()])
