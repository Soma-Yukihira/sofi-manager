> [🇬🇧 English](Building) · 🇫🇷 Français

# Compilation

Selfbot Manager s'utilise depuis les sources, mais une seule commande
produit un `.exe` Windows autonome pour les utilisateurs qui ne veulent
pas toucher à Python.

## TL;DR

```bash
python tools/build.py
```

Sortie : `dist/SelfbotManager/SelfbotManager.exe` (+ son dossier de
support). Double-clic — pas de Python, pas de venv, pas de console.

## Ce qui s'exécute

`tools/build.py` est l'unique point d'entrée. Il :

1. Installe `pyinstaller>=6.0` à la demande si absent (dépendance de
   build uniquement — pas dans `requirements.txt`).
2. Invoque PyInstaller contre le spec versionné
   [`selfbot-manager.spec`](https://github.com/Soma-Yukihira/sofi-manager/blob/main/selfbot-manager.spec).
3. Affiche le chemin de sortie en cas de succès.

Le spec est la seule source de vérité pour la configuration du build.
Ne passe pas de flags supplémentaires à PyInstaller — modifie le spec.

## Structure de sortie

### Par défaut (`onedir`)

```
dist/
└── SelfbotManager/
    ├── SelfbotManager.exe        ← point d'entrée
    ├── assets/app.ico
    └── _internal/                ← runtime Python + libs embarquées
```

Distribue le dossier entier. Démarrage plus rapide, moins de faux
positifs antivirus.

### Fichier unique (`--onefile`)

```bash
python tools/build.py --onefile
```

Produit `dist/SelfbotManager.exe`, un bundle auto-extractible. Premier
lancement plus lent (extraction vers un dossier temporaire), plus
susceptible d'être flaggé par les heuristiques AV — à n'utiliser que si
tu as vraiment besoin d'un fichier unique.

### Reconstruction propre

```bash
python tools/build.py --clean
```

Supprime `build/` et `dist/` avant de lancer. À utiliser après un
changement de spec, d'asset ou de `requirements.txt`.

## Chemins runtime

L'exe gelé doit lire son icône embarquée d'un côté et écrire sa config
runtime d'un autre. Deux helpers dans `gui.py` font le tri :

| Helper       | Résout vers (frozen)              | Résout vers (source)         |
| ------------ | --------------------------------- | ---------------------------- |
| `BUNDLE_DIR` | `sys._MEIPASS` (assets read-only) | racine du repo (next to `gui.py`) |
| `USER_DIR`   | dossier contenant le .exe         | racine du repo               |

- **Assets read-only** (`assets/app.ico`, thèmes customtkinter) vivent
  dans `BUNDLE_DIR`. PyInstaller les embarque à la compilation.
- **État mutable** (`bots.json`, `settings.json`, `grabs.db`) vit dans
  `USER_DIR`. L'utilisateur final peut donc éditer/sauvegarder ces
  fichiers à côté de l'exe, exactement comme dans l'install source.

`cli.py` applique la même règle. La résolution vit dans `paths.py` —
GUI, CLI et `storage.py` partagent la même racine.

> [!NOTE]
> Les versions antérieures stockaient `grabs.db` sous
> `%APPDATA%/sofi-manager/` (Windows) ou `~/.local/share/sofi-manager/`
> (POSIX). Au premier lancement après mise à jour, la GUI déplace
> silencieusement toute DB existante vers `USER_DIR/grabs.db` et
> affiche un banner gold à dismisser. Utilise `SOFI_DB_PATH` pour
> garder la DB ailleurs (utile sur VPS).

> [!NOTE]
> N'écris jamais dans `BUNDLE_DIR` à l'exécution. En mode `--onefile`
> il pointe vers un dossier temporaire qui disparaît à la sortie du
> processus.

## Après le build · épingler à la barre des tâches

```bash
python tools/create_shortcut.py
```

Détecte automatiquement le build à
`dist/SelfbotManager/SelfbotManager.exe` et crée
`Selfbot Manager.lnk` qui pointe dessus. Glisse sur la barre des tâches
ou clic droit → *Épingler à la barre des tâches*.

Si aucun build n'est présent, le raccourci retombe sur le couple
`pythonw.exe` + `main.py` du venv, comme avant.

## Publication

Pour l'instant, les releases sont manuelles :

1. Mettre à jour le changelog (si tu en tiens un).
2. `python tools/build.py --clean`
3. Zipper `dist/SelfbotManager/` en
   `SelfbotManager-vX.Y.Z-win64.zip`.
4. Uploader comme asset d'une GitHub Release sur le tag.

Pas d'installeur, pas d'auto-update. Volonté assumée de transparence
totale.

## Notes antivirus

Les apps bundlées via PyInstaller sont parfois flaggées par Windows
Defender ou des AV tiers — limite connue de tout bootloader
auto-extractible, pas un signe de malveillance. Mitigations appliquées
ici :

- `onedir` par défaut (moins d'heuristiques déclenchées que `--onefile`).
- Pas de compression UPX (UPX est un trigger AV majeur).
- Icône embarquée = signal éditeur clair.

Si un scan flagge quand même le build, soumets-le à ton éditeur AV
comme faux positif, ou recompile depuis les sources.

## Dépannage

| Symptôme                                  | Cause / correctif                                                                          |
| ----------------------------------------- | ------------------------------------------------------------------------------------------ |
| `ModuleNotFoundError` au premier lancement | Un nouvel import runtime n'est pas dans le spec. Ajoute-le à `hiddenimports`.              |
| Icône absente sur la fenêtre / barre       | `assets/app.ico` n'a pas été embarqué. Vérifie `datas` dans le spec.                       |
| `bots.json` introuvable à côté de l'exe   | Mauvais répertoire de travail. Lance toujours via le .exe (ou le raccourci), pas via `_internal/`. |
| Build OK mais l'exe se ferme immédiatement | Un `print()` console-only a crashé sans console. Lance l'exe depuis un terminal pour voir la trace. |
| Premier lancement lent (`--onefile` seul)  | Normal — le bundle s'extrait à chaque démarrage à froid. Préfère le `onedir` par défaut.   |

## Suite

- [Mise à jour](Updating-fr) — récupérer les nouvelles versions sur une
  install source.
- [Installation](Installation-fr) — install source (la voie d'origine).
