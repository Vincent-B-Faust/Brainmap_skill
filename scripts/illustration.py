"""Publication illustration: smooth atlas reconstruction / registered BioArt + routed nodes.

Node size and arrow curvature are graphical conventions; anchors are checked in the
selected atlas. A source artwork is not silently treated as a metric atlas section.
"""
import argparse
import copy
import gzip
import hashlib
import html
import json
import re
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import contourpy
import numpy as np
from scipy import ndimage

if __package__:
    from . import atlas_schematic as atlas
    from .diagram_export import diagram_only
    from .validation import finite_json, finite_array, parse_svg
    from .output_bundle import staged_output
else:
    import atlas_schematic as atlas
    from diagram_export import diagram_only
    from validation import finite_json, finite_array, parse_svg
    from output_bundle import staged_output

LEGACY_URL = atlas.BASE + "/annotation/mouse_2011/annotation_25.nrrd"
LEGACY_HASH = "2a69a4a21f56251cebb1564b3ec172c6de8c855a3ca90edce29ff43ba21d7e08"
PALETTE = ["#649E81", "#8477AC", "#D2A35D", "#C7786D", "#6097B0", "#BD8195"]
EXCITATORY, INHIBITORY = "#3E83A5", "#BE655B"


def load_atlas(name, cache):
    nodes = atlas.tree(cache)
    if name == "ccf_2017":
        return atlas.load_volume(cache), nodes, {"name":"Allen CCF2017", "url":atlas.URLS["annotation_25.nrrd"],"sha256":atlas.ANNOTATION_HASH}
    if name != "mouse_2011":
        raise ValueError("Unknown atlas")
    destination = cache.parent / "mouse_2011_25um" / "annotation_25.nrrd"
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".part")
        subprocess.run(["curl","-fL","--retry","2","--max-time","180",LEGACY_URL,"-o",str(temporary)],check=True)
        temporary.replace(destination)
    if atlas.digest(destination) != LEGACY_HASH:
        raise ValueError("Legacy annotation hash mismatch")
    header, payload = destination.read_bytes().split(b"\n\n",1)
    for field in [b"sizes: 528 320 456",b"space directions: (25,0,0) (0,25,0) (0,0,25)",b"encoding: gzip",b"type: unsigned int",b"endian: little"]:
        if field not in header:raise ValueError("Unexpected legacy annotation header")
    volume = np.frombuffer(gzip.decompress(payload),dtype="<u4").reshape(atlas.SHAPE,order="F")
    return volume,nodes,{"name":"Allen Mouse Reference annotation mouse_2011", "url":LEGACY_URL,"sha256":LEGACY_HASH,
                         "note":"Entire figure uses this legacy annotation, including PBl descendants. No CCF2017/2011 mixing."}


def smooth_path(mask, sigma=1.2, knots=28):
    """Stylize background with sparse, closed cubic curves, not traced pixel edges.

    Equidistant contour samples avoid a pile-up of control points at voxel stairs.
    These illustrative curves are never used for anatomical membership checks.
    """
    z=ndimage.gaussian_filter(np.pad(mask.astype(float),8),sigma)
    lines=contourpy.contour_generator(z=z).lines(.5)
    result=[]
    for line in lines:
        line=line-8
        if len(line)<8:continue
        if np.linalg.norm(line[0]-line[-1])>1e-8:line=np.vstack([line,line[0]])
        lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(line,axis=0),axis=1))]
        if lengths[-1]<3:continue
        count=max(8,min(knots,int(lengths[-1]/5)))
        t=np.linspace(0,lengths[-1],512,endpoint=False)
        samples=np.column_stack([np.interp(t,lengths,line[:,dim]) for dim in (0,1)])
        samples=ndimage.gaussian_filter1d(samples,512/count*.38,axis=0,mode="wrap")
        base=samples[np.linspace(0,511,count,endpoint=False).astype(int)]
        path=f'M{base[0,0]:.2f},{base[0,1]:.2f}'
        for i,p in enumerate(base):
            before,after,later=base[(i-1)%count],base[(i+1)%count],base[(i+2)%count]
            c1=p+(after-before)/6
            c2=after-(later-p)/6
            path+=f' C{c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {after[0]:.2f},{after[1]:.2f}'
        result.append(path+' Z')
    return " ".join(result)


