"""Source-backed mouse section library, shared styling and plate-native circuits.

Official plate pixels are deliberately kept separate from volumetric CCF space.
"""
import argparse
import copy
import hashlib
import html
import io
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import jsonschema
import numpy as np
from scipy import ndimage

if __package__:
    from . import atlas_schematic as atlas, atlas_drawings as drawings, illustration as art
    from .diagram_export import diagram_only, uniform_background_outline
    from .validation import finite_json, parse_svg, validate_svg
    from .output_bundle import staged_output
else:
    import atlas_schematic as atlas
    import atlas_drawings as drawings
    import illustration as art
    from diagram_export import diagram_only, uniform_background_outline
    from validation import finite_json, parse_svg, validate_svg
    from output_bundle import staged_output

NS='http://www.w3.org/2000/svg'
DEFAULT=Path(__file__).parent/'assets'/'section-library'
ATLASES=[(1,'coronal','Mouse P56 Coronal'),(2,'sagittal','Mouse P56 Sagittal'),(602630314,'coronal','Adult Mouse 3D Coronal')]
TERMS='https://alleninstitute.org/legal/terms-of-use'
CITATION='Allen Institute for Brain Science. Allen Mouse Brain Reference Atlas. https://atlas.brain-map.org/'


def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write_json(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2, allow_nan=False)+'\n',encoding='utf-8')
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_svg(path):
    return parse_svg(Path(path).read_text(encoding='utf-8'),native=True)


def source_mask(root,ids=None,width=1000):
    """Render passive original paths to a mask, preserving source transforms."""
    try:
        import cairosvg
        from PIL import Image
    except (ImportError,OSError) as error:
        raise ValueError('Library building and plate-native placement require CairoSVG, Cairo and Pillow') from error
    validate_svg(root,native=True)
    root=copy.deepcopy(root)
    w,h=float(root.get('width')),float(root.get('height'))
    height=int(np.ceil(width*h/w))
    root.set('viewBox',f'0 0 {w} {height*w/width}')
    root.set('width',str(width));root.set('height',str(height))
    for e in root.iter():
        if e.tag.split('}')[-1]=='path':
            visible=ids is None or int(e.get('structure_id','-1')) in ids
            source_style=dict(item.split(':',1) for item in e.get('style','').split(';') if ':' in item)
            fill_rule=source_style.get('fill-rule',e.get('fill-rule','nonzero')).strip()
            e.set('style',('fill:#000000;stroke:none' if visible else 'fill:none;stroke:none')+';fill-rule:'+fill_rule)
    png=cairosvg.svg2png(bytestring=ET.tostring(root),output_width=width,output_height=height)
    return np.asarray(Image.open(io.BytesIO(png)).convert('RGBA'))[:,:,3]>=128


def outline(mask,sigma=1.1,knots=100):
    # Remove tiny disconnected annotation fragments; preserve original mask for QA.
    labels,n=ndimage.label(mask)
    sizes=np.bincount(labels.ravel());sizes[0]=0
    return art.smooth_path(sizes[labels]>=12,sigma,knots)


