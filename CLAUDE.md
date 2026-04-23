# holophonix_export — notes pour Claude

Projet : exporter les enceintes d'une scène Rhino 8 vers un CSV compatible Holophonix Overview (import via la fenêtre Overview).

## Fichiers

- `holophonix_export.py` — script à coller dans un composant GhPython3 de Grasshopper.
- `New Preset - SPEAKER Overview.csv` — exemple d'export natif Holophonix, **référence de format**.
- `users-zak-desktop-new-preset-speaker-hashed-hummingbird.md` — plan historique, garder pour contexte.

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

Enceintes placées comme **Block Instances** sur des sous-calques de `SPEAKERS::` (ex: `SPEAKERS::MDC5`, `SPEAKERS::HOPS8`). La **couleur du calque** détermine la couleur de l'enceinte.

## Inputs du composant GhPython

| Nom          | Type | Défaut      |
|--------------|------|-------------|
| `filepath`   | str  | —           |
| `run`        | bool | —           |
| `axis_mode`  | int  | `0`         |
| `layer_root` | str  | `SPEAKERS`  |
| `auto_orient`| bool | `False`     |
| `flip_x`     | bool | `False`     |
| `flip_y`     | bool | `False`     |
| `flip_z`     | bool | `False`     |

Outputs : `lines`, `count`, `log`.

Les `flip_*` s'appliquent **après** le mapping `axis_mode` — ils inversent simplement le signe sur l'axe concerné pour gérer les conventions miroir.

## Modifs typiques

- Format couleur → `rgba_color()` seulement.
- Convention axes → `to_holophonix()` (toggle `axis_mode` : 0 Direct, 1 Rhino→Holophonix `(Y, -X, Z)`).
- Unités → déjà géré auto.

## Ne PAS faire

- Remettre `#RRGGBB` sur la couleur (rejeté par Holophonix).
- Ajouter un `\n` final.
- Passer le Name en `Speaker N` sans confirmation (l'utilisateur tient à `LAYER_NN`).
- Toucher aux offsets X/Y/Z (feature abandonnée, voir plan historique).

## Référence externe

Plugin Ruby SketchUp officiel `HOLOPHONIX_speaker_export` (Holophonix S.A.S., 2024) — source des formules AED, conventions booléennes et séparateurs. Pas dans le repo mais lu par l'utilisateur pour valider l'alignement.
