> [🇬🇧 English](Home) · 🇫🇷 Français

# SOFI Manager · Wiki

Bienvenue. Ce wiki est le complément détaillé du
[README](https://github.com/Soma-Yukihira/sofi-manager#readme).

> [!WARNING]
> Les selfbots violent les ToS Discord. Lis [Avis ToS Discord](Discord-ToS-fr)
> avant de lancer quoi que ce soit.

## Par où commencer

| Si tu es…                          | Lis d'abord                              |
| ---------------------------------- | ---------------------------------------- |
| En première installation           | [Installation](Installation-fr)          |
| Tu règles un bot existant          | [Configuration](Configuration-fr)        |
| Tu regardes l'historique / exports | [Stats](Stats-fr)                        |
| Tu personnalises l'UI              | [Thèmes](Theming-fr)                     |
| Tu débogues un drop raté           | [Dépannage](Troubleshooting-fr)          |
| Tu forkes ou étends                | [Architecture](Architecture-fr)          |

## Ce que ce projet est — et n'est pas

**Est** — Un GUI desktop qui fait tourner **ton** compte Discord en
auto-dropper SOFI, avec des défauts sensés : intervalles aléatoires, pause
nocturne, scoring de carte intelligent.

**N'est pas** — Une ferme multi-comptes, un outil furtif ou un bouclier
contre l'application des ToS. Il logue tout ce qu'il fait et ne tente
rien pour se cacher.

## Vie privée

- Les tokens restent dans `bots.json` sur ton disque, chiffrés en Fernet. Jamais transmis.
- Aucune télémétrie, aucun analytics.
- Trafic sortant : Discord (ops du selfbot) et GitHub (vérif de mise à
  jour en arrière-plan). Rien d'autre.
