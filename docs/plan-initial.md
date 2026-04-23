# Plan — Définition Grasshopper : export enceintes Rhino → CSV Holophonix

## Contexte

Le projet contient une scène Rhino où chaque enceinte est placée comme une **instance de bloc** (CS7P, G18-SUB, HOPS5, HOPS8, MAUI28G2, MDC5) sur un sous-calque dédié de `SPEAKERS::*`. Chaque sous-calque a une couleur identifiant le type d'enceinte.

On veut générer un CSV au format **Holophonix Overview** :

```
OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
```

Décisions confirmées :
- **Plugin** : composants natifs Rhino 8 uniquement (pas d'Elefront/Human).
- **OSC Address** : `/track/[LAYER]/N` (numérotation par type, ex: `/track/MDC5/1`).
- **Axes** : inclure un toggle pour basculer entre deux conventions (scène Rhino ↔ Holophonix).
- **Nom** : `[Modèle]_NN` zero-padded (ex: `MDC5_01`, `MDC5_02`).

## Vue d'ensemble du flux GH

```
Query Model Objects   ──►  Deconstruct Block Instance ──►  Insertion Point
      │  (filtre                  │
      │   Layer: SPEAKERS::*)     └──►  Block Definition ──► Nom modèle (MDC5, HOPS8…)
      │
      ├──►  Model Object Attributes ──►  Layer ──► Model Layer ──►  Display Color
      │                                                         └──►  Layer Name (leaf)
      │
      └──►  (Group by layer) ──► Incrément par groupe ──► Index NN
                                                 │
                                                 ▼
                                    Cartesian → Polar (Azim/Elev/Dist)
                                                 │
                                                 ▼
                                    Format CSV (Concatenate / Python) ──►  Write File
```

## Structure détaillée

### 1. Requête des enceintes

- **Composant** : `Query Model Objects` (onglet Rhino)
  - Filtre d'entrée : `Content Filter` avec type `Block Instance` et `Layer` contenant `SPEAKERS::` (ou un panel listant chaque sous-calque s'il faut être explicite).
  - Sortie utilisée : branche **Block Instances** (clic droit → *Show All Params*).

Limitation connue : filtrer par *nom de définition de bloc* n'est pas natif (RH-78812). Ce n'est pas bloquant ici puisqu'on filtre par calque ; on lira le nom du bloc via `Deconstruct Block Instance` en aval.

### 2. Extraction position + modèle

- **Composant** : `Deconstruct Block Instance`
  - Entrée : les block instances filtrés.
  - Sorties : **Transform** + **Block Definition**.
- **Transform → Point** : `Transform Point` avec l'origine `(0,0,0)` comme entrée → donne le **point d'insertion** de chaque bloc.
- **Block Definition → Name** : `Deconstruct Block Definition` → sortie **Name** (ex: `MDC5`).

### 3. Extraction calque + couleur

