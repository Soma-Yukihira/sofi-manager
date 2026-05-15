> [🇬🇧 English](Troubleshooting) · 🇫🇷 Français

# Dépannage

L'outil le plus utile quand ça casse : les lignes **`📥 SOFI:`** dans les
logs. Elles montrent ce que SOFI a réellement envoyé dans le salon que le
bot écoute. La plupart des "le bot ne réagit pas" sont visibles là.

---

## Installation

### `python: command not found` / `'python' is not recognized`

Python n'est pas dans le PATH. Réinstalle en cochant *"Add Python to PATH"*,
ou appelle-le explicitement : `C:\Chemin\Vers\Python\python.exe`.

### `ModuleNotFoundError: No module named 'discord'`

Le venv n'est pas activé, ou `pip install -r requirements.txt` n'a pas été
lancé dedans. Réactive (`.\env\Scripts\activate`) et réinstalle.

### `ModuleNotFoundError: No module named 'customtkinter'`

Même cause. `pip install -r requirements.txt` dans le venv actif.

---

## Authentification

### `Token invalide`

Le token est vide, expiré, ou collé avec des espaces parasites. Re-récupère-le
(voir [Installation › Récupérer un token](Installation-fr#récupérer-un-token))
et recolle.

### Compte verrouillé / demande 2FA

Discord peut flag un nouveau login depuis l'IP du selfbot. Connecte-toi une
fois depuis un navigateur sur la même machine, valide la 2FA, puis ré-essaie.

---

## Détection de drop

### "Drop envoyé" s'affiche mais rien après

Vérifie qu'une ligne `📥 SOFI:` suit. Si absente, SOFI n'a pas répondu (rare)
ou le message n'était pas dans un salon écouté. Vérifie le champ **Salons
écoutés** dans l'onglet Configuration.

Si `📥 SOFI:` est présente mais pas de `🎴 Drop détecté` ensuite : le
message n'a pas matché `_DROP_TRIGGER_RE`. Ouvre une issue avec la ligne
`📥 SOFI:` — il faudra peut-être étendre le regex pour un nouveau format
SOFI.

### `Drop ignoré (pas le tien)`

Un autre utilisateur a droppé dans le même salon. Comportement attendu.

### `Aucune carte parsée`

Le format de drop a changé. La ligne `📥 SOFI:` au-dessus montre ce qui est
arrivé — colle-la dans une issue.

### `Boutons toujours disabled`

Le bot a attendu 10× 0.5s pour que les boutons s'activent mais ça n'est
jamais arrivé. Rare, généralement un hoquet Discord. Le drop est perdu
pour ce cycle. Si c'est chronique, augmente le nombre de retries dans
[`bot_core.py`](../../blob/main/sofi_manager/bot_core.py) (`for attempt in range(10)`).

---

## Mises à jour

L'updater auto reste silencieux sur trois états git réservés aux devs.
Le bouton de vérification manuelle dans le menu (`↻ MAJ`) est ce qui
les remonte. Pour les chemins end-user (bandeaux doré / ambre), voir
[Mise à jour](Updating-fr).

### Bandeau ambre : *Installation .exe — MAJ auto désactivées*

Tu fais tourner un build `.exe` PyInstaller. L'updater ne peut pas
swap atomiquement les fichiers sources du bundle pendant qu'il
tourne, donc il s'écarte. Pour mettre à jour : télécharge un clone
source frais et recompile avec `python tools/build.py`, puis remplace
l'ancien dossier `dist/SelfbotManager/`. Tes `bots.json`,
`settings.json` et `grabs.db` vivent dans ce même dossier et ne sont
pas touchés par le rebuild.

### Vérif manuelle silencieuse (sur une branche feature)

L'updater refuse de toucher un arbre qui n'est pas sur `main`. Reviens
dessus :

```bash
git checkout main
git pull --ff-only
```

Si tu travaillais sur la branche feature, push d'abord ou stash
(voir les deux cas suivants).

### `Modifications locales en cours : commit ou stash requis`

`git status --porcelain --untracked-files=no` signale des
modifications sur des fichiers suivis. Un fast-forward pourrait
conflict, donc l'updater abandonne. Au choix :

```bash
git status            # voir ce qui est modifié
git stash             # mettre les changements de côté, MAJ, puis `git stash pop`
git restore <fichier> # jeter un fichier qu'on ne veut pas garder
git commit -am "..."  # commit le travail, puis MAJ
```

Les fichiers non suivis sont ignorés — seules les modifs sur fichiers
suivis déclenchent ce cas.

### `Commits locaux en avance sur origin/main : push ou reset requis`

Tu as des commits qui ne sont pas sur `origin/main`. Un pull
fast-forward forcerait un merge, donc l'updater abandonne. Push le
travail :

```bash
git push origin main
```

Ou, si ces commits ne valent pas la peine d'être gardés :

```bash
git reset --hard origin/main   # destructif — perd les commits locaux
```

---

## GUI

### Le toggle de thème tout casse en gris

Probablement un override custom qui clashe avec le nouveau preset. Ouvre la
modale 🎨 Couleurs et **Réinitialiser**.

### `bots.json` grossit ou contient des doublons

Un crash en plein save peut laisser le fichier sale. Arrête l'app, ouvre
`bots.json`, dédoublonne par champ `_id`, sauvegarde, redémarre.

### CPU élevé avec plusieurs bots

Chaque bot = un thread + une loop asyncio + un client Discord. 5+ bots sur
une seule machine reste OK ; au-delà, envisage un petit VPS avec un bot
par process.

---

## Autre

Ouvre une [issue](../../issues/new) avec :

- Le message exact depuis le GUI (barre de statut + lignes de log).
- Les lignes `📥 SOFI:` autour du fail.
- OS, version Python, versions des paquets.
