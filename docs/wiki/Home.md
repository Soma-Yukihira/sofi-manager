> 🇬🇧 English · [🇫🇷 Français](Home-fr)

# SOFI Manager · Wiki

Welcome. This wiki is the long-form companion to the
[README](https://github.com/Soma-Yukihira/sofi-manager#readme).

> [!WARNING]
> Selfbots violate the Discord ToS. Read [Discord ToS Notice](Discord-ToS)
> before running anything.

## Where to start

| If you are…                       | Read first                            |
| --------------------------------- | ------------------------------------- |
| Installing for the first time     | [Installation](Installation)          |
| Tweaking a running bot            | [Configuration](Configuration)        |
| Reviewing grab history / exports  | [Stats](Stats)                        |
| Customizing the look              | [Theming](Theming)                    |
| Debugging a missed drop           | [Troubleshooting](Troubleshooting)    |
| Forking or extending              | [Architecture](Architecture)          |

## What this project is — and isn't

**Is** — A desktop GUI that runs **your** Discord account as a SOFI auto-dropper,
with sane defaults: jittered intervals, night pause, smart card scoring.

**Isn't** — A multi-account farm, a stealth tool, or a shield against ToS
enforcement. It logs everything it does and makes no attempt to hide.

## Privacy

- Tokens stay in `bots.json` on your disk, Fernet-encrypted. Never transmitted.
- No telemetry, no analytics.
- Outbound traffic: Discord (selfbot ops) and GitHub (background update
  check). Nothing else.
