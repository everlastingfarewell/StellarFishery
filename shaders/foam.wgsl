struct Params { origin: vec2i, size: i32, count: i32, dx: f32, dt: f32, courant: f32, mass: f32 }
@group(0) @binding(0) var<uniform> p: Params;
@group(0) @binding(1) var height: texture_2d<f32>;
@group(0) @binding(2) var flow: texture_2d<f32>;
@group(0) @binding(3) var history: texture_2d<f32>;
@group(0) @binding(4) var result: texture_storage_2d<r32float,write>;
fn addr(c: vec2i) -> vec2i { return (clamp(c,vec2i(0),vec2i(p.size-1))+p.origin)&vec2i(p.size-1); }
fn h(c: vec2i) -> f32 { return textureLoad(height,addr(c),0).x; }
fn old(c: vec2i) -> f32 {
    if any(c<vec2i(0)) || any(c>=vec2i(p.size)) { return 0; }
    return textureLoad(history,addr(c),0).x;
}
// Local material displacement estimated from wave slope and horizontal contact flow.
fn displacement(c: vec2i) -> vec2f {
    let xz=vec2f(c+p.origin)*p.dx;
    var d=p.dt*textureLoad(flow,addr(c),0).xy;
    for(var b=0u;b<3u;b++){d+=oceanBand(xz,b).disp.xz;}
    return d;
}
@compute @workgroup_size(16,16) fn foam(@builtin(global_invocation_id) id: vec3u) {
    let c = vec2i(id.xy);
    if any(c>=vec2i(p.size)) {return;}
    let dx = (displacement(c+vec2i(1,0))-displacement(c-vec2i(1,0)))/(2*p.dx);
    let dz = (displacement(c+vec2i(0,1))-displacement(c-vec2i(0,1)))/(2*p.dx);
    let jac = (1+dx.x)*(1+dz.y)-dx.y*dz.x;
    var velocity=textureLoad(flow,addr(c),0).xy;
    var wave=h(c);
    for(var b=0u;b<3u;b++){
        let band=oceanBand(vec2f(c+p.origin)*p.dx,b);
        velocity+=band.slopes.zw;
        wave+=band.disp.y;
    }
    let back = vec2f(c)-p.dt*velocity/p.dx;
    let b = vec2i(floor(back));
    let f = fract(back);
    let drift = mix(mix(old(b),old(b+vec2i(1,0)),f.x),
                    mix(old(b+vec2i(0,1)),old(b+vec2i(1,1)),f.x),f.y);
    let depth = wave-bed(f32((c+p.origin).x)*p.dx);
    let shore = (1-smoothstep(0,0.42,depth))*smoothstep(0.003,0.045,abs(wave));
    let injection = (1-smoothstep(0.15,0.78,jac))*12+shore*22;
    let value = clamp(drift*exp(-0.9*p.dt)+injection*p.dt,0,1);
    textureStore(result,addr(c),vec4f(select(0.0,value,depth>0)));
}
