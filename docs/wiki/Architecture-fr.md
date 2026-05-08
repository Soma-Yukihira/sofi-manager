> [🇬🇧 English](Architecture) · 🇫🇷 Français

# Architecture

Petit tour pour qui veut forker ou étendre le projet.

## Fichiers

```
main.py        ← point d'entrée, appelle juste gui.run()
gui.py         ← toute l'UI : système thèmes, sidebar, tabs, logs, modale
bot_core.py    ← classe SelfBot, parsing, scoring, aucun import UI
```

Le split est enforced par convention :

- `bot_core.py` n'importe **rien** d'UI.
- `gui.py` n'importe **pas** `discord`. Il connaît juste `SelfBot`,
  `default_config()` et les helpers de parsing.

Conséquence : tu peux livrer une variante CLI en écrivant un `cli.py` qui
utilise `SelfBot` directement.

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

| Fichier         | Owner    | Notes                                          |
| --------------- | -------- | ---------------------------------------------- |
| `bots.json`     | `gui.py` | Array de configs. Créé au premier ajout.       |
| `settings.json` | `gui.py` | Prefs UI (mode thème + overrides couleurs).    |

Les deux sont gitignorés.
