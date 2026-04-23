# Holophonix Overview export — GhPython (Rhino 8, Python 3)
#
# Composant GhPython à configurer ainsi :
#   Inputs :
#     filepath     (str,  Item Access) — chemin du CSV de sortie
#     run          (bool, Item Access) — bouton, déclenche l'écriture
#     layer_root   (str,  Item Access) — préfixe de calque, défaut "SPEAKERS"
#     auto_orient  (bool, Item Access) — rempli "true"/"false" dans la colonne Auto Orientation
#   Outputs :
#     lines        — liste des lignes CSV (header inclus), pour preview
#     count        — nombre d'enceintes exportées
#     log          — diagnostic (un item par groupe de modèle)
#
# Comportement : scanne tous les Block Instances dont le calque complet
# commence par "<layer_root>::", convertit le point d'insertion en mètres
# quelle que soit l'unité du document Rhino, groupe par nom de calque
# feuille, numérote NN zero-padded par groupe, convertit en polaire
# (formules alignées sur le plugin Ruby officiel Holophonix), écrit le
# CSV si `run` est True.
#
# Mapping d'axes figé : (X_h, Y_h, Z_h) = (Y_r, X_r, Z_r) — validé sur
# la scène de référence. Pour une autre convention, éditer to_holophonix.

import Rhino
import math
import os
from collections import defaultdict

HEADER = "OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock"

DEFAULT_PAN = "0"
DEFAULT_TILT = "0"
DEFAULT_LOCK = "false"


def to_holophonix(xyz):
    # Mapping figé Rhino → Holophonix : permutation X ↔ Y, Z inchangé.
    x, y, z = xyz
    return y, x, z


def polar(xh, yh, zh):
    d = math.sqrt(xh * xh + yh * yh + zh * zh)
    if d == 0.0:
        return 0.0, 0.0, 0.0
    az = math.degrees(math.atan2(yh, xh))
    el = math.degrees(math.atan2(zh, math.sqrt(xh * xh + yh * yh)))
    return az, el, d


def rgba_color(c):
    # Format Holophonix: R,G,B,A en flottants 0-1, pleine précision.
    # Entiers (0, 1) rendus sans décimales pour coller à l'export natif.
    def fmt(v):
        iv = int(v)
        return str(iv) if v == iv else repr(v)
    return ",".join(fmt(x / 255.0) for x in (c.R, c.G, c.B, c.A))


def collect_speakers(doc, root):
    root_prefix = root + "::"
    # Facteur de conversion unité-du-doc → mètres (Ruby = 0.0254 en dur car SketchUp=pouces).
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
        leaf = full_path.split("::")[-1]
        speakers.append({
            "leaf": leaf,
            "model": block_def.Name,
            "xyz": (pt.X * scale, pt.Y * scale, pt.Z * scale),
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
    # Index global 1..N dans l'ordre trié (utilisé pour l'OSC `/speaker/N`).
    for i, s in enumerate(speakers, start=1):
        s["global_index"] = i
    return groups


def format_line(s, auto_orient_str):
    xh, yh, zh = to_holophonix(s["xyz"])
    az, el, d = polar(xh, yh, zh)
    osc = "/speaker/{}".format(s["global_index"])
    name = "{}_{}".format(s["leaf"], s["nn"])
    return ";".join([
        osc, name, s["color"],
        "{:.3f}".format(xh), "{:.3f}".format(yh), "{:.3f}".format(zh),
        "{:.3f}".format(az), "{:.3f}".format(el), "{:.3f}".format(d),
        auto_orient_str, DEFAULT_PAN, DEFAULT_TILT, DEFAULT_LOCK,
    ])


def _opt(name, default):
    # Tolère l'input non déclaré sur le composant ET l'input déclaré mais non branché (None).
    v = globals().get(name, default)
    return default if v is None else v


doc = Rhino.RhinoDoc.ActiveDoc
root = _opt("layer_root", "SPEAKERS") or "SPEAKERS"
auto_orient_str = "true" if _opt("auto_orient", False) else "false"
filepath_val = _opt("filepath", None)
run_val = _opt("run", False)

speakers = collect_speakers(doc, root)
groups = assign_indices(speakers)

rows = [format_line(s, auto_orient_str) for s in speakers]
lines = [HEADER] + rows
count = len(rows)
log = ["{}: {}".format(leaf, len(grp)) for leaf, grp in groups.items()]

if run_val and filepath_val:
    out = os.path.expanduser(filepath_val)
    with open(out, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines))
    log.append("WROTE: {}".format(out))
