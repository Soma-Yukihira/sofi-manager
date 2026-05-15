> [🇬🇧 English](Stats) · 🇫🇷 Français

# Statistiques

L'onglet **Stats** est un dashboard lecture seule sur `grabs.db`. Chaque
tentative du bot — succès ou échec — est enregistrée par
`storage.record_grab` ; cet onglet est la façon de regarder.

Pour l'emplacement et la structure de la base, voir
[Base de données](Database-fr).

## Barre supérieure

| Contrôle         | Ce qu'il fait                                                                            |
| ---------------- | ---------------------------------------------------------------------------------------- |
| **Filtre bot**   | Dropdown de chaque `bot_label` vu en base. *Tous les bots* agrège tout.                  |
| **↻ Refresh**    | Relit la DB et reconstruit chaque panneau. L'onglet se rafraîchit aussi après un grab.   |
| **↓ CSV**        | Exporte les grabs filtrés courants dans un CSV (voir *Export* plus bas).                 |

## Cartes KPI

Quatre cartes compactes en haut, recalculées depuis le set filtré :

- **TOTAL GRABS** — chaque tentative, succès ou échec.
- **SUCCESS RATE** — `succès / total`, en pourcentage.
- **TOP 3 SÉRIES** — les trois séries les plus grab (succès uniquement).
- **TOP 3 RARETÉS** — les trois raretés les plus grab (succès uniquement).

Les deux cartes TOP ignorent les échecs : un grab raté n'a ni série
ni rareté à compter.

## Graphique journalier

Bar chart 14 jours du nombre de grabs (`GRABS / JOUR — 14 DERNIERS
JOURS`). Axe x au format `jj/mm` en heure locale. Les jours vides
rendent des barres à zéro, jamais des trous.

**Clique sur une barre** pour ouvrir le drill-down du jour :

- En-tête : `GRABS DU <date> · <scope du filtre bot>`
- Ligne résumé : `<N> tentatives — <S> succès, <F> échecs`
- Tableau de chaque grab du jour, plus récent d'abord :
  - Lignes succès : timestamp (HH:MM:SS), ✓, bot label, nom de carte, série, rareté, hearts
  - Lignes échec : timestamp (HH:MM:SS), ✗, bot label, code erreur

Le filtre bot de la barre du haut s'applique — cliquer un jour avec
*"Tous les bots"* sélectionné montre les grabs de tous les bots.

## Export

Le bouton **↓ CSV** écrit chaque grab matchant le filtre courant dans
un fichier nommé `sofi-grabs-YYYYMMDD-HHMMSS.csv` dans un dossier que
tu choisis.

- Encodage : **UTF-8 avec BOM** pour qu'Excel ouvre sans corrompre les
  noms de carte accentués.
- Ligne d'en-tête incluse. L'ordre des colonnes est pensé pour la
  lecture en tableur : `ts, iso_ts, bot_label, channel_id, card_name,
  series, rarity, hearts, score, success, error_code`.
- `iso_ts` est la forme lisible de `ts` (heure locale, précision
  seconde) ; les deux sont inclus pour trier numériquement et lire
  visuellement.

La barre de statut affiche `<N> grabs exportés` en cas de succès.

## États vides / erreur

- **Pas encore de DB** — les panneaux affichent `aucune donnée`
  jusqu'au premier grab.
- **DB verrouillée ou illisible** — la GUI remonte `Erreur DB` et
  garde l'ancien contenu. La DB est ouverte en mode WAL donc un grab
  qui insère pendant que tu lis est normal et ne déclenche pas ce cas.
- **L'export CSV échoue** — généralement un problème de permission
  sur le dossier cible. Choisis un autre emplacement.

## Suite

- [Base de données](Database-fr) — emplacement, schéma, override
  `SOFI_DB_PATH`, inspection sqlite3.
- [Configuration](Configuration-fr) — les autres onglets.
