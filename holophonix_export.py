# Holophonix Overview export — GhPython (Rhino 8.3+, Python 3)
#
# GhPython component setup:
#   Inputs:
#     folder           (str,  Item Access) — output folder (CSV + .glb)
#     run              (bool, Item Access) — button, writes CSV + GLBs
#     layer_root       (str,  Item Access) — speakers layer prefix, defaults to "SPEAKERS"
#     auto_orient      (bool, Item Access) — writes "true"/"false" in the Auto Orientation column
#     export_venue     (bool, Item Access) — writes venue.glb when True (default True)
#     export_speakers  (bool, Item Access) — writes one <MODEL>.glb per model when True (default True)
#     sync             (bool, Item Access) — button, pushes speakers to Holophonix via OSC
#     osc_host         (str,  Item Access) — Holophonix host for OSC sync, defaults to "127.0.0.1"
#     osc_port         (int,  Item Access) — Holophonix OSC port, defaults to 4003
#   Outputs:
#     lines  — list of CSV lines (header included), for preview
#     count  — number of exported speakers
#     log    — diagnostics (groups + written paths + OSC status)
#
# Behavior: scans every Block Instance whose full layer path starts with
# "<layer_root>::", converts the insertion point to meters regardless of
# the document unit, groups by leaf layer name, assigns a zero-padded NN
# index per group, converts to polar (formulas aligned with the official
# Holophonix Ruby plugin), then if `run` is True writes into `folder`:
#   - holophonix_overview.csv    (positions + colors)
#   - venue.glb                  (geometry of the VENUE::* layer)
#   - <MODEL>.glb                (block definition, pivot = insertion point;
#                                 one file per SPEAKERS::<MODEL> sub-layer)
#
# Frozen CSV axis mapping: (X_h, Y_h, Z_h) = (Y_r, X_r, Z_r).
# GLBs are written through Rhino.FileIO.FileGltf.Write (RhinoCommon API,
# no GUI dialog) into a temporary headless document. Requires Rhino >= 8.3.

import Rhino
import math
import os
import socket
import struct
from collections import defaultdict

HEADER = "OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock"

DEFAULT_LOCK = "false"

VENUE_ROOT = "VENUE"
CSV_NAME = "holophonix_overview.csv"
VENUE_GLB_NAME = "venue.glb"
# Speakers are exported as one .glb per model, named "<leaf>.glb"
# (e.g. MDC5.glb, HOPS8.glb, G18-SUB.glb).

# Local forward of a speaker block (front face direction in the block
# definition's coordinate system). Applied via InstanceXform to get the
# world-space forward used for Pan / Tilt extraction.
FORWARD_LOCAL = (0.0, 1.0, 0.0)


def to_holophonix(xyz):
    # Frozen Rhino -> Holophonix mapping: swap X and Y, Z unchanged.
    x, y, z = xyz
    return y, x, z


def polar(xh, yh, zh):
    d = math.sqrt(xh * xh + yh * yh + zh * zh)
    if d == 0.0:
        return 0.0, 0.0, 0.0
    az = math.degrees(math.atan2(yh, xh))
    el = math.degrees(math.atan2(zh, math.sqrt(xh * xh + yh * yh)))
    return az, el, d


def pan_tilt(forward_holo):
    """Pan and tilt (degrees) of a forward vector expressed in Holophonix coords.

    Pan  = -atan2(y, x)              — azimuth in the horizontal plane
                                       (negated to match Holophonix's sign convention)
    Tilt = atan2(z, sqrt(x² + y²))   — elevation above horizontal
    """
    x, y, z = forward_holo
    horiz = math.sqrt(x * x + y * y)
    if horiz == 0.0:
        return 0.0, (90.0 if z > 0 else -90.0 if z < 0 else 0.0)
    return -math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, horiz))


def rgba_color(c):
    # Holophonix format: R,G,B,A as full-precision 0-1 floats.
    # Integer values (0, 1) are rendered without decimals to match the native export.
    def fmt(v):
        iv = int(v)
        return str(iv) if v == iv else repr(v)
    return ",".join(fmt(x / 255.0) for x in (c.R, c.G, c.B, c.A))


def collect_objects_on_layer(doc, root):
    """Object IDs whose layer FullPath equals `root` OR starts with `root::`."""
    ids = []
    for obj in doc.Objects:
        layer = doc.Layers[obj.Attributes.LayerIndex]
        fp = layer.FullPath
        if fp == root or fp.startswith(root + "::"):
            ids.append(obj.Id)
    return ids


