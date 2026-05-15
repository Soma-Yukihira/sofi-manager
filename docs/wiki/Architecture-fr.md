> [🇬🇧 English](Architecture) · 🇫🇷 Français

# Architecture

Petit tour pour qui veut forker ou étendre le projet.

## Fichiers

```
main.py        ← Entrée GUI. Lance apply_pending_on_startup() avant
                  d'importer gui, puis gui.run().
cli.py         ← Entrée headless / VPS. Partage le même cœur.
gui.py         ← UI CustomTkinter : système thèmes, sidebar, tabs,
                  logs, modales, bandeau update.
bot_core.py    ← Classe SelfBot. Parsing + scoring SOFI. Logique pure.
updater.py     ← Auto-updater : fast-forward git, fallback ZIP
                  codeload, classifieur skip_reason (5 états).
crypto.py      ← Chiffrement Fernet des tokens. Clé dans le keyring OS
                  avec fallback fichier.
paths.py       ← Résolution bundle_dir() / user_dir(). Source de
                  vérité pour les chemins source-vs-frozen.
storage.py     ← Historique SQLite des grabs (WAL). Migration legacy.
```

Le split est enforced par convention :

- `bot_core.py` n'importe **rien** d'UI.
- `gui.py` n'importe **pas** `discord`. Il connaît juste `SelfBot`,
  `default_config()` et les helpers de parsing.
- `cli.py` est la preuve que le cœur est UI-agnostique : il instancie
  `SelfBot` directement, sans dépendance Tk.

## Modèle de threading

Chaque bot tourne dans son **propre thread OS** avec sa **propre boucle
asyncio**.

```
┌─────────────────────┐         ┌────────────────────────────┐
│  Tkinter main loop  │         │   Bot 1 thread             │
│  (thread UI)        │         │   ├── asyncio loop         │
│                     │         │   │   ├── drop_loop        │
│   ─ poll des logs  ─┼────────►│   │   ├── cooldown_handler │
│   ─ updates statut ─┼◄────────┤   │   └── night_pause      │
│                     │         │   └── discord.Client       │
└─────────────────────┘         └────────────────────────────┘
                                ┌────────────────────────────┐
                                │   Bot 2 thread (idem)      │
                                └────────────────────────────┘
```

Communication :

- **bot → UI** via `queue.Queue` (`SelfBot.log_queue`).
  Le thread UI poll toutes les 120 ms via `after()` et draine toutes les queues.
- **bot → UI** pour les changements de statut via `status_callback` —
  appelé depuis la boucle asyncio, wrappé avec `self.after(0, ...)` pour
  rebondir sur le thread Tk.
- **UI → arrêt bot** via `asyncio.run_coroutine_threadsafe()` qui planifie
  `client.close()` sur la loop du bot.

## Système de thèmes

Deux presets (`DARK_THEME`, `LIGHT_THEME`) et un helper `Theme(mode,
overrides)` qui les merge. Toute création de widget passe par les helpers
`_mk_*` de l'app qui lisent `self.theme[key]`.

Quand l'utilisateur bascule le thème ou applique des couleurs custom,
l'app appelle `_rebuild_ui()` :

1. Persiste les configs des bots courants.
2. Détache `status_callback` des instances en marche.
3. Détruit tous les enfants widgets de `self`.
4. Appelle `_apply_appearance()` et `_build_layout()`.
5. Ré-enregistre chaque bot sauvegardé en gardant son instance `SelfBot`
   et son buffer de logs en vie.
6. Restaure la sélection précédente.

Les threads en marche ne sont pas impactés — ils continuent leur loop. Seule
la vue est reconstruite.

## Pipeline de drop

```
on_message
  └── filtre : de SOFI, dans les salons écoutés
  └── extract_full_text(message)        # content + chaque part d'embed
  └── si match _COOLDOWN_RE → schedule cooldown handler
  └── si match _DROP_TRIGGER_RE → continuer
  └── check mention (couvre <@id>, <@!id>, message.mentions)
  └── smart_parse_cards(full_text)      # regex G•/série/hearts
  └── choose_card(cards, cfg, log)      # pick initial (pas encore hearts)
  └── fetch message → poll 10× pour les boutons actifs
  └── update les hearts des cartes depuis les labels boutons
  └── choose_card(cards, cfg, log)      # pick final
  └── delay aléatoire, puis click
```

`extract_full_text` est ce qui gère SOFI émettant les drops en embed.
`_DROP_TRIGGER_RE` match à la fois les variantes FR (`drop des cartes`) et
EN (`dropping cards`) — étends-le si SOFI ajoute d'autres langues.

## Persistance

| Fichier         | Owner                | Notes                                       |
| --------------- | -------------------- | ------------------------------------------- |
| `bots.json`     | `gui.py` / `cli.py`  | Configs bot. Tokens chiffrés en Fernet via `crypto.py`. |
| `settings.json` | `gui.py`             | Prefs thème + état updater (`zip_install_sha`). |
| `grabs.db`      | `storage.py`         | Historique SQLite (WAL). `USER_DIR/grabs.db` par défaut, override avec `SOFI_DB_PATH`. Chemins legacy `%APPDATA%` / XDG migrés au premier lancement. |

Les trois sont gitignorés — ils survivent à chaque update.

## Flux d'update

`updater.skip_reason()` classe l'install dans l'un des cinq cas. La
GUI branche dessus :

```
                  ┌── None      → chemin git : git pull --ff-only,
                  │               re-exec au clic "Redémarrer".
                  │
                  ├── no-git    → chemin ZIP : fetch codeload +
                  │               écrasement via _apply_zip_bytes,
   skip_reason() ─┤               même bandeau, baseline persistée
                  │               en zip_install_sha dans
                  │               settings.json.
                  │
                  ├── frozen    → bandeau ambre seulement. Les
                  │               bundles PyInstaller ne peuvent pas
                  │               swap atomiquement leurs sources.
                  │
                  └── off-main  → silencieux. États dev. Le check à
                      / dirty     la demande dans le menu les remonte
                      / ahead     quand on l'invoque.
```

`apply_pending_on_startup` (appelé depuis `main.py` *avant* `import
gui`) ne prend que le chemin git — les cas ZIP et frozen sont gérés
plus tard depuis le thread UI une fois Tk lancé, via
`check_zip_in_background` et `_maybe_show_skip_reason_banner`.

## Packaging

L'arborescence source tourne telle quelle avec `python main.py`. Pour
les utilisateurs finaux, un spec PyInstaller versionné
(`selfbot-manager.spec`) bundle le GUI en exécutable Windows autonome
via `python tools/build.py`.

Deux helpers de chemins runtime dans `paths.py` synchronisent les
builds source et gelés, et sont importés par `gui.py`, `cli.py` et
`storage.py` :

- `bundle_dir()` — assets read-only. Vaut `sys._MEIPASS` une fois gelé,
  sinon la racine du repo.
- `user_dir()` — état mutable (`bots.json`, `settings.json`,
  `grabs.db`). Résout toujours vers le dossier contenant le .exe (ou
  l'arbre source). Une migration one-shot déplace toute `grabs.db`
  pré-existante depuis `%APPDATA%` / XDG vers `USER_DIR` au premier
  lancement.

Voir la page wiki [Compilation](Building-fr) pour la structure
complète et les gotchas PyInstaller.
