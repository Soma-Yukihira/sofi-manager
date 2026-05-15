> [🇬🇧 English](Architecture) · 🇫🇷 Français

# Architecture

Petit tour pour qui veut forker ou étendre le projet.

## Fichiers

Les modules runtime vivent sous le package `sofi_manager/`. `main.py` et
`cli.py` à la racine sont de fins shims qui délèguent — ils restent au
root pour que le raccourci Windows, le spec PyInstaller, et les units
systemd VPS existantes (`python cli.py …`) continuent de fonctionner
sans changement.

```
main.py                       ← shim racine. Lance la migration cleanup
                                + apply_pending_on_startup(), puis
                                sofi_manager.gui.run().
cli.py                        ← shim racine. Délègue à
                                sofi_manager.cli.main().
sofi_manager/
├── gui.py                    ← UI CustomTkinter : système thèmes,
│                               sidebar, tabs, logs, modales, bandeau
│                               update.
├── cli.py                    ← Sous-commandes headless / VPS. Même cœur.
├── bot_core.py               ← Classe SelfBot. Orchestration Discord.
├── parsing.py                ← Parseurs messages SOFI (FR + EN, purs).
├── scoring.py                ← Scoring cartes + override wishlist (pur).
├── updater.py                ← Auto-updater : fast-forward git, fallback
│                               ZIP codeload, classifieur skip_reason
│                               (5 états).
├── crypto.py                 ← Chiffrement Fernet des tokens. Clé dans
│                               le keyring OS avec fallback fichier.
├── paths.py                  ← Résolution bundle_dir() / user_dir().
│                               Source de vérité pour les chemins
│                               source-vs-frozen.
├── storage.py                ← Historique SQLite des grabs (WAL).
│                               Migration legacy.
└── _migrations.py            ← Cleanup one-shot des .py racine
                                orphelinés par l'updater ZIP.
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

| Fichier         | Owner                              | Notes                                       |
| --------------- | ---------------------------------- | ------------------------------------------- |
| `bots.json`     | `sofi_manager.gui` / `.cli`        | Configs bot. Tokens chiffrés en Fernet via `sofi_manager.crypto`. |
| `settings.json` | `sofi_manager.gui`                 | Prefs thème + état updater (`zip_install_sha`). |
| `grabs.db`      | `sofi_manager.storage`             | Historique SQLite (WAL). `USER_DIR/grabs.db` par défaut, override avec `SOFI_DB_PATH`. Chemins legacy `%APPDATA%` / XDG migrés au premier lancement. |

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

`apply_pending_on_startup` (appelé depuis `main.py` *avant* l'import de
`sofi_manager.gui`) ne prend que le chemin git — les cas ZIP et frozen
sont gérés plus tard depuis le thread UI une fois Tk lancé, via
`check_zip_in_background` et `_maybe_show_skip_reason_banner`.

Le shim racine appelle aussi `sofi_manager._migrations.cleanup_legacy_root_files()`
avant tout le reste. C'est un wipe one-shot des modules `.py`
pre-refactor laissés à la racine du projet par l'updater ZIP
(l'extraction codeload est overwrite-only, ne supprime jamais les
fichiers retirés en amont). No-op sur les installs git-clone — git a
déjà supprimé les orphelins.

## Packaging

L'arborescence source tourne telle quelle avec `python main.py`. Pour
les utilisateurs finaux, un spec PyInstaller versionné
(`selfbot-manager.spec`) bundle le GUI en exécutable Windows autonome
via `python tools/build.py`.

Deux helpers de chemins runtime dans `sofi_manager.paths` synchronisent
les builds source et gelés, et sont importés par `sofi_manager.gui`,
`sofi_manager.cli` et `sofi_manager.storage` :

- `bundle_dir()` — assets read-only. Vaut `sys._MEIPASS` une fois gelé,
  sinon la racine du repo.
- `user_dir()` — état mutable (`bots.json`, `settings.json`,
  `grabs.db`). Résout toujours vers le dossier contenant le .exe (ou
  l'arbre source). Une migration one-shot déplace toute `grabs.db`
  pré-existante depuis `%APPDATA%` / XDG vers `USER_DIR` au premier
  lancement.

Voir la page wiki [Compilation](Building-fr) pour la structure
complète et les gotchas PyInstaller.
