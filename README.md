# holophonix_export

Export d'une scène Rhino 8 vers un CSV au format **Holophonix Overview**, via un composant Grasshopper GhPython3.

## Pré-requis

- **Rhino 8** (CPython 3 embarqué côté Grasshopper).
- Scène contenant les enceintes posées comme **Block Instances** sur des sous-calques de `SPEAKERS::*` — un sous-calque par modèle (`SPEAKERS::MDC5`, `SPEAKERS::HOPS8`, …). La **couleur du calque** est utilisée comme couleur de l'enceinte.

## Installation

1. Ouvrir Grasshopper dans Rhino 8.
2. Poser un composant **GhPython3** (*Script → Python 3*).
3. Coller le contenu de [`holophonix_export.py`](holophonix_export.py) dans l'éditeur du composant.
4. Ajouter les inputs (clic droit sur le composant, `+`) :

   | Nom           | Type | Détail                                                           |
   |---------------|------|------------------------------------------------------------------|
   | `filepath`    | str  | Panel avec le chemin du CSV de sortie                            |
   | `run`         | bool | **Button** (one-shot, pour ne pas écraser à chaque tick)         |
   | `layer_root`  | str  | Panel, défaut `SPEAKERS`                                         |
   | `auto_orient` | bool | Toggle, défaut `False`                                           |

5. Ajouter les outputs `lines`, `count`, `log`.

## Utilisation

1. Brancher un Panel sur `lines` pour previewer les lignes CSV.
2. Vérifier `count` (nombre d'enceintes détectées) et `log` (répartition par modèle).
3. Basculer `axis_mode` pour tester les deux conventions d'axes ; retenir celle qui donne la disposition cohérente dans Holophonix.
4. Cliquer **`run`** → le CSV est écrit au chemin `filepath`.
5. Importer dans Holophonix via la **fenêtre Overview**.

## Format de sortie

```
OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
/speaker/1;MDC5_01;0.4588235294117647,0.20392156862745098,0.20392156862745098,1;1.200;-2.500;1.800;-64.358;31.128;3.431;true;0;0;false
...
```

- **OSC** : index global (`/speaker/1`, `/speaker/2`, …) dans l'ordre du tri.
- **Name** : `<modèle>_NN` zero-padded par groupe.
- **Color** : `R,G,B,A` flottants 0–1.
- **X/Y/Z** : mètres — conversion automatique depuis l'unité du document Rhino.
- Toutes les valeurs numériques à **3 décimales**.

## Conventions d'axes

Mapping figé : `(X_h, Y_h, Z_h) = (Y_r, X_r, Z_r)` — permutation X ↔ Y, Z inchangé. Validé sur la scène de référence. Pour une autre convention, éditer la fonction `to_holophonix()` dans [`holophonix_export.py`](holophonix_export.py).

## Limitations

- Filtrage par nom de définition de bloc non natif côté Grasshopper (RH-78812). On filtre par calque, ce qui suffit ici.
- Pas de gestion d'offset d'origine (feature volontairement abandonnée — repositionner l'origine de la scène Rhino si besoin).

## Inspiration

Plugin Ruby SketchUp **`HOLOPHONIX_speaker_export`** (Holophonix S.A.S., 2024) — même logique AED et mêmes conventions de sérialisation (booléens string, séparateurs, absence de newline final), adapté à Rhino/Grasshopper.
