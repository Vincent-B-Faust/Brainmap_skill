# Illustration design

## Canvas

Final artwork contains only tissue, requested regions, short labels and requested connections. Extra titles, legends, coordinates, scale bars, orientation letters, insets and panels are opt-in. Keep source and reconstruction/projection disclosures in audit/notes.

## Geometry and styling

- Prefer native atlas plates; use consistent volumetric annotation for other views.
- Background curves may be smoothed and simplified. ROI membership and anatomical anchors remain unchanged.
- Pale-gray tissue; white fiber cues; restrained green, purple, gold, coral, blue and rose accents.
- Use one effective outer stroke weight and color. Tissue fills precede the final outline. Bake nonuniform transforms into path coordinates.
- Cerebellar texture follows source lobules and white-matter branches. Do not invent random folds or use a generic fan pattern.
- Node size is schematic. Do not move anatomical centers to fix overlap; use shorter labels or an explicitly requested detail view.

## Connections and review

Triangles indicate specified activation; perpendicular bars indicate inhibition. Native `projection` uses rounded boutons without a functional sign. Curve paths are not traced axons. Avoid unrelated nodes, separate bidirectional curves and inspect terminal visibility in a rendered PNG/PDF.

Check audit IDs, anchor membership, source version and masks. Numerical checks do not replace visual inspection. Synthetic layouts are not biological evidence.

## BioArt registration

A matching profile requires species, plane, atlas, section position, source hash, at least 3 noncollinear fit landmarks and 2 independent held-out landmarks. Maximum held-out error defaults to 8 artwork units. Low fit error alone does not prove anatomical matching. BioArt 370 has no declared AP level; any mapping must disclose that uncertainty outside the canvas.
