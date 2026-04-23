# holophonix_export

Export d'une scène Rhino 8 vers un **package Holophonix** (CSV Overview + `venue.glb` + un `.glb` par modèle d'enceinte), via un composant Grasshopper GhPython3.

## Pré-requis

- **Rhino ≥ 8.3** (CPython 3 embarqué côté Grasshopper + API `Rhino.FileIO.FileGltf` utilisée pour l'export programmatique des .glb).
- Scène Rhino avec :
  - **Enceintes** — Block Instances sur des sous-calques de `SPEAKERS::*` (un sous-calque par modèle : `SPEAKERS::MDC5`, `SPEAKERS::HOPS8`, …). La couleur du calque sert de couleur d'enceinte dans le CSV.
  - **Salle** — géométrie quelconque sur le calque `VENUE` (ou `VENUE::*`). Exportée telle quelle en .glb.

## Installation

1. Ouvrir Grasshopper dans Rhino 8.
2. Poser un composant **GhPython3** (*Script → Python 3*).
3. Coller le contenu de [`holophonix_export.py`](holophonix_export.py) dans l'éditeur du composant.
4. Ajouter les inputs (clic droit sur le composant, `+`) :

   | Nom           | Type | Détail                                                           |
   |---------------|------|------------------------------------------------------------------|
   | `folder`      | str  | Panel avec le **dossier** de sortie (créé s'il manque)           |
   | `run`         | bool | **Button** (one-shot, pour ne pas écraser à chaque tick)         |
   | `layer_root`  | str  | Panel, défaut `SPEAKERS`                                         |
   | `auto_orient` | bool | Toggle, défaut `False`                                           |

5. Ajouter les outputs `lines`, `count`, `log`.

## Utilisation

1. Brancher un Panel sur `lines` pour previewer les lignes CSV.
2. Vérifier `count` (nombre d'enceintes détectées) et `log` (répartition par modèle + chemins écrits).
3. Cliquer **`run`** → fichiers produits dans `folder` :
   - `holophonix_overview.csv`
   - `venue.glb` — géométrie de la salle
   - `<MODEL>.glb` pour chaque sous-calque `SPEAKERS::<MODEL>` (ex: `MDC5.glb`, `HOPS8.glb`, `G18-SUB.glb`, …) — **un asset par modèle**, contenant seulement la définition du bloc avec son point d'insertion comme pivot. Pas les instances placées dans la scène.
4. Dans Holophonix : importer le CSV via la fenêtre **Overview**, charger `venue.glb` comme décor, et chaque `<MODEL>.glb` comme asset instancié aux positions des enceintes du CSV correspondant.

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

Mapping figé pour le **CSV** : `(X_h, Y_h, Z_h) = (Y_r, X_r, Z_r)` — permutation X ↔ Y, Z inchangé. Validé sur la scène de référence. Pour une autre convention, éditer la fonction `to_holophonix()` dans [`holophonix_export.py`](holophonix_export.py).

Les **GLB** sont exportés en coords Rhino brutes (aucune transformation pré-export). À vérifier côté Holophonix ; si la géométrie apparaît miroir par rapport aux positions CSV, il faudra ajouter une étape de transformation dans `export_glb` / `export_block_def_as_glb`.

## Limitations

- Filtrage par nom de définition de bloc non natif côté Grasshopper (RH-78812). On filtre par calque, ce qui suffit ici.
- Pas de gestion d'offset d'origine (feature volontairement abandonnée — repositionner l'origine de la scène Rhino si besoin).
- L'export GLB s'appuie sur `Rhino.FileIO.FileGltf` (depuis Rhino 8.3). Sur des versions plus anciennes, le script échouera avec une `AttributeError`.
- Les `InstanceReference` imbriquées dans une définition de bloc d'enceinte ne sont pas résolues (leur définition n'est pas répliquée dans le doc temporaire utilisé pour l'export). Typiquement sans impact pour les blocs d'enceintes "plats".

## Inspiration

Plugin Ruby SketchUp **`HOLOPHONIX_speaker_export`** (Holophonix S.A.S., 2024) — même logique AED et mêmes conventions de sérialisation (booléens string, séparateurs, absence de newline final), adapté à Rhino/Grasshopper.
