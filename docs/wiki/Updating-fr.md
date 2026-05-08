> [🇬🇧 English](Updating) · 🇫🇷 Français

# Mettre à jour

Le projet bouge — les formats des drops changent, les presets de thème
évoluent, les dépendances bumpent. La bonne nouvelle : **ta config locale
n'est jamais touchée** par une mise à jour.

## TL;DR

```powershell
.\tools\update.ps1
```

C'est tout. Le script fait ce qu'il faut.

## Ce qu'il fait vraiment

1. **Sanity check** — vérifie que le dossier est un clone git (pas un ZIP
   téléchargé).
2. **`git fetch`** — regarde s'il y a du neuf sur `main`.
3. **`git pull --ff-only`** — fast-forward vers le dernier commit.
   - Refuse de merger si tu as des commits locaux qui divergent
     d'`origin/main` (te donne un hint stash/commit clair).
4. **`pip install -r requirements.txt`** — seulement si
   `requirements.txt` a vraiment changé dans le pull. Skipped sinon pour
   gagner du temps.
5. **Résumé** — ancien hash → nouveau hash + nombre de fichiers changés.

Exemple de sortie :

```
⚜  SELFBOT MANAGER  ·  UPDATER
------------------------------------------------------------
->  Checking remote...
->  Pulling latest changes (3 commit(s) behind)...
->  Installing updated dependencies (venv: env\)...
OK  Up to date

    6c1709e  ->  9aab1f4    (4 file(s) changed)

    Your bots.json + settings.json are untouched.
    Launch the app from the taskbar pin or:
      python main.py
```

## Ce qui est préservé

| Fichier / dossier          | Rôle                              | Touché par l'update ? |
| -------------------------- | --------------------------------- | --------------------- |
| `bots.json`                | Tous tes bots et tokens           | ❌ jamais             |
| `settings.json`            | Mode thème + couleurs custom      | ❌ jamais             |
| `Selfbot Manager.lnk`      | Ton raccourci taskbar             | ❌ jamais             |
| `env/`                     | Ton venv                          | ❌ jamais             |
| Code projet & icône        | La codebase                       | ✅ écrasé             |

## Quand le script refuse

### « Not a git repository »

Tu as téléchargé un ZIP au lieu de cloner. Le script ne peut pas
`git pull` depuis un dossier non-git. Fix :

```powershell
git clone https://github.com/Soma-Yukihira/sofi-manager.git sofi-manager-new
# copie ta config dans le nouveau dossier
copy sofi-manager\bots.json     sofi-manager-new\
copy sofi-manager\settings.json sofi-manager-new\
```

Puis supprime l'ancien dossier. Les prochaines updates marcheront avec
`update.ps1`.

### « git pull failed »

Presque toujours parce que tu as édité un fichier tracké (ex: bidouille
locale dans `gui.py`). Le script te dit de stasher :

```powershell
git stash
.\tools\update.ps1
git stash pop
```

Si `git stash pop` reporte des conflits, résous-les dans ton éditeur.

### Erreur internet

Évident — vérifie ta connexion et réessaie.

## Quand `requirements.txt` change

Si une nouvelle dépendance est ajoutée (rare), le script lance auto
`pip install -r requirements.txt` dans le venv qu'il détecte (`env/`,
`venv/`, ou `.venv/`). Tu n'as rien à faire à la main.

## Migrations de format

Aujourd'hui les schémas de `bots.json` et `settings.json` sont stables. Si
une release future les change de façon breaking, le changelog le
mentionnera et le GUI affichera un message de migration clair. Pas de
corruption silencieuse.
