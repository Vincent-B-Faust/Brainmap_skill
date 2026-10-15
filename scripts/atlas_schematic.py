#!/usr/bin/env python3
"""Allen CCF2017 25 um -> editable SVG, PNG/PDF, masks and spatial audit.

Dependencies: numpy scipy matplotlib contourpy jsonschema. Downloads use curl with TLS verification.
No generative anatomy, approximate Bregma transform, or implicit acronym guessing.
"""
import argparse
import copy
import datetime
import gzip
import hashlib
import html
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import numpy as np
from scipy import ndimage
import contourpy
from jsonschema import Draft202012Validator

if __package__:
    from .validation import finite_json, parse_svg
    from .output_bundle import staged_output
else:
    from validation import finite_json, parse_svg
    from output_bundle import staged_output

BASE = "https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf"
URLS = {
    "annotation_25.nrrd": BASE + "/annotation/ccf_2017/annotation_25.nrrd",
    "structure_graph.json": "https://api.brain-map.org/api/v2/structure_graph_download/1.json",
}
ANNOTATION_HASH = "c620cbcc562183e4dcd40250d440130501781f74b41de35b1c1bdabace290c42"
ALIASES = {"LPB": "PBl", "Arc": "ARH", "ARC": "ARH", "MnPO": "MEPO"}
COLORS = ["#7c70bf", "#d6a34b", "#4d9cb3", "#ba667d", "#649756", "#cb7151", "#727bad"]
RES = 25.0
SHAPE = (528, 320, 456)
MIDLINE_UM = SHAPE[2] * RES / 2


def request_schema():
    return json.loads(Path(__file__).with_name("request.schema.json").read_text(encoding="utf-8"))


def validate_request(config):
    # Reject non-JSON numeric values even for callers constructing Python dictionaries.
    finite_json(config)
    errors = list(Draft202012Validator(request_schema()).iter_errors(config))
    if errors:
        error = errors[0]
        path = ".".join(map(str,error.absolute_path)) or "request"
        raise ValueError(f"Invalid request at {path}: {error.message}")
    config = copy.deepcopy(config)
    view = config["view"]
    view.setdefault("position_um", MIDLINE_UM)
    if "slab_um" in view and view.get("mode","slice") != "projection":
        raise ValueError("slab_um requires mode=projection; it must not silently be ignored in a slice")
    if view.get("mode","slice") == "projection" and any(view.get("rotation_deg_ap_dv_ml",[0,0,0])):
        raise ValueError("Oblique projection is not implemented; choose an oblique slice or orthogonal projection")
    if "slab_um" in view and view["slab_um"][0] > view["slab_um"][1]:
        raise ValueError("slab_um must have min <= max")
    axis = {"sagittal":2,"coronal":0,"horizontal":1}[view.get("plane","sagittal")]
    if view["position_um"] > (SHAPE[axis]-1)*RES:
        raise ValueError("position_um outside atlas")
    if "slab_um" in view and view["slab_um"][1] > (SHAPE[axis]-1)*RES:
        raise ValueError("slab_um outside atlas")
    labels = [r.get("label",str(r.get("structure",r.get("structures")))) for r in config["regions"]]
    if len(labels)!=len(set(labels)):
        raise ValueError("Display labels must be unique")
    # Connection endpoints are checked after ontology resolution: an integer ID
    # or full English structure name can acquire a different default acronym.
    return config


