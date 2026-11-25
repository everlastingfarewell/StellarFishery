struct Modes { values: array<vec2f,7> }
struct Field { disp: vec4f, slopes: vec4f }
@group(0) @binding(0) var<storage,read> seed: array<vec2f>;
@group(0) @binding(1) var<uniform> clock: vec4f;
@group(0) @binding(2) var<storage,read_write> tmp: array<Modes>;
@group(0) @binding(3) var<storage,read> src: array<Modes>;
@group(0) @binding(4) var<storage,read_write> field: array<Field>;
var<workgroup> scratch: array<Modes,32>;
fn mul(a:vec2f,b:vec2f)->vec2f{return vec2f(a.x*b.x-a.y*b.y,a.x*b.y+a.y*b.x);}
fn cis(t:f32)->vec2f{return vec2f(cos(t),sin(t));}
fn transform(i:u32,m:Modes)->Modes{
    scratch[reverseBits(i)>>27u]=m;
    workgroupBarrier();
    for(var stride=1u;stride<32u;stride*=2u){
        let lo=(i/(2u*stride))*2u*stride+i%stride;
        let a=scratch[lo];let b=scratch[lo+stride];
        let tw=cis(3.14159265*f32(i%stride)/f32(stride))*select(-1.,1.,(i&stride)==0u);
        workgroupBarrier();
        for(var j=0u;j<7u;j++){scratch[i].values[j]=a.values[j]+mul(tw,b.values[j]);}
        workgroupBarrier();
    }
    return scratch[i];
}
@compute @workgroup_size(32) fn rows(@builtin(local_invocation_index) x:u32,@builtin(workgroup_id) g:vec3u){
    let z=g.x;let band=g.y;let base=band*1024u;
    let lengthM=array<f32,3>(256,32,4)[band];
    let ij=vec2i(i32(x),i32(z));
    let k=vec2f(select(ij,ij-32,ij>=vec2i(16)))*6.2831853/lengthM;
    let km=max(length(k),1e-10);
    let rot=cis(-sqrt(9.81*km)*clock.x);
    let a=mul(seed[base+32u*z+x],rot);
    let b=mul(seed[base+32u*((32u-z)%32u)+(32u-x)%32u],rot);
    let h=a+b*vec2f(1,-1);let ih=vec2f(-h.y,h.x);
    var m:Modes;m.values=array<vec2f,7>(h,ih*k.x/km,ih*k.y/km,ih*k.x,ih*k.y,
        (a-b*vec2f(1,-1))*k.x/km*sqrt(9.81*km),(a-b*vec2f(1,-1))*k.y/km*sqrt(9.81*km));
    tmp[base+32u*z+x]=transform(x,m);
}
@compute @workgroup_size(32) fn columns(@builtin(local_invocation_index) z:u32,@builtin(workgroup_id) g:vec3u){
    let i=g.y*1024u+z*32u+g.x;let m=transform(z,src[i]);
    field[i]=Field(vec4f(m.values[1].x,m.values[0].x,m.values[2].x,0),vec4f(m.values[3].x,m.values[4].x,m.values[5].x,m.values[6].x));
}