def cerebellum_schematic(mask, stroke_width=1.9):
    """Decorative lobules/arbor within the atlas CB box; not parcel boundaries."""
    yy,xx=np.where(mask)
    x,y,w,h=xx.min(),yy.min(),np.ptp(xx),np.ptp(yy)
    outline=("M18,7 C9,3 3,13 6,22 C-1,27 0,40 5,46 "
             "C0,53 1,65 7,70 C4,80 12,90 24,91 "
             "C30,101 43,103 51,96 C62,103 75,100 79,92 "
             "C91,94 100,83 96,74 C105,67 101,55 96,50 "
             "C103,40 98,29 90,27 C93,17 81,9 72,10 "
             "C68,0 53,-1 44,5 C35,-2 23,0 18,7 Z")
    branches=[
      "M43,86 C45,65 45,42 29,24 C23,18 21,13 23,8 C31,14 33,19 36,24 C47,37 54,62 43,86 Z",
      "M45,76 C55,57 63,35 55,16 C52,10 51,7 53,4 C63,11 68,23 66,35 C64,52 56,67 45,76 Z",
      "M48,77 C65,65 80,48 81,30 C82,23 81,18 78,14 C89,22 91,30 86,41 C79,58 65,69 48,77 Z",
      "M47,83 C67,80 81,69 91,55 C94,51 95,47 95,43 C100,56 95,65 85,72 C71,82 58,86 47,83 Z",
      "M42,85 C32,72 17,68 10,55 C8,51 8,46 10,42 C15,53 21,57 29,64 C39,72 43,78 42,85 Z",
      "M40,75 C34,57 18,48 13,31 C11,26 12,22 14,19 C17,32 25,38 32,46 C41,57 44,67 40,75 Z",
      "M43,89 C59,94 75,92 85,86 C80,97 60,100 43,89 Z"]
    # Bake the nonuniform local scale into coordinates, never into the stroke.
    def mapped(path):
        return re.sub(r'(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)',
                      lambda m:f'{x+float(m[1])*w/100:.3f},{y+float(m[2])*h/100:.3f}',path)
    paths=''.join(f'<path d="{mapped(d)}" fill="#FFFFFF" stroke="none"/>' for d in branches)
    return f'<g id="stylized-cerebellar-lobules"><path d="{mapped(outline)}" fill="#F3F3F3" stroke="#606162" stroke-width="{stroke_width}"/>{paths}</g>'


def ellipse_port(center, radius, toward, gap=2):
    direction=np.asarray(toward,float)-center
    if np.linalg.norm(direction)<1e-8:raise ValueError("Undefined node port")
    t=1/np.sqrt(np.sum((direction/np.asarray(radius))**2))
    return center+direction*t+direction/np.linalg.norm(direction)*gap


def bezier_points(control, count=101):
    t=np.linspace(0,1,count)[:,None]
    p=np.asarray(control,float)
    return (1-t)**3*p[0]+3*(1-t)**2*t*p[1]+3*(1-t)*t*t*p[2]+t**3*p[3]


def overlaps(points, node, margin=6):
    return np.sum(((points-np.asarray(node["center"]))/(np.asarray(node["radius"])+margin))**2,axis=1)<1


def crossings(a,b):
    # Count crossings using downsampled polylines, excluding endpoint neighborhoods.
    a=a[5:-5:4];b=b[5:-5:4]
    if len(a)<2 or len(b)<2:return 0
    p=a[:-1,None,:];r=(a[1:]-a[:-1])[:,None,:]
    q=b[None,:-1,:];s=(b[1:]-b[:-1])[None,:,:]
    cross=lambda u,v:u[...,0]*v[...,1]-u[...,1]*v[...,0]
    den=cross(r,s);valid=np.abs(den)>1e-8
    safe=np.where(valid,den,1)
    t=cross(q-p,s)/safe;u=cross(q-p,r)/safe
    return int(np.count_nonzero(valid&(t>0)&(t<1)&(u>0)&(u<1)))


