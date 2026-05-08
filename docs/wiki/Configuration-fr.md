> [🇬🇧 English](Configuration) · 🇫🇷 Français

# Configuration

Chaque champ de l'onglet **Configuration**, dans l'ordre.

## Identité

| Champ      | Ce qu'il fait                                                  |
| ---------- | -------------------------------------------------------------- |
| **Nom**    | Libellé libre affiché dans la sidebar. Aucun effet métier.     |
| **Token**  | Ton token Discord. Stocké en local dans `bots.json`. Masqué.   |

## Channels

| Champ                  | Ce qu'il fait                                                                                                              |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **ID du salon de drop**| Où le bot envoie `sd`. Clic droit sur un salon Discord → *Copier l'identifiant du salon*.                                  |
| **Salons écoutés**     | Un ID par ligne. Les messages SOFI dans ces salons sont traités. Le drop channel y est inclus automatiquement.             |
| **Commande envoyée**   | Le texte droppé à chaque cycle. Défaut : `sd`.                                                                             |

## Timing des drops

Le bot dort une durée aléatoire dans `[interval_min, interval_max]` entre
deux drops. Mets toujours un range — un intervalle fixe est le plus simple
à détecter.

| Champ                | Unité | Défaut sensé | Ce qu'il fait                                                  |
| -------------------- | ----- | ------------ | -------------------------------------------------------------- |
| Intervalle min       | s     | 510 (8m30s)  | Borne basse du sommeil entre deux `sd`.                        |
| Intervalle max       | s     | 600 (10m)    | Borne haute.                                                   |
| Cooldown extra min   | s     | 30           | Délai aléatoire ajouté au cooldown annoncé par SOFI.           |
| Cooldown extra max   | s     | 145          | Borne haute de ce délai extra.                                 |

## Pause nocturne

Chaque jour, le bot choisit un début aléatoire entre `22:00` et `01:00`,
puis dort une durée aléatoire.

| Champ                  | Unité  | Défaut sensé |
| ---------------------- | ------ | ------------ |
| Activer pause nocturne | bool   | on           |
| Durée min              | heures | 6.5          |
| Durée max              | heures | 9.0          |

## Scoring

Chaque carte reçoit un score dans `[0, 1]`. Le bot prend le plus élevé,
**sauf** si un match wishlist est suffisamment bon — voir *Override
wishlist* ci-dessous.

```
score = poids_rareté · max(0, 1 − G/RARITY_NORM)
      + poids_hearts · min(1, hearts/HEARTS_NORM)
```

| Champ                            | Range  | Défaut | Effet                                                                |
| -------------------------------- | ------ | ------ | -------------------------------------------------------------------- |
| Poids rareté                     | 0–1    | 0.30   | Plus haut = préférer les G bas.                                      |
| Poids hearts                     | 0–1    | 0.70   | Plus haut = préférer les cartes populaires.                          |
| Norm rareté                      | int    | 2000   | Valeur G considérée "commune".                                       |
| Norm hearts                      | int    | 500    | hearts considérés "très populaires".                                 |
| Seuil override wishlist          | float  | 1.40   | Si meilleur score non-wishlist ≥ score wishlist × ce seuil, prends-le. |

> Les poids doivent totaliser 1.0.

### Override wishlist — comment ça marche

Si une carte wishlist est dans le drop, elle gagne en général. Mais si une
carte non-wishlist score **40%+ plus haut**, le bot la prend à la place.
Baisse le seuil pour favoriser plus la wishlist, monte-le pour favoriser
le score.

## Onglet Wishlist

Deux zones de texte, une entrée par ligne.

- **Personnages** — comparé au nom de la carte, substring insensible à la casse.
- **Séries** — comparé à la série de la carte, mêmes règles.

À la sauvegarde, les deux listes sont **dédoublonnées** (insensible à la
casse) et **triées alphabétiquement**. Les doublons avec casse différente
fusionnent vers la première casse vue.

## Onglet Logs

Console en direct du bot sélectionné. Code couleur :

- **or** — événements système (start, stop, drop détecté, save).
- **vert** — succès (login, click).
- **ambre** — warnings (cooldown remplacé, drop loop annulé).
- **rouge** — erreurs.
- **gris** — info (drop envoyé, intervalles, chaque message SOFI reçu).

Les lignes `📥 SOFI:` affichent chaque message SOFI vu dans les salons
écoutés. Utile pour diagnostiquer un drop raté.
