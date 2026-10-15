#!/usr/bin/env python3
"""Behavioral checks for slicing, projection, axes, labels and anchors.

Run after installing requirements: python scripts/check_spatial_invariants.py
Real atlas check is enabled by --real-atlas and requires an existing validated cache.
"""
import sys
import unittest
from unittest.mock import patch
import numpy as np
import atlas_schematic as a


REAL = "--real-atlas" in sys.argv
if REAL:sys.argv.remove("--real-atlas")


class SpatialChecks(unittest.TestCase):
    def setUp(self):
        self.shape=(9,7,11)
        self.volume=np.ones(self.shape,dtype=np.uint32)
        self.volume[2,3,8]=42
        self.region=[{"ids":[42]}]
        self.patch=patch.object(a,"SHAPE",self.shape);self.patch.start()

    def tearDown(self):self.patch.stop()

    def view(self,plane,pos,**kwargs):
        return a.section(self.volume,{"plane":plane,"position_um":pos,**kwargs},self.region)

    def test_axes_and_voxel_placement(self):
        for plane,pos,expected in [("sagittal",200,(3,2)),("coronal",50,(3,8)),("horizontal",75,(2,8))]:
            s=self.view(plane,pos)
            self.assertEqual(int(s["masks"][0].sum()),1)
            self.assertTrue(s["masks"][0][expected])
            np.testing.assert_array_equal(s["points"][:,expected[0],expected[1]],[50,75,200])

    def test_projection_depth_and_hemisphere(self):
        s=self.view("sagittal",125,mode="projection",slab_um=[190,210])
        self.assertTrue(s["masks"][0][3,2])
        self.assertFalse(self.view("sagittal",125,mode="projection",slab_um=[0,175])["masks"][0].any())
        self.assertFalse(self.view("coronal",50,hemisphere="left")["masks"][0].any())
        self.assertTrue(self.view("coronal",50,hemisphere="right")["masks"][0].any())

    def test_projection_all_planes(self):
        for plane,shape,loc in [("sagittal",(7,9),(3,2)),("coronal",(7,11),(3,8)),("horizontal",(9,11),(2,8))]:
            s=self.view(plane,50,mode="projection")
            self.assertEqual(s["masks"][0].shape,shape)
            self.assertTrue(s["masks"][0][loc])

    def test_projection_across_memory_chunk_boundaries(self):
        shape=(35,7,11);volume=np.ones(shape,dtype=np.uint32)
        volume[2,3,8]=42;volume[30,4,7]=42
        with patch.object(a,"SHAPE",shape):
            s=a.section(volume,{"plane":"coronal","position_um":50,"mode":"projection"},self.region)
            self.assertTrue(s["masks"][0][3,8]);self.assertTrue(s["masks"][0][4,7])
            s=a.section(volume,{"plane":"sagittal","position_um":200,"mode":"projection"},self.region)
            self.assertTrue(s["masks"][0][3,2]);self.assertTrue(s["masks"][0][4,30])

    def test_oblique_sampling_is_categorical(self):
        self.volume[2:5,2:5,6:10]=42
        s=self.view("coronal",75,rotation_deg_ap_dv_ml=[0,17,0])
        for y,x in zip(*np.where(s["masks"][0])):
            voxel=np.floor(s["points"][:,y,x]/a.RES+.5).astype(int)
            self.assertEqual(self.volume[tuple(voxel)],42)
        self.assertTrue(s["masks"][0].any())

    def test_unsupported_or_invalid_requests_stop(self):
        with self.assertRaises(ValueError):self.view("sagittal",125,mode="projection",rotation_deg_ap_dv_ml=[5,0,0])
        with self.assertRaises(ValueError):self.view("coronal",-1)
        with self.assertRaises(ValueError):self.view("coronal",50,hemisphere="unknown")
        with self.assertRaises(ValueError):self.view("coronal",50,mode="projection",slab_um=[0,100000])

    def test_concave_anchor_stays_inside(self):
        mask=np.ones((15,15),bool);mask[3:12,3:12]=False
        y,x=a.anchor(mask)
        self.assertTrue(mask[y,x])
        self.assertIsNone(a.anchor(np.zeros((5,5),bool)))


class RequestChecks(unittest.TestCase):
    def test_publication_request_cannot_silently_use_qa_renderer(self):
        request={"view":{"plane":"sagittal","position_um":5500},"regions":[{"structure":"PVH"}],"illustration":{"background":"allen-reconstruction","allow_reconstruction":True}}
        with self.assertRaisesRegex(ValueError,"brainmap-illustrate"):
            a.render_request(request,"unused-output",cache="missing-cache")

    def test_accepts_documented_example_requests(self):
        from pathlib import Path
        import json
        for p in (Path(__file__).resolve().parents[1]/"references").glob("example-*.json"):
            request=json.loads(p.read_text(encoding="utf-8"))
            if "template_id" in request:
                import jsonschema
                from template_library import plate_schema
                jsonschema.Draft202012Validator(plate_schema()).validate(request)
            else:
                a.validate_request(request)

    def test_rejects_silent_wrong_units_and_ignored_parameters(self):
        import copy
        valid={"view":{"plane":"coronal","position_um":6975},"regions":[{"structure":"DMH"}]}
        for change in [{"position_mm":6.975},{"slab_um":[6000,7000]},{"position_um":"6975"},{"position_um":float("nan")}]:
            config=copy.deepcopy(valid);config["view"].update(change)
            with self.assertRaises(ValueError):a.validate_request(config)

    def test_rejects_unverified_connection_and_empty_region_selection(self):
        valid={"view":{"plane":"coronal","position_um":6975},"regions":[{"structure":"DMH"}]}
        valid["connections"]=[{"from":"DMH","to":"DMH","evidence":"published"}]
        with self.assertRaises(ValueError):a.validate_request(valid)
        valid.pop("connections");valid["regions"]=[]
        with self.assertRaises(ValueError):a.validate_request(valid)


@unittest.skipUnless(REAL,"Enable --real-atlas after fetch")
class RealAtlasChecks(unittest.TestCase):
    def test_ontology_and_coverage(self):
        nodes=a.tree(a.cache_default());volume=a.load_volume(a.cache_default())
        ids=a.annotation_ids(volume)
        for query,expected in [("LPB","PBl"),("Arc","ARH"),("PVH","PVH")]:
            node,_=a.resolve(query,nodes);self.assertEqual(node["acronym"],expected)
        with self.assertRaises(ValueError):a.resolve("POA",nodes)
        node,_=a.resolve("PBl",nodes)
        self.assertFalse(ids.intersection(a.descendants(node)))
        for name in ["PVH","DMH","ARH","RPA","PB"]:
            node,_=a.resolve(name,nodes)
            self.assertTrue(ids.intersection(a.descendants(node)))


if __name__=="__main__":unittest.main(verbosity=2)
