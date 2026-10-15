#!/usr/bin/env python3
"""Retrieve official 2D atlas plates; preserve geometry and inventory structure paths.

This does not register 2D plates to CCF or reconstruct absent 3D labels.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

if __package__:
    from .atlas_schematic import cache_default, tree, resolve, descendants
    from .validation import parse_svg
else:
    from atlas_schematic import cache_default, tree, resolve, descendants
    from validation import parse_svg


def download(url, path):
    subprocess.run(["curl", "-fL", "--retry", "2", "--max-time", "90", url, "-o", str(path)], check=True)


def query(criteria):
    url = "https://api.brain-map.org/api/v2/data/query.json?"+urlencode({"criteria":criteria})
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/"query.json";download(url,p);obj=json.loads(p.read_text(encoding="utf-8"))
    if not obj.get("success"):
        raise ValueError(obj.get("msg"))
    return obj["msg"], url


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("list");p.add_argument("--atlas-id",type=int,required=True);p.add_argument("--out",type=Path,required=True)
    p=sub.add_parser("plate");p.add_argument("--image-id",type=int,required=True);p.add_argument("--group-id",type=int,default=28);p.add_argument("--out",type=Path,required=True);p.add_argument("--highlight",nargs="*",default=[]);p.add_argument("--cache",type=Path,default=cache_default())
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    if args.command=="list":
        criteria=f"model::AtlasImage,rma::criteria,[annotated$eqtrue],atlas_data_set(atlases[id$eq{args.atlas_id}]),rma::options[order$eq'sub_images.section_number'][num_rows$eqall]"
        rows,url=query(criteria)
        # Retain only useful public metadata, not backend path fields.
        record={"url":url,"atlas_id":args.atlas_id,"plates":[{k:r.get(k) for k in ("id","section_number","resolution","width","height")} for r in rows]}
        (args.out/"plates.json").write_text(json.dumps(record,indent=2, allow_nan=False),encoding="utf-8")
        print(json.dumps({"atlas_id":args.atlas_id,"count":len(rows),"saved":str(args.out/"plates.json")}, allow_nan=False));return
    url=f"https://api.brain-map.org/api/v2/svg_download/{args.image_id}?groups={args.group_id}"
    raw=args.out/"official-original.svg";download(url,raw)
    root=parse_svg(raw.read_text(encoding="utf-8"),native=True)
    inventory={}
    for element in root.iter():
        sid=element.get("structure_id")
        if sid and element.tag.split("}")[-1]=="path":inventory.setdefault(int(sid),[]).append(element.get("id"))
    nodes=tree(args.cache)
    targets={}
    for q in args.highlight:
        node,_=resolve(int(q) if q.isdigit() else q,nodes)
        matching=set(descendants(node)).intersection(inventory)
        targets[q]={"id":node["id"],"acronym":node["acronym"],"matching_structure_ids":sorted(matching),"path_ids":[p for sid in matching for p in inventory[sid]],"status":"delineated" if matching else "not_delineated_on_this_plate"}
    record={"source":url,"image_id":args.image_id,"group_id":args.group_id,"original_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),
            "structures":{str(sid):{"path_ids":ids,"acronym":nodes.get(sid,{}).get("acronym")} for sid,ids in inventory.items()},"targets":targets,
            "coordinate_system":"Original official SVG coordinates and transforms; not CCF coordinates. No rotation, registration or Bregma conversion inferred."}
    (args.out/"drawing-audit.json").write_text(json.dumps(record,indent=2, allow_nan=False),encoding="utf-8")
    if any(x["status"]!="delineated" for x in targets.values()):
        raise ValueError("Requested structure is not delineated on this plate; original and audit saved. Inspect other plates/datasets; never replace it with its parent.")
    highlights={sid for target in targets.values() for sid in target["matching_structure_ids"]}
    for element in root.iter():
        if element.tag.split("}")[-1]=="path" and element.get("structure_id"):
            sid=int(element.get("structure_id"))
            element.set("style", "fill:#c36683;stroke:#722943;stroke-width:10" if sid in highlights else "fill:#f0f2f4;stroke:#bbc3cb;stroke-width:4")
    ET.register_namespace("","http://www.w3.org/2000/svg")
    ET.ElementTree(root).write(args.out/"highlighted-plate.svg",encoding="utf-8",xml_declaration=True)
    print(json.dumps({"image_id":args.image_id,"targets":targets,"geometry":"original path data and transforms preserved"}, allow_nan=False))


def cli():
    try:main()
    except (ValueError,subprocess.CalledProcessError) as e:
        print(f"ERROR: {e}",file=sys.stderr)
        return 2
    return 0


if __name__=="__main__":
    raise SystemExit(cli())
