# Plan — Grasshopper definition: Rhino speakers -> Holophonix CSV export

> Historical document, kept for context. Reflects the initial plan before the script and GLB export pipeline were implemented. The current implementation is described in [CLAUDE.md](../CLAUDE.md) and [README.md](../README.md).

## Context

The project contains a Rhino scene where each speaker is placed as a **block instance** (CS7P, G18-SUB, HOPS5, HOPS8, MAUI28G2, MDC5) on a dedicated `SPEAKERS::*` sub-layer. Each sub-layer has a color identifying the speaker type.

We want to generate a CSV in the **Holophonix Overview** format:

```
OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
```

Confirmed decisions:
- **Plugin**: native Rhino 8 components only (no Elefront/Human).
- **OSC Address**: `/track/[LAYER]/N` (per-type numbering, e.g. `/track/MDC5/1`).
- **Axes**: include a toggle to switch between two conventions (Rhino scene <-> Holophonix).
- **Name**: `[Model]_NN` zero-padded (e.g. `MDC5_01`, `MDC5_02`).

## GH flow overview

```
Query Model Objects   ──►  Deconstruct Block Instance ──►  Insertion Point
      │  (filter                  │
      │   Layer: SPEAKERS::*)     └──►  Block Definition ──► Model name (MDC5, HOPS8…)
      │
      ├──►  Model Object Attributes ──►  Layer ──► Model Layer ──►  Display Color
      │                                                         └──►  Layer Name (leaf)
      │
      └──►  (Group by layer) ──► Per-group increment ──► NN index
                                                 │
                                                 ▼
                                    Cartesian -> Polar (Azim/Elev/Dist)
                                                 │
                                                 ▼
                                    Format CSV (Concatenate / Python) ──►  Write File
```

## Detailed structure

### 1. Speaker query

- **Component**: `Query Model Objects` (Rhino tab)
  - Input filter: `Content Filter` with type `Block Instance` and `Layer` containing `SPEAKERS::` (or a panel listing each sub-layer explicitly).
  - Output used: the **Block Instances** branch (right-click -> *Show All Params*).

Known limitation: filtering by *block definition name* is not native (RH-78812). Not blocking here since we filter by layer; the block name is read through `Deconstruct Block Instance` downstream.

### 2. Position + model extraction

- **Component**: `Deconstruct Block Instance`
  - Input: the filtered block instances.
  - Outputs: **Transform** + **Block Definition**.
- **Transform -> Point**: `Transform Point` with origin `(0,0,0)` as input → yields the **insertion point** of each block.
- **Block Definition -> Name**: `Deconstruct Block Definition` → **Name** output (e.g. `MDC5`).

### 3. Layer + color extraction

- `Model Object Attributes` on the block instances → **Layer** output (full path `SPEAKERS::MDC5`).
- `Deconstruct Model Layer` (or `Model Layer` + path) → **Display Color** output (layer color) + **Full Path** / **Name**.
- Leaf name (`MDC5`): *Text Split* on `::` → last element (also used for the OSC Address and for naming).

### 4. Per-type numbering

- `Group` (native *Group Data*) by leaf layer name.
- In each group: `Series` (Start=1, Count=group size) → `Format` with `{0:00}` for zero-padding → `NN` index.
- Flatten via `Flatten Tree` while preserving the group order.

### 5. Coordinate conversion + axis toggle

- **Toggle**: `Value List` with two entries — `Direct` and `Rhino→Holophonix`.
- A native `Expression` component (or two small branches with `Deconstruct Point`/`Construct Point`) remaps:
  - **Direct**: `(Xh, Yh, Zh) = (Xr, Yr, Zr)`
  - **Rhino→Holophonix**: mapping to validate empirically (standard audio hypothesis: `Xh = Yr`, `Yh = -Xr`, `Zh = Zr` — front/left/up). The toggle allows testing both and keeping the correct one after verification in Holophonix.
- **Polar (Azim, Elev, Dist)** — `Expression` or 3 math components:
  - `Dist = Sqrt(Xh² + Yh² + Zh²)`
  - `Azim = Degrees( Atan2(Yh, Xh) )`
  - `Elev = Degrees( Asin(Zh / Dist) )` (with a guard for `Dist == 0`)

### 6. Color format

- `Deconstruct Color` → R, G, B (0–255).
- `Expression` / `Concatenate` → hex `#RRGGBB` (default).
- To validate: if Holophonix expects another format (`R,G,B` decimal, name, etc.), change only this step. Exporting a reference CSV from Holophonix with a manually placed speaker will confirm.

### 7. Building CSV lines

- Fixed columns with default values (to adjust as needed):
  - `Auto Orientation` = `0` (or `false`)
  - `Pan`, `Tilt` = `0`
  - `Lock` = `0` (or `false`)
- `Concatenate` with `;` separator in the exact order of the header:
  ```
  /track/<LAYER>/<N>;<LAYER>_<NN>;<#RRGGBB>;<X>;<Y>;<Z>;<Azim>;<Elev>;<Dist>;0;0;0;0
  ```
- Prepend the target header on the first line:
  ```
  OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
  ```
- `Merge` header + lines.

### 8. Writing the file

- Native **`Write File`** component (*Sets → Text* tab):
  - `File`: output path (e.g. `/Users/zak/Desktop/holophonix_export.csv`).
  - `Content`: list of lines.
  - `Append`: `false`.
- Add a **Button** (native `Button`) to trigger writing on demand and avoid overwriting on every GH change.

## Files / deliverables

- **Grasshopper definition** (.gh) to be authored by the user according to the schema above. No code in the `momesu_migration` repo (unrelated topic).
- Optional: a short **GhPython** component to replace steps 4–7 if the native wiring becomes too cluttered (fewer wires, more maintainable for you). I can provide this script on request — it remains compatible with native Rhino 8 (embedded IronPython / Python 3).

## Points to validate after the first export

1. **Color format** accepted by Holophonix (`#RRGGBB` vs `R,G,B` vs other) → export a reference CSV from Holophonix.
2. **Axis convention** correct → flip the toggle if the speakers appear mis-oriented in the Holophonix view.
3. **Angle signs** `Azim` / `Elev` (clockwise vs trigonometric, range `[-180, 180]` vs `[0, 360]`).
4. **Default values** for `Auto Orientation`, `Pan`, `Tilt`, `Lock` (`0/1` booleans vs `true/false`).

## End-to-end verification

1. Open the Rhino scene with the speakers in place.
2. Load the GH definition, confirm:
   - Number of CSV lines = number of blocks on `SPEAKERS::*` sub-layers.
   - Names follow `MODEL_NN`.
   - OSC addresses follow `/track/MODEL/N`.
3. Click the Button → CSV file written.
4. Open the CSV in a text editor → verify the `;` separator and the identical header.
5. Import into Holophonix via the Overview window.
6. Visually compare the layout in Holophonix vs Rhino (top view) — tweak the axis toggle if needed.
7. If colors are wrong: export a reference CSV from Holophonix, diff the format, adjust step 6.