def collect_block_defs_by_leaf(doc, root):
    """Dict {leaf: (InstanceDefinition, layer_color)} — one definition per
    `root::` sub-layer, together with the source layer color so we can apply
    a consistent material in the .glb."""
    root_prefix = root + "::"
    defs = {}
    for obj in doc.Objects:
        if obj.ObjectType != Rhino.DocObjects.ObjectType.InstanceReference:
            continue
        layer = doc.Layers[obj.Attributes.LayerIndex]
        fp = layer.FullPath
        if not fp.startswith(root_prefix):
            continue
        leaf = fp.split("::")[-1]
        if leaf not in defs:
            defs[leaf] = (obj.InstanceDefinition, layer.Color)
    return defs


def _gltf_options():
    """Default glTF export options. Consistent with the CSV (Z up)."""
    opts = Rhino.FileIO.FileGltfWriteOptions()
    opts.MapZToY = False                          # keep Z as height (matches CSV)
    opts.ExportMaterials = True
    opts.UseDisplayColorForUnsetMaterials = True  # fallback when no material is set
    opts.CullBackfaces = True
    opts.ExportLayers = False                     # GLB = neutral asset
    return opts


def _resolve_display_color(source_doc, rh_obj):
    """Display color of `rh_obj` in the source document (from object or layer)."""
    attrs = rh_obj.Attributes
    if attrs.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromObject:
        return attrs.ObjectColor
    return source_doc.Layers[attrs.LayerIndex].Color


def _add_with_color(tmp_doc, rh_obj, color):
    """Add `rh_obj` to the temporary document with an explicit display color.

    The glTF exporter uses that display color as the PBR BaseColor thanks to the
    `UseDisplayColorForUnsetMaterials = True` option in `_gltf_options`. We do
    **not** create any material in the tmp doc — this sidesteps Rhino bug
    RH-81973 (PhysicallyBasedMaterials created inside a RhinoDoc.CreateHeadless
    lose their PBR parameters on glTF export: BaseColor goes black, Roughness 0, ...)."""
    attrs = rh_obj.Attributes.Duplicate()
    attrs.ObjectColor = color
    attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromLayer
    attrs.MaterialIndex = -1   # no material assigned -> display color is used
    attrs.LayerIndex = 0       # default layer of the tmp doc
    tmp_doc.Objects.Add(rh_obj.Geometry, attrs)


def _create_tmp_doc(source_doc):
    """Create a headless RhinoDoc whose unit system is aligned with the source doc.

    `CreateHeadless(None)` defaults to meters. If the source doc is in mm (a
    common case for floor plans), adding the geometry as-is produces a GLB with
    coordinates that are 1000x too small — objects become invisible in
    Holophonix. We therefore match the unit system without rescaling geometry."""
    tmp = Rhino.RhinoDoc.CreateHeadless(None)
    tmp.AdjustModelUnitSystem(source_doc.ModelUnitSystem, False)
    return tmp


def export_glb(source_doc, object_ids, output_path):
    """Export the given objects as binary .glb through the RhinoCommon API (no dialog).
    Pattern: headless doc (same units as source) -> objects added with their
    display color (no material) -> FileGltf.Write -> dispose. Requires Rhino >= 8.3."""
    if not object_ids:
        return False
    tmp = _create_tmp_doc(source_doc)
    try:
        for oid in object_ids:
            obj = source_doc.Objects.FindId(oid)
            if obj is not None:
                _add_with_color(tmp, obj, _resolve_display_color(source_doc, obj))
        return Rhino.FileIO.FileGltf.Write(output_path, tmp, _gltf_options())
    finally:
        tmp.Dispose()


def export_block_def_as_glb(source_doc, block_def, output_path, color):
    """Export a block definition's geometry as binary .glb.
    Pivot = block origin in Rhino (insertion point). Every sub-object receives
    the display color `color` (the color of the source SPEAKERS::<leaf> layer,
    to stay consistent with the CSV).

    Limitation: nested InstanceReferences inside the definition are not
    resolved (their block definition is not copied into the tmp doc).
    Usually a non-issue for "flat" speaker blocks."""
    tmp = _create_tmp_doc(source_doc)
    try:
        for rh_obj in block_def.GetObjects():
            _add_with_color(tmp, rh_obj, color)
        return Rhino.FileIO.FileGltf.Write(output_path, tmp, _gltf_options())
    finally:
        tmp.Dispose()


