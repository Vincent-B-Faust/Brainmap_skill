"""Source-derived template checks: provenance, coordinates, guards and installed data."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import numpy as np

import template_library as lib


class LibraryChecks(unittest.TestCase):
    def test_original_transforms_are_respected(self):
        root=ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"><g transform="translate(30,10)"><path structure_id="1" d="M0,0H20V30H0Z"/></g></svg>')
        mask=lib.source_mask(root,{1},100)
        self.assertTrue(mask[20,40])
        self.assertFalse(mask[20,10])
        self.assertEqual(mask.sum(),600)
        self.assertFalse(lib.source_mask(root,{2},100).any())

    def test_source_masks_are_not_artistic_background(self):
        root=ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="80"><path structure_id="1" d="M10,10H90V70H10Z M40,30V50H60V30Z" style="fill-rule:evenodd"/></svg>')
        before=ET.tostring(root)
        mask=lib.source_mask(root,{1},100)
        self.assertEqual(before,ET.tostring(root))
        self.assertFalse(mask[40,50])
        y,x=map(int,lib.atlas.anchor(mask));self.assertTrue(mask[y,x])

    def test_untrusted_svg_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'source.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>bad</script></svg>')
            with self.assertRaises(ValueError):lib.check_svg(path)

    def test_actual_library_hashes_and_geometry(self):
        catalog=lib.read_json(lib.DEFAULT/'catalog.json')
        self.assertEqual(catalog['downloaded_template_count'],13)
        self.assertEqual(catalog['source_index_count'],287)
        self.assertEqual(len(catalog['reconstructions']),4)
        for e in catalog['templates']:
            folder=lib.DEFAULT/e['id'];root=lib.check_svg(folder/'source.svg')
            ids={int(p.get('structure_id')) for p in root.iter() if p.get('structure_id')}
            self.assertEqual(ids,set(e['source_structure_ids']))
            self.assertEqual(lib.digest(folder/'source.svg'),e['source_sha256'])
            self.assertEqual(lib.digest(folder/'base.svg'),e['base_sha256'])
            self.assertGreater(e['mask_to_canvas_scale'],0)
        for e in catalog['reconstructions']:
            self.assertEqual(lib.digest(lib.DEFAULT/e['id']/'base.svg'),e['base_sha256'])
            self.assertEqual(e['source_sha256'],lib.atlas.ANNOTATION_HASH)
        self.assertEqual(sum(e['oblique'] for e in catalog['reconstructions']),2)

    def test_bundled_image_reference_is_midline_without_target_labels(self):
        assets=Path(__file__).parent/'assets'
        record=lib.read_json(assets/'midsagittal-reference.json')
        self.assertEqual(record['view'],{'plane':'sagittal','mode':'slice','position_um':5700,'hemisphere':'both'})
        self.assertEqual(record['atlas']['sha256'],lib.atlas.ANNOTATION_HASH)
        for kind in ('svg','png'):
            self.assertEqual(lib.digest(assets/f'midsagittal-reference.{kind}'),record[f'{kind}_sha256'])
        root=lib.parse_svg((assets/'midsagittal-reference.svg').read_text())
        self.assertFalse(any(e.tag.split('}')[-1] in ('text','image') for e in root.iter()))
        self.assertFalse(any(e.get('id') in ('region-labels','region-node-labels','circuit-connections') for e in root.iter()))

    def test_da_projection_has_boutons_without_functional_arrow(self):
        request=lib.read_json(Path(__file__).parent.parent/'references'/'example-vta-da.json')
        with tempfile.TemporaryDirectory() as td:
            audit=lib.illustrate(lib.DEFAULT,request,Path(td),lib.atlas.cache_default())
            self.assertTrue(all(e['terminal']=='axon_boutons' for e in audit['connections']))
            self.assertTrue(all(r['anchor_membership_pass'] for r in audit['regions']))
            self.assertEqual(audit['claims']['crossings'],0)
            root=ET.parse(Path(td)/'figure.svg').getroot()
            group=next(g for g in root if g.get('id')=='circuit-connections')
            self.assertFalse(any(e.tag.split('}')[-1]=='polygon' for e in group.iter()))
            self.assertEqual(sum(e.tag.split('}')[-1]=='circle' for e in group.iter()),6)

    def test_missing_target_is_not_invented(self):
        catalog=lib.read_json(lib.DEFAULT/'catalog.json');e=catalog['templates'][0]
        request={'template_id':e['id'],'regions':[{'structure':'RPA'}]}
        if 230 in e['source_structure_ids']:self.skipTest('Sample unexpectedly includes RPA')
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError,'not delineated'):
                lib.illustrate(lib.DEFAULT,request,Path(td),lib.atlas.cache_default())


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LibraryChecks))
    raise SystemExit(0 if result.wasSuccessful() else 1)