def build_one(row,plane,atlas_id,name,out,ontology):
    image_id=row['id'];key=f'allen-{atlas_id}-{image_id}'
    dest=out/key;dest.mkdir(parents=True,exist_ok=True)
    raw=dest/'source.svg';url=f'https://api.brain-map.org/api/v2/svg_download/{image_id}?groups=28'
    if not raw.exists():
        temporary=raw.with_suffix('.part')
        subprocess.run(['curl','-fsSL','--compressed','--retry','1','--max-time','180',url,'-o',str(temporary)],check=True)
        check_svg(temporary)
        temporary.replace(raw)
    root=check_svg(raw)
    inventory=sorted({int(e.get('structure_id')) for e in root.iter() if e.tag.split('}')[-1]=='path' and e.get('structure_id')})
    tissue=source_mask(root)
    if not tissue.any():raise ValueError(f'Empty source {image_id}')
    yy,xx=np.where(tissue);xmin,xmax,ymin,ymax=int(xx.min()),int(xx.max()),int(yy.min()),int(yy.max())
    scale=min(924/max(1,xmax-xmin),600/max(1,ymax-ymin));offset=np.array([512-(xmin+xmax)*scale/2,340-(ymin+ymax)*scale/2])
    transform=f'translate({offset[0]},{offset[1]}) scale({scale})'
    path=outline(ndimage.binary_fill_holes(tissue),1.0,140)
    pieces=[f'<svg xmlns="{NS}" width="1024" height="768" viewBox="0 0 1024 768">',
      '<rect width="1024" height="768" fill="white"/>',
      f'<g id="source-derived-background" transform="{transform}">',
      f'<defs><clipPath id="tissue"><path d="{path}"/></clipPath></defs>',
      f'<path d="{path}" fill="#F2F2F2" stroke="#606162" stroke-width="{3.2/scale}" stroke-linejoin="round"/>',
      '<g clip-path="url(#tissue)">']
    contexts=[('CTX','#F7F7F7'),('HPF','#E7E7E7'),('CB','#EEF0EE')]
    if plane=='sagittal':
        contexts += [(q,'#E1E6E2' if i%2==0 else '#E8ECE9') for i,q in enumerate(['LING','CENT2','CENT3','CUL','DEC','FOTU','PYR','UVU','NOD'])]
    contexts += [('fiber tracts','#FFFFFF'),('arb','#FFFFFF'),('VS','#FFFFFF')]
    context_record=[]
    for q,color in contexts:
        node,_=atlas.resolve(q,ontology);ids=set(atlas.descendants(node))&set(inventory)
        if not ids:continue
        mask=source_mask(root,ids)
        if not mask.any():continue
        pieces.append(f'<path d="{outline(mask,.8,90)}" fill="{color}" stroke="none"/>')
        context_record.append({'query':q,'source_structure_ids':sorted(ids)})
    pieces+=['</g></g>']
    display=f'{plane.capitalize()} · atlas {atlas_id} · section {row["section_number"]}'
    pieces.append(f'<text x="50" y="704" font-family="Arial,Helvetica,sans-serif" font-size="20" fill="#343B3F">{html.escape(display)}</text>')
    pieces.append('<text x="50" y="731" font-family="Arial,Helvetica,sans-serif" font-size="13" fill="#697477">Allen-derived schematic · source plate pixels; no inferred CCF or Bregma coordinate</text>')
    record={'id':key,'species':'Mus musculus','age':('adult' if atlas_id==602630314 else 'P56'),'plane':plane,'atlas_id':atlas_id,'atlas_name':name,
      'image_id':image_id,'section_number':row['section_number'],'source_url':url,'source_sha256':digest(raw),
      'source_file':'source.svg','base_file':'base.svg','license':'Allen Institute Terms of Use; research/noncommercial use; source rights retained',
      'terms_url':TERMS,'citation':CITATION,'coordinate_system':'original plate SVG pixels; not volumetric CCF or Bregma','hemisphere_note':'As published; unilateral plates are not mirrored to invent a full section',
      'source_size':[float(root.get('width')),float(root.get('height'))],'mask_width':1000,
      'mask_to_canvas_scale':scale,'mask_to_canvas_offset':offset.tolist(),'source_structure_ids':inventory,
      'context_layers':context_record,'style':'gray-white-reference-v1','modifications':'Source paths rasterized only for masks, simplified to closed cubic vector background; small islands omitted. Original source.svg unchanged. Placement QA uses unsmoothed source-path masks.'}
    pieces+=['<metadata>'+html.escape(json.dumps(record, allow_nan=False))+'</metadata></svg>']
    (dest/'base.svg').write_text(ET.tostring(uniform_background_outline(ET.fromstring('\n'.join(pieces))),encoding='unicode'),encoding='utf-8')
    record['base_sha256']=digest(dest/'base.svg');write_json(dest/'template.json',record)
    return record


