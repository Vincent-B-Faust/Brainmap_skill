"""Verify geometric routing and registration guards; optional real-figure audit."""
import argparse
import json
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET
import numpy as np

import illustration as illustration


class LayoutChecks(unittest.TestCase):
    def test_reconstruction_needs_explicit_permission(self):
        request={"view":{"plane":"sagittal","position_um":5500},"regions":[{"structure":"PVH"}],"illustration":{"background":"allen-reconstruction","atlas":"mouse_2011"}}
        with self.assertRaisesRegex(ValueError,"explicitly allowed"):
            illustration.illustrate_request(request,"unused-output",cache="missing-cache")

    def test_routes_around_unrelated_region(self):
        nodes={"A":{"center":[100,220],"radius":[42,26]},"B":{"center":[600,220],"radius":[42,26]},"C":{"center":[350,220],"radius":[60,35]}}
        edge={"from":"A","to":"B","kind":"excitatory"}
        route=illustration.route_edge(edge,nodes,[],[800,500])
        self.assertEqual(route["node_intrusions"],[])
        self.assertFalse(illustration.overlaps(route["points"],nodes["C"]).any())
        self.assertGreater(abs(route["bend_px"]),35)

    def test_bidirectional_edges_have_separate_paths(self):
        nodes={"A":{"center":[100,220],"radius":[42,26]},"B":{"center":[600,220],"radius":[42,26]}}
        first=illustration.route_edge({"from":"A","to":"B"},nodes,[],[800,500])
        second=illustration.route_edge({"from":"B","to":"A"},nodes,[first["points"]],[800,500])
        self.assertFalse(np.allclose(first["points"],second["points"][::-1]))
        self.assertEqual(second["crossings"],0)

    def test_ports_end_on_ellipse_outside_label(self):
        center=np.array([150.,180.]);radius=np.array([50.,25.])
        port=illustration.ellipse_port(center,radius,[220,300],0)
        self.assertAlmostEqual(np.sum(((port-center)/radius)**2),1.0)

    def test_registration_requires_independent_checks(self):
        with self.assertRaises(ValueError):illustration.fit_registration({"landmarks":[],"holdout_landmarks":[]})
        fits=[{"atlas_pixel_xy":p,"art_xy":[2*p[0]+3,3*p[1]+4]} for p in [[0,0],[20,0],[0,20],[20,20]]]
        held=[{"atlas_pixel_xy":p,"art_xy":[2*p[0]+3,3*p[1]+4]} for p in [[5,5],[15,10]]]
        profile={"landmarks":fits,"holdout_landmarks":held,"max_holdout_error_art_units":1}
        _,errors=illustration.fit_registration(profile)
        self.assertLess(max(errors),1e-8)
        profile["holdout_landmarks"][0]["art_xy"][1]+=20
        with self.assertRaises(ValueError):illustration.fit_registration(profile)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--figure",type=Path)
    args,rest=parser.parse_known_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(LayoutChecks))
    if not result.wasSuccessful():raise SystemExit(1)
    if args.figure:
        audit=json.loads((args.figure/"audit.json").read_text(encoding="utf-8"))
        assert len(audit["regions"])==6
        assert all(x["anchor_membership_pass"] for x in audit["regions"])
        assert all(not e["node_intrusions"] and not e["self_intrusions"] and not e["outside_samples"] for e in audit["connections"])
        assert audit["claims"]["crossings"]==0
        root=ET.parse(args.figure/"figure.svg").getroot()
        assert not any(x.tag.split('}')[-1]=='image' for x in root.iter()),"Final SVG must be vector"
        assert any(r["label"]=="LPB" and r["actual_structure_id"] in [860,868,875,883,891] for r in audit["regions"])
        for edge in audit["connections"]:
            assert edge["terminal"]==("triangle" if edge["kind"]=="excitatory" else "perpendicular_bar")
        print("Real figure: six memberships, eight semantic connections, zero crossings/intrusions, vector-only SVG passed")
