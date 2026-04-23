# Holophonix Overview export — GhPython (Rhino 8.3+, Python 3)
#
# Composant GhPython à configurer ainsi :
#   Inputs :
#     folder       (str,  Item Access) — dossier de sortie (CSV + .glb)
#     run          (bool, Item Access) — bouton, déclenche l'écriture
#     layer_root   (str,  Item Access) — préfixe de calque speakers, défaut "SPEAKERS"
#     auto_orient  (bool, Item Access) — rempli "true"/"false" dans la colonne Auto Orientation
#   Outputs :
#     lines        — liste des lignes CSV (header inclus), pour preview
#     count        — nombre d'enceintes exportées
#     log          — diagnostic (groupes + chemins écrits)
#
# Comportement : scanne tous les Block Instances dont le calque complet
# commence par "<layer_root>::", convertit le point d'insertion en mètres
# quelle que soit l'unité du document Rhino, groupe par nom de calque
# feuille, numérote NN zero-padded par groupe, convertit en polaire
# (formules alignées sur le plugin Ruby officiel Holophonix), puis si
# `run` est True écrit dans `folder` :
#   - holophonix_overview.csv    (positions + couleurs)
#   - venue.glb                  (géométrie du calque VENUE::*)
#   - <MODEL>.glb                (définition du bloc, pivot = point d'insertion ;
#                                 un fichier par sous-calque SPEAKERS::<MODEL>)
#
# Mapping d'axes figé pour le CSV : (X_h, Y_h, Z_h) = (Y_r, X_r, Z_r).
# Les GLB sont écrits via Rhino.FileIO.FileGltf.Write (API RhinoCommon,
# pas de dialogue graphique) dans un doc headless temporaire. Requiert
# Rhino >= 8.3.

import Rhino
import math
import os
from collections import defaultdict

HEADER = "OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock"

DEFAULT_PAN = "0"
DEFAULT_TILT = "0"
DEFAULT_LOCK = "false"

VENUE_ROOT = "VENUE"
CSV_NAME = "holophonix_overview.csv"
VENUE_GLB_NAME = "venue.glb"
# Les speakers sont exportés en un .glb par modèle, nommé "<leaf>.glb"
# (ex: MDC5.glb, HOPS8.glb, G18-SUB.glb).


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


def collect_objects_on_layer(doc, root):
    """Object IDs dont le layer FullPath == root OU commence par root::."""
    ids = []
    for obj in doc.Objects:
        layer = doc.Layers[obj.Attributes.LayerIndex]
        fp = layer.FullPath
        if fp == root or fp.startswith(root + "::"):
            ids.append(obj.Id)
    return ids


def collect_block_defs_by_leaf(doc, root):
    """Dict {leaf: (InstanceDefinition, layer_color)} — une définition unique
    par sous-calque de `root::`, avec la couleur du layer source pour appliquer
    un matériau cohérent dans le .glb."""
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
    """Options par défaut pour l'export glTF. Cohérentes avec le CSV (Z up)."""
    opts = Rhino.FileIO.FileGltfWriteOptions()
    opts.MapZToY = False                          # Z reste la hauteur (cf. CSV)
    opts.ExportMaterials = True
    opts.UseDisplayColorForUnsetMaterials = True  # fallback si jamais aucun mat
    opts.CullBackfaces = True
    opts.ExportLayers = False                     # GLB = asset neutre
    return opts


def _resolve_display_color(source_doc, rh_obj):
    """Couleur affichée de l'objet dans le doc source (depuis object ou layer)."""
    attrs = rh_obj.Attributes
    if attrs.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromObject:
        return attrs.ObjectColor
    return source_doc.Layers[attrs.LayerIndex].Color


def _add_with_color(tmp_doc, rh_obj, color):
    """Ajoute l'objet au doc temporaire avec sa display color explicite.

    L'exporter glTF utilise cette display color comme BaseColor PBR grâce à
    l'option `UseDisplayColorForUnsetMaterials = True` dans `_gltf_options`.
    On ne crée **aucun matériau** dans le tmp doc — contourne le bug Rhino
    RH-81973 (les `PhysicallyBasedMaterial` créés dans un `RhinoDoc.CreateHeadless`
    perdent leurs paramètres PBR à l'export glTF : BaseColor noire, Roughness 0, …)."""
    attrs = rh_obj.Attributes.Duplicate()
    attrs.ObjectColor = color
    attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
    attrs.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromLayer
    attrs.MaterialIndex = -1   # pas de matériau assigné → display color utilisée
    attrs.LayerIndex = 0       # default layer du tmp doc
    tmp_doc.Objects.Add(rh_obj.Geometry, attrs)


def _create_tmp_doc(source_doc):
    """Crée un RhinoDoc headless aligné sur l'unité du doc source.

    `CreateHeadless(None)` part en mètres par défaut. Si le source est en mm
    (cas courant pour un plan de salle), ajouter la géométrie telle quelle
    aboutit à un GLB avec des coords 1000× trop petites — objets invisibles
    dans Holophonix. On aligne donc les unités sans rescaler la géométrie."""
    tmp = Rhino.RhinoDoc.CreateHeadless(None)
    tmp.AdjustModelUnitSystem(source_doc.ModelUnitSystem, False)
    return tmp


def export_glb(source_doc, object_ids, output_path):
    """Exporte les objets passés en .glb binary via l'API RhinoCommon (sans dialogue).
    Pattern : doc headless (mêmes unités que source) → objets ajoutés avec leur
    display color (sans matériau) → FileGltf.Write → dispose. Requiert Rhino >= 8.3."""
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
    """Exporte la géométrie de la définition du bloc en .glb binary.
    Pivot = origine du bloc dans Rhino (point d'insertion). Tous les sous-objets
    reçoivent la display color `color` (celle du layer SPEAKERS::<leaf> côté
    source, pour rester cohérent avec le CSV).

    Limitation : les InstanceReferences imbriquées dans la définition ne sont
    pas résolues (leur définition n'est pas répliquée dans le tmp doc).
    Typiquement sans impact pour les blocs d'enceintes "plats"."""
    tmp = _create_tmp_doc(source_doc)
    try:
        for rh_obj in block_def.GetObjects():
            _add_with_color(tmp, rh_obj, color)
        return Rhino.FileIO.FileGltf.Write(output_path, tmp, _gltf_options())
    finally:
        tmp.Dispose()


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
folder_val = _opt("folder", None)
run_val = _opt("run", False)

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
    venue_ids = collect_objects_on_layer(doc, VENUE_ROOT)
    if venue_ids:
        venue_path = os.path.join(folder, VENUE_GLB_NAME)
        if export_glb(doc, venue_ids, venue_path):
            log.append("WROTE: {}".format(venue_path))
        else:
            log.append("FAILED venue.glb (FileGltf.Write returned False)")
    else:
        log.append("SKIP venue.glb: no geometry on '{}'".format(VENUE_ROOT))

    # SPEAKERS .glb : un fichier par modèle, contenant la définition du bloc
    # (géométrie brute, pivot = point d'insertion du bloc, matériau = couleur du layer).
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
