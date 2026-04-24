# holophonix_export

Export a Rhino 8 scene to a **Holophonix package** (Overview CSV + `venue.glb` + one `.glb` per speaker model), from a Grasshopper GhPython3 component.

> Project language is English. All code, comments, docs, and commit messages are in English.

## Prerequisites

- **Rhino >= 8.3** (embedded CPython 3 on the Grasshopper side + `Rhino.FileIO.FileGltf` API used for programmatic .glb export).
- A Rhino scene with:
  - **Speakers** — Block Instances on sub-layers of `SPEAKERS::*` (one sub-layer per model: `SPEAKERS::MDC5`, `SPEAKERS::HOPS8`, ...). The layer color is used as the speaker color in the CSV.
  - **Venue** — any geometry on the `VENUE` layer (or `VENUE::*`). Exported as-is to .glb.

## Installation

**Quick path** — open [`holophonix_export.ghx`](holophonix_export.ghx) in Grasshopper. The definition already embeds the GhPython3 component, its script, all the inputs, the Button for `run`, and the output Panels.

**Manual path** (if you prefer to rebuild the component from scratch):

1. Open Grasshopper inside Rhino 8.
2. Drop a **GhPython3** component (*Script → Python 3*).
3. Paste the contents of [`holophonix_export.py`](holophonix_export.py) into the component editor.
4. Add the inputs (right-click on the component, `+`):

   | Name              | Type | Details                                                          |
   |-------------------|------|------------------------------------------------------------------|
   | `folder`          | str  | Panel with the output **folder** path (created if missing)       |
   | `run`             | bool | **Button** — writes CSV + GLB package                            |
   | `layer_root`      | str  | Panel, defaults to `SPEAKERS`                                    |
   | `auto_orient`     | bool | Toggle, defaults to `False`                                      |
   | `export_venue`    | bool | Toggle, defaults to `True` — writes `venue.glb` when enabled     |
   | `export_speakers` | bool | Toggle, defaults to `True` — writes one `<MODEL>.glb` per model  |
   | `sync`            | bool | **Button** — pushes speakers to Holophonix via OSC               |
   | `osc_host`        | str  | Panel, defaults to `127.0.0.1`                                   |
   | `osc_port`        | int  | Panel, defaults to `4003`                                        |

5. Add the outputs `lines`, `count`, `log`.

> The `.ghx` is the versioned Grasshopper definition (XML, diff-friendly). The binary `.gh` variant is intentionally kept out of the repo.

## Usage

1. Wire a Panel to `lines` to preview the CSV rows.
2. Check `count` (number of detected speakers) and `log` (per-model breakdown + written paths).
3. Click **`run`** → files produced in `folder`:
   - `holophonix_overview.csv`
   - `venue.glb` — venue geometry
   - `<MODEL>.glb` for each `SPEAKERS::<MODEL>` sub-layer (e.g. `MDC5.glb`, `HOPS8.glb`, `G18-SUB.glb`, ...) — **one asset per model**, containing only the block definition with its insertion point as pivot. Not the instances placed in the scene.
4. In Holophonix: import the CSV through the **Overview** window, load `venue.glb` as the stage decor, and each `<MODEL>.glb` as an asset instantiated at the positions of the matching speakers in the CSV.

## OSC live sync

Once the speakers exist in Holophonix (from the CSV import above), you can push live updates without going through a file round-trip:

1. Set `osc_host` and `osc_port` to match your Holophonix instance (defaults `127.0.0.1:4003`).
2. Click **`sync`** → the component sends one UDP/OSC message per parameter per speaker: `name`, `color` (RGBA), `azim` / `elev` / `dist`, `view3D/pan`, `view3D/tilt`, `view3D/autoOrientation`.
3. The speakers keep their index from the CSV import, so positions update in place.

The OSC encoder is a ~30-line helper in [`holophonix_export.py`](holophonix_export.py) (no external dependency). It speaks OSC 1.0 over UDP — address + typetag + 4-byte-aligned args.

> OSC cannot create new speakers — only update existing ones. If you add/remove speakers in Rhino, re-export the CSV and re-import it in Holophonix so slot indices stay in sync.

## Output format

```
OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
/speaker/1;MDC5_01;0.4588235294117647,0.20392156862745098,0.20392156862745098,1;1.200;-2.500;1.800;-64.358;31.128;3.431;true;0;0;false
...
```

- **OSC**: global index (`/speaker/1`, `/speaker/2`, ...) in sort order.
- **Name**: `<model>_NN` zero-padded per group, or `<model>_<objname>_NN` when the Rhino block instance has a Name attribute set (e.g. `G18-SUB_CENTER_01`).
- **Color**: `R,G,B,A` as 0–1 floats.
- **X/Y/Z**: meters — automatic conversion from the Rhino document unit.
- **Pan / Tilt**: derived from each speaker block's orientation in the scene. Forward axis convention: local +Y inside the block definition (see `FORWARD_LOCAL` in the script). Pan = azimuth of the forward vector in the horizontal plane, Tilt = elevation above horizontal, both in degrees.
- Numeric fields written at **full precision** (`repr()`-style), kept consistent with what `sync` pushes over OSC so the two paths produce identical positions in Holophonix.

## Axis conventions

Locked **CSV** mapping: `(X_h, Y_h, Z_h) = (Y_r, X_r, Z_r)` — swap X and Y, Z unchanged. Validated on the reference scene. To change the convention, edit `to_holophonix()` in [`holophonix_export.py`](holophonix_export.py).

The **GLBs** are exported in raw Rhino coordinates (no pre-export transform). Verify on the Holophonix side; if the geometry appears mirrored relative to the CSV positions, a transformation step should be added in `export_glb` / `export_block_def_as_glb`.

## Limitations

- Filtering by block definition name is not native in Grasshopper (RH-78812). We filter by layer, which is enough here.
- No origin-offset handling (feature deliberately abandoned — reposition the Rhino scene origin instead if needed).
- GLB export relies on `Rhino.FileIO.FileGltf` (available since Rhino 8.3). On older versions the script fails with an `AttributeError`.
- Nested `InstanceReference`s inside a speaker block definition are not resolved (their definition is not copied into the temporary document used for export). Usually a non-issue for "flat" speaker blocks.

## Inspiration

Official Holophonix Ruby SketchUp plugin **`HOLOPHONIX_speaker_export`** (Holophonix S.A.S., 2024) — same AED logic and same serialization conventions (string booleans, separators, no trailing newline), adapted to Rhino/Grasshopper.
