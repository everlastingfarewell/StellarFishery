struct Camera {
    eye: vec4f, right: vec4f, up: vec4f, forward: vec4f, grid: vec4f, sun: vec4f
}
@group(0) @binding(0) var<uniform> camera: Camera;
fn project(p: vec3f) -> vec4f {
    let d = p-camera.eye.xyz;
    let z = dot(d,camera.forward.xyz);
    return vec4f(dot(d,camera.right.xyz)*camera.right.w, dot(d,camera.up.xyz)*camera.up.w,z-0.05,z);
}
fn sky(r: vec3f, rough: f32) -> vec3f {
    let haze = exp(-4*max(r.y,0));
    let s = max(dot(r,camera.sun.xyz),0);
    // Analytic roughness filter: broaden the solar lobe and preserve its integral.
    let power = 1.0/(0.0007+rough*rough);
    return mix(vec3f(0.18,0.42,0.67),vec3f(0.8,0.83,0.8),haze)
         + vec3f(1,0.8,0.52)*pow(s,power)*(power*0.002);
}
