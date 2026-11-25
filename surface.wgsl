struct Camera {
    eye: vec4f, right: vec4f, up: vec4f, forward: vec4f, grid: vec4f
}
@group(0) @binding(0) var<uniform> camera: Camera;
@group(0) @binding(1) var heights: texture_2d<f32>;
fn sample_height(cell: vec2i) -> f32 {
    let n = i32(camera.grid.w);
    let logical = clamp(cell, vec2i(0), vec2i(n-1));
    return textureLoad(heights, (logical + vec2i(camera.grid.xy)) & vec2i(n-1), 0).r;
}
struct Vertex { @builtin(position) clip: vec4f, @location(0) world: vec3f }
@vertex fn vertex(@builtin(vertex_index) id: u32) -> Vertex {
    let n = u32(camera.grid.w);
    let cell = vec2i(i32(id % n), i32(id / n));
    let xz = (vec2f(cell) + camera.grid.xy)*camera.grid.z;
    let world = vec3f(xz.x, sample_height(cell), xz.y);
    let delta = world-camera.eye.xyz;
    let depth = dot(delta,camera.forward.xyz);
    return Vertex(vec4f(dot(delta,camera.right.xyz)*camera.right.w,
                        dot(delta,camera.up.xyz)*camera.up.w,depth-0.05,depth),world);
}
@fragment fn fragment(v: Vertex) -> @location(0) vec4f {
    let normal = normalize(cross(dpdy(v.world),dpdx(v.world)));
    let view = normalize(camera.eye.xyz-v.world);
    let reflected = reflect(-view,normal);
    let sky = mix(vec3f(0.78,0.85,0.88),vec3f(0.27,0.49,0.66),clamp(reflected.y,0,1));
    let light = normalize(vec3f(-0.45,0.68,-0.58));
    let glint = pow(max(0,dot(reflected,light)),160);
    let fresnel = 0.08+0.92*pow(1-abs(dot(normal,view)),5);
    return vec4f(mix(vec3f(0.035,0.23,0.29),sky,fresnel)+glint*vec3f(1,0.9,0.72),1);
}