- `Model Object Attributes` sur les block instances → sortie **Layer** (chemin complet `SPEAKERS::MDC5`).
- `Deconstruct Model Layer` (ou `Model Layer` + path) → sortie **Display Color** (couleur du calque) + **Full Path** / **Name**.
- Nom de feuille (`MDC5`) : *Text Split* sur `::` → dernier élément (sert aussi pour l'OSC Address et le nommage).

### 4. Numérotation par type

- `Group` (native *Group Data*) par nom de calque leaf.
- Dans chaque groupe : `Series` (Start=1, Count=group size) → `Format` avec `{0:00}` pour le zero-padding → index `NN`.
- Remettre à plat avec `Flatten Tree` en conservant l'ordre de groupe.

### 5. Conversion coordonnées + toggle axes

- **Toggle** : `Value List` avec deux entrées — `Direct` et `Rhino→Holophonix`.
- Un composant `Expression` (natif) ou deux petites branches avec `Deconstruct Point`/`Construct Point` remappe :
  - **Direct** : `(Xh, Yh, Zh) = (Xr, Yr, Zr)`
  - **Rhino→Holophonix** : mapping à valider empiriquement (hypothèse standard audio : `Xh = Yr`, `Yh = -Xr`, `Zh = Zr` — devant/gauche/haut). Le toggle permet de tester les deux et retenir la bonne après vérification dans Holophonix.
- **Polar (Azim, Elev, Dist)** — `Expression` ou 3 composants math :
  - `Dist = Sqrt(Xh² + Yh² + Zh²)`
  - `Azim = Degrees( Atan2(Yh, Xh) )`
  - `Elev = Degrees( Asin(Zh / Dist) )` (avec garde si `Dist == 0`)

### 6. Format couleur

- `Deconstruct Color` → R, G, B (0–255).
- `Expression` / `Concatenate` → hex `#RRGGBB` (par défaut).
- À valider : si Holophonix attend un autre format (`R,G,B` décimal, nom, etc.), changer uniquement cette étape. Exporter un CSV test depuis Holophonix avec une enceinte placée manuellement permettra de confirmer.

### 7. Construction des lignes CSV

- Colonnes figées à valeurs par défaut (à ajuster selon besoin) :
  - `Auto Orientation` = `0` (ou `false`)
  - `Pan`, `Tilt` = `0`
  - `Lock` = `0` (ou `false`)
- `Concatenate` avec séparateur `;` dans l'ordre exact du header :
  ```
  /track/<LAYER>/<N>;<LAYER>_<NN>;<#RRGGBB>;<X>;<Y>;<Z>;<Azim>;<Elev>;<Dist>;0;0;0;0
  ```
- Préfixer la première ligne avec le header exact de la cible :
  ```
  OSC Address;Name;Color;X;Y;Z;Azim;Elev;Dist;Auto Orientation;Pan;Tilt;Lock
  ```
- `Merge` header + lignes.

### 8. Écriture du fichier

- Composant natif **`Write File`** (onglet *Sets → Text*) :
  - `File` : chemin de sortie (ex: `/Users/zak/Desktop/holophonix_export.csv`).
  - `Content` : liste des lignes.
  - `Append` : `false`.
- Ajouter un **Button** (`Button` natif) pour déclencher l'écriture uniquement à la demande et éviter l'écrasement à chaque modif GH.

## Fichiers / livrables

- **Définition Grasshopper** (.gh) à créer par l'utilisateur selon le schéma ci-dessus. Pas de code dans le repo `momesu_migration` (sujet non lié).
- Optionnel : un court composant **GhPython** pour remplacer les étapes 4–7 si le câblage natif devient trop encombrant (moins de fils, plus maintenable pour toi). Je peux fournir ce script si souhaité — il reste compatible Rhino 8 natif (IronPython/Python3 embarqué).

## Points à valider après un premier export

1. **Format couleur** accepté par Holophonix (`#RRGGBB` vs `R,G,B` vs autre) → exporter un CSV de référence depuis Holophonix.
2. **Convention d'axes** correcte → basculer le toggle si les enceintes apparaissent mal orientées dans la vue Holophonix.
3. **Signe des angles** `Azim`/`Elev` (sens horaire vs trigonométrique, plage `[-180,180]` vs `[0,360]`).
4. **Valeurs par défaut** pour `Auto Orientation`, `Pan`, `Tilt`, `Lock` (booléens `0/1` vs `true/false`).

## Vérification end-to-end

1. Ouvrir la scène Rhino avec les enceintes en place.
2. Charger la définition GH, confirmer :
   - Le nombre de lignes CSV = nombre de blocs sur les sous-calques `SPEAKERS::*`.
   - Les noms suivent bien `MODEL_NN`.
   - Les OSC addresses suivent `/track/MODEL/N`.
3. Cliquer le Button → fichier CSV écrit.
4. Ouvrir le CSV dans un éditeur texte → vérifier séparateur `;` et header identique.
5. Importer dans Holophonix via l'Overview window.
6. Comparer visuellement la disposition dans Holophonix vs Rhino (top view) — ajuster le toggle d'axes si besoin.
7. Si couleurs incorrectes : exporter depuis Holophonix un CSV référence, diff du format, ajuster l'étape 6.