def render_request(config, out, cache=None):
    """Validate and render a model-independent request; return its spatial audit."""
    config = validate_request(config)
    if config.get("illustration"):
        raise ValueError("Illustration settings require brainmap-illustrate / illustrate_request; brainmap render is the atlas QA renderer")
    cache = Path(cache) if cache is not None else cache_default()
    out = Path(out)
    make_output(config,load_volume(cache),tree(cache),cache,out)
    return json.loads((out/"audit.json").read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cache_default():
    return Path.home() / ".cache/allen-mouse-brain-schematic/ccf_2017_25um"


def fetch(cache):
    cache.mkdir(parents=True, exist_ok=True)
    for name, url in URLS.items():
        dest = cache / name
        if not dest.exists():
            temp = dest.with_suffix(".part")
            subprocess.run(["curl", "--fail", "--location", "--retry", "2", "--max-time", "180", url, "-o", str(temp)], check=True)
            temp.replace(dest)
    # Validate before recording a cache as usable.
    load_volume(cache)
    tree(cache)
    record = {"retrieved_or_verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "files": {k: {"url": u, "sha256": digest(cache / k)} for k, u in URLS.items()}}
    (cache / "download_manifest.json").write_text(json.dumps(record, indent=2, allow_nan=False),encoding="utf-8")
    print(json.dumps(record, indent=2, allow_nan=False))


def tree(cache):
    obj = json.loads((cache / "structure_graph.json").read_text(encoding="utf-8"))
    nodes = {}
    def visit(n):
        nodes[n["id"]] = n
        for child in n.get("children", []):
            visit(child)
    for root in obj["msg"]:
        visit(root)
    return nodes


def resolve(query, nodes):
    if isinstance(query, int):
        if query not in nodes:
            raise ValueError(f"Unknown Allen structure ID: {query}")
        return nodes[query], None
    alias = ALIASES.get(query)
    key = alias or query
    hits = [n for n in nodes.values() if n["acronym"] == key or n["name"].lower() == key.lower()]
    if len(hits) != 1:
        candidates = [{k: n[k] for k in ("id", "acronym", "name")} for n in nodes.values()
                      if query.lower() in n["name"].lower() or query.lower() in n["acronym"].lower()][:20]
        if query.upper() == "POA":
            candidates = [{k: n[k] for k in ("id", "acronym", "name")} for n in nodes.values() if n["acronym"] in ("MPO", "MEPO", "LPO", "AVPV", "MPN")]
        raise ValueError(f"Unresolved/ambiguous region {query!r}; specify exact Allen acronym/ID or an explicit union. Candidates: {candidates}")
    return hits[0], ({"input": query, "canonical": key} if alias else None)


def descendants(node):
    result = [node["id"]]
    for child in node.get("children", []):
        result += descendants(child)
    return result


def annotation_ids(volume):
    present=set()
    for ap in range(0,volume.shape[0],16):
        present.update(map(int,np.unique(volume[ap:ap+16])))
    return present


def load_volume(cache):
    path = cache / "annotation_25.nrrd"
    if digest(path) != ANNOTATION_HASH:
        raise ValueError("Annotation SHA256 differs from the validated CCF2017 25um file. Inspect the new release; do not silently accept a different atlas.")
    with path.open("rb") as f:
        lines = []
        while True:
            line = f.readline()
            if not line.strip():
                break
            lines.append(line.decode().strip())
        header = dict(s.split(":", 1) for s in lines if ":" in s and not s.startswith("#"))
        header = {k: v.strip() for k, v in header.items()}
        expected = {"type": "unsigned int", "dimension": "3", "sizes": "528 320 456", "encoding": "gzip", "endian": "little", "space directions": "(25,0,0) (0,25,0) (0,0,25)", "space origin": "(0,0,0)"}
        for k, v in expected.items():
            if header.get(k) != v:
                raise ValueError(f"Unexpected NRRD header {k}: {header.get(k)}")
        a = np.frombuffer(gzip.decompress(f.read()), dtype="<u4").reshape(SHAPE, order="F")
    return a


def prepare_regions(config, nodes):
    result = []
    for i, region in enumerate(config["regions"]):
        queries = region.get("structures", [region.get("structure", region.get("label"))])
        if not queries or any(x is None for x in queries):
            raise ValueError("Each region needs structure(s) or an exact label.")
        resolved = [resolve(q, nodes) for q in queries]
        ids = sorted({sid for n, _ in resolved for sid in descendants(n)})
        label = region.get("label", resolved[0][0]["acronym"])
        color = region.get("color", COLORS[i % len(COLORS)])
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Colors must be #RRGGBB")
        result.append({"label": label, "ids": ids, "color": color,
                       "components": [{k: n[k] for k in ("id", "name", "acronym")} for n, _ in resolved],
                       "aliases": [alias for _, alias in resolved if alias],
                       "custom_union": len(queries) > 1})
    labels = [r["label"] for r in result]
    if len(labels) != len(set(labels)):
        raise ValueError("Display labels must be unique")
    return result


def rotation(angles):
    # Active right-handed rotations in the numeric CCF (AP,DV,ML) basis.
    out = np.eye(3)
    for axis, deg in enumerate(angles):
        t = math.radians(float(deg)); c, s = math.cos(t), math.sin(t)
        j, k = (axis + 1) % 3, (axis + 2) % 3
        r = np.eye(3); r[j, j] = r[k, k] = c; r[j, k] = -s; r[k, j] = s
        out = r @ out
    return out


def section(volume, view, regions):
    plane = view.get("plane", "sagittal")
    # [slice axis, horizontal array axis, vertical array axis]
    axes = {"sagittal": (2, 0, 1), "coronal": (0, 2, 1), "horizontal": (1, 2, 0)}
    if plane not in axes:
        raise ValueError("plane must be sagittal, coronal or horizontal")
    axis, ux, vy = axes[plane]
    if "position_um" not in view:
        raise ValueError("Specify position_um in CCF coordinates; no implicit Bregma conversion")
    position = float(view["position_um"])
    if not 0 <= position <= (SHAPE[axis]-1)*RES:
        raise ValueError("position_um outside atlas")
    center = (np.array(SHAPE)-1) * RES / 2
    center[axis] = position
    mode = view.get("mode", "slice")
    if mode not in ("slice", "projection"):
        raise ValueError("mode must be slice or projection")
    hemisphere = view.get("hemisphere", "both")
    if hemisphere not in ("both", "left", "right"):
        raise ValueError("hemisphere must be both, left or right")
    angles = np.asarray(view.get("rotation_deg_ap_dv_ml", [0, 0, 0]), float)
    if angles.shape != (3,) or not np.all(np.isfinite(angles)):
        raise ValueError("rotation_deg_ap_dv_ml must contain three finite angles")
    oblique = bool(np.any(angles != 0))
    if mode == "projection" and oblique:
        raise ValueError("Oblique projection is not implemented. Use an oblique slice or an orthogonal projection; do not rotate a 2D projection and call it a new slice.")
    r = rotation(angles)
    u, v, n = r[:, ux], r[:, vy], r[:, axis]
    if oblique:
        corners = np.array(np.meshgrid(*[[0, (s-1)*RES] for s in SHAPE], indexing="ij")).reshape(3, -1).T
        pc = corners-center
        xs = np.arange(np.floor((pc @ u).min()/RES), np.ceil((pc @ u).max()/RES)+1) * RES
        ys = np.arange(np.floor((pc @ v).min()/RES), np.ceil((pc @ v).max()/RES)+1) * RES
    else:
        xs = np.arange(SHAPE[ux])*RES-center[ux]
        ys = np.arange(SHAPE[vy])*RES-center[vy]
    xx, yy = np.meshgrid(xs, ys)
    points = center[:, None, None]+u[:, None, None]*xx+v[:, None, None]*yy
    def hemi(mask, coords_ml):
        if hemisphere == "left":
            return mask & (coords_ml < SHAPE[2]*RES/2)
        if hemisphere == "right":
            return mask & (coords_ml >= SHAPE[2]*RES/2)
        return mask
    if mode == "slice":
        # Constant mode guards outside-volume positions before nearest-neighbor indexing.
        sampled = ndimage.map_coordinates(volume, points/RES, order=0, mode="constant", cval=0, prefilter=False)
        brain = hemi(sampled != 0, points[2])
        masks = [hemi(np.isin(sampled, reg["ids"]), points[2]) for reg in regions]
        depths = None
    else:
        lo, hi = view.get("slab_um", [0, (SHAPE[axis]-1)*RES])
        if not 0 <= lo <= hi <= (SHAPE[axis]-1)*RES:
            raise ValueError("Invalid slab_um interval")
        # Slab includes only voxel centers in the closed physical interval.
        start, stop = int(math.ceil(lo/RES)), int(math.floor(hi/RES))+1
        if stop <= start:
            raise ValueError("Projection slab contains no voxel centers")
        selection = [slice(None)]*3; selection[axis] = slice(start, stop)
        sub = volume[tuple(selection)]
        ml = np.arange(SHAPE[2])*RES
        if axis == 2:
            ml = ml[start:stop]
        hm = np.ones(len(ml), bool) if hemisphere == "both" else (ml < SHAPE[2]*RES/2 if hemisphere == "left" else ml >= SHAPE[2]*RES/2)
        order = [a for a in range(3) if a != axis]
        transpose = [order.index(vy), order.index(ux)]
        def project(ids=None):
            # Bound temporary memory for annotation sets with widely separated IDs.
            output_shape=tuple(sub.shape[i] for i in range(3) if i!=axis)
            output=np.zeros(output_shape,dtype=bool)
            for ap in range(0,sub.shape[0],16):
                block=sub[ap:ap+16]
                mask=(block!=0) if ids is None else np.isin(block,ids)
                reduced=np.any(mask & hm[None,None,:],axis=axis)
                if axis==0:output|=reduced
                else:output[ap:ap+16]=reduced
            return output.transpose(transpose)
        brain = project()
        masks = [project(reg["ids"]) for reg in regions]
        depths = (start, stop)
    return {"brain": brain, "masks": masks, "points": points, "xs": xs, "ys": ys,
            "axis": axis, "ux": ux, "vy": vy, "center": center, "u": u, "v": v,
            "normal": n, "depths": depths, "mode": mode, "plane": plane, "hemisphere": hemisphere,
            "rotation": angles.tolist(), "oblique": oblique}


def anchor(mask):
    # Largest connected component, then a maximum interior-distance pixel.
    components, count = ndimage.label(mask)
    if not count:
        return None
    counts = np.bincount(components.ravel()); counts[0] = 0
    component = components == counts.argmax()
    return np.unravel_index(ndimage.distance_transform_edt(np.pad(component, 1))[1:-1, 1:-1].argmax(), mask.shape)


def path_mask(mask, scale):
    # Marching squares at 0.5; no simplification/smoothing, closed holes via evenodd.
    padded = np.pad(mask.astype(float), 1)
    generator = contourpy.contour_generator(x=(np.arange(padded.shape[1])-1)*scale,
                                            y=(np.arange(padded.shape[0])-1)*scale, z=padded)
    paths = []
    for line in generator.lines(.5):
        paths.append("M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in line) + " Z")
    return " ".join(paths)


def make_output(config, volume, nodes, cache, out):
    regions = prepare_regions(config, nodes)
    annotated_ids = annotation_ids(volume)
    unannotated = {r["label"] for r in regions if not annotated_ids.intersection(r["ids"])}
    if unannotated and not config.get("allow_absent",False):
        raise ValueError(f"Ontology entries have no labeled voxels anywhere in this volume: {sorted(unannotated)}. Use a separately verified 2D atlas drawing or a dataset that delineates them; a parent region is not an equivalent substitute.")
    view = config["view"]
    context = prepare_regions({"regions": [{"structure":q} for q in config.get("context_structures", [])]}, nodes)
    s = section(volume, view, regions+context)
    context_masks = s["masks"][len(regions):]
    s["masks"] = s["masks"][:len(regions)]
    missing = [r["label"] for r, mask in zip(regions, s["masks"]) if not mask.any()]
    if missing and not config.get("allow_absent", False):
        raise ValueError(f"Regions absent from this view: {missing}. Choose another section, multiple panels or explicitly request projection; never relocate them by eye. Set allow_absent=true only to report them as absent.")
    if not s["brain"].any():
        raise ValueError("No annotated tissue in view")
    scale = 1.9
    h, w = s["brain"].shape
    bw, bh = (w-1)*scale, (h-1)*scale
    margin, top, rail = 45, 115, 320
    width, height = bw+2*margin+rail, max(bh+top+175, top+len(regions)*75+160)
    def esc(x): return html.escape(str(x), quote=True)
    def text(x, y, value, size=16, fill="#283747", extra=""):
        return f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" fill="{fill}" {extra}>{esc(value)}</text>'
    title = config.get("title", "Allen mouse brain regions")
    label_mode = "OBLIQUE SECTION" if s["oblique"] else "SINGLE SECTION"
    if s["mode"] == "projection": label_mode = "DEPTH PROJECTION — NOT A SINGLE SECTION"
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.1f}" height="{height:.1f}" viewBox="0 0 {width:.1f} {height:.1f}">',
             '<style>text{font-family:Arial,Helvetica,sans-serif}path{stroke-linejoin:round;stroke-linecap:round}</style>',
             '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10Z" fill="context-stroke"/></marker><marker id="bar" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="9" markerHeight="9" orient="auto"><path d="M5 0 L5 10" stroke="context-stroke" stroke-width="2"/></marker></defs>',
             '<rect width="100%" height="100%" fill="white"/>', text(margin, 36, title, 24),
             text(margin, 64, label_mode, 15, "#a14039" if s["mode"] == "projection" else "#526170"),
             text(margin, 89, f'{s["plane"]} | CCF2017 / 25 um | {s["hemisphere"]} hemisphere(s)', 14, "#526170"),
             f'<g id="atlas-anatomy" transform="translate({margin},{top})">',
             f'<path id="annotated-tissue" d="{path_mask(s["brain"], scale)}" fill="#f1f3f5" stroke="#677481" stroke-width="2" fill-rule="evenodd"/>']
    parts.append('<g id="context-boundaries">')
    for c, cm in zip(context, context_masks):
        if cm.any():
            parts.append(f'<path d="{path_mask(cm,scale)}" fill="none" stroke="#c6cdd5" stroke-width="1"><title>{esc(c["label"])}</title></path>')
    parts.append('</g>')
    audits, anchors = [], {}
    for reg, mask in zip(regions, s["masks"]):
        label = reg["label"]
        if not mask.any():
            audits.append({**reg, "status": "unannotated_in_volume" if label in unannotated else "absent_in_view", "sampled_pixels": 0})
            continue
        y, x = map(int, anchor(mask))
        ccf = s["points"][:, y, x].copy()
        if s["mode"] == "projection":
            a, b = s["depths"]
            candidate = np.tile(ccf, (b-a, 1)); candidate[:, s["axis"]] = np.arange(a, b)*RES
            inds = np.floor(candidate/RES+.5).astype(int)
            labels = volume[tuple(inds.T)]
            hits = np.isin(labels, reg["ids"])
            if s["hemisphere"] != "both":
                hits &= (candidate[:, 2] < SHAPE[2]*RES/2) if s["hemisphere"] == "left" else (candidate[:, 2] >= SHAPE[2]*RES/2)
            ccf = candidate[np.flatnonzero(hits)[0]]
        ijk = np.floor(ccf/RES+.5).astype(int)
        actual_id = int(volume[tuple(ijk)])
        if actual_id not in reg["ids"] or not mask[y, x]:
            raise AssertionError("Label anchor failed atlas membership check")
        px, py = x*scale, y*scale
        anchors[label] = (px, py)
        parts.append(f'<g id="region-{len(audits)}" data-label="{esc(label)}"><path d="{path_mask(mask,scale)}" fill="{reg["color"]}" fill-opacity="0.55" fill-rule="evenodd" stroke="{reg["color"]}" stroke-width="1.2"/></g>')
        audits.append({**reg, "status": "visible", "sampled_pixels": int(mask.sum()),
                       "anchor_pixel_xy": [x, y], "anchor_ccf_ap_dv_ml_um": ccf.tolist(),
                       "anchor_voxel_ap_dv_ml": ijk.tolist(), "anchor_actual_structure_id": actual_id,
                       "anchor_membership_pass": True})
    parts.append('<g id="connections">')
    for edge_index, edge in enumerate(config.get("connections", [])):
        if edge["from"] not in anchors or edge["to"] not in anchors:
            raise ValueError("Connection endpoint absent from current view")
        if edge.get("evidence") not in ("user-specified", "published", "hypothesis") or not edge.get("source"):
            raise ValueError("Every edge needs evidence=user-specified/published/hypothesis and a source; atlas membership does not establish connectivity")
        color = edge.get("color", "#3e708e")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color): raise ValueError("Invalid edge color")
        kind = edge.get("kind", "projection")
        if kind not in ("projection", "excitatory", "inhibitory"):
            raise ValueError("Unknown connection kind")
        x1,y1 = anchors[edge["from"]]; x2,y2 = anchors[edge["to"]]
        bend = float(edge.get("bend_px", -70))
        dash = 'stroke-dasharray="7 5"' if edge["evidence"] in ("hypothesis", "user-specified") else ""
        marker = "bar" if kind == "inhibitory" else "arrow"
        # Explicit colors also work in SVG renderers without context-stroke support.
        marker_id = f'edge-marker-{edge_index}'
        glyph = f'<path d="M5 0 L5 10" stroke="{color}" stroke-width="2"/>' if marker=="bar" else f'<path d="M0 0 L10 5 L0 10Z" fill="{color}"/>'
        parts.append(f'<defs><marker id="{marker_id}" viewBox="0 0 10 10" refX="{5 if marker=="bar" else 9}" refY="5" markerWidth="7" markerHeight="7" orient="auto">{glyph}</marker></defs>')
        parts.append(f'<path d="M{x1},{y1} Q{(x1+x2)/2},{(y1+y2)/2+bend} {x2},{y2}" fill="none" stroke="{color}" stroke-width="3" marker-end="url(#{marker_id})" {dash}><title>{esc(edge["evidence"]+": "+edge["source"])}</title></path>')
    parts.append('</g><g id="labels">')
    for i, a in enumerate(audits):
        lx, ly = bw+35, 35+i*72
        if a["status"] != "visible":
            reason = "not delineated" if a["status"]=="unannotated_in_volume" else "absent in view"
            parts.append(text(lx,ly,a["label"]+" — "+reason,17,"#9a4f45")); continue
        px,py = anchors[a["label"]]
        parts.append(f'<path d="M{px},{py} L{lx-12},{ly-6}" stroke="{a["color"]}" stroke-width="1" fill="none"/><circle cx="{px}" cy="{py}" r="3" fill="{a["color"]}"/>')
        parts.append(text(lx,ly,a["label"],19,a["color"], 'font-weight="bold"'))
        parts.append(text(lx,ly+21," + ".join(n["acronym"] for n in a["components"]),13))
        parts.append(text(lx,ly+39,"custom union" if a["custom_union"] else f'Allen ID {a["components"][0]["id"]}',12,"#697783"))
    parts.append('</g></g>')
    u, v = s["u"], s["v"]
    orientation = (f'u(AP,DV,ML)={np.round(u,3).tolist()}  v={np.round(v,3).tolist()}' if s["oblique"] else
                   {"sagittal": "Left to right: A → P   |   Top to bottom: D → V",
                    "coronal": "Left to right: anatomical L → R   |   Top to bottom: D → V",
                    "horizontal": "Left to right: anatomical L → R   |   Top to bottom: A → P"}[s["plane"]])
    footer_y = height-123
    parts.append(text(margin,footer_y,orientation,14))
    depth_desc = f'CCF plane origin: {np.round(s["center"],2).tolist()} um (AP,DV,ML)'
    if s["depths"]:
        a,b = s["depths"]; depth_desc = f'Projected CCF depth: {a*RES:g}–{(b-1)*RES:g} um along axis {s["axis"]} (AP=0,DV=1,ML=2)'
    parts.append(text(margin,footer_y+24,depth_desc,13,"#526170"))
    # Physical scale is defined by the sampled geometry, including for oblique sections.
    bar = 1000/RES*scale
    parts.append(f'<path d="M{margin},{footer_y+49} h{bar}" stroke="#283747" stroke-width="3"/>')
    parts.append(text(margin+bar+10,footer_y+54,"1 mm (atlas)",12))
    parts.append(text(margin,height-39,"Anatomy: Allen Institute, Mouse CCFv3 / CCF2017. Boundaries are atlas-derived; animal-specific anatomy may differ.",11,"#697783"))
    parts.append(text(margin,height-19,"Dashed connections, if present: supplied circuit or hypothesis; arrows are schematic and do not represent axon trajectories.",11,"#697783"))
    report = {"atlas": "Allen Mouse CCF2017 (CCFv3)", "resolution_um": RES,
              "axis_order": ["AP increasing posterior", "DV increasing ventral", "ML increasing right"],
              "array_order": "NRRD Fortran; do not reinterpret the space header as anatomical array order",
              "view": view, "context_structures":context, "actual_plane_origin_ccf_um": s["center"].tolist(),
              "actual_basis_u_v_n": [s[k].tolist() for k in ("u","v","normal")],
              "pixel_grid": {"xs_relative_um": [float(s["xs"][0]),float(s["xs"][-1])], "ys_relative_um": [float(s["ys"][0]),float(s["ys"][-1])], "step_um": RES},
              "geometry": "nearest-neighbor labels; marching squares at 0.5; no smoothing",
              "regions": audits, "connections": config.get("connections", []),
              "sources": {k: {"url":u,"sha256":digest(cache/k)} for k,u in URLS.items()},
              "limitations": ["Atlas accuracy is limited by 25um voxels, section sampling, atlas registration and biological variation.", "Projection combines different depths; overlapping silhouettes do not establish colocalization.", "No Bregma conversion; no axonal-trajectory inference."]}
    if config.get("bioart_mouse_inset", False):
        asset = Path(__file__).resolve().parent/"assets/bioart-283.svg"
        root = parse_svg(asset.read_text(encoding="utf-8"))
        ix, iy = width-210, max(top+len(regions)*72+35, height-300)
        root.set("x",str(ix));root.set("y",str(iy));root.set("width","140");root.set("height","100")
        parts.append('<g id="bioart-species-inset">'+ET.tostring(root,encoding="unicode")+text(ix-15,iy+115,"Mouse icon: NIAID BioArt 283",10)+text(ix-15,iy+130,"Species key; no spatial registration",10)+"</g>")
        report["bioart"] = {"entry":"https://bioart.niaid.nih.gov/bioart/283", "license":"Public Domain", "sha256":digest(asset), "role":"separate species icon; not anatomical ground truth"}
    parts.append('<metadata>'+esc(json.dumps(report,ensure_ascii=False, allow_nan=False))+'</metadata></svg>')
    destination=Path(out)
    with staged_output(destination) as out:
        (out/"figure.svg").write_text("\n".join(parts),encoding="utf-8")
        (out/"audit.json").write_text(json.dumps(report,indent=2,ensure_ascii=False, allow_nan=False),encoding="utf-8")
        (out/"request.json").write_text(json.dumps(config,indent=2,ensure_ascii=False, allow_nan=False),encoding="utf-8")
        np.savez_compressed(out/"masks.npz", brain=s["brain"], **{f"region_{i}":m for i,m in enumerate(s["masks"])})
        # Independent raster QA: nearest-neighbor annotation masks, not a render of the SVG.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import ListedColormap
        fig, ax = plt.subplots(figsize=(12,7))
        ax.imshow(np.where(s["brain"],1,np.nan),cmap=ListedColormap(["#edf0f3"]),interpolation="nearest")
        for reg,mask,a in zip(regions,s["masks"],audits):
            ax.imshow(np.where(mask,1,np.nan),cmap=ListedColormap([reg["color"]]),interpolation="nearest",alpha=.7)
            if a["status"]=="visible":
                x,y=a["anchor_pixel_xy"];ax.plot(x,y,"k+",ms=7);ax.annotate(reg["label"],(x,y),xytext=(8,-10),textcoords="offset points",fontsize=10)
        ax.set_title(label_mode+" | "+s["plane"]+" | raw mask / anchor QA")
        fig.savefig(out/"atlas-mask-qa.png",dpi=150,bbox_inches="tight");plt.close(fig)
    out=destination
    print(json.dumps({"output":str(out),"visible":[a["label"] for a in audits if a["status"]=="visible"],"absent":missing,"anchor_membership":"all passed"},ensure_ascii=False, allow_nan=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",type=Path,default=cache_default())
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("fetch")
    p=sub.add_parser("resolve");p.add_argument("queries",nargs="+")
    p=sub.add_parser("render");p.add_argument("request",type=Path);p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("validate");p.add_argument("request",type=Path)
    sub.add_parser("schema")
    args=parser.parse_args()
    if args.command=="schema":print(json.dumps(request_schema(),indent=2, allow_nan=False))
    elif args.command=="validate":
        validate_request(json.loads(args.request.read_text(encoding="utf-8")))
        print(json.dumps({"valid":True,"scope":"request schema and geometry parameters; no atlas membership check"}, allow_nan=False))
    elif args.command=="fetch":fetch(args.cache)
    elif args.command=="resolve":
        nodes=tree(args.cache)
        for q in args.queries:
            n,alias=resolve(int(q) if q.isdigit() else q,nodes)
            print(json.dumps({**{k:n[k] for k in ("id","acronym","name")},"alias":alias},ensure_ascii=False, allow_nan=False))
    else:
        config=json.loads(args.request.read_text(encoding="utf-8"))
        render_request(config,args.out,args.cache)


def cli():
    try:main()
    except (ValueError,KeyError,OSError,subprocess.CalledProcessError) as e:
        print(f"ERROR: {e}",file=sys.stderr);return 2
    return 0


if __name__=="__main__":
    raise SystemExit(cli())