def collect_speakers(doc, root):
    root_prefix = root + "::"
    # Conversion factor doc unit -> meters (Ruby hard-codes 0.0254 because SketchUp = inches).
    scale = Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Meters)
    speakers = []
    for obj in doc.Objects:
        if obj.ObjectType != Rhino.DocObjects.ObjectType.InstanceReference:
            continue
        layer = doc.Layers[obj.Attributes.LayerIndex]
        full_path = layer.FullPath
        if not full_path.startswith(root_prefix):
            continue
        block_def = obj.InstanceDefinition
        pt = Rhino.Geometry.Point3d.Origin
        pt.Transform(obj.InstanceXform)
        # Forward direction of the block in world coordinates (rotation only;
        # Vector3d.Transform ignores the translation part of InstanceXform).
        fwd = Rhino.Geometry.Vector3d(*FORWARD_LOCAL)
        fwd.Transform(obj.InstanceXform)
        leaf = full_path.split("::")[-1]
        speakers.append({
            "leaf": leaf,
            "model": block_def.Name,
            "obj_name": (obj.Attributes.Name or "").strip(),
            "xyz": (pt.X * scale, pt.Y * scale, pt.Z * scale),
            "forward": (fwd.X, fwd.Y, fwd.Z),
            "color": rgba_color(layer.Color),
        })
    return speakers


def assign_indices(speakers):
    speakers.sort(key=lambda s: (s["leaf"], s["xyz"][1], s["xyz"][0], s["xyz"][2]))
    groups = defaultdict(list)
    for s in speakers:
        groups[s["leaf"]].append(s)
    for leaf, grp in groups.items():
        pad = max(2, len(str(len(grp))))
        for i, s in enumerate(grp, start=1):
            s["index"] = i
            s["nn"] = str(i).zfill(pad)
    # Global 1..N index in sorted order (used for the `/speaker/N` OSC address).
    for i, s in enumerate(speakers, start=1):
        s["global_index"] = i
    return groups


def _build_name(s):
    """Speaker Name string: '<LEAF>_<OBJNAME>_<NN>' if the Rhino object has a
    Name attribute, otherwise '<LEAF>_<NN>'."""
    parts = [s["leaf"]]
    if s.get("obj_name"):
        parts.append(s["obj_name"])
    parts.append(s["nn"])
    return "_".join(parts)


def format_line(s, auto_orient_str):
    xh, yh, zh = to_holophonix(s["xyz"])
    az, el, d = polar(xh, yh, zh)
    pan, tilt = pan_tilt(to_holophonix(s["forward"]))
    osc = "/speaker/{}".format(s["global_index"])
    name = _build_name(s)
    return ";".join([
        osc, name, s["color"],
        "{:.3f}".format(xh), "{:.3f}".format(yh), "{:.3f}".format(zh),
        "{:.3f}".format(az), "{:.3f}".format(el), "{:.3f}".format(d),
        auto_orient_str,
        "{:.3f}".format(pan),
        "{:.3f}".format(tilt),
        DEFAULT_LOCK,
    ])


# ---------------------------------------------------------------------------
# OSC sync (Holophonix) — minimal UDP encoder, no external dependency.
# Spec: http://opensoundcontrol.org/spec-1_0 — address + ",<typetag>" + args,
# each padded to 4-byte boundaries. We only encode the types we need: f, i, s,
# T (true), F (false).
# ---------------------------------------------------------------------------


def _osc_string(s):
    """Encode a string in OSC format: null-terminated, padded to 4 bytes."""
    data = s.encode("utf-8") + b"\x00"
    pad = (4 - len(data) % 4) % 4
    return data + b"\x00" * pad


def _osc_message(address, typetag, *args):
    """Build a single OSC message.
    typetag: string of type codes without the leading comma (e.g. "f", "sffff").
    args: values in order; 'T' and 'F' consume no arg (the value is the type)."""
    msg = _osc_string(address) + _osc_string("," + typetag)
    ai = 0
    for t in typetag:
        if t == "f":
            msg += struct.pack(">f", float(args[ai])); ai += 1
        elif t == "i":
            msg += struct.pack(">i", int(args[ai])); ai += 1
        elif t == "s":
            msg += _osc_string(str(args[ai])); ai += 1
        elif t in ("T", "F"):
            pass   # no payload for bool types
    return msg


