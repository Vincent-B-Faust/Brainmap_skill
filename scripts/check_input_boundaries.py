"""Offline regressions for numeric input, passive SVG, registration and bundles."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np

import atlas_schematic as atlas
import illustration as art
import template_library as lib
import output_bundle
from diagram_export import diagram_only
from validation import parse_svg


class BoundaryChecks(unittest.TestCase):
    def nodes(self):
        return {'A':{'center':[100,220],'radius':[42,26]},
                'B':{'center':[600,220],'radius':[42,26]}}

    def profile(self):
        point=lambda xy:{'atlas_pixel_xy':xy,'art_xy':[2*xy[0]+3,3*xy[1]+4]}
        return {'landmarks':[point(p) for p in [[0,0],[20,0],[0,20],[20,20]]],
                'holdout_landmarks':[point(p) for p in [[5,5],[15,10]]],
                'max_holdout_error_art_units':1}

    def test_nonfinite_rejected_at_both_request_entries(self):
        for value in (float('nan'),float('inf'),-float('inf')):
            with self.subTest(value=value):
                req={'template_id':'allen-2-1','regions':[{'structure':'VTA'}],
                     'connections':[{'from':'A','to':'B','bend_px':value}]}
                # Invalid numbers fail before reading any assets or creating output.
                with patch.object(lib,'read_json',side_effect=AssertionError('asset access')):
                    with self.assertRaises(ValueError):lib.illustrate(Path('missing'),req,Path('unused'),Path('missing'))
                with self.assertRaises(ValueError):
                    atlas.validate_request({'view':{'plane':'coronal','position_um':value},'regions':[{'structure':'VTA'}]})
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'request.json';p.write_text('{"bend_px": NaN}')
            with self.assertRaises(ValueError):lib.illustrate(Path(td),lib.read_json(p),Path(td)/'out',Path(td))

    def test_route_rejects_nonfinite_geometry_and_degeneracy(self):
        for value in (float('nan'),float('inf'),-float('inf')):
            for field in ('center','radius','bend','canvas','previous'):
                nodes=self.nodes();edge={'from':'A','to':'B'};canvas=[800,500];previous=[]
                if field in ('center','radius'):nodes['A'][field][0]=value
                elif field=='bend':edge['bend_px']=value
                elif field=='canvas':canvas[0]=value
                else:previous=[np.full((101,2),value)]
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                    art.route_edge(edge,nodes,previous,canvas)
        for radius in ([0,20],[-1,20]):
            nodes=self.nodes();nodes['A']['radius']=radius
            with self.assertRaises(ValueError):art.route_edge({'from':'A','to':'B'},nodes,[],[800,500])
        nodes=self.nodes();nodes['B']['center']=nodes['A']['center']
        with self.assertRaises(ValueError):art.route_edge({'from':'A','to':'B'},nodes,[],[800,500])
        with patch.object(art,'bezier_points',return_value=np.full((101,2),np.nan)):
            with self.assertRaises(ValueError):art.route_edge({'from':'A','to':'B'},self.nodes(),[],[800,500])
        # Finite coordinates whose norm overflows must also fail.
        nodes=self.nodes();nodes['B']['center']=[1e308,1e308]
        with np.errstate(over='ignore'),self.assertRaises(ValueError):
            art.route_edge({'from':'A','to':'B'},nodes,[],[800,500])

    def test_registration_rejects_reuse_and_invalid_threshold(self):
        for group in ('landmarks','holdout_landmarks'):
            p=self.profile();p[group][1]=copy.deepcopy(p[group][0])
            with self.assertRaises(ValueError):art.fit_registration(p)
        for space in ('atlas_pixel_xy','art_xy'):
            p=self.profile();p['holdout_landmarks'][0][space]=p['landmarks'][0][space][:]
            with self.assertRaises(ValueError):art.fit_registration(p)
            p=self.profile();p['holdout_landmarks'][0][space]=[v+1e-8 for v in p['landmarks'][0][space]]
            with self.assertRaises(ValueError):art.fit_registration(p)
        for value in (float('nan'),float('inf'),-float('inf'),-1):
            p=self.profile();p['max_holdout_error_art_units']=value
            with self.assertRaises(ValueError):art.fit_registration(p)
        for group in ('landmarks','holdout_landmarks'):
            for space in ('atlas_pixel_xy','art_xy'):
                p=self.profile();p[group][0][space][0]=float('nan')
                with self.assertRaises(ValueError):art.fit_registration(p)
        p=self.profile();matrix,errors=art.fit_registration(p)
        self.assertTrue(np.isfinite(matrix).all());self.assertLess(max(errors),1e-8)

    def test_bioart_entry_uses_passive_validation_and_viewbox_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);asset=root/'asset.svg';(root/'structure_graph.json').write_text('{}')
            point=lambda xy:{'atlas_pixel_xy':xy,'art_xy':[100+10*xy[0],200+10*xy[1]]}
            profile={'species':'Mus musculus','plane':'coronal','atlas':'ccf_2017','position_um':0,
                     'asset_file':str(asset),'landmarks':[point(p) for p in [[0,0],[4,0],[0,4]]],
                     'holdout_landmarks':[point(p) for p in [[1,1],[3,3]]]}
            request={'view':{'plane':'coronal','position_um':0},'regions':[{'structure':1,'label':'A'}],
                     'illustration':{'background':'bioart','atlas':'ccf_2017'}}
            mask=np.ones((5,5),dtype=bool)
            section={'brain':mask,'masks':[mask],'plane':'coronal','mode':'slice','oblique':False,
                     'points':np.zeros((3,5,5))}
            region={'ids':[1],'label':'A','components':[],'custom_union':False}
            with patch.object(art,'load_atlas',return_value=(np.ones((1,1,1),dtype=int),{}, {'name':'synthetic'})),patch.object(art.atlas,'prepare_regions',return_value=[region]),patch.object(art.atlas,'section',return_value=section),contextlib.redirect_stdout(io.StringIO()):
                asset.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="100 200 100 100"><rect x="100" y="200" width="100" height="100"/></svg>')
                profile['sha256']=atlas.digest(asset)
                audit=art.draw(request,root/'out',root,profile)
                x,y=audit['regions'][0]['atlas_anchor_pixel_xy']
                np.testing.assert_allclose(audit['regions'][0]['drawing_center_xy'],[60+x*148,15+y*148])
                self.assertTrue((root/'out'/'masks.npz').exists())
                # Even an exactly matching source hash must not authorize events.
                asset.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="100 200 100 100" onload="void(0)"/>')
                profile['sha256']=atlas.digest(asset)
                with self.assertRaises(ValueError):art.draw(request,root/'unsafe',root,profile)
                self.assertFalse((root/'unsafe').exists())

    def test_nonzero_viewbox_origin(self):
        root=parse_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="100 200 100 100"/>')
        mapping,height=art.bioart_viewport(root,np.array([[1,0],[0,1],[0,0]]))
        np.testing.assert_allclose(mapping([120,220]),[356,311])
        self.assertEqual(height,1630)
        for box in ('0 0 0 10','0 0 -1 10','0 0 10 nan','0 0 inf 10','1 2 3'):
            root.set('viewBox',box)
            with self.assertRaises(ValueError):art.bioart_viewport(root,np.array([[1,0],[0,1],[0,0]]))

    def test_nonzero_viewbox_raster_alignment(self):
        try:
            import cairosvg
            from PIL import Image
        except (ImportError,OSError):self.skipTest('Optional Cairo/Pillow runtime unavailable')
        root=parse_svg('<svg xmlns="http://www.w3.org/2000/svg" viewBox="100 200 100 100"><circle cx="120" cy="220" r="1" fill="#000"/></svg>')
        mapping,height=art.bioart_viewport(root,np.array([[1,0],[0,1],[0,0]]))
        svg='<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1630">'+ET.tostring(root,encoding='unicode')+'</svg>'
        png=cairosvg.svg2png(bytestring=svg.encode())
        mask=np.asarray(Image.open(io.BytesIO(png)).convert('RGBA'))[:,:,3]>128
        y,x=np.where(mask)
        np.testing.assert_allclose([x.mean()+.5,y.mean()+.5],mapping([120,220]),atol=1)

    def test_svg_rejects_active_and_external_content(self):
        cases=[
            '<g onload="void(0)"/>','<g ONCLICK="void(0)"/>',
            '<script/>','<foreignObject/>','<image href="https://example.invalid/x"/>',
            '<g xmlns="https://example.invalid/ns"/>',
            '<path xmlns:a="https://example.invalid/ns" a:onload="void(0)"/>',
            '<linearGradient href="https://example.invalid/g"/>',
            '<linearGradient xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="data:x"/>',
            '<g xml:base="https://example.invalid/"/>',
            '<path fill="url(https://example.invalid/x)"/>',
            '<path style="fill:url(https://example.invalid/x)"/>',
            '<style>@import "https://example.invalid/x";</style>',
            '<style>path{fill:u\\72l(https://example.invalid/x)}</style>',
            '<style>path{fill:url/**/(https://example.invalid/x)}</style>',
            '<path style="behavior: url(#local)"/>',
        ]
        for content in cases:
            svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'+content+'</svg>'
            with self.subTest(content=content):
                with self.assertRaises(ValueError):parse_svg(svg)
                with self.assertRaises(ValueError):diagram_only(svg,[])
        for prefix in ('<!DOCTYPE svg [<!ENTITY x "x">]>','<?xml-stylesheet href="https://example.invalid/x"?>'):
            with self.assertRaises(ValueError):parse_svg(prefix+'<svg/>')

    def test_static_bioart_and_local_css_survive(self):
        for asset in (Path(__file__).parent/'assets').glob('bioart*.svg'):
            parse_svg(asset.read_text())
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><defs><clipPath id="clip"><path d="M0,0H10V10Z"/></clipPath></defs><style>.a {clip-path: url(#clip); fill: #abc;}</style><g class="a"><path d="M0,0H10V10Z"/></g></svg>'
        self.assertIn('url(#clip)',ET.tostring(parse_svg(svg),encoding='unicode'))

    def fixture(self,root):
        folder=root/'allen-2-1';folder.mkdir()
        source='<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path structure_id="1" d="M0,0H100V100H0Z"/></svg>'
        (folder/'source.svg').write_text(source);(folder/'base.svg').write_text(source)
        entry={'id':'allen-2-1','source_sha256':lib.digest(folder/'source.svg'),
               'base_sha256':lib.digest(folder/'base.svg'),'source_structure_ids':[1],
               'source_size':[100,100],'mask_to_canvas_scale':1,
               'mask_to_canvas_offset':[100,100],'citation':'Synthetic fixture',
               'source_url':'https://example.invalid','coordinate_system':'synthetic pixels',
               'terms_url':'https://example.invalid'}
        lib.write_json(root/'catalog.json',{'templates':[entry]})
        return {'template_id':'allen-2-1','regions':[{'structure':1,'label':'file'}]}

    def render_fixture(self,root,request,out):
        region={'ids':[1],'label':request['regions'][0]['label']}
        with patch.object(lib.atlas,'tree',return_value={}),patch.object(lib.atlas,'prepare_regions',return_value=[region]),patch.object(lib,'source_mask',return_value=np.ones((100,100),dtype=bool)),contextlib.redirect_stdout(io.StringIO()):
            return lib.illustrate(root,request,out,root)

    def test_reserved_labels_have_internal_mask_keys(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);request=self.fixture(root)
            for label in ('file','allow_pickle','brain','region_0'):
                request['regions'][0]['label']=label
                audit=self.render_fixture(root,request,root/'out')
                self.assertEqual(audit['regions'][0]['mask_key'],'region_0')
                self.assertEqual(audit['regions'][0]['label'],label)
                with np.load(root/'out'/'masks.npz') as data:
                    self.assertEqual(data.files,['region_0']);self.assertTrue(data['region_0'].all())

    def test_failed_write_preserves_previous_bundle_or_absence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);request=self.fixture(root);out=root/'out'
            for existing in (False,True):
                if existing:out.mkdir();(out/'figure.svg').write_text('previous result')
                with patch.object(lib.np,'savez_compressed',side_effect=OSError('simulated disk write failure')):
                    with self.assertRaises(OSError):self.render_fixture(root,request,out)
                if existing:self.assertEqual([p.name for p in out.iterdir()],['figure.svg'])
                else:self.assertFalse(out.exists())
                self.assertEqual(list(root.glob('.brainmap-*')),[])

    def test_failed_publish_restores_previous_directory(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';out.mkdir();(out/'figure.svg').write_text('old')
            replace=output_bundle.os.replace
            def fail_stage(source,target):
                if Path(source).name=='bundle':raise OSError('simulated rename failure')
                return replace(source,target)
            with patch.object(output_bundle.os,'replace',side_effect=fail_stage):
                with self.assertRaises(OSError):
                    with output_bundle.staged_output(out) as stage:(stage/'new').write_text('new')
            self.assertEqual((out/'figure.svg').read_text(),'old')
            self.assertFalse((out/'new').exists())

    def test_unrelated_output_files_are_never_removed(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';out.mkdir();(out/'document.txt').write_text('keep')
            with self.assertRaises(ValueError):
                with output_bundle.staged_output(out):pass
            self.assertEqual((out/'document.txt').read_text(),'keep')

    def test_failed_rollback_retains_recoverable_previous_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'out';out.mkdir();(out/'figure.svg').write_text('old')
            replace=output_bundle.os.replace
            def fail_after_backup(source,target):
                if Path(source).name in ('bundle','previous'):raise OSError('simulated failure')
                return replace(source,target)
            with patch.object(output_bundle.os,'replace',side_effect=fail_after_backup):
                with self.assertRaisesRegex(OSError,'previous bundle retained'):
                    with output_bundle.staged_output(out) as stage:(stage/'figure.svg').write_text('new')
            backups=list(Path(td).glob('.brainmap-backup-*/previous/figure.svg'))
            self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(),'old')

    def test_json_writer_never_emits_nan(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'audit.json'
            with self.assertRaises(ValueError):lib.write_json(path,{'score':float('nan')})
            self.assertFalse(path.exists())


if __name__=='__main__':unittest.main(verbosity=2)