def route_edge(edge, nodes, previous, canvas):
    finite_json(edge)
    canvas=finite_array(canvas,"canvas",(2,))
    if np.any(canvas<=24):raise ValueError("Canvas must exceed routing margins")
    checked_nodes={}
    for label,node in nodes.items():
        center=finite_array(node["center"],"node center",(2,))
        radius=finite_array(node["radius"],"node radius",(2,))
        if np.any(radius<=0):raise ValueError("Node radii must be positive")
        checked_nodes[label]={**node,"center":center,"radius":radius}
    nodes=checked_nodes
    checked_previous=[]
    for points in previous:
        p=finite_array(points,"previous route")
        if p.ndim!=2 or p.shape[1]!=2 or len(p)<31:raise ValueError("Invalid previous route shape")
        checked_previous.append(p)
    previous=checked_previous
    start,end=nodes[edge["from"]],nodes[edge["to"]]
    if edge["from"]==edge["to"]:raise ValueError("Self loops require an explicit specialized layout")
    s,t=np.array(start["center"]),np.array(end["center"])
    delta=t-s;length=np.linalg.norm(delta)
    if not np.isfinite(length) or length<1e-8:raise ValueError("Node centers must be distinct and finite")
    normal=np.array([-delta[1],delta[0]])/length
    bends=[0,-35,35,-65,65,-90,90,-130,130,-190,190,-260,260,-350,350,-450,450]
    if "bend_px" in edge:bends=[float(edge["bend_px"])]+bends
    best=None
    for bend in bends:
        c1=s+delta/3+normal*bend;c2=s+2*delta/3+normal*bend
        p0=ellipse_port(s,start["radius"],c1,3)
        p3=ellipse_port(t,end["radius"],c2,5)
        cp=finite_array([p0,c1,c2,p3],"route control points",(4,2));points=finite_array(bezier_points(cp),"route samples",(101,2))
        hit_labels=[label for label,n in nodes.items() if label not in (edge["from"],edge["to"]) and overlaps(points,n).any()]
        self_hits=int(overlaps(points[12:-12],start,0).any())+int(overlaps(points[12:-12],end,0).any())
        cross_count=sum(crossings(points,p) for p in previous)
        near_overlap=sum(int((np.linalg.norm(points[15:-15,None,:]-p[None,15:-15,:],axis=2).min(axis=1)<9).sum()) for p in previous)
        outside=int(((points[:,0]<12)|(points[:,0]>canvas[0]-12)|(points[:,1]<12)|(points[:,1]>canvas[1]-12)).sum())
        score=len(hit_labels)*1e7+self_hits*1e7+outside*1e6+cross_count*40000+near_overlap*70+abs(bend)*.18+np.linalg.norm(np.diff(points,axis=0),axis=1).sum()*.01
        if bend==0:score+=1200
        if "bend_px" in edge:score+=abs(bend-edge["bend_px"])*12
        if not np.isfinite(score):raise ValueError("Non-finite route score")
        candidate={"control":np.asarray(cp),"points":points,"score":float(score),"node_intrusions":hit_labels,"self_intrusions":self_hits,"crossings":cross_count,"near_overlap_samples":near_overlap,"outside_samples":outside,"bend_px":bend}
        if best is None or score<best["score"]:best=candidate
    if best["node_intrusions"] or best["self_intrusions"] or best["outside_samples"]:
        raise ValueError(f"Cannot route {edge['from']} -> {edge['to']} without node/canvas collisions; change layout or use several panels")
    return best


def fit_registration(profile):
    finite_json(profile)
    fit=profile.get("landmarks",[]);held=profile.get("holdout_landmarks",[])
    if len(fit)<3 or len(held)<2:raise ValueError("BioArt mapping requires >=3 fitting and >=2 independent held-out landmarks")
    threshold=finite_array(profile.get("max_holdout_error_art_units",8),"holdout threshold",())
    if threshold<0:raise ValueError("Holdout threshold must be nonnegative")
    points=fit+held
    atlas_xy=finite_array([p["atlas_pixel_xy"] for p in points],"atlas landmarks",(len(points),2))
    art_xy=finite_array([p["art_xy"] for p in points],"art landmarks",(len(points),2))
    # A fixed absolute tolerance in each native coordinate system; no relative
    # tolerance that would merge distinct points at large coordinate origins.
    tolerance=1e-6
    for coords in (atlas_xy,art_xy):
        for i in range(len(coords)):
            if np.any(np.linalg.norm(coords[i+1:]-coords[i],axis=1)<=tolerance):
                raise ValueError("Duplicate or reused registration landmark (tolerance 1e-6 native units)")
    x=np.column_stack([atlas_xy[:len(fit)],np.ones(len(fit))]);y=art_xy[:len(fit)]
    if np.linalg.matrix_rank(x)<3:raise ValueError("Registration landmarks are collinear")
    matrix=finite_array(np.linalg.lstsq(x,y,rcond=None)[0],"registration matrix",(3,2))
    if np.linalg.matrix_rank(matrix[:2])<2:raise ValueError("Registration transform is singular")
    h=np.column_stack([atlas_xy[len(fit):],np.ones(len(held))])
    errors=finite_array(np.linalg.norm(h@matrix-art_xy[len(fit):],axis=1),"holdout errors",(len(held),))
    if np.max(errors)>threshold:
        raise ValueError(f"BioArt landmark holdout error too high: {errors.tolist()}")
    return matrix,errors.tolist()


