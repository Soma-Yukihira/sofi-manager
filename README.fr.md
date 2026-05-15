<div align="center">

<img src="docs/images/banner.svg" alt="SOFI Manager" width="100%">

<p>
  <a href="README.md">English</a> ·
  <a href="README.fr.md"><b>Français</b></a>
</p>

<p><i>Interface premium black &amp; gold pour orchestrer plusieurs selfbots Discord SOFI en parallèle.</i></p>

<p>
  <a href="https://github.com/Soma-Yukihira/sofi-manager/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Soma-Yukihira/sofi-manager/ci.yml?branch=main&style=flat-square&labelColor=0a0a0a&color=d4af37&label=CI" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-d4af37?style=flat-square&labelColor=0a0a0a" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/license-MIT-d4af37?style=flat-square&labelColor=0a0a0a" alt="Licence MIT">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-d4af37?style=flat-square&labelColor=0a0a0a" alt="Multi-plateforme">
  <img src="https://img.shields.io/badge/UI-CustomTkinter-d4af37?style=flat-square&labelColor=0a0a0a" alt="CustomTkinter">
</p>

</div>

> [!WARNING]
> **Les selfbots violent les [Conditions d'utilisation Discord](https://discord.com/terms).**
> Utiliser ce projet sur ton compte peut entraîner une suspension ou un bannissement définitif.
> Ce projet est fourni à titre éducatif — **à tes risques et périls**.

---

## ✨ Fonctionnalités

- 🪶 **Multi-bot** — gère plusieurs selfbots depuis une seule fenêtre, chacun avec son thread, sa boucle asyncio et sa config
- 🎴 **Sélection intelligente** — scoring rareté + popularité avec override wishlist (personnages & séries)
- 🌙 **Pause nocturne** — fenêtre de sommeil aléatoire entre 22h et 01h pour imiter un humain
- 🌍 **Détection SOFI multilingue** — messages drop & cooldown analysés en **français et anglais**
- 🎨 **Thèmes premium** — presets sombre et clair + personnalisation couleur par couleur (17 slots)
- 📜 **Logs en direct** — console colorée par bot avec un flux diagnostic de tous les messages SOFI reçus
- 💾 **Local first** — config sur disque dans `bots.json` ; tokens chiffrés (Fernet) avec une clé stockée dans le keyring OS (fallback fichier sous `%APPDATA%/sofi-manager/`)

---

## 📸 Captures d'écran

|                                 |                                |
| :-----------------------------: | :----------------------------: |
| ![Mode sombre](docs/images/screenshot-dark.png) | ![Mode clair](docs/images/screenshot-light.png) |
| _Preset sombre_                 | _Preset clair_                 |

---

## 🚀 Démarrage rapide

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
python -m venv env
# Windows
.\env\Scripts\activate
# macOS / Linux
# source env/bin/activate

pip install -r requirements.txt
python main.py
```

L'interface s'ouvre. Clique **+ AJOUTER UN BOT**, remplis ton token + drop channel, **Sauvegarder**, puis **▶ Démarrer**.

### Optionnel · .exe Windows autonome

Évite l'install Python avec un build en une commande :

```bash
python tools/build.py
```

Produit `dist/SelfbotManager/SelfbotManager.exe` — double-clic pour
lancer. Voir la page wiki [Compilation](../../wiki/Building-fr) pour les
options (`--onefile`, `--clean`) et la stratégie de chemins runtime.

### Optionnel · Épingler à la barre des tâches (Windows)

```bash
python tools/create_shortcut.py
```

Génère `Selfbot Manager.lnk` avec l'icône ⚜ dorée — pointe automatique
sur le `.exe` si tu en as compilé un, sinon sur le `pythonw.exe` du
venv. Glisse-le sur la barre des tâches (ou clic droit → *Épingler à la
barre des tâches*) — l'app se lance sans fenêtre de console.

### Mettre à jour

**Auto-update façon Discord (clones git).** Au démarrage, l'app vérifie
`origin/main` dans un thread d'arrière-plan. Quand de nouveaux commits
arrivent, un bandeau doré apparaît en haut de la fenêtre : *Mise à jour
disponible — Redémarrez pour appliquer*. Un clic sur **Redémarrer**,
l'app applique `git pull --ff-only`, relance Python, et le nouveau code
tourne. Pas de fichier de release, pas d'étape manuelle — chaque commit
sur `main` est une release.

L'auto-updater s'adapte à ton install :
- **Clone git** — `git pull --ff-only origin main` puis re-exec.
- **Téléchargement ZIP** (pas de `.git/`) — récupère `main` depuis
  `codeload.github.com` et écrase les fichiers suivis en place. Même
  bandeau, même flux de redémarrage.
- **`.exe` gelé** — désactivé ; un bandeau ambre passif renvoie vers
  un rebuild depuis un clone frais.
- Également désactivé sur une branche autre que `main`, avec des
  commits locaux en avance, ou des fichiers suivis modifiés.
- `bots.json`, `settings.json` et `grabs.db` sont gitignorés — ils
  survivent à chaque update intacts.

**Update manuel** (résumé verbeux en CLI, utile aussi sur VPS) :

```bash
python tools/update.py
```

Même commande sur Windows, macOS et Linux. Rafraîchit les dépendances
Python si `requirements.txt` a changé et imprime un résumé propre.

### Headless / VPS

Pour les serveurs sans écran, un CLI partage le même `bots.json` et le
même cœur :

```bash
python cli.py add                     # wizard interactif
python cli.py list                    # liste les bots configurés
python cli.py run                     # lance tout au premier plan
sudo ./tools/install-systemd.sh       # installateur systemd clé en main
```

Voir la [page wiki Déploiement VPS](../../wiki/VPS-Deployment-fr) pour le
guide complet, incluant `tmux`, hardening `systemd`, et push de la config
depuis le GUI vers le serveur.

📖 **Documentation complète dans le [Wiki](../../wiki).**

---

## 📂 Structure du projet

```
sofi-manager/
├── main.py              # Lanceur GUI (hook de mise à jour pré-import)
├── cli.py               # Lanceur headless / VPS (même cœur)
├── gui.py               # UI CustomTkinter + thèmes + bandeau update
├── bot_core.py          # Classe SelfBot + parsing / scoring SOFI
├── updater.py           # Auto-updater git + ZIP-codeload
├── crypto.py            # Chiffrement Fernet des tokens (keyring OS)
├── paths.py             # Résolution bundle_dir() / user_dir()
├── storage.py           # Historique SQLite + migration legacy DB
├── selfbot-manager.spec # Spec PyInstaller (piloté par tools/build.py)
├── tools/               # build / update / shortcut / installeur systemd
├── assets/app.ico       # Icône ⚜ dorée, embarquée dans le .exe
├── requirements.txt     # discord.py-self, customtkinter, curl_cffi
├── tests/               # tests unitaires pytest
├── docs/
│   ├── wiki/            # Sources des pages wiki (EN + FR)
│   └── images/          # Bannière + captures
└── LICENSE              # MIT
```

Les fichiers runtime `bots.json` (tokens chiffrés + configs bot),
`settings.json` (préférences thème + état updater) et `grabs.db`
(historique SQLite des grabs) sont créés au premier lancement et
gitignorés.

---

## 📚 Documentation

Le [Wiki](../../wiki) couvre chaque sujet en détail :

| Page | Contenu |
| ---- | ------- |
| [Installation](../../wiki/Installation-fr) | Setup Python, venv, dépendances |
| [Compilation](../../wiki/Building-fr) | .exe Windows autonome en une commande |
| [Configuration](../../wiki/Configuration-fr) | Chaque champ du GUI expliqué |
| [Thèmes](../../wiki/Theming-fr) | Presets et personnalisation 17 couleurs |
| [Mise à jour](../../wiki/Updating-fr) | Updater intégré, fallback ZIP, garde-fous |
| [Déploiement VPS](../../wiki/VPS-Deployment-fr) | CLI, `tmux`, hardening `systemd` |
| [Architecture](../../wiki/Architecture-fr) | Comment bots, threads et event loops sont câblés |
| [Dépannage](../../wiki/Troubleshooting-fr) | Erreurs courantes + log debug `📥 SOFI:` |
| [Avis ToS Discord](../../wiki/Discord-ToS-fr) | Risques et conséquences possibles |

---

## 🤝 Contribuer

Les PR sont les bienvenues. Lis [CONTRIBUTING.fr.md](CONTRIBUTING.fr.md) avant d'en ouvrir une.

Pour un bug, ouvre une [issue](../../issues/new) en y collant les lignes
`📥 SOFI:` de ton run — elles pointent immédiatement les changements de
format côté SOFI.

---

## 📄 Licence

[MIT](LICENSE) © Soma-Yukihira.

Ce logiciel est fourni "tel quel", sans garantie d'aucune sorte. En l'utilisant,
tu reconnais les risques décrits dans l'avertissement ci-dessus.
