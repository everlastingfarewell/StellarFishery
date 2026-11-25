import math
import time

import numpy as np
import wgpu

from water import Contact, DT, DX, N, ROOT, Water


class Camera:
    def __init__(self):
        self.target = np.zeros(3)
        self.yaw, self.pitch, self.distance = 0.55, 0.73, 10.0

    def basis(self):
        s, c = math.sin(self.yaw), math.cos(self.yaw)
        back = np.array([s * math.cos(self.pitch), math.sin(self.pitch), c * math.cos(self.pitch)])
        right = np.array([c, 0, -s])
        return self.target + self.distance * back, right, np.cross(back, right), -back

    def ray(self, x, y, size):
        width, height = size
        eye, right, up, forward = self.basis()
        direction = forward + 0.5 * ((2*x-width)*right + (height-2*y)*up)/height
        return eye.copy(), direction / np.linalg.norm(direction)


class Scene:
    def __init__(self, canvas):
        self.water, self.camera = Water(), Camera()
        self.canvas = canvas
        device = self.water.device
        self.context = canvas.get_context("wgpu")
        fmt = self.context.get_preferred_format(self.water.adapter)
        self.context.configure(device=device, format=fmt)
        shader = device.create_shader_module(code=(ROOT/"surface.wgsl").read_text())
        self.pipeline = device.create_render_pipeline(layout="auto",
            vertex={"module":shader, "entry_point":"vertex"},
            primitive={"topology":"triangle-list"},
            depth_stencil={"format":"depth24plus","depth_write_enabled":True,"depth_compare":"less"},
            fragment={"module":shader,"entry_point":"fragment","targets":[{"format":fmt}]})
        self.uniform = device.create_buffer(size=80, usage=wgpu.BufferUsage.UNIFORM | wgpu.BufferUsage.COPY_DST)
        self.groups = [device.create_bind_group(layout=self.pipeline.get_bind_group_layout(0), entries=[
            {"binding":0,"resource":{"buffer":self.uniform}}, {"binding":1,"resource":im.create_view()}])
            for im in self.water.images[:2]]
        cells = (np.arange(N-1)[:,None]*N + np.arange(N-1)).ravel()
        indices = (cells[:,None]+[0,N,1,1,N,N+1]).astype(np.uint32)
        self.indices = device.create_buffer_with_data(data=indices, usage=wgpu.BufferUsage.INDEX)
        self.index_count = indices.size
        self.depth_size = None

    def draw(self):
        surface = self.context.get_current_texture()
        width, height = surface.size[:2]
        if self.depth_size != (width,height):
            self.depth = self.water.device.create_texture(size=(width,height,1), format="depth24plus",
                usage=wgpu.TextureUsage.RENDER_ATTACHMENT).create_view()
            self.depth_size = width,height
        eye,right,up,forward = self.camera.basis()
        data = [*eye,1,*right,2*height/width,*up,2,*forward,0,*self.water.origin,DX,N]
        self.water.q.write_buffer(self.uniform,0,np.array(data,np.float32))
        enc = self.water.device.create_command_encoder()
        draw = enc.begin_render_pass(color_attachments=[{"view":surface.create_view(),"resolve_target":None,
            "load_op":"clear","store_op":"store","clear_value":(0.12,0.19,0.24,1)}],
            depth_stencil_attachment={"view":self.depth,"depth_load_op":"clear","depth_store_op":"discard",
                                      "depth_clear_value":1})
        draw.set_pipeline(self.pipeline)
        draw.set_bind_group(0,self.groups[self.water.phase])
        draw.set_index_buffer(self.indices,"uint32")
        draw.draw_indexed(self.index_count)
        draw.end()
        self.water.q.submit([enc.finish()])


def main():
    from rendercanvas.glfw import RenderCanvas, loop
    canvas = RenderCanvas(size=(960,640),title="StellarFishery | Calm water",update_mode="continuous")
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
            (keys.add if kind=="key_down" else keys.discard)(e["key"].lower())
            return
        x,y = e["x"],e["y"]
        if kind=="pointer_down" and e["button"]==1:
            press = (*camera.ray(x,y,canvas.get_logical_size()),time.perf_counter())
        elif kind=="pointer_up" and e["button"]==1 and press:
            eye,ray,started = press
            hit = water.pick(eye,ray)
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
        water.recenter(*camera.target[[0,2]])
        water.advance(elapsed)
        scene.draw()
    canvas.request_draw(frame)
    loop.run()


if __name__ == "__main__":
    main()