def build_reconstructions(out,cache,ontology):
    """Additional planes are resampled from real 3D labels, not rotated drawings."""
    volume=atlas.load_volume(cache)
    views=[('ccf-horizontal-dorsal',{'plane':'horizontal','position_um':2500}),
           ('ccf-horizontal-ventral',{'plane':'horizontal','position_um':4500}),
           ('ccf-oblique-coronal',{'plane':'coronal','position_um':6500,'rotation_deg_ap_dv_ml':[0,15,0]}),
           ('ccf-oblique-sagittal',{'plane':'sagittal','position_um':6500,'rotation_deg_ap_dv_ml':[10,0,0]})]
    context=atlas.prepare_regions({'regions':[{'structure':q} for q in ['CTX','HPF','CB','fiber tracts','VS']]},ontology)
    entries=[]
    for key,view in views:
        sec=atlas.section(volume,view,context);mask=sec['brain'];yy,xx=np.where(mask)
        scale=min(924/max(1,np.ptp(xx)),600/max(1,np.ptp(yy)))
        offset=np.array([512-(xx.min()+xx.max())*scale/2,340-(yy.min()+yy.max())*scale/2])
        path=outline(ndimage.binary_fill_holes(mask),1.1,120)
        pieces=[f'<svg xmlns="{NS}" width="1024" height="768" viewBox="0 0 1024 768"><rect width="1024" height="768" fill="white"/>',
          f'<g transform="translate({offset[0]},{offset[1]}) scale({scale})"><path d="{path}" fill="#F2F2F2" stroke="#606162" stroke-width="{3.2/scale}" stroke-linejoin="round"/>']
        for m,color in zip(sec['masks'],['#F7F7F7','#E7E7E7','#EEEEEE','#FFFFFF','#FFFFFF']):
            if m.any():pieces.append(f'<path d="{outline(m,.8,90)}" fill="{color}" stroke="none"/>')
        pieces.append('</g>')
        title=f"{view['plane'].capitalize()} · CCF {view['position_um']} µm"
        if sec['oblique']:title+=' · oblique'
        pieces.append(f'<text x="50" y="704" font-family="Arial" font-size="20" fill="#343B3F">{html.escape(title)}</text>')
        pieces.append('<text x="50" y="731" font-family="Arial" font-size="13" fill="#697477">Allen CCF2017 reconstruction · 25 µm · nearest-neighbor 3D resampling</text>')
        record={'id':key,'plane':view['plane'],'kind':'volume-reconstruction','view':view,'atlas':'CCF2017','source_url':atlas.URLS['annotation_25.nrrd'],
          'source_sha256':atlas.ANNOTATION_HASH,'base_file':'base.svg','style':'gray-white-reference-v1','terms_url':TERMS,'citation':CITATION,
          'modifications':'Nearest-neighbor 3D section, smoothed schematic background. These are new reconstructions, not downloaded 2D artwork.',
          'coordinate_system':'CCF AP/DV/ML µm; rotation about section center, see atlas coordinate documentation',
          'mask_to_canvas_scale':scale,'mask_to_canvas_offset':offset.tolist(),'oblique':sec['oblique'],
          'reuse':'Use brainmap-illustrate with the exact recorded view and CCF2017 atlas to place verified regions; do not transfer source-plate pixel coordinates.'}
        pieces.append('<metadata>'+html.escape(json.dumps(record, allow_nan=False))+'</metadata></svg>')
        dest=out/key;dest.mkdir(parents=True,exist_ok=True);(dest/'base.svg').write_text(ET.tostring(uniform_background_outline(ET.fromstring('\n'.join(pieces))),encoding='unicode'),encoding='utf-8')
        record['base_sha256']=digest(dest/'base.svg');write_json(dest/'template.json',record);entries.append(record)
    return entries


def build(out,cache,index_root=None):
    out.mkdir(parents=True,exist_ok=True);ontology=atlas.tree(cache)
    indexes=[];jobs=[]
    for atlas_id,plane,name in ATLASES:
        if index_root:
            folder={1:'coronal',2:'sagittal',602630314:'coronal-3d'}[atlas_id]
            data=read_json(index_root/folder/'plates.json')
        else:
            criteria=f"model::AtlasImage,rma::criteria,[annotated$eqtrue],atlas_data_set(atlases[id$eq{atlas_id}]),rma::options[order$eq'sub_images.section_number'][num_rows$eqall]"
            rows,url=drawings.query(criteria)
            data={'atlas_id':atlas_id,'url':url,'plates':[{k:r.get(k) for k in ('id','section_number','resolution','width','height')} for r in rows]}
        data.update(plane=plane,atlas_name=name);indexes.append(data)
        # Sample the middle span rather than near-empty extreme tips. Every plate
        # remains discoverable in indexes.json and can be fetched on demand.
        fractions=[.12,.30,.47,.63,.80] if atlas_id==1 else ([.02,.25,.50,.75,.95] if atlas_id==2 else [.30,.60])
        for f in fractions:jobs.append((data['plates'][round((len(data['plates'])-1)*f)],plane,atlas_id,name))
        if atlas_id==2:
            showcase=next((r for r in data['plates'] if r['id']==100883900),None)
            if showcase is not None and not any(job[0]['id']==showcase['id'] for job in jobs):
                jobs.append((showcase,plane,atlas_id,name))
    write_json(out/'indexes.json',{'atlases':indexes})
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(build_one,*job,out,ontology) for job in jobs]
        entries=[f.result() for f in futures]
    reconstructions=build_reconstructions(out,cache,ontology)
    write_json(out/'catalog.json',{'schema_version':1,'style':'gray-white-reference-v1','templates':entries,
      'source_index_count':sum(len(d['plates']) for d in indexes),'downloaded_template_count':len(entries),'reconstructions':reconstructions,
      'coverage_note':'Indexes are discovery metadata, not downloaded templates or guaranteed target coverage. Match actual source_structure_ids before overlay. Arbitrary oblique angles use volumetric resampling, not rotated plate art.'})
    gallery(out,entries+reconstructions)
    print(json.dumps({'templates':len(entries),'reconstructions':len(reconstructions),'indexed_plates':sum(len(d['plates']) for d in indexes),'out':str(out)}, allow_nan=False))


