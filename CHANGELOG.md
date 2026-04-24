# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-04-24

First public release. The GhPython component exports a Rhino 8 scene to a Holophonix package (CSV Overview + one venue .glb + one .glb per speaker model) and can push the current speaker state live to a running Holophonix instance over UDP/OSC.

### Added
- CSV export in Holophonix **Overview** format (13 columns, `;` separator, no trailing newline).
- OSC addresses `/speaker/N`, names `LAYER_NN` or `LAYER_OBJNAME_NN` (the Rhino block instance `Attributes.Name` is inserted when set).
- Color column as `R,G,B,A` floats 0–1, full precision (matches Holophonix's native export style).
- Document-unit-aware coordinates via `Rhino.RhinoMath.UnitScale` — positions always written in meters regardless of the Rhino doc unit.
- Frozen Rhino → Holophonix axis mapping `(X_h, Y_h, Z_h) = (Y_r, X_r, Z_r)`.
- Polar formulas aligned with the official Holophonix Ruby plugin (`atan2`-based elevation, degrees with full precision).
- Pan / Tilt derived from each speaker block's orientation in Rhino. Physical forward axis: local −Y.
- GLB export via the RhinoCommon `Rhino.FileIO.FileGltf` API (Rhino 8.3+), no dialog, no per-user setup. Temporary headless document pattern, unit-aligned with the source doc.
- One `venue.glb` for the `VENUE::*` geometry and one `<MODEL>.glb` per `SPEAKERS::<MODEL>` sub-layer, each containing the block definition with its insertion point as pivot.
- Display-color–based material assignment in the GLBs to sidestep Rhino bug RH-81973 (PBR parameters lost in headless docs).
- **OSC live sync** (`sync` button) — pushes name, color, azim, elev, dist, view3D/pan, view3D/tilt, view3D/autoOrientation for each speaker. Minimal in-file OSC 1.0 UDP encoder, no external dependency. Numeric payload sent as float32 for bit-accurate round-trip with the CSV.
- Component inputs: `folder`, `run`, `layer_root`, `auto_orient`, `export_venue`, `export_speakers`, `sync`, `osc_host`, `osc_port`.
- Versionable Grasshopper definition in XML form (`holophonix_export.ghx`) embedding the script and wiring.
- Sample scene `starting_scene.3dm` with the expected layer hierarchy.
- MIT license and English-only source.

[1.0.0]: https://github.com/aker-dev/holophonix_export/releases/tag/v1.0.0
