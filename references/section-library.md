# Section library

The package contains 13 native Allen SVG plates, 4 CCF2017 reconstruction bases and 287 discovery records. Indexed plates are not all downloaded. Native sources retain original bytes; template.json records URLs, IDs, hashes and display transforms.

```sh
brainmap-library choose --plane sagittal --regions VTA ACB PL
brainmap-library illustrate references/example-vta-da.json --out outputs/figure
brainmap-library schema
```

For a sagittal view with no specified offset, first require verified midsagittal provenance; never infer ML from the section number or silently select a lateral plate for better coverage. If no suitable midline plate is verified, use an Allen midsagittal reconstruction. Within the chosen view, prefer `all_targets_delineated: true`. Explicit `template_id` requests select that native plate and remain unchanged. Selection uses actual structure IDs and descendants; rendering verifies an interior point against unsmoothed source-path masks. Do not add targets absent from a plate.

For more plates, copy `scripts/assets/section-library` to a writable directory:

```sh
brainmap-library --library /path/to/library fetch --atlas-id 1 --image-id 100960033
brainmap-library build --out /path/to/library
```

- Native plate space: source SVG pixels and transforms, not CCF/Bregma. Do not mirror unilateral source plates automatically.
- Volume space: explicit CCF AP/DV/ML coordinates and rotations. Horizontal/oblique examples are resampled reconstructions, not downloaded 2D artwork.
- `kind:projection` draws rounded boutons; activation and inhibition require their corresponding explicit kinds.
- Final exports contain only diagrams. Gallery captions are selection aids and must not be copied onto final artwork.

The VTA example uses atlas 2, image 100883900, section 180: VTA, ACB and PL are delineated on the same plate. Its cerebellar texture uses source lobules and fiber paths. See [example notes](../examples/vta-da-circuit.notes.md).

Sources: [Allen SVG API](https://brain-map.org/support/tutorials/atlas-drawing-and-ontologies), [BioArt 370](https://bioart.niaid.nih.gov/bioart/370). BioArt 370 is a mouse coronal drawing without a declared AP level; 369 is an external lateral view. See [attribution](../THIRD_PARTY_NOTICES.md).
