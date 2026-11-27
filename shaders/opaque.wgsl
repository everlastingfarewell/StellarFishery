struct Screen { @builtin(position) pos: vec4f, @location(0) uv: vec2f }
@vertex fn fullscreen(@builtin(vertex_index) i: u32) -> Screen {
    let uv = vec2f(f32((i<<1u)&2u), f32(i&2u))*2-1;
    return Screen(vec4f(uv,0,1),uv);
}
struct Opaque { @location(0) display: vec4f, @location(1) color: vec4f, @location(2) depth: f32 }
@fragment fn opaque(v: Screen) -> Opaque {
    let eye = camera.eye.xyz;
    let ray = normalize(camera.forward.xyz + v.uv.x*camera.right.xyz/camera.right.w
                        + v.uv.y*camera.up.xyz/camera.up.w);
    var t = 1000.0;
    var color = sky(ray,0);
    var floorT = (-0.32*(eye.x+6.0)-eye.y)/(ray.y+0.32*ray.x);
    if eye.x+floorT*ray.x < -8 { floorT=1000.; }
    let bankT=(0.64-eye.y)/ray.y;
    if bankT>0.05 && eye.x+bankT*ray.x<=-8 {floorT=bankT;}
    if floorT>0.05 && floorT<t {
        t = floorT;
        let p = eye+t*ray;
        let ripple = sin(11*p.z+2*sin(p.x))*0.025;
        color = vec3f(0.59,0.48,0.31)*(0.92+(ripple+0.06*sin(p.x*3+p.z))*(1-smoothstep(12,40,t)));
    }
    // Identical pale stones on the bank and at two submerged depths.
    for(var i=0;i<4;i++){
        let xs = array<f32,4>(-3,-4.3,2.8,-5.4);
        let zs = array<f32,4>(-2,1,1,-3);
        let sizes = array<f32,4>(1.65,0.45,0.45,0.76);
        let center = vec3f(xs[i],bed(xs[i])+sizes[i]*0.32,zs[i]);
        let offset = eye-center;
        let b = dot(offset,ray);
        let disc = b*b-dot(offset,offset)+sizes[i]*sizes[i];
        if disc>0 {
            let hit = -b-sqrt(disc);
            if hit>0.05 && hit<t {
                t = hit;
                let n = normalize(eye+ray*t-center);
                color = vec3f(0.73,0.66,0.51)*(0.36+0.64*max(0,dot(n,camera.sun.xyz)));
            }
        }
    }
    return Opaque(vec4f(color,1),vec4f(color,1),t*dot(ray,camera.forward.xyz));
}
