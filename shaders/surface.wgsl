@group(0) @binding(1) var heights: texture_2d<f32>;
@group(0) @binding(2) var foam: texture_2d<f32>;
@group(0) @binding(3) var opaqueColor: texture_2d<f32>;
@group(0) @binding(4) var opaqueDepth: texture_2d<f32>;
fn address(cell: vec2i) -> vec2i {
    let n = i32(camera.grid.w);
    return (clamp(cell,vec2i(0),vec2i(n-1))+vec2i(camera.grid.xy)) & vec2i(n-1);
}
fn h(c: vec2i) -> f32 { return textureLoad(heights,address(c),0).r; }
@group(0) @binding(6) var<storage,read> coordinates: array<vec2f>;
struct Vertex { @builtin(position) clip: vec4f, @location(0) world: vec3f,
                @location(1) normal: vec3f, @location(2) coverage: f32, @location(3) rough:f32 }
fn geometry(id:u32)->Vertex {
    let offset=coordinates[id]*camera.grid.z;
    let xz=(camera.grid.xy+camera.grid.ww*0.5)*camera.grid.z+offset;
    let c=vec2i(round(xz/camera.grid.z))-vec2i(camera.grid.xy);
    let radius=max(abs(offset.x),abs(offset.y));
    let edge=min(min(c.x,c.y),min(127-c.x,127-c.y));
    let localWeight=smoothstep(0.,5.,f32(edge));
    var position=vec3f(xz.x,h(c)*localWeight,xz.y);
    var slope=localWeight*vec2f(h(c+vec2i(1,0))-h(c-vec2i(1,0)),h(c+vec2i(0,1))-h(c-vec2i(0,1)))/(2*camera.grid.z);
    var rough=0.045;
    for(var b=0u;b<3u;b++){
        let cutoff=array<f32,3>(480,64,6)[b];
        let weight=1-smoothstep(cutoff,2*cutoff,radius);
        let band=oceanBand(xz,b);
        position+=weight*band.disp.xyz;
        slope+=weight*band.slopes.xy;
        rough+=0.045*(1-weight)*camera.eye.w;
    }
    return Vertex(project(position),position,normalize(vec3f(-slope.x,1,-slope.y)),
                  localWeight*textureLoad(foam,address(c),0).r,rough);
}
@vertex fn vertex(@builtin(vertex_index) id:u32)->Vertex {return geometry(id);}
@group(0) @binding(7) var<storage,read_write> points:array<vec4f>;
@compute @workgroup_size(64) fn probe(@builtin(global_invocation_id) id:vec3u){
    if id.x<arrayLength(&coordinates){points[id.x]=vec4f(geometry(id.x).world,1);}
}
struct Hit { color: vec3f, distance: f32, confidence: f32 }
fn trace(start: vec3f, dir: vec3f, underwater:bool) -> Hit {
    let dims = vec2f(textureDimensions(opaqueDepth));
    var previous = 0.0;
    for(var i=1;i<=64;i++){
        let t = f32(i)*(0.042+0.0035*f32(i));
        let q = project(start+dir*t);
        let uv = q.xy/q.w*vec2f(0.5,-0.5)+0.5;
        if q.w<0.05 || any(uv<=vec2f(0)) || any(uv>=vec2f(1)) {break;}
        let pix = vec2i(uv*dims);
        let z = textureLoad(opaqueDepth,pix,0).x;
        if z<=q.w {
            // Ignore foreground silhouettes and discontinuities along the march.
            let hitWorld=camera.eye.xyz+(start+dir*t-camera.eye.xyz)*(z/q.w);
            if underwater && hitWorld.y>start.y+0.03 {break;}
            if z>0 && q.w-z < 0.10+1.4*(t-previous) {
                let edge = min(uv,1-uv);
                let weight = smoothstep(0,0.09,min(edge.x,edge.y))*(1-smoothstep(13,16,t));
                return Hit(textureLoad(opaqueColor,pix,0).rgb,t,weight);
            }
            break;
        }
        previous = t;
    }
    return Hit(vec3f(0),0,0);
}
@fragment fn fragment(v: Vertex) -> @location(0) vec4f {
    let pixel = vec2i(v.clip.xy);
    let viewDepth = project(v.world).w;
    if textureLoad(opaqueDepth,pixel,0).x<=viewDepth {discard;}
    let n = normalize(v.normal);
    let view = normalize(camera.eye.xyz-v.world);
    let r = reflect(-view,n);
    let reflected = trace(v.world,r,false);
    let reflection = mix(sky(r,v.rough),reflected.color,reflected.confidence);
    let refr = refract(-view,n,1.0/1.333);
    let under = trace(v.world,refr,true);
    let bedDistance = clamp((bed(v.world.x)-v.world.y)/min(-0.001,refr.y+0.32*refr.x),0,60);
    let path = mix(bedDistance,under.distance,under.confidence);
    let trans = exp(-vec3f(0.62,0.22,0.11)*path);
    let bottom = mix(vec3f(0.55,0.46,0.30),under.color,under.confidence);
    let water = bottom*trans+vec3f(0.018,0.13,0.16)*(1-trans);
    let fresnel = 0.0204+0.9796*pow(1-clamp(dot(view,n),0,1),5);
    let thickness = clamp(v.world.y*4,0,0.65);
    let backlit = pow(max(0,dot(-view,camera.sun.xyz)),3);
    let crest = thickness*backlit*(0.3+0.7*max(dot(n,camera.sun.xyz),0));
    let color = mix(water,reflection,fresnel)+vec3f(0.07,0.64,0.43)*crest;
    return vec4f(mix(color,vec3f(0.85,0.91,0.87),v.coverage),1);
}
