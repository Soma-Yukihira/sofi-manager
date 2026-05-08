> 🇬🇧 English · [🇫🇷 Français](Theming-fr)

# Theming

Two presets and 17 customizable color slots. Saved per-machine in
`settings.json` next to the bots file.

## Presets

| Preset | Vibe                              | Toggle                              |
| ------ | --------------------------------- | ----------------------------------- |
| Dark   | Premium black & gold              | Top bar → **🌙 Sombre / ☀ Clair**   |
| Light  | Warm white & gold (off-white bg)  | Same button                         |

Toggling a preset clears your custom overrides for the new mode — you see
the preset clean. Re-customize from there.

## Customizing colors

Click **🎨 Couleurs** in the top bar. A modal lists every slot with a color
swatch.

| Slot               | Where it appears                            |
| ------------------ | ------------------------------------------- |
| `bg`               | Main window background                      |
| `panel`            | Cards, sidebar, top bar                     |
| `panel_hover`      | Hovered list items                          |
| `panel_selected`   | Selected bot in sidebar                     |
| `input_bg`         | Inside text fields                          |
| `border`           | All thin borders                            |
| `accent`           | Section titles, default button border       |
| `accent_bright`    | Primary button (Start)                      |
| `accent_dim`       | Scrollbars, button border (idle)            |
| `text`             | Main labels                                 |
| `text_dim`         | Hints, secondary labels                     |
| `text_on_accent`   | Text on the primary button                  |
| `log_bg`           | Background of the log console               |
| `success`          | Green dot, success log lines                |
| `error`            | Red dot, error log lines, danger buttons    |
| `warn`             | Amber dot, warning log lines                |
| `info`             | Info log lines                              |

Click a swatch → native color picker → pick → preview updates. **Apply**
saves to `settings.json` and rebuilds the UI in place.

The text color of each swatch is computed for contrast — dark text on
light backgrounds, white on dark — so you always see the hex value.

## Reset

In the modal, **Réinitialiser / Reset** clears all overrides for the
**current preset**. Switch the preset toggle if you want to start from
the other preset's defaults.

## Where the values live

```json
{
  "theme": {
    "mode": "dark",
    "overrides": {
      "accent": "#ff6b6b"
    }
  }
}
```

Delete `settings.json` to reset everything to factory defaults.

## Tips for a custom palette that works

- **Keep `bg` and `panel` close.** Big contrast between background and
  panels makes the panels look like floating boxes — fine for dashboards,
  busy for a long log feed.
- **Pick `accent` first.** Everything keys off it visually.
- **Keep `text` very high-contrast against `panel`.** Long log sessions
  matter more than the marketing screenshot.
- **`success` / `error` / `warn` / `info` should be distinct enough at a
  glance** — that's the whole point of color-coding logs.
