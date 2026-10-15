# Requests

## Native plates

Use `brainmap-library schema`. Inputs contain `template_id`, `regions`, optional `connections`; example: [example-vta-da.json](example-vta-da.json). No CCF coordinate is inferred from the plate ID.

## Volumetric views

Use `brainmap schema` or [request.schema.json](../scripts/request.schema.json).

```json
{
  "view": {"plane":"coronal", "mode":"slice", "position_um":6975, "hemisphere":"both"},
  "regions": [{"structure":"DMH"}, {"label":"Arc", "structure":"ARH"}]
}
```

- `plane`: sagittal, coronal, horizontal. `position_um`: CCF µm on the fixed axis. An orthogonal sagittal slice may omit it and defaults to the midsagittal plane, ML 5700 µm; explicit coordinates are preserved. Coronal, horizontal, rotated and projected requests still require `position_um`. Validation returns a normalized copy; the caller input is not mutated.
- `mode`: slice or orthogonal projection. `slab_um`: inclusive projection depth range. `hemisphere`: both, left or right.
- `rotation_deg_ap_dv_ml`: three explicit rotation angles; oblique depth projection is unsupported.
- Regions use `structure` (exact acronym/ID) or an explicit `structures` union, optional label/color/fill_color. Parent masks include descendants. Labels must be unique.
- `allow_absent:true` reports missing targets; it does not permit invented placement.
- Volumetric artwork adds `illustration.background`, `atlas` and, for an accepted reconstruction, `allow_reconstruction:true`. BioArt requires a matching landmark profile.
- Connections require existing endpoint labels, `kind`, `evidence` and `source`; optional `color`, `bend_px`. Evidence is published, user-specified, or hypothesis. Published claims need checked literature. Unverified demonstration layouts are hypotheses.
- Triangles indicate activation, T bars inhibition. Native `projection` uses rounded boutons without assigning a functional effect. The volumetric illustration tool currently requires excitatory/inhibitory kinds; QA may show unsigned projections.

Output audit/masks establish spatial placement, not biological connectivity. Coordinate and source records remain outside the visible diagram.

All numeric input must be finite. Render bundles are staged before publication; a failed render leaves an existing output intact. A successful render replaces the output directory, so use a dedicated directory and export previews afterward. NPZ masks use stable `region_0`, `region_1`, … keys; native-plate audits map each `mask_key` to its display label.

For unspecified sagittal circuit views, keep a midsagittal backdrop. If targets lie at different depths, record an explicit projection/slab and verify each anchor at its own depth; do not describe the result as a single slice. A literal midline slice must not acquire missing lateral targets. Image-tool execution follows [image-generation.md](image-generation.md).
