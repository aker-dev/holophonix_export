# holophonix_export — notes pour Claude

Projet : exporter une scène Rhino 8 vers un package Holophonix — CSV Overview (positions + couleurs) + deux .glb (géométrie de la salle et blocs enceintes) à réimporter dans Holophonix.

**Prérequis** : Rhino ≥ 8.3 (pour l'API `Rhino.FileIO.FileGltf`).

## Fichiers

- `holophonix_export.py` — script à coller dans un composant GhPython3 de Grasshopper.
- `New Preset - SPEAKER Overview.csv` — exemple d'export natif Holophonix, **référence de format**.
- `docs/plan-initial.md` — plan historique, garder pour contexte.

## Format cible (verrouillé)

Header :
```
OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
```

Conventions :
- **OSC** : `/speaker/N` — index global dans l'ordre du tri.
- **Name** : `LAYER_NN` zero-padded par groupe de modèle (ex: `MDC5_01`, `HOPS8_02`).
- **Color** : `R,G,B,A` flottants 0-1 pleine précision, séparés par `,` (attention : virgules DANS un champ `;`-séparé — c'est le format natif Holophonix).
- **X/Y/Z** : mètres, 3 décimales (conversion auto depuis l'unité du doc via `Rhino.RhinoMath.UnitScale`).
- **Azim/Elev/Dist** : degrés/mètres, 3 décimales. Formule Elev : `atan2(z, sqrt(x²+y²))` (plus robuste qu'`asin`, aligné plugin Ruby officiel).
- **Booléens** : `true` / `false` en string (pas `0`/`1`).
- **Pas de `\n` final** dans le fichier.

## Scène Rhino attendue

- **Enceintes** : Block Instances sur des sous-calques de `SPEAKERS::` (ex: `SPEAKERS::MDC5`, `SPEAKERS::HOPS8`). Couleur du calque = couleur de l'enceinte dans le CSV.
- **Venue** : toute géométrie sur le calque `VENUE` (ou sous-calques `VENUE::*`). Exportée telle quelle dans `venue.glb`.

## Inputs du composant GhPython

| Nom          | Type | Défaut      |
|--------------|------|-------------|
| `folder`     | str  | —           |
| `run`        | bool | —           |
| `layer_root` | str  | `SPEAKERS`  |
| `auto_orient`| bool | `False`     |

Outputs : `lines`, `count`, `log`.

Fichiers produits dans `folder` (créé s'il manque) :
- `holophonix_overview.csv` — positions + couleurs au format Holophonix Overview.
- `venue.glb` — géométrie du calque `VENUE` (constante `VENUE_ROOT` en tête de script).
- `<MODEL>.glb` — **un fichier par sous-calque** `SPEAKERS::<MODEL>` (ex: `MDC5.glb`). Contient **la définition du bloc uniquement** (pas les instances placées dans la scène), avec le **point d'insertion du bloc comme pivot / origine**. Holophonix se charge d'instancier le modèle aux positions du CSV.

**Mapping d'axes figé (CSV uniquement)** : `(X_h, Y_h, Z_h) = (Y_r, X_r, Z_r)` — permutation X ↔ Y, Z inchangé. Les **GLB sont exportés en coords Rhino brutes** (à valider côté Holophonix ; si miroir, il faudra transformer la géométrie avant export).

## Modifs typiques

- Format couleur → `rgba_color()` seulement.
- Convention axes CSV → éditer `to_holophonix()` directement (mapping figé, pas de runtime).
- Unités → déjà géré auto.
- Calque VENUE → constante `VENUE_ROOT` en tête de script.
- Noms de fichiers de sortie → constantes `CSV_NAME`, `VENUE_GLB_NAME`. Les .glb par modèle sont nommés `<leaf>.glb` (si besoin de préfixer, modifier directement la boucle de main).
- Options glTF → fonction `_gltf_options()` en un seul endroit (MapZToY, ExportMaterials, UseDisplayColorForUnsetMaterials, CullBackfaces, ExportLayers).
- Export GLB → via l'API **`Rhino.FileIO.FileGltf.Write(path, tmp_doc, options)`** (zéro dialogue, zéro setup utilisateur). Pattern : `Rhino.RhinoDoc.CreateHeadless(None)` → `_add_with_material` (qui crée un matériau PBR par objet et l'assigne explicitement) → `FileGltf.Write` → `tmp.Dispose()`. Utilisé pour le venue (`export_glb`) et par modèle (`export_block_def_as_glb`, flatten via `InstanceDefinition.GetObjects()`).
- **Matériaux via display color** (fonction `_add_with_color`) : on ne crée **aucun** `Material` ni `RenderMaterial` dans le tmp doc. On pose `ObjectColor = <couleur>` + `ColorSource = ColorFromObject` sur les attributs, `MaterialIndex = -1`, puis `tmp_doc.Objects.Add(geom, attrs)`. L'option `UseDisplayColorForUnsetMaterials = True` de `_gltf_options()` fait que l'exporter glTF utilise cette display color comme BaseColor PBR (documenté par McNeel : *"Objects using the default material export with their display colors as material colors"*).
- **Ne PAS créer de matériau PBR dans le tmp doc** : bug Rhino **RH-81973** — les `PhysicallyBasedMaterial` créés dans un `RhinoDoc.CreateHeadless(None)` perdent leurs paramètres (BaseColor, Roughness, Clearcoat…) à l'export glTF. Symptôme : GLB avec matériaux tout noirs. Ref : https://discourse.mcneel.com/t/physically-based-material-in-headless-doc/182696. Si un jour on veut ajouter métallique/roughness/texture, il faudra soit attendre la fix du bug, soit changer l'architecture (plus de tmp headless).
- La couleur passée à `_add_with_color` vient de `_resolve_display_color` côté venue (par objet) ou de `collect_block_defs_by_leaf` côté speakers (couleur du layer `SPEAKERS::<leaf>`, retourné avec la `InstanceDefinition` dans le tuple `{leaf: (def, color)}`).
- **Ne jamais revenir** à `RhinoApp.RunScript("_-Export …")` : sur macOS ça ouvre un dialogue bloquant qui ne peut être supprimé que par un setup manuel non-distribuable.
- Speakers GLB : toujours exporter la **définition** (asset neutre), pas les instances placées dans la scène — Holophonix instancie côté CSV.

## Ne PAS faire

- Remettre `#RRGGBB` sur la couleur (rejeté par Holophonix).
- Ajouter un `\n` final.
- Passer le Name en `Speaker N` sans confirmation (l'utilisateur tient à `LAYER_NN`).
- Toucher aux offsets X/Y/Z (feature abandonnée, voir plan historique).

## Référence externe

Plugin Ruby SketchUp officiel `HOLOPHONIX_speaker_export` (Holophonix S.A.S., 2024) — source des formules AED, conventions booléennes et séparateurs. Pas dans le repo mais lu par l'utilisateur pour valider l'alignement.
