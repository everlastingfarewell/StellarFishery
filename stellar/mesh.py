"""Square clipmap rings. Split each coarse inner edge at the fine neighbour."""
import numpy as np


def rings(levels=8, half=32):
    """Vertex offsets and triangle indices of the stitched clipmap."""
    vertices, triangles, cache = [], [], {}
    def index(x,z):
        if (x,z) not in cache:
            cache[x,z] = len(vertices)
            vertices.append((x,z))
        return cache[x,z]
    for level in range(levels):
        step = 2**level
        inner = half//2
        for z in range(-half,half):
            for x in range(-half,half):
                if level and -inner<=x<inner and -inner<=z<inner:
                    continue
                outline = [(x,z),(x,z+1),(x+1,z+1),(x+1,z)]
                polygon = []
                for (a,b),(c,d) in zip(outline,outline[1:]+outline[:1]):
                    polygon.append(index(a*step,b*step))
                    if level and max(abs(a),abs(b))==inner and max(abs(c),abs(d))==inner:
                        polygon.append(index((a+c)*step/2,(b+d)*step/2))
                if len(polygon)==4:
                    a,b,c,d=polygon
                    triangles.extend([(a,b,d),(d,b,c)])
                else:
                    center=index((x+.5)*step,(z+.5)*step)
                    triangles.extend((center,p,q) for p,q in zip(polygon,polygon[1:]+polygon[:1]))
    return np.asarray(vertices,np.float32),np.asarray(triangles,np.uint32)
