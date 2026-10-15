# Official atlas drawings

Use this route when volumetric labels lack a target or a native section is preferred.

```sh
brainmap-drawings list --atlas-id 1 --out outputs/plates
brainmap-drawings plate --image-id 100960033 --out outputs/plate
```

Atlas 1 is Mouse P56 Coronal; 2 is Mouse P56 Sagittal; 602630314 is Adult Mouse 3D Coronal. Preserve atlas/image IDs, section_number and graphic group. Section numbers are sequence identifiers, not CCF µm or Bregma mm.

The tool preserves original SVG paths/transforms and inventories structure_id paths. Highlighting includes descendants only when actually delineated; a missing target must fail. The native library additionally verifies internal label anchors against rendered original paths.

Do not mix native plate boundaries with CCF data without a verified registration. Arbitrary oblique views require suitable 3D labels, not rotation of a 2D plate.

[Official SVG API](https://brain-map.org/support/tutorials/atlas-drawing-and-ontologies)
