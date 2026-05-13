> [🇬🇧 English](Updating) · 🇫🇷 Français

# Mettre à jour

Le projet bouge — les formats des drops changent, les presets de thème
évoluent, les dépendances bumpent. La bonne nouvelle : **ta config locale
n'est jamais touchée** par une mise à jour.

## Vérifier depuis la GUI

Clique sur **`⟳  Mises à jour`** dans la barre du haut. L'app interroge la
dernière GitHub Release et affiche :

- la version installée (`version.py:__version__`),
- le dernier tag publié,
- le titre de la release et un extrait des notes,
- un bouton **Ouvrir la release** pour télécharger le nouveau build.

Le check tourne dans un thread d'arrière-plan et ne bloque jamais l'UI. Si
aucune release n'a encore été publiée, le message *"Aucune release publiée
pour le moment."* s'affiche — il faut publier une release sur GitHub pour
que la fonctionnalité remonte quelque chose.

Le bouton **vérifie seulement** ; il ne télécharge rien et ne remplace
aucun fichier. Utilise `python tools/update.py` (install source) ou
télécharge le `.exe` depuis la page de release (build figé).

## TL;DR

```bash
python tools/update.py
```

C'est tout — même commande sur Windows, macOS et Linux.

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

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git sofi-manager-new
# copie ta config dans le nouveau dossier
# (Windows : `copy` ; macOS/Linux : `cp`)
```

Puis supprime l'ancien dossier. Les prochaines updates marcheront avec
`python tools/update.py`.

### « git pull failed »

Presque toujours parce que tu as édité un fichier tracké (ex: bidouille
locale dans `gui.py`). Le script te dit de stasher :

```bash
git stash
python tools/update.py
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

---

# Publier une release (mainteneurs uniquement)

Cette section concerne le mainteneur du projet. Les utilisateurs n'en ont
pas besoin.

## Prérequis

- **Python 3.10+** avec `pytest` et `pyinstaller` dispo (PyInstaller est
  installé automatiquement par `tools/build.py` si manquant)
- **Git** avec les droits push sur `origin`
- **GitHub CLI** (`gh`) — installer depuis <https://cli.github.com/>
  puis `gh auth login` une fois

## Source unique de vérité

`version.py:__version__` est le **seul** endroit où bumper la version.
Le GUI le lit pour la ligne "version installée", le vérificateur de
mises à jour intégré le compare au dernier tag GitHub, et
`tools/release.py` en dérive le tag.

Le format est strictement SemVer `MAJEUR.MINEUR.PATCH` (pas de suffixes
pre-release). Le tag GitHub est toujours `v{__version__}` — ex.
`__version__ = "0.2.0"` → tag `v0.2.0`.

## Workflow

1. **Bump** `version.py:__version__` dans une branche.
2. **Répète** la release sans toucher à git ni GitHub :
   ```bash
   python tools/release.py --dry-run
   ```
   Autorisé depuis n'importe quelle branche — pratique avant de merger
   la PR de bump. Affiche un warning si tu n'es pas sur `main`, lance
   tests + build + archive, puis s'arrête.
3. **Merge** la PR de bump dans `main`.
4. **Bascule** sur `main` avec un working tree propre :
   ```bash
   git checkout main
   git pull --ff-only
   ```
5. **Publie** :
   ```bash
   python tools/release.py
   ```

## Ce que fait le script en mode live

1. Lit `__version__` / `__repo__` depuis `version.py` et valide le
   SemVer strict.
2. Échec dur si la branche n'est pas `main`.
3. Échec dur si le working tree n'est pas propre (staged, unstaged ou
   untracked).
4. Échec dur si le tag `v{version}` existe déjà localement ou sur
   origin.
5. Vérifie que `gh` est installé et authentifié.
6. Lance `python -m pytest -q tests` (skip avec `--skip-tests`).
7. Lance `python tools/build.py --clean` et vérifie que
   `dist/SelfbotManager/SelfbotManager.exe` existe.
8. Empaquette `dist/SelfbotManager/` dans un zip déterministe :
   `dist/releases/SelfbotManager-v{version}-windows.zip`
   (entrées triées + mtime fixe → byte-stable entre machines).
9. Crée le tag annoté `v{version}` et le push sur origin (rollback du
   tag local si le push échoue).
10. `gh release create v{version} <archive> --repo {__repo__}` — crée
    la GitHub Release et upload le zip en pièce jointe.

## Comment le check de mises à jour intégré la voit

`updater.py` interroge
`GET https://api.github.com/repos/{__repo__}/releases/latest` et lit
`tag_name`. Le GUI retire un éventuel `v` de tête et compare à
`version.py:__version__`. Le tag de release **doit** être
`v{__version__}` à l'identique, sinon la comparaison mismatch et les
utilisateurs verront un état "mise à jour dispo" / "à jour" incorrect.

Si tu publies une release à la main (sans `tools/release.py`),
assure-toi que le tag matche et que le zip Windows est bien attaché à la
release — le bouton de téléchargement dans le GUI pointe vers la page
de release, pas vers le zip directement.

## Flags

| Flag           | Effet                                                              |
| -------------- | ------------------------------------------------------------------ |
| `--dry-run`    | Plan + checks + tests + build + archive. Pas de tag / push / publish. |
| `--skip-tests` | Skip pytest. À n'utiliser qu'après avoir lancé les tests en CI.    |

## Outputs de build et hygiène git

`dist/`, `build/`, `dist/releases/`, `*.exe`, `*.zip`, `__pycache__/` et
`.claude/worktrees/` sont tous gitignorés. Ne jamais committer ces
fichiers — le script de release écrit tout dans `dist/` exprès pour
qu'un checkout propre le reste.
