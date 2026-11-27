struct Field { disp: vec4f, slopes: vec4f }
@group(0) @binding(5) var<storage,read> ocean: array<Field>;
@group(0) @binding(8) var<uniform> seaTime:vec4f;
fn oceanCell(p:vec2i,b:u32)->Field {
    let q=p&vec2i(31);return ocean[b*1024u+u32(q.y*32+q.x)];
}
fn oceanBand(xz:vec2f,b:u32)->Field {
    let uv=xz*(32./array<f32,3>(256,32,4)[b]);
    let cell=vec2i(floor(uv));let f=fract(uv);
    let a=oceanCell(cell,b);let c=oceanCell(cell+vec2i(0,1),b);
    let d=oceanCell(cell+vec2i(1,1),b);let e=oceanCell(cell+vec2i(1,0),b);
    var result=Field(mix(mix(a.disp,e.disp,f.x),mix(c.disp,d.disp,f.x),f.y),
                 mix(mix(a.slopes,e.slopes,f.x),mix(c.slopes,d.slopes,f.x),f.y));
    if b==0u && seaTime.y>0 {
        let dir=vec2f(0.8,0.6);
        let k=0.019635; // 320 metre swell beyond the largest FFT period
        let omega=sqrt(9.81*k);
        let phase=k*dot(dir,xz)-omega*seaTime.x;
        let a=seaTime.y;
        let d=-a*dir*sin(phase);
        result.disp+=vec4f(d.x,a*cos(phase),d.y,0);
        result.slopes+=vec4f(-a*k*dir*sin(phase),a*omega*dir*cos(phase));
    }
    return result;
}
