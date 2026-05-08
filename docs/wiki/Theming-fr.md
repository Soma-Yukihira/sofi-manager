> [🇬🇧 English](Theming) · 🇫🇷 Français

# Thèmes

Deux presets et 17 slots de couleur personnalisables. Sauvegardés par
machine dans `settings.json` à côté du fichier bots.

## Presets

| Preset | Style                              | Toggle                              |
| ------ | ---------------------------------- | ----------------------------------- |
| Dark   | Black & gold premium               | Top bar → **🌙 Sombre / ☀ Clair**   |
| Light  | White & gold chaud (fond off-white)| Même bouton                         |

Basculer un preset efface tes overrides custom pour le nouveau mode — tu
vois le preset propre. Re-personnalise à partir de là.

## Personnaliser les couleurs

Clique **🎨 Couleurs** dans la top bar. Une modale liste chaque slot avec
sa pastille couleur.

| Slot               | Où ça apparaît                                |
| ------------------ | --------------------------------------------- |
| `bg`               | Fond principal de la fenêtre                  |
| `panel`            | Cartes, sidebar, top bar                      |
| `panel_hover`      | Élément de liste survolé                      |
| `panel_selected`   | Bot sélectionné dans la sidebar               |
| `input_bg`         | Intérieur des champs de saisie                |
| `border`           | Toutes les fines bordures                     |
| `accent`           | Titres de section, bordure de bouton défaut   |
| `accent_bright`    | Bouton primaire (Démarrer)                    |
| `accent_dim`       | Scrollbars, bordure de bouton (idle)          |
| `text`             | Libellés principaux                           |
| `text_dim`         | Indications, libellés secondaires             |
| `text_on_accent`   | Texte sur le bouton primaire                  |
| `log_bg`           | Fond de la console de logs                    |
| `success`          | Dot vert, lignes de log success               |
| `error`            | Dot rouge, lignes de log error, boutons danger|
| `warn`             | Dot ambre, lignes de log warning              |
| `info`             | Lignes de log info                            |

Clique une pastille → color picker natif → choisis → l'aperçu se met à jour.
**Appliquer** sauvegarde dans `settings.json` et reconstruit l'UI sur place.

La couleur du texte de chaque pastille est calculée pour le contraste —
texte foncé sur fond clair, blanc sur fond sombre — donc tu vois toujours
la valeur hex.

## Reset

Dans la modale, **Réinitialiser** efface tous les overrides du **preset
courant**. Bascule le toggle preset si tu veux repartir des défauts de
l'autre preset.

## Où sont stockées les valeurs

```json
{
  "theme": {
    "mode": "dark",
    "overrides": {
      "accent": "#ff6b6b"
    }
  }
}
```

Supprime `settings.json` pour tout reset aux défauts d'usine.

## Conseils pour une palette custom qui tient

- **Garde `bg` et `panel` proches.** Trop de contraste entre fond et
  panneaux fait flotter les panneaux — sympa pour un dashboard, agité pour
  un long flux de logs.
- **Choisis `accent` en premier.** Tout se cale visuellement sur lui.
- **Garde `text` très contrasté avec `panel`.** Les longues sessions de
  logs comptent plus que la screenshot marketing.
- **`success` / `error` / `warn` / `info` doivent être distincts au coup
  d'œil** — c'est tout l'intérêt du code couleur des logs.