def send_osc_sync(host, port, speakers, auto_orient_bool):
    """Push every speaker's parameters to Holophonix over UDP/OSC.

    Speakers must already exist in Holophonix (via a prior CSV import) — OSC
    updates existing slots indexed by `/speaker/<global_index>/…`, it does not
    create new ones. Returns the number of OSC messages sent.

    `view3D/autoOrientation` is sent FIRST so Holophonix knows the mode before
    it receives numeric angles. If sent last while True, Holophonix may
    auto-recompute pan/tilt and overwrite our values.

    Angles and distance are sent as float32 (type `f`). The Holophonix OSC
    spec labels them "entier" (integer), but the server accepts floats and a
    CSV round-trip preserves the decimal values — integer rounding drifts
    positions by up to 40 cm per speaker."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sent = 0
    try:
        for s in speakers:
            idx = s["global_index"]
            xh, yh, zh = to_holophonix(s["xyz"])
            az, el, d = polar(xh, yh, zh)
            pan, tilt = pan_tilt(to_holophonix(s["forward"]))
            name = _build_name(s)
            rgba = [float(v) for v in s["color"].split(",")]
            base = "/speaker/{}".format(idx)
            messages = [
                _osc_message(base + "/view3D/autoOrientation",
                             "T" if auto_orient_bool else "F"),
                _osc_message(base + "/name", "s", name),
                _osc_message(base + "/color", "ffff", *rgba),
                _osc_message(base + "/azim", "f", az),
                _osc_message(base + "/elev", "f", el),
                _osc_message(base + "/dist", "f", d),
                _osc_message(base + "/view3D/pan", "f", pan),
                _osc_message(base + "/view3D/tilt", "f", tilt),
            ]
            for m in messages:
                sock.sendto(m, (host, port))
                sent += 1
    finally:
        sock.close()
    return sent


def _opt(name, default):
    # Tolerates both an input that is not declared on the component AND a
    # declared input that is not wired (value is None).
    v = globals().get(name, default)
    return default if v is None else v


doc = Rhino.RhinoDoc.ActiveDoc
root = _opt("layer_root", "SPEAKERS") or "SPEAKERS"
auto_orient_bool = bool(_opt("auto_orient", False))
auto_orient_str = "true" if auto_orient_bool else "false"
folder_val = _opt("folder", None)
run_val = _opt("run", False)
export_venue_val = bool(_opt("export_venue", False))
export_speakers_val = bool(_opt("export_speakers", False))
sync_val = bool(_opt("sync", False))
osc_host_val = _opt("osc_host", "127.0.0.1") or "127.0.0.1"
osc_port_val = int(_opt("osc_port", 4003))

speakers = collect_speakers(doc, root)
groups = assign_indices(speakers)

rows = [format_line(s, auto_orient_str) for s in speakers]
lines = [HEADER] + rows
count = len(rows)
log = ["{}: {}".format(leaf, len(grp)) for leaf, grp in groups.items()]

if run_val and folder_val:
    folder = os.path.expanduser(folder_val)
    os.makedirs(folder, exist_ok=True)

    # CSV
    csv_path = os.path.join(folder, CSV_NAME)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    log.append("WROTE: {}".format(csv_path))

    # VENUE .glb
    if export_venue_val:
        venue_ids = collect_objects_on_layer(doc, VENUE_ROOT)
        if venue_ids:
            venue_path = os.path.join(folder, VENUE_GLB_NAME)
            if export_glb(doc, venue_ids, venue_path):
                log.append("WROTE: {}".format(venue_path))
            else:
                log.append("FAILED venue.glb (FileGltf.Write returned False)")
        else:
            log.append("SKIP venue.glb: no geometry on '{}'".format(VENUE_ROOT))
    else:
        log.append("SKIP venue.glb (export_venue=False)")

    # SPEAKERS .glb: one file per model, containing the block definition
    # (raw geometry, pivot = block insertion point, material = layer color).
    if export_speakers_val:
        defs_by_leaf = collect_block_defs_by_leaf(doc, root)
        if defs_by_leaf:
            for leaf in sorted(defs_by_leaf):
                spk_path = os.path.join(folder, "{}.glb".format(leaf))
                block_def, color = defs_by_leaf[leaf]
                if export_block_def_as_glb(doc, block_def, spk_path, color):
                    log.append("WROTE: {}".format(spk_path))
                else:
                    log.append("FAILED {}.glb (FileGltf.Write returned False)".format(leaf))
        else:
            log.append("SKIP speakers: no blocks on '{}'".format(root))
    else:
        log.append("SKIP speakers (export_speakers=False)")

# OSC sync — independent of run/folder, triggered by its own button so you
# can push live updates without re-exporting the CSV/GLB package.
if sync_val:
    if not speakers:
        log.append("OSC SKIP: no speakers to sync")
    else:
        try:
            n = send_osc_sync(osc_host_val, osc_port_val, speakers, auto_orient_bool)
            log.append("OSC: sent {} messages to {}:{}".format(n, osc_host_val, osc_port_val))
        except Exception as e:
            log.append("OSC FAILED ({}:{}): {}".format(osc_host_val, osc_port_val, e))
