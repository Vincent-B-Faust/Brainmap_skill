# Atlas and coordinates

## Sources

- [CCF2017 25 µm annotation](https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/ccf_2017/annotation_25.nrrd), SHA256 `c620cbcc562183e4dcd40250d440130501781f74b41de35b1c1bdabace290c42`.
- [mouse_2011 annotation](https://download.alleninstitute.org/informatics-archive/current-release/mouse_ccf/annotation/mouse_2011/annotation_25.nrrd), SHA256 `2a69a4a21f56251cebb1564b3ec172c6de8c855a3ca90edce29ff43ba21d7e08`.
- [Structure graph 1](https://api.brain-map.org/api/v2/structure_graph_download/1.json), [official axis example](https://allensdk.readthedocs.io/en/latest/_static/examples/nb/reference_space.html), [CCFv3 paper](https://doi.org/10.1016/j.cell.2020.04.007).

The fixed NRRD is decoded in Fortran order as `(528,320,456)`, 25 µm. Axes are AP anterior→posterior, DV dorsal→ventral, ML left→right. Do not infer this ordering solely from the NRRD space label. Other files require independent affine/axis checks.

## Sampling

- Coordinates are CCF µm, with voxel center `index * 25`; they are not Bregma mm.
- Coronal: fixed AP, horizontal ML, vertical DV. Sagittal: fixed ML, horizontal AP, vertical DV. Horizontal: fixed DV, horizontal ML, vertical AP.
- Hemisphere boundary: ML 5700 µm; sampled voxel centers span 0..11375 µm.
- Rotations are active right-handed rotations in AP/DV/ML basis: `R_ML @ R_DV @ R_AP`, about the recorded section center.
- Use nearest-neighbor label sampling. Oblique projections are unsupported. No atlas→Bregma conversion without a verified transform.
- Parent masks include descendants. ROI contours and membership checks remain unsmoothed; background smoothing is illustrative.

## Names and coverage

| Display/input | Allen structure | ID |
|---|---|---:|
| PVH | Paraventricular hypothalamic nucleus | 38 |
| DMH | Dorsomedial nucleus of the hypothalamus | 830 |
| Arc | ARH | 223 |
| LPB | PBl, lateral parabrachial division | 881 |
| RPA | Nucleus raphe pallidus | 230 |
| MnPO | MEPO | 452 |
| Medial preoptic area | MPO | 523 |
| Medial preoptic nucleus | MPN | 515 |

Resolve IDs against the actual ontology at runtime. MPA may refer to medial preoptic area, not MPN. POA is not one precise entry; define a union explicitly. MPO+MEPO+LPO is an example, not a universal definition. RPA is not automatically a rostral subset; cell types and injection ranges are not whole-region masks.

CCF2017 has no distinct PBl/descendant voxels in the fixed volume. The legacy mouse_2011 annotation contains PBl subdivisions. Choose one supported source consistently; never replace LPB with PB or mix unregistered versions. Distinguish no labels anywhere in a volume from absence in a particular view.

Slices show actual intersections. Projections combine an explicit depth range and cannot establish depth colocalization. A single node anchors one connected component, not a bilateral center. Accuracy is limited by annotation, resolution and individual variation.