def gallery(out,entries):
    cols=4;rows=(len(entries)+cols-1)//cols
    recon_count=sum(e.get('kind')=='volume-reconstruction' for e in entries)
    source_count=len(entries)-recon_count
    pieces=[f'<svg xmlns="{NS}" width="2048" height="{rows*400+95}" viewBox="0 0 2048 {rows*400+95}"><rect width="100%" height="100%" fill="white"/>',
      '<text x="28" y="38" font-size="27" font-family="Arial" fill="#303A40">Mouse brain section library · unified source-derived style</text>',
      f'<text x="28" y="67" font-size="16" font-family="Arial" fill="#687577">{source_count} source plates + {recon_count} CCF reconstructions · shared style · source plate and CCF coordinates kept separate</text>']
    for i,e in enumerate(entries):
        root=uniform_background_outline(ET.parse(out/e['id']/'base.svg').getroot())
        root.set('x',str((i%cols)*512));root.set('y',str(95+(i//cols)*400));root.set('width','512');root.set('height','384')
        # Avoid duplicate clip IDs across nested SVGs in a single document.
        prefix=e['id']+'-'
        for el in root.iter():
            if el.get('id'):el.set('id',prefix+el.get('id'))
            if el.get('clip-path'):el.set('clip-path',el.get('clip-path').replace('#tissue','#'+prefix+'tissue'))
        pieces.append(ET.tostring(root,encoding='unicode'))
    pieces.append('</svg>');(out/'gallery.svg').write_text('\n'.join(pieces),encoding='utf-8')


def choose(library,plane,queries,cache):
    ontology=atlas.tree(cache);targets={}
    for q in queries:
        node,_=atlas.resolve(int(q) if q.isdigit() else q,ontology);targets[q]=set(atlas.descendants(node))
    matches=[]
    for e in read_json(library/'catalog.json')['templates']:
        if plane and e['plane']!=plane:continue
        visible={q:bool(ids&set(e['source_structure_ids'])) for q,ids in targets.items()}
        matches.append({'id':e['id'],'plane':e['plane'],'section_number':e['section_number'],'visible_targets':visible,'matched_count':sum(visible.values()),'all_targets_delineated':all(visible.values()),'coordinate_system':e['coordinate_system']})
    return sorted(matches,key=lambda x:(-x['matched_count'],x['id']))


def plate_schema():
    base=read_json(Path(__file__).parent/'request.schema.json')
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object',
      'required':['template_id','regions'],'additionalProperties':False,'$defs':base['$defs'],
      'properties':{'template_id':{'type':'string','pattern':'^allen-[0-9]+-[0-9]+$'},'title':{'type':'string'},
                    'regions':base['properties']['regions'],'connections':base['properties']['connections']}}


def illustrate(library,request,out,cache):
    finite_json(request)
    library=Path(library)
    try:jsonschema.Draft202012Validator(plate_schema()).validate(request)
    except jsonschema.ValidationError as error:raise ValueError('Invalid plate request: '+error.message) from error
    entry_id=request['template_id']
    entries={e['id']:e for e in read_json(library/'catalog.json')['templates']}
    if entry_id not in entries:raise ValueError('Unknown template ID')
    e=entries[entry_id];folder=library/entry_id
    if digest(folder/'source.svg')!=e['source_sha256'] or digest(folder/'base.svg')!=e['base_sha256']:
        raise ValueError('Template/source hash mismatch')
    root=check_svg(folder/'source.svg');ontology=atlas.tree(cache)
    regions=atlas.prepare_regions(request,ontology)
    if not regions:raise ValueError('At least one region is required')
    nodes={};records=[];masks={};scale=e['mask_to_canvas_scale'];offset=np.asarray(e['mask_to_canvas_offset'])
    for i,reg in enumerate(regions):
        ids=set(reg['ids'])&set(e['source_structure_ids'])
        if not ids:raise ValueError(f"{reg['label']} is not delineated on this plate; choose another plate or atlas reconstruction")
        mask=source_mask(root,ids)
        if not mask.any():raise ValueError(f"{reg['label']} source paths have no visible mask")
        y,x=map(int,atlas.anchor(mask));center=np.array([x,y])*scale+offset
        if not mask[y,x]:raise AssertionError('Source-path anchor membership failed')
        label=reg['label']
        if label in nodes:raise ValueError('Duplicate region label')
        color=request['regions'][i].get('color',art.PALETTE[i%len(art.PALETTE)])
        nodes[label]={'center':center.tolist(),'radius':[max(34,len(label)*5.7+12),21],'color':color,'fill_color':request['regions'][i].get('fill_color')}
        records.append({'label':label,'mask_key':f'region_{i}','source_structure_ids':sorted(ids),'source_mask_anchor_xy':[x,y],
          'source_svg_anchor_xy':[(x+.5)*e['source_size'][0]/1000,(y+.5)*e['source_size'][0]/1000],
          'drawing_center_xy':center.tolist(),'anchor_membership_pass':True,'ccf_coordinate':None})
        masks[f'region_{i}']=mask
    labels=list(nodes)
    for i,a in enumerate(labels):
        for b in labels[i+1:]:
            na,nb=nodes[a],nodes[b]
            if np.sum(((np.array(na['center'])-nb['center'])/(np.array(na['radius'])+nb['radius']+4))**2)<1:
                raise ValueError(f'{a}/{b} labels overlap; use a detail panel')
    base=parse_svg((folder/'base.svg').read_text(encoding='utf-8'))
    pieces=[f'<svg xmlns="{NS}" width="1024" height="768" viewBox="0 0 1024 768">',ET.tostring(base,encoding='unicode'),'<g id="circuit-connections">']
    previous=[];edges=[]
    for i,edge in enumerate(request.get('connections',[])):
        if edge['from'] not in nodes or edge['to'] not in nodes:raise ValueError('Unknown connection endpoint')
        kind=edge.get('kind')
        if kind not in ('projection','excitatory','inhibitory'):raise ValueError('Connection kind must be projection, excitatory or inhibitory')
        if not edge.get('evidence') or not edge.get('source'):raise ValueError('Connection evidence/source required')
        route=art.route_edge(edge,nodes,previous,[1024,670]);previous.append(route['points']);cp=route['control']
        end=cp[-1];direction=end-cp[-2];direction/=np.linalg.norm(direction);normal=np.array([-direction[1],direction[0]])
        color=edge.get('color',art.EXCITATORY if kind=='excitatory' else (art.INHIBITORY if kind=='inhibitory' else '#6C7E79'))
        d=f'M{cp[0,0]:.2f},{cp[0,1]:.2f} C{cp[1,0]:.2f},{cp[1,1]:.2f} {cp[2,0]:.2f},{cp[2,1]:.2f} {cp[3,0]:.2f},{cp[3,1]:.2f}'
        pieces.append(f'<g data-kind="{kind}"><path d="{d}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
        if kind=='excitatory':
            tail=end-direction*15;pts=[end,tail+normal*7,tail-normal*7]
            pieces.append('<polygon points="'+' '.join(f'{x:.2f},{y:.2f}' for x,y in pts)+f'" fill="{color}"/>')
        elif kind=='inhibitory':
            a,b=end+normal*9,end-normal*9
            pieces.append(f'<path d="M{a[0]:.2f},{a[1]:.2f} L{b[0]:.2f},{b[1]:.2f}" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
        else:
            # Rounded boutons indicate an axonal projection, not its functional sign.
            stem=end-direction*13
            for spread in [-7,0,7]:
                target=end+normal*spread
                pieces.append(f'<path d="M{stem[0]:.2f},{stem[1]:.2f} Q{end[0]:.2f},{end[1]:.2f} {target[0]:.2f},{target[1]:.2f}" fill="none" stroke="{color}" stroke-width="2.2"/>')
                pieces.append(f'<circle cx="{target[0]:.2f}" cy="{target[1]:.2f}" r="3.2" fill="{color}"/>')
        terminal={'excitatory':'triangle','inhibitory':'perpendicular_bar','projection':'axon_boutons'}[kind]
        pieces.append('</g>');edges.append({**edge,'control_xy':cp.tolist(),'terminal':terminal,'node_intrusions':route['node_intrusions'],'crossings':route['crossings']})
    pieces.append('</g><g id="region-labels">')
    for label,node in nodes.items():
        x,y=node['center'];rx,ry=node['radius'];color=node['color']
        rgb=np.array([int(color[j:j+2],16) for j in (1,3,5)]);light=np.round(rgb*.3+255*.7).astype(int);fill=node.get('fill_color') or '#'+''.join(f'{c:02x}' for c in light)
        fill_rgb=np.array([int(fill[j:j+2],16) for j in (1,3,5)])
        text_color='#FFFFFF' if np.dot(fill_rgb,[.2126,.7152,.0722])<145 else '#26343D'
        pieces.append(f'<ellipse cx="{x:.2f}" cy="{y:.2f}" rx="{rx}" ry="{ry}" fill="{fill}" stroke="{color}" stroke-width="2.2"/><text x="{x:.2f}" y="{y+7.5:.2f}" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-size="23" fill="{text_color}">{html.escape(label)}</text>')
    audit={'renderer':'plate-library-v0.4.0','template':e,'regions':records,'connections':edges,
      'claims':{'source_path_anchor_membership':'verified in unsmoothed rendered source paths','ccf_registration':False,'glyph_is_region_boundary':False,'arrow_is_axon_trajectory':False,'crossings':sum(x['crossings'] for x in edges)}}
    pieces+=['</g><text x="50" y="754" font-family="Arial" font-size="10" fill="#697477">Schematic node sizes and curves; connection signs follow the supplied evidence recorded in the audit.</text><metadata>'+html.escape(json.dumps(audit, allow_nan=False))+'</metadata></svg>']
    destination=Path(out)
    with staged_output(destination) as out:
        (out/'figure.svg').write_text(diagram_only('\n'.join(pieces),nodes,680),encoding='utf-8')
        (out/'figure-notes.md').write_text(e['citation']+'\n'+e['source_url']+'\n\n'+e['coordinate_system']+'\nSchematic node sizes and curves. Connection evidence is recorded in audit.json.\nSource terms: '+e['terms_url']+'\n',encoding='utf-8')
        write_json(out/'audit.json',audit);write_json(out/'request.json',request);np.savez_compressed(out/'masks.npz',**masks)
    out=destination
    print(json.dumps({'regions':len(records),'connections':len(edges),'template':entry_id,'out':str(out)}, allow_nan=False))
    return audit


def cli():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--library',type=Path,default=DEFAULT);parser.add_argument('--cache',type=Path,default=atlas.cache_default())
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('schema')
    p=sub.add_parser('build');p.add_argument('--out',type=Path,required=True);p.add_argument('--index-root',type=Path)
    p=sub.add_parser('choose');p.add_argument('--plane',choices=['sagittal','coronal']);p.add_argument('--regions',nargs='+',required=True)
    p=sub.add_parser('illustrate');p.add_argument('request',type=Path);p.add_argument('--out',type=Path,required=True)
    p=sub.add_parser('fetch');p.add_argument('--atlas-id',type=int,required=True);p.add_argument('--image-id',type=int,required=True)
    args=parser.parse_args()
    try:
        if args.command=='schema':print(json.dumps(plate_schema(),indent=2, allow_nan=False))
        elif args.command=='build':build(args.out,args.cache,args.index_root)
        elif args.command=='choose':print(json.dumps(choose(args.library,args.plane,args.regions,args.cache),ensure_ascii=False,indent=2, allow_nan=False))
        elif args.command=='illustrate':illustrate(args.library,read_json(args.request),args.out,args.cache)
        else:
            indexes=read_json(args.library/'indexes.json')['atlases'];index=next(d for d in indexes if d['atlas_id']==args.atlas_id)
            row=next(r for r in index['plates'] if r['id']==args.image_id)
            entry=build_one(row,index['plane'],args.atlas_id,index['atlas_name'],args.library,atlas.tree(args.cache))
            catalog=read_json(args.library/'catalog.json');catalog['templates']=[e for e in catalog['templates'] if e['id']!=entry['id']]+[entry]
            catalog['downloaded_template_count']=len(catalog['templates']);write_json(args.library/'catalog.json',catalog);gallery(args.library,catalog['templates']+catalog.get('reconstructions',[]))
    except (ValueError,KeyError,StopIteration,OSError,subprocess.CalledProcessError) as error:
        print(f'ERROR: {error}',file=sys.stderr);return 2
    return 0


if __name__=='__main__':raise SystemExit(cli())