def bioart_viewport(root, matrix):
    """Map original SVG user coordinates, including a nonzero viewBox origin."""
    try:viewbox=finite_array([float(x) for x in root.get("viewBox", "").replace(',', ' ').split()],"viewBox",(4,))
    except (TypeError,ValueError) as error:raise ValueError("BioArt needs a finite viewBox with positive dimensions") from error
    if np.any(viewbox[2:]<=0):raise ValueError("viewBox dimensions must be positive")
    matrix=finite_array(matrix,"registration matrix",(3,2))
    art_scale=1480/viewbox[2];height=float(viewbox[3]*art_scale+150)
    finite_array([art_scale,height],"BioArt viewport",(2,))
    root.set("x","60");root.set("y","15");root.set("width","1480");root.set("height",str(viewbox[3]*art_scale))
    root.set("preserveAspectRatio","xMinYMin meet")
    def map_xy(xy):
        xy=finite_array(xy,"atlas point",(2,))
        return finite_array(((np.r_[xy,1]@matrix)-viewbox[:2])*art_scale+np.array([60,15]),"drawing point",(2,))
    return map_xy,height


def draw(request,out,cache,profile=None):
    request=atlas.validate_request(request)
    if profile is not None:finite_json(profile)
    style=request.get("illustration",{})
    background=style.get("background","allen-reconstruction")
    version=style.get("atlas","mouse_2011")
    if background=="allen-reconstruction" and not style.get("allow_reconstruction",False):
        raise ValueError("Atlas reconstruction must be explicitly allowed; do not silently replace requested BioArt artwork")
    volume,ontology,source=load_atlas(version,cache)
    regions=atlas.prepare_regions(request,ontology)
    s=atlas.section(volume,request["view"],regions)
    if not s["brain"].any():raise ValueError("No tissue in view")
    if any(not m.any() for m in s["masks"]):
        raise ValueError("Illustration target missing from selected atlas/view. Do not invent a node or substitute its parent.")
    background_mask=s["brain"]
    background_view=copy.deepcopy(request["view"])
    if background=="allen-reconstruction" and s["plane"]=="sagittal" and s["mode"]=="projection":
        # Off-plane target anchors remain depth-projected; the anatomical
        # backdrop is the actual midsagittal slice, not a silently widened slab.
        background_view.update(mode="slice",position_um=atlas.MIDLINE_UM,hemisphere="both")
        background_view.pop("slab_um",None)
        background_mask=atlas.section(volume,background_view,[])["brain"]
        if not background_mask.any():raise ValueError("No midsagittal tissue for the projection background")
    bb=np.where(background_mask);xmin,xmax=int(bb[1].min()),int(bb[1].max());ymin,ymax=int(bb[0].min()),int(bb[0].max())
    width=1600;scale=1480/max(1,xmax-xmin);height=(ymax-ymin)*scale+200
    offset=np.array([60-xmin*scale,45-ymin*scale])
    profile_audit=None
    if background=="bioart":
        if profile is None:raise ValueError("BioArt mode needs a verified species/plane/landmark registration profile")
        if profile.get("species")!="Mus musculus" or profile.get("plane")!=s["plane"]:
            raise ValueError("BioArt species/plane mismatch")
        if s["oblique"] or s["mode"]!="slice":raise ValueError("A registered BioArt coronal drawing cannot be reused as oblique section or depth projection")
        if profile.get("atlas")!=version or profile.get("position_um")!=request["view"]["position_um"]:
            raise ValueError("BioArt registration was created for another atlas or section")
        artwork=Path(__file__).parent/"assets"/profile["asset_file"]
        if atlas.digest(artwork)!=profile["sha256"]:raise ValueError("BioArt asset hash mismatch")
        matrix,errors=fit_registration(profile)
        root=parse_svg(artwork.read_text(encoding="utf-8"))
        map_xy,height=bioart_viewport(root,matrix)
        profile_audit={"profile":profile,"matrix_atlas_pixel_to_art_xy":matrix.tolist(),"holdout_errors_art_units":errors,"claim":"Schematic landmark mapping; artwork has no source AP coordinate, not a histological registration."}
        background_svg=ET.tostring(root,encoding="unicode")
    elif background=="allen-reconstruction":
        map_xy=lambda xy:np.array(xy)*scale+offset
        art_mask=background_mask.copy()
        background_path=smooth_path(ndimage.binary_fill_holes(art_mask),4.5,32)
        cb_svg=""
        background_svg=f'<defs><linearGradient id="brain-tissue" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F2F2F2"/><stop offset="1" stop-color="#F2F2F2"/></linearGradient><clipPath id="tissue-clip"><path d="{background_path}"/></clipPath></defs><g id="allen-reconstructed-background" transform="translate({offset[0]},{offset[1]}) scale({scale})"><path d="{background_path}" fill="url(#brain-tissue)" stroke="#606162" stroke-width="{5/scale}" fill-rule="evenodd"/><g clip-path="url(#tissue-clip)">'
        # Show a small number of real atlas landmarks, not the complete parcellation.
        lobules=["LING","CENT2","CENT3","CUL","DEC","FOTU","PYR","UVU","NOD"]
        context_queries=["CTX","CB"]+lobules+["arb","cc"] if s["plane"]=="sagittal" else ["cc"]
        context_regions=atlas.prepare_regions({"regions":[{"structure":q} for q in context_queries]},ontology)
        context_view=copy.deepcopy(background_view)
        ctx=atlas.section(volume,context_view,context_regions)
        if ctx["brain"].shape==s["brain"].shape:
            for query,mask in zip(context_queries,ctx["masks"]):
                if mask.any():
                    fill,stroke=("#E8ECE9","none") if query=="CB" else (("#F5F5F5","none") if query=="CTX" else ("#FFFFFF","none"))
                    if query in lobules:fill="#E2E7E3" if lobules.index(query)%2==0 else "#ECEFEC"
                    labels,count=ndimage.label(mask);sizes=np.bincount(labels.ravel());sizes[0]=0
                    mask=sizes[labels]>=35
                    background_svg+=f'<path d="{smooth_path(mask,3 if query in ("CB","CTX") else 1.5,24 if query in ("CB","CTX") else 12)}" fill="{fill}" stroke="{stroke}" stroke-width="0.65" fill-rule="evenodd"/>'
            # Unassigned internal spaces in the actual median section provide a
            # white-matter/ventricular visual cue, without inventing a named tract.
            # Unassigned islands are kept out of the artwork; they can be
            # annotation gaps rather than meaningful white-matter anatomy.
        background_svg+='</g>'+cb_svg+'</g>'
    else:raise ValueError("background must be bioart or allen-reconstruction")
    data={};qa={};entries=[]
    for i,(reg,mask) in enumerate(zip(regions,s["masks"])):
        y,x=map(int,atlas.anchor(mask));ccf=s["points"][:,y,x].copy()
        if s["mode"]=="projection":
            first,last=s["depths"]
            candidates=np.tile(ccf,(last-first,1));candidates[:,s["axis"]]=np.arange(first,last)*atlas.RES
            ijk=np.floor(candidates/atlas.RES+.5).astype(int);labels=volume[tuple(ijk.T)]
            hits=np.isin(labels,reg["ids"])
            if s["hemisphere"]=="left":hits&=candidates[:,2]<5700
            if s["hemisphere"]=="right":hits&=candidates[:,2]>=5700
            ccf=candidates[np.flatnonzero(hits)[0]]
        ijk=np.floor(ccf/atlas.RES+.5).astype(int);actual=int(volume[tuple(ijk)])
        if actual not in reg["ids"]:raise AssertionError("Illustration anchor membership failed")
        center=map_xy([x,y]);label=reg["label"]
        radius=np.array([max(48,len(label)*8+15),27.0])
        color=request["regions"][i].get("color",PALETTE[i%len(PALETTE)])
        data[label]={"center":center.tolist(),"radius":radius.tolist(),"color":color,"fill_color":request["regions"][i].get("fill_color")}
        entries.append({"label":label,"structures":reg["components"],"custom_union":reg["custom_union"],"atlas_anchor_pixel_xy":[x,y],"ccf_anchor_ap_dv_ml_um":ccf.tolist(),"actual_structure_id":actual,"anchor_membership_pass":True,"drawing_center_xy":center.tolist(),"glyph_radius_px":radius.tolist()})
        qa[f'region_{i}']=mask
    # Labels stay on their atlas anchors. Stop rather than hiding overlap by moving anatomy.
    labels=list(data)
    for i,label in enumerate(labels):
        for other in labels[i+1:]:
            a,b=data[label],data[other]
            if np.sum(((np.array(a["center"])-b["center"])/(np.array(a["radius"])+b["radius"]+4))**2)<1:
                raise ValueError(f"Node labels {label}/{other} overlap at this scale; use a detail panel or shorter labels")
    esc=lambda x:html.escape(str(x),quote=True)
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height:.2f}" width="{width}" height="{height:.2f}">',
           '<style>text{font-family:Arial,Helvetica,sans-serif}path{stroke-linejoin:round;stroke-linecap:round}</style>',
           '<rect width="100%" height="100%" fill="white"/>',background_svg,'<g id="circuit-connections">']
    routes=[];previous=[]
    for i,edge in enumerate(request.get("connections",[])):
        if edge["from"] not in data or edge["to"] not in data:raise ValueError("Missing connection endpoint")
        kind=edge.get("kind","projection")
        if kind not in ("excitatory","inhibitory"):
            raise ValueError("Illustration arrows require explicit excitatory or inhibitory kind; do not infer sign from projection existence")
        route=route_edge(edge,data,previous,[width,height-85]);previous.append(route["points"])
        color=edge.get("color",EXCITATORY if kind=="excitatory" else INHIBITORY)
        cp=route["control"];end=cp[-1];direction=end-cp[-2];direction/=np.linalg.norm(direction);normal=np.array([-direction[1],direction[0]])
        d=f'M{cp[0,0]:.2f},{cp[0,1]:.2f} C{cp[1,0]:.2f},{cp[1,1]:.2f} {cp[2,0]:.2f},{cp[2,1]:.2f} {cp[3,0]:.2f},{cp[3,1]:.2f}'
        parts.append(f'<g id="edge-{i}" data-kind="{kind}"><title>{esc(edge["evidence"]+": "+edge["source"])}</title><path d="{d}" fill="none" stroke="{color}" stroke-width="6.2"/>')
        if kind=="excitatory":
            p=end-direction*21
            points=[end,p+normal*10,p-normal*10]
            parts.append('<polygon points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in points)+f'" fill="{color}"/>')
        else:
            a,b=end+normal*13,end-normal*13
            parts.append(f'<path d="M{a[0]:.2f},{a[1]:.2f} L{b[0]:.2f},{b[1]:.2f}" fill="none" stroke="{color}" stroke-width="6.2"/>')
        parts.append('</g>')
        routes.append({**edge,**{k:v for k,v in route.items() if k not in ("points","control")},"control_xy":cp.tolist(),"terminal":"triangle" if kind=="excitatory" else "perpendicular_bar"})
    parts.append('</g><g id="region-node-labels">')
    for label,node in data.items():
        x,y=node["center"];rx,ry=node["radius"];color=node["color"]
        rgb=np.array([int(color[j:j+2],16) for j in (1,3,5)]);light=np.round(rgb*.35+255*.65).astype(int);fill=node.get('fill_color') or '#'+''.join(f'{c:02x}' for c in light)
        fill_rgb=np.array([int(fill[j:j+2],16) for j in (1,3,5)])
        text_color='#FFFFFF' if np.dot(fill_rgb,[.2126,.7152,.0722])<145 else '#26343D'
        parts.append(f'<g data-region="{esc(label)}"><ellipse cx="{x:.2f}" cy="{y:.2f}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{color}" stroke-width="3.0"/><text x="{x:.2f}" y="{y+9.5:.2f}" text-anchor="middle" font-size="31" font-weight="500" fill="{text_color}">{esc(label)}</text></g>')
    parts.append('</g>')
    parts.append('<g id="figure-annotations">')
    caption=('Allen atlas reconstruction' if background=='allen-reconstruction' else 'NIH BioArt + Allen landmark mapping')
    caption+=(' · midsagittal backdrop + depth-projected regions' if s['plane']=='sagittal' else ' · depth-projected regions') if s['mode']=='projection' else ' · section schematic'
    parts.append(f'<text x="60" y="{height-51:.2f}" font-family="Arial" font-size="16" fill="#687577">{esc(caption)}</text>')
    parts.append(f'<text x="60" y="{height-25:.2f}" font-family="Arial" font-size="13" fill="#7D8787">Atlas-derived anchor positions; node sizes and curves are schematic. Connection evidence is recorded in audit.json.</text>')
    # Compact semantic key; evidence status is kept separate from terminal shape.
    parts.append(f'<path d="M1190,{height-54} h58" stroke="{EXCITATORY}" stroke-width="4"/><polygon points="1248,{height-54} 1234,{height-61} 1234,{height-47}" fill="{EXCITATORY}"/><text x="1260" y="{height-48}" font-size="15" fill="#556369">Activation</text>')
    parts.append(f'<path d="M1390,{height-54} h52 m0,-10 v20" fill="none" stroke="{INHIBITORY}" stroke-width="4"/><text x="1454" y="{height-48}" font-size="15" fill="#556369">Inhibition</text>')
    parts.append('</g>')
    audit={"renderer":"publication-illustration-v0.3.2","background":background,"background_view":background_view,"atlas":source,"ontology_url":atlas.URLS["structure_graph.json"],"ontology_sha256":atlas.digest(cache/"structure_graph.json"),"view":request["view"],"regions":entries,"connections":routes,"registration":profile_audit,
           "background_smoothing":"Artistically simplified background: Gaussian sigma 4.5 voxels, equal-arclength low-pass sampling and 32 closed cubic Bezier segments. Internal shapes use 12-24 segments. Unassigned islands omitted; ROI anchors and masks remain unsmoothed.", "visual_style":"Uniform gray brain outline, pale tissue and pastel nodes; cerebellar lobules and arbor vitae follow actual source annotation masks in the background view. Background smoothing is illustrative; ROI anchors remain unsmoothed.","claims":{"anchor_membership":"verified","glyph_is_region_boundary":False,"arrow_is_axon_trajectory":False,"crossings":sum(r['crossings'] for r in routes)}}
    parts.append('<metadata>'+esc(json.dumps(audit,ensure_ascii=False,allow_nan=False))+'</metadata></svg>')
    destination=Path(out)
    with staged_output(destination) as out:
        (out/'figure.svg').write_text(diagram_only('\n'.join(parts),data,height-85),encoding='utf-8')
        (out/'figure-notes.md').write_text(caption+'\n\nAtlas-derived anchor positions; node glyphs and curves are schematic. Connection evidence is recorded in audit.json.\n\nAllen Institute: https://atlas.brain-map.org/ ; terms and citation: https://alleninstitute.org/legal/terms-of-use and https://alleninstitute.org/legal/citation-policy/\n',encoding='utf-8')
        (out/'audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        (out/'request.json').write_text(json.dumps(request,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        np.savez_compressed(out/'masks.npz',brain=s['brain'],**qa)
    out=destination
    print(json.dumps({"output":str(out),"background":background,"atlas":source['name'],"regions":len(entries),"edges":len(routes),"node_intrusions":0,"crossings":audit['claims']['crossings']}, allow_nan=False))
    return audit


def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--cache',type=Path,default=atlas.cache_default());parser.add_argument('--profile',type=Path)
    args=parser.parse_args()
    try:
        request=json.loads(args.request.read_text(encoding='utf-8'))
        profile=json.loads(args.profile.read_text(encoding='utf-8')) if args.profile else None
        illustrate_request(request,args.out,args.cache,profile)
    except (ValueError,KeyError,OSError,subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}',file=sys.stderr);return 2
    return 0


def illustrate_request(request,out,cache=None,profile=None):
    """Public model-independent illustration API; returns the spatial/layout audit."""
    return draw(request,out,Path(cache) if cache is not None else atlas.cache_default(),profile)


if __name__=='__main__':raise SystemExit(cli())
