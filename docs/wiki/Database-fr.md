> [🇬🇧 English](Database) · 🇫🇷 Français

# Base de données

Selfbot Manager stocke chaque tentative de grab dans un fichier
SQLite local — `grabs.db`. Cette page couvre où il vit, ce qu'il
contient, et comment l'inspecter depuis l'extérieur.

Pour le dashboard intégré, voir [Stats](Stats-fr).

## Emplacement

Résolu par `paths.user_dir()`, la même racine que `bots.json` /
`settings.json`. Soit :

- **Install source** — racine du repo, à côté de `gui.py`.
- **`.exe` gelé** — le dossier contenant l'exécutable.

### Override avec `SOFI_DB_PATH`

Définis la variable d'environnement à un chemin absolu pour relocaliser
la base. Utile sur un VPS pour mettre la DB sur un autre volume, ou
pour lancer plusieurs instances contre des bases séparées.

```bash
# POSIX
export SOFI_DB_PATH=/var/lib/sofi/grabs.db
# Windows (PowerShell)
$env:SOFI_DB_PATH = "D:\sofi\grabs.db"
```

Le dossier parent est créé à la demande. Les chemins relatifs et
préfixés par `~` sont étendus.

### Emplacements legacy (pré-PR-30)

Les anciennes versions gardaient la DB sous le dossier de données
utilisateur :

- Windows : `%APPDATA%\sofi-manager\grabs.db`
- POSIX : `$XDG_DATA_HOME/sofi-manager/grabs.db`
  (fallback `~/.local/share/sofi-manager/grabs.db`)

Au premier lancement après mise à jour, la GUI exécute une migration
one-shot : le fichier legacy (plus ses sidecars `-wal` / `-shm`) est
déplacé vers le nouvel emplacement et un bandeau doré annonce *"Base
de données déplacée vers le dossier projet. Vos statistiques sont
préservées."* La migration est un no-op si le fichier legacy est
absent, si la cible existe déjà, ou si `SOFI_DB_PATH` pointe
justement vers le chemin legacy.

## Schéma

Une seule table `grabs` :

| Colonne       | Type     | Notes                                                                  |
| ------------- | -------- | ---------------------------------------------------------------------- |
| `id`          | INTEGER  | Clé primaire, autoincrement.                                           |
| `ts`          | INTEGER  | Epoch Unix en secondes. Non null.                                      |
| `bot_label`   | TEXT     | Le champ *Nom* du bot au moment du grab. Non null.                     |
| `channel_id`  | INTEGER  | ID du salon Discord où le drop a eu lieu. Nullable.                    |
| `card_name`   | TEXT     | Titre de la carte tel que parsé depuis SOFI. Nullable.                 |
| `series`      | TEXT     | Série de la carte. Nullable.                                           |
| `rarity`      | TEXT     | Libellé de rareté (ex. `SR`, `UR`). Nullable.                          |
| `hearts`      | INTEGER  | Nombre de hearts quand connu. Nullable.                                |
| `score`       | REAL     | Score interne dans `[0, 1]`. Nullable.                                 |
| `success`     | INTEGER  | `1` si le clic est passé, `0` sinon. Non null.                         |
| `error_code`  | TEXT     | Tag court en cas d'échec (ex. `BUTTON_TIMEOUT`). Nullable.             |

Deux indices : `(ts)` et `(bot_label, ts)` — ils gardent le graphique
journalier et le filtre par bot réactifs sur de longs historiques.

Les lignes `success` conservent `card_name` / `series` / `rarity`
quand le parse a réussi ; les lignes `success=0` n'ont généralement
que `error_code` rempli.

## Mode WAL

`init_db` lance `PRAGMA journal_mode=WAL` au démarrage. C'est pour
ça que l'onglet Stats peut lire pendant qu'un grab insère, et que tu
peux ouvrir la DB depuis un CLI `sqlite3` sans bloquer le bot.

Le mode WAL laisse deux sidecars à côté de la DB :

- `grabs.db-wal` — écritures en attente de checkpoint.
- `grabs.db-shm` — index en mémoire partagée.

Les deux sont gitignorés à côté de `grabs.db` et peuvent être
supprimés en toute sécurité quand aucun process n'a la DB ouverte.
SQLite les recrée à la prochaine ouverture.

> [!WARNING]
> Le mode WAL ne fonctionne pas bien sur les partages réseau (SMB,
> NFS, OneDrive, Dropbox, Google Drive). Les sémantiques de verrou
> cassent et tu peux perdre des écritures ou corrompre le fichier.
> Garde `grabs.db` sur un disque local, ou fais pointer `SOFI_DB_PATH`
> vers un disque local.

## Inspection depuis le CLI

Le schéma est assez simple pour répondre à la plupart des questions
avec un shell `sqlite3`.

```bash
sqlite3 grabs.db
```

Requêtes utiles :

```sql
-- Combien de grabs au total, et quel taux de succès ?
SELECT COUNT(*) AS total,
       SUM(success) AS hits,
       ROUND(100.0 * SUM(success) / COUNT(*), 1) AS pct
FROM grabs;

-- Taux de succès par bot, plus actifs d'abord.
SELECT bot_label,
       COUNT(*) AS total,
       SUM(success) AS hits,
       ROUND(100.0 * SUM(success) / COUNT(*), 1) AS pct
FROM grabs
GROUP BY bot_label
ORDER BY total DESC;

-- Codes d'erreur les plus fréquents.
SELECT error_code, COUNT(*) AS n
FROM grabs
WHERE success = 0 AND error_code IS NOT NULL
GROUP BY error_code
ORDER BY n DESC;

-- Dernières 24h pour un bot donné, plus récent d'abord.
SELECT datetime(ts, 'unixepoch', 'localtime') AS quand_local,
       success, card_name, series, rarity, hearts, error_code
FROM grabs
WHERE bot_label = 'main'
  AND ts >= strftime('%s', 'now', '-1 day')
ORDER BY ts DESC;
```

Ouvre la DB en **lecture seule** si le bot tourne et que tu veux juste
jeter un œil :

```bash
sqlite3 "file:grabs.db?mode=ro" -cmd ".uri on"
```

## Sauvegarde

`grabs.db` est gitignoré, donc rien dans le flux de mise à jour n'y
touche. Sauvegarde-le comme n'importe quel SQLite :

1. GUI **fermée** : copie simplement `grabs.db`. (Si le sidecar
   `-wal` est présent et non vide, copie-le aussi.)
2. GUI **en cours** : utilise l'API SQLite online backup ou lance
   `VACUUM INTO 'snapshot.db';` depuis un shell `sqlite3` — les deux
   produisent un snapshot cohérent sans arrêter le bot.

## Suite

- [Stats](Stats-fr) — le dashboard qui lit cette DB.
- [Architecture](Architecture-fr) — comment `storage.py` s'intègre
  dans le reste du projet.
