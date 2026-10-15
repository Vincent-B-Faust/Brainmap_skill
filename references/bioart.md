# BioArt sources

Prefer the native atlas library. When BioArt is explicitly required, match species, internal/external view, plane and anatomical level, then verify landmark mapping. A downloaded drawing is not automatically registered.

- [370: Mouse Brain Coronal](https://bioart.niaid.nih.gov/bioart/370), Public Domain, Ryan Kissinger / NIAID Visual & Medical Arts. SVG: `scripts/assets/bioart-370-632537.svg`. AP level is not declared.
- [369: Mouse Brain](https://bioart.niaid.nih.gov/bioart/369) is an external lateral surface, not an internal sagittal section.
- [283: Lab Mouse](https://bioart.niaid.nih.gov/bioart/283), Public Domain, Ryan Kissinger / NIAID. Independent animal illustration, not a brain-section base.

Source URLs and hashes: [catalog](bioart-catalog.json), [third-party notices](../THIRD_PARTY_NOTICES.md). Check licensing per entry; do not apply one entry's status to all BioArt or Allen content.

Registration requires ≥3 noncollinear fit landmarks and ≥2 independent held-out landmarks with acceptable error. Preserve the source, transform and uncertainty. If artwork does not match, use another suitable source or an accepted reconstruction; never relabel an external view as a section or a reconstruction as BioArt.

Profile `art_xy` uses the original SVG user coordinate system, before the `viewBox` viewport transform. Its origin may be nonzero; width and height must be finite and positive. Fit and held-out landmarks must be distinct in both atlas-pixel and artwork coordinates (absolute tolerance 1e-6 native units). The holdout error threshold must be finite and nonnegative. Numerical checks prevent point reuse; they cannot establish independent human annotation.

Only static SVG elements, attributes and a restricted CSS subset are accepted. Events, scripts, foreign namespaces, declarations and external references are rejected; local fragment references are allowed. A matching hash verifies file identity, not safety.
