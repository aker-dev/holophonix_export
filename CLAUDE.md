# holophonix_export — notes for Claude

**Project language: English.** All code, comments, documentation, and commit messages are written in English. Earlier revisions were in French; everything has been translated as of the *"Translate everything to English"* commit.

Project: export a Rhino 8 scene into a Holophonix package — Overview CSV (positions + colors) + two kinds of .glb (venue geometry and speaker blocks) that can be re-imported into Holophonix.

**Prerequisite**: Rhino >= 8.3 (for the `Rhino.FileIO.FileGltf` API).

## Files

- `holophonix_export.py` — script pasted inside the GhPython3 component (source of truth for the logic).
- `holophonix_export.ghx` — Grasshopper definition in XML form (versionable, diff-friendly). Embeds the `holophonix_export.py` script and the component wiring (inputs, panels, button). Open in Rhino 8 / Grasshopper to use directly.

## Target format (locked)

Header:
```
OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
```

Conventions:
- **OSC**: `/speaker/N` — global index in sort order.
- **Name**: `LAYER_NN` zero-padded per model group (e.g. `MDC5_01`, `HOPS8_02`). If the Rhino block instance has a `Name` attribute set (`ObjectAttributes.Name`), it is inserted between the layer and the index — e.g. `G18-SUB_CENTER_01`.
- **Color**: `R,G,B,A` as full-precision 0-1 floats, comma-separated (watch out: commas *inside* a `;`-separated field — that's the native Holophonix format).
- **X/Y/Z**: meters, 3 decimals (automatic conversion from the doc unit via `Rhino.RhinoMath.UnitScale`).
- **Azim/Elev/Dist**: degrees/meters, 3 decimals. Elev formula: `atan2(z, sqrt(x²+y²))` (more robust than `asin`, aligned with the official Ruby plugin).
- **Booleans**: `true` / `false` as strings (not `0`/`1`).
- **No trailing `\n`** in the file.

## Expected Rhino scene

- **Speakers**: Block Instances on sub-layers of `SPEAKERS::` (e.g. `SPEAKERS::MDC5`, `SPEAKERS::HOPS8`). Layer color = speaker color in the CSV.
- **Venue**: any geometry on the `VENUE` layer (or `VENUE::*` sub-layers). Exported as-is to `venue.glb`.

## GhPython component inputs

| Name              | Type | Default     |
|-------------------|------|-------------|
| `folder`          | str  | —           |
| `run`             | bool | —           |
| `layer_root`      | str  | `SPEAKERS`  |
| `auto_orient`     | bool | `False`     |
| `export_venue`    | bool | `True`      |
| `export_speakers` | bool | `True`      |

Outputs: `lines`, `count`, `log`.

Files produced in `folder` (created if missing):
- `holophonix_overview.csv` — positions + colors in the Holophonix Overview format.
- `venue.glb` — geometry of the `VENUE` layer (constant `VENUE_ROOT` at the top of the script).
- `<MODEL>.glb` — **one file per** `SPEAKERS::<MODEL>` sub-layer (e.g. `MDC5.glb`). Contains **only the block definition** (not the instances placed in the scene), with the **block insertion point as pivot / origin**. Holophonix instantiates the model at the CSV positions.

**Locked axis mapping (CSV only)**: `(X_h, Y_h, Z_h) = (Y_r, X_r, Z_r)` — swap X and Y, Z unchanged. **GLBs are exported in raw Rhino coordinates** (to be validated on the Holophonix side; if mirrored we'll need to transform the geometry before export).

## Typical edits

- Color format -> `rgba_color()` only.
- CSV axis convention -> edit `to_holophonix()` directly (mapping is frozen, not runtime).
- Units -> already handled automatically.
- VENUE layer -> `VENUE_ROOT` constant at the top of the script.
- Output file names -> constants `CSV_NAME`, `VENUE_GLB_NAME`. The per-model .glb files are named `<leaf>.glb` (if a prefix is needed, tweak the loop in `main` directly).
- glTF options -> `_gltf_options()` function, single source of truth (MapZToY, ExportMaterials, UseDisplayColorForUnsetMaterials, CullBackfaces, ExportLayers).
- GLB export -> via the **`Rhino.FileIO.FileGltf.Write(path, tmp_doc, options)`** API (no dialog, no user setup). Pattern: `Rhino.RhinoDoc.CreateHeadless(None)` -> `_add_with_color` (copies the geometry with an explicit display color) -> `FileGltf.Write` -> `tmp.Dispose()`. Used for the venue (`export_glb`) and per model (`export_block_def_as_glb`, flatten via `InstanceDefinition.GetObjects()`).
- **tmp doc units** (`_create_tmp_doc`): `CreateHeadless(None)` defaults to **meters**. If the source doc is in mm and we add the geometry as-is, the resulting GLB has coordinates 1000x too small — geometry invisible in Holophonix (1.6 cm instead of 16 m). We therefore call `tmp.AdjustModelUnitSystem(source_doc.ModelUnitSystem, False)` right after creation, to align units without rescaling the geometry.
- **Materials via display color** (`_add_with_color`): we do **not** create any `Material` or `RenderMaterial` in the tmp doc. We set `ObjectColor = <color>` + `ColorSource = ColorFromObject` on the attributes, `MaterialIndex = -1`, then `tmp_doc.Objects.Add(geom, attrs)`. The `UseDisplayColorForUnsetMaterials = True` option in `_gltf_options()` makes the glTF exporter use that display color as the PBR BaseColor (documented by McNeel: *"Objects using the default material export with their display colors as material colors"*).
- **Do NOT create a PBR material in the tmp doc**: Rhino bug **RH-81973** — `PhysicallyBasedMaterial` instances created inside a `RhinoDoc.CreateHeadless(None)` lose their parameters (BaseColor, Roughness, Clearcoat, ...) on glTF export. Symptom: GLBs with all-black materials. Ref: https://discourse.mcneel.com/t/physically-based-material-in-headless-doc/182696. If we ever need metallic/roughness/textures, we'll either need to wait for the fix or change the architecture (drop the tmp headless doc).
- The color passed to `_add_with_color` comes from `_resolve_display_color` on the venue side (per object) or from `collect_block_defs_by_leaf` on the speakers side (layer color of `SPEAKERS::<leaf>`, returned with the `InstanceDefinition` as a `{leaf: (def, color)}` tuple).
- **Never go back** to `RhinoApp.RunScript("_-Export …")`: on macOS it opens a blocking dialog that can only be dismissed by a manual, non-distributable setup.
- Speaker GLBs: always export the **definition** (neutral asset), not the instances placed in the scene — Holophonix handles instantiation from the CSV.
- **Pan / Tilt from block orientation**: the local forward of a speaker block is `FORWARD_LOCAL = (0, 1, 0)` (local +Y). We transform it by `InstanceXform` (rotation-only for vectors) and apply `to_holophonix` before computing `pan = -atan2(y, x)` (sign flipped to match Holophonix) and `tilt = atan2(z, horizontal)` in degrees (function `pan_tilt`). If the front face of a block points along another local axis, change `FORWARD_LOCAL`.

## Do NOT

- Switch the color back to `#RRGGBB` (rejected by Holophonix).
- Add a trailing `\n`.
- Rename `Name` to `Speaker N` without confirmation (the user specifically wants `LAYER_NN` or `LAYER_OBJNAME_NN`).
- Re-introduce X/Y/Z offsets (abandoned feature — reposition the Rhino scene origin if needed).
- Commit the binary `.gh` alongside the `.ghx`. The repo versions `.ghx` only (text XML, diffable).

## External reference

Official Holophonix Ruby plugin `HOLOPHONIX_speaker_export` (Holophonix S.A.S., 2024) — source of the AED formulas, boolean conventions, and separators. Not in the repo but read by the user to validate alignment.
