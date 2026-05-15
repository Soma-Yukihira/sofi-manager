"""
gui.py
Interface premium pour gérer plusieurs selfbots.
Thèmes : preset dark (black & gold), preset light (white & gold), couleurs personnalisables.
"""

from __future__ import annotations

import json
import sys
import threading
import tkinter as tk
import uuid
import webbrowser
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox
from typing import Any, ClassVar, Literal

import customtkinter as ctk

import storage
import updater
from bot_core import SelfBot, default_config, sanitize_config
from crypto import decrypt_token, encrypt_token

WIKI_UPDATING_URL = "https://github.com/Soma-Yukihira/sofi-manager/wiki/Updating-fr"

# =============================================
# PyInstaller-safe paths
# =============================================
#
# Two distinct roots:
#   - BUNDLE_DIR : read-only resources (assets/). Inside the PyInstaller
#     bundle when frozen (sys._MEIPASS), otherwise next to the source.
#   - USER_DIR   : mutable state (bots.json, settings.json). Always next
#     to the exe / source so the user can edit/back up these files.


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _user_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BUNDLE_DIR = _bundle_dir()
USER_DIR = _user_dir()


# =============================================
# THEME — presets & registry
# =============================================

DARK_THEME = {
    "bg": "#0a0a0a",
    "panel": "#141414",
    "panel_hover": "#1c1c1c",
    "panel_selected": "#222018",
    "input_bg": "#1a1a1a",
    "border": "#2a2a2a",
    "accent": "#d4af37",
    "accent_bright": "#f4d03f",
    "accent_dim": "#8b7320",
    "text": "#e8e8e8",
    "text_dim": "#8a8a8a",
    "text_on_accent": "#0a0a0a",
    "success": "#4ade80",
    "error": "#f87171",
    "warn": "#fbbf24",
    "info": "#9ca3af",
    "log_bg": "#050505",
    "dot_off": "#444444",
}

LIGHT_THEME = {
    "bg": "#f4f1ea",
    "panel": "#ffffff",
    "panel_hover": "#f5f3ee",
    "panel_selected": "#fbf3dc",
    "input_bg": "#fafafa",
    "border": "#e5e2da",
    "accent": "#b8860b",
    "accent_bright": "#d4af37",
    "accent_dim": "#8b7320",
    "text": "#1f1f1f",
    "text_dim": "#6b6b6b",
    "text_on_accent": "#1a1a1a",
    "success": "#16a34a",
    "error": "#dc2626",
    "warn": "#d97706",
    "info": "#525252",
    "log_bg": "#fdfcf8",
    "dot_off": "#bdbdbd",
}

PRESETS = {"dark": DARK_THEME, "light": LIGHT_THEME}

# Slots exposés dans la modale de personnalisation
THEME_LABELS = [
    ("bg", "Fond principal"),
    ("panel", "Panneaux / cartes"),
    ("panel_hover", "Panneau survolé"),
    ("panel_selected", "Élément sélectionné"),
    ("input_bg", "Fond des champs"),
    ("border", "Bordures"),
    ("accent", "Accent (titre, bordure)"),
    ("accent_bright", "Accent vif (boutons)"),
    ("accent_dim", "Accent sombre"),
    ("text", "Texte principal"),
    ("text_dim", "Texte secondaire"),
    ("text_on_accent", "Texte sur fond accent"),
    ("log_bg", "Fond des logs"),
    ("success", "Succès"),
    ("error", "Erreur"),
    ("warn", "Avertissement"),
    ("info", "Info"),
]

LEVEL_KEYS = {
    "info": "info",
    "success": "success",
    "error": "error",
    "warn": "warn",
    "system": "accent",
}


CONFIG_PATH = USER_DIR / "bots.json"
SETTINGS_PATH = USER_DIR / "settings.json"


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def load_bots() -> list[dict[str, Any]]:
    if not CONFIG_PATH.exists():
        return []
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            bots: list[dict[str, Any]] = json.load(f).get("bots", [])
        for bot in bots:
            tok = bot.get("token")
            if tok:
                bot["token"] = decrypt_token(tok)
        return bots
    except Exception as e:
        print(f"⚠ Impossible de charger {CONFIG_PATH}: {e}")
        return []


def save_bots(bots: list[dict[str, Any]]) -> None:
    serialised = []
    for bot in bots:
        copy = dict(bot)
        tok = copy.get("token")
        if tok:
            copy["token"] = encrypt_token(tok)
        serialised.append(copy)
    write_json_atomic(CONFIG_PATH, {"bots": serialised})


def load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {"theme": {"mode": "dark", "overrides": {}}}
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("theme", {"mode": "dark", "overrides": {}})
        data["theme"].setdefault("mode", "dark")
        data["theme"].setdefault("overrides", {})
        return data
    except Exception:
        return {"theme": {"mode": "dark", "overrides": {}}}


def save_settings(settings: dict[str, Any]) -> None:
    write_json_atomic(SETTINGS_PATH, settings)


def dedupe_sort(items: Iterable[str]) -> list[str]:
    """Trie alphabétiquement + dédoublonne (insensible à la casse).
    Garde la première casse rencontrée pour les doublons."""
    seen: dict[str, str] = {}
    for item in items:
        if not item:
            continue
        s = item.strip()
        if not s:
            continue
        key = s.casefold()
        if key not in seen:
            seen[key] = s
    return sorted(seen.values(), key=str.casefold)


def contrast_text(hex_color: str) -> str:
    """Retourne #000 ou #fff selon la luminance."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        return "#000000" if lum > 140 else "#ffffff"
    except Exception:
        return "#000000"


class Theme:
    def __init__(self, mode: str = "dark", overrides: dict[str, str] | None = None):
        self.mode = mode if mode in PRESETS else "dark"
        self.overrides = dict(overrides or {})

    @property
    def colors(self) -> dict[str, str]:
        d = dict(PRESETS[self.mode])
        d.update(self.overrides)
        return d

    def __getitem__(self, key: str) -> str:
        return self.colors[key]


# =============================================
# Bot list entry (sidebar)
# =============================================


class BotListEntry(ctk.CTkFrame):
    def __init__(
        self,
        master: Any,
        theme: Theme,
        bot_id: str,
        on_click: Callable[[str], None],
    ):
        super().__init__(master, fg_color=theme["panel"], corner_radius=6, height=52)
        self.theme = theme
        self.bot_id = bot_id
        self.on_click = on_click
        self.selected = False
        self.pack_propagate(False)

        self._dot_color = theme["dot_off"]
        self.dot = tk.Canvas(
            self, width=12, height=12, bg=theme["panel"], highlightthickness=0, bd=0
        )
        self.dot_id = self.dot.create_oval(2, 2, 11, 11, fill=self._dot_color, outline="")
        self.dot.pack(side="left", padx=(14, 10), pady=20)

        self.label = ctk.CTkLabel(
            self,
            text="Bot",
            text_color=theme["text"],
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.label.pack(side="left", fill="x", expand=True, pady=8)

        for w in (self, self.dot, self.label):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _click(self, _e: Any) -> None:
        self.on_click(self.bot_id)

    def _enter(self, _e: Any) -> None:
        if not self.selected:
            self._set_bg(self.theme["panel_hover"])

    def _leave(self, _e: Any) -> None:
        if not self.selected:
            self._set_bg(self.theme["panel"])

    def _set_bg(self, color: str) -> None:
        self.configure(fg_color=color)
        self.dot.configure(bg=color)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._set_bg(self.theme["panel_selected"] if selected else self.theme["panel"])

    def set_name(self, name: str) -> None:
        self.label.configure(text=name or "(sans nom)")

    def set_status(self, status: str) -> None:
        colors = {
            "running": self.theme["success"],
            "starting": self.theme["warn"],
            "error": self.theme["error"],
            "stopped": self.theme["dot_off"],
        }
        self._dot_color = colors.get(status, self.theme["dot_off"])
        self.dot.itemconfig(self.dot_id, fill=self._dot_color)


# =============================================
# Application principale
# =============================================


class SelfbotManagerApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.theme = Theme(
            self.settings["theme"]["mode"],
            self.settings["theme"]["overrides"],
        )

        self.title("⚜  SELFBOT MANAGER")
        self.geometry("1320x820")
        self.minsize(1100, 720)

        # Icône fenêtre + taskbar (Windows : grouping basé sur app id)
        icon_path = BUNDLE_DIR / "assets" / "app.ico"
        if icon_path.exists():
            try:
                self.iconbitmap(default=str(icon_path))
            except Exception:
                pass
            try:
                # Force Windows à utiliser une AppUserModelID dédiée
                # → le taskbar regroupe sous notre icône au lieu de pythonw.exe
                import ctypes

                # `ctypes.windll` only exists on Windows; dual ignore handles
                # both platforms (see cli.py:_enable_windows_vt for details).
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined,unused-ignore]
                    "Soma-Yukihira.SelfbotManager.1"
                )
            except Exception:
                pass

        # bot_id -> {"config", "instance", "entry", "log_widget", "log_scroll", "log_buffer"}
        self.bots: dict[str, dict[str, Any]] = {}
        self.selected_id: str | None = None
        self.cfg_widgets: dict[str, Any] = {}

        # Update banner state. `_update_mode` is "git" for clones (fast-forward
        # pull) or "zip" for ZIP installs (download + overwrite). Dictates which
        # apply path the Restart button takes. `_pending_zip_sha` is the SHA the
        # ZIP banner is offering — persisted to settings.json post-apply so the
        # next launch knows the new baseline.
        self._update_mode: Literal["git", "zip"] | None = None
        self._pending_zip_sha: str | None = None

        self._apply_appearance()
        self._build_layout()
        self._load_existing_bots()

        self.after(120, self._drain_logs)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Discord-style update check: fire-and-forget once the UI is up.
        # The callback marshals back to the Tk thread via `self.after`.
        updater.check_in_background(lambda n: self.after(0, self._show_update_banner, n))

        # ZIP-mode users (no .git/) get a parallel check that polls the
        # GitHub API for the latest main SHA. The skip_reason gate inside
        # `check_zip_in_background` no-ops on git / frozen installs.
        updater.check_zip_in_background(
            installed_sha=self.settings.get("zip_install_sha"),
            on_baseline=lambda sha: self.after(0, self._on_zip_baseline_established, sha),
            on_update_available=lambda sha: self.after(0, self._on_zip_update_available, sha),
        )

        # Frozen .exe installs still need a passive amber banner: we can't
        # atomically swap source files into a running PyInstaller bundle,
        # so the user has to rebuild. Deferred so the layout is settled.
        self.after(0, self._maybe_show_skip_reason_banner)

    # ---------- thème ----------

    def _apply_appearance(self) -> None:
        ctk.set_appearance_mode("light" if self.theme.mode == "light" else "dark")
        self.configure(fg_color=self.theme["bg"])

    # ---------- helpers UI ----------

    def _mk_label(
        self, parent: Any, text: str, dim: bool = False, size: int = 12, bold: bool = False
    ) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent,
            text=text,
            text_color=self.theme["text_dim"] if dim else self.theme["text"],
            font=ctk.CTkFont(size=size, weight="bold" if bold else "normal"),
        )

    def _mk_entry(
        self, parent: Any, show: str | None = None, placeholder: str = ""
    ) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent,
            fg_color=self.theme["input_bg"],
            border_color=self.theme["border"],
            border_width=1,
            text_color=self.theme["text"],
            placeholder_text=placeholder,
            placeholder_text_color=self.theme["text_dim"],
            show=show,
            height=32,
        )

    def _mk_textbox(self, parent: Any, height: int = 120) -> ctk.CTkTextbox:
        return ctk.CTkTextbox(
            parent,
            fg_color=self.theme["input_bg"],
            border_color=self.theme["border"],
            border_width=1,
            text_color=self.theme["text"],
            height=height,
            font=ctk.CTkFont(family="Consolas", size=12),
        )

    def _mk_button(
        self,
        parent: Any,
        text: str,
        command: Callable[[], None] | None = None,
        variant: str = "default",
        width: int = 100,
    ) -> ctk.CTkButton:
        T = self.theme
        base = {
            "text": text,
            "command": command,
            "width": width,
            "height": 32,
            "corner_radius": 4,
            "font": ctk.CTkFont(size=12, weight="bold"),
        }
        if variant == "primary":
            return ctk.CTkButton(
                parent,
                **base,
                fg_color=T["accent"],
                hover_color=T["accent_bright"],
                text_color=T["text_on_accent"],
                border_width=0,
            )
        if variant == "danger":
            return ctk.CTkButton(
                parent,
                **base,
                fg_color=T["panel"],
                hover_color=T["panel_hover"],
                text_color=T["error"],
                border_color=T["error"],
                border_width=1,
            )
        if variant == "ghost":
            return ctk.CTkButton(
                parent,
                **base,
                fg_color="transparent",
                hover_color=T["panel_hover"],
                text_color=T["text_dim"],
                border_width=0,
            )
        return ctk.CTkButton(
            parent,
            **base,
            fg_color=T["panel"],
            hover_color=T["panel_hover"],
            text_color=T["accent"],
            border_color=T["accent_dim"],
            border_width=1,
        )

    def _mk_section(self, parent: Any, title: str) -> ctk.CTkFrame:
        T = self.theme
        wrap = ctk.CTkFrame(
            parent, fg_color=T["panel"], corner_radius=8, border_color=T["border"], border_width=1
        )
        wrap.pack(fill="x", pady=(0, 14), padx=2)

        head = ctk.CTkFrame(wrap, fg_color="transparent", height=42)
        head.pack(fill="x", padx=18, pady=(12, 4))
        ctk.CTkFrame(head, fg_color=T["accent"], width=3, height=16).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            head,
            text=title.upper(),
            text_color=T["accent"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        body = ctk.CTkFrame(wrap, fg_color="transparent")
        body.pack(fill="x", padx=18, pady=(2, 16))
        return body

    # ---------- Layout ----------

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=0, minsize=270)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_panel()

    def _build_sidebar(self) -> None:
        T = self.theme
        side = ctk.CTkFrame(self, fg_color=T["panel"], corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(side, fg_color="transparent", height=80)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(20, 14))
        header.grid_propagate(False)
        ctk.CTkLabel(
            header,
            text="⚜  SELFBOT",
            text_color=T["accent"],
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="MANAGER · PREMIUM",
            text_color=T["text_dim"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(anchor="w")

        self.bot_list = ctk.CTkScrollableFrame(
            side,
            fg_color="transparent",
            scrollbar_button_color=T["accent_dim"],
            scrollbar_button_hover_color=T["accent"],
        )
        self.bot_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)

        footer = ctk.CTkFrame(side, fg_color="transparent", height=70)
        footer.grid(row=2, column=0, sticky="ew", padx=14, pady=(8, 16))
        footer.grid_propagate(False)
        self._mk_button(
            footer,
            "  +  AJOUTER UN BOT  ",
            command=self._add_bot,
            variant="default",
            width=240,
        ).pack(fill="x", pady=4)

    # ---------- Update banner ----------

    def _build_update_banner(self, parent: Any) -> None:
        """
        Gold strip above the top bar, hidden until the updater finds new
        commits on origin/main. The frame is gridded but immediately
        `grid_remove`d - `_show_update_banner` re-reveals it later.
        """
        T = self.theme
        self.update_banner = ctk.CTkFrame(
            parent,
            fg_color=T["accent"],
            corner_radius=0,
            height=38,
        )
        self.update_banner.grid(row=0, column=0, sticky="ew")
        self.update_banner.grid_propagate(False)
        self.update_banner.grid_columnconfigure(0, weight=1)

        self.update_banner_label = ctk.CTkLabel(
            self.update_banner,
            text="",
            text_color=T["text_on_accent"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.update_banner_label.grid(row=0, column=0, sticky="w", padx=18)

        btns = ctk.CTkFrame(self.update_banner, fg_color="transparent")
        btns.grid(row=0, column=1, sticky="e", padx=10, pady=4)
        ctk.CTkButton(
            btns,
            text="Plus tard",
            command=self._dismiss_update_banner,
            fg_color="transparent",
            hover_color=T["accent_bright"],
            text_color=T["text_on_accent"],
            border_width=0,
            width=80,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btns,
            text="Redemarrer",
            command=self._on_update_restart,
            fg_color=T["text_on_accent"],
            hover_color=T["bg"],
            text_color=T["accent"],
            border_width=0,
            width=110,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="right", padx=4)

        self.update_banner.grid_remove()

    def _show_update_banner(self, behind: int) -> None:
        self._update_mode = "git"
        self._pending_zip_sha = None
        msg = (
            f"  Mise a jour disponible  -  {behind} commit"
            f"{'s' if behind > 1 else ''} en attente. Redemarrez pour appliquer."
        )
        try:
            self.update_banner_label.configure(text=msg)
            self.update_banner.grid()
            # Gold > amber: hide the skip-reason banner if it was up.
            if hasattr(self, "skip_banner"):
                self.skip_banner.grid_remove()
        except Exception:
            pass

    def _show_zip_update_banner(self, sha: str) -> None:
        """Variant of the gold banner for ZIP installs. Same look, but the
        Restart button kicks off a codeload download + in-place overwrite
        instead of a git fast-forward."""
        self._update_mode = "zip"
        self._pending_zip_sha = sha
        msg = (
            f"  Mise a jour disponible (mode ZIP) - commit {sha[:7]}. "
            "Redemarrez pour telecharger et appliquer."
        )
        try:
            self.update_banner_label.configure(text=msg)
            self.update_banner.grid()
            if hasattr(self, "skip_banner"):
                self.skip_banner.grid_remove()
        except Exception:
            pass

    def _on_zip_baseline_established(self, sha: str) -> None:
        """First launch on a fresh ZIP install: record the current upstream
        SHA as the baseline. Subsequent launches will compare against it.
        Silent - no banner, since we just adopted whatever the user already
        has as "in sync"."""
        if self.settings.get("zip_install_sha") == sha:
            return
        self.settings["zip_install_sha"] = sha
        try:
            save_settings(self.settings)
        except Exception:
            pass

    def _on_zip_update_available(self, sha: str) -> None:
        self._show_zip_update_banner(sha)

    def _check_updates_now(self) -> None:
        """Manual update check - mirrors the background poller's logic for
        whichever install mode applies, always with explicit feedback
        (banner if behind, messagebox otherwise)."""
        btn = getattr(self, "check_updates_btn", None)
        if btn is not None:
            try:
                btn.configure(state="disabled", text="...")
            except Exception:
                pass

        zip_mode = updater.skip_reason() == "no-git"
        installed_sha = self.settings.get("zip_install_sha") if zip_mode else None

        def _worker() -> None:
            try:
                if zip_mode:
                    remote = updater.fetch_remote_main_sha()
                    if remote is None:
                        result: dict[str, Any] = {"state": "fetch_failed", "behind": 0}
                    elif installed_sha is None or installed_sha == remote:
                        result = {"state": "uptodate", "behind": 0, "sha": remote}
                    else:
                        result = {"state": "available_zip", "behind": 0, "sha": remote}
                else:
                    result = updater.fetch_and_status()
            except Exception as e:
                result = {"state": "error", "behind": 0, "err": str(e)}
            self.after(0, self._on_check_updates_result, result)

        threading.Thread(target=_worker, name="updater-manual", daemon=True).start()

    def _on_check_updates_result(self, result: dict[str, Any]) -> None:
        btn = getattr(self, "check_updates_btn", None)
        if btn is not None:
            try:
                btn.configure(state="normal", text="↻  MAJ")
            except Exception:
                pass

        state = result.get("state", "error")
        n = int(result.get("behind", 0) or 0)
        if state == "available" and n > 0:
            self._show_update_banner(n)
            return
        if state == "available_zip":
            sha = result.get("sha")
            if isinstance(sha, str):
                # On ZIP installs with no recorded baseline, this can fire on
                # the very first manual check; treat it the same as if the
                # background path had detected drift.
                if self.settings.get("zip_install_sha") is None:
                    self.settings["zip_install_sha"] = sha
                    try:
                        save_settings(self.settings)
                    except Exception:
                        pass
                    messagebox.showinfo("Mise a jour", "Vous etes a jour.")
                    return
                self._show_zip_update_banner(sha)
                return

        messages = {
            "uptodate": ("Mise a jour", "Vous etes a jour."),
            "not_git": ("Mise a jour", "Installation sans .git : MAJ automatique desactivee."),
            "fetch_failed": (
                "Mise a jour",
                "Echec du fetch (hors-ligne, git absent ou API GitHub injoignable).",
            ),
            "dirty": ("Mise a jour", "Modifications locales en cours : commit ou stash requis."),
            "ahead": (
                "Mise a jour",
                "Commits locaux en avance sur origin/main : push ou reset requis.",
            ),
            "error": ("Mise a jour", "Erreur : " + str(result.get("err") or "inconnue")),
        }
        title, msg = messages.get(state, ("Mise a jour", "Etat inconnu."))
        if state == "uptodate":
            messagebox.showinfo(title, msg)
        elif state in ("fetch_failed", "error"):
            messagebox.showerror(title, msg)
        else:
            messagebox.showwarning(title, msg)

    def _dismiss_update_banner(self) -> None:
        try:
            self.update_banner.grid_remove()
        except Exception:
            pass

    # ---------- Skip-reason banner ----------

    # Reasons that warrant a passive banner. Dev cases ("off-main", "dirty",
    # "ahead") are intentionally excluded: devs are already aware, and
    # `_check_updates_now` surfaces them on demand.
    # `no-git` is intentionally absent: ZIP installs are now handled by
    # the codeload fallback (`updater.apply_zip_update`). Only the frozen
    # case is structurally un-updatable and keeps the passive banner.
    _SKIP_BANNER_REASONS: ClassVar[dict[str, str]] = {
        "frozen": (
            "  Installation .exe : les mises a jour automatiques sont desactivees. "
            "Telechargez la derniere version pour rester a jour."
        ),
    }

    def _build_skip_reason_banner(self, parent: Any) -> None:
        """
        Amber strip above the top bar, hidden until the updater reports it
        cannot fast-forward this install. Same grid slot as the gold update
        banner - the two are mutually exclusive (gold takes priority).
        """
        T = self.theme
        self.skip_banner = ctk.CTkFrame(
            parent,
            fg_color=T["warn"],
            corner_radius=0,
            height=38,
        )
        self.skip_banner.grid(row=0, column=0, sticky="ew")
        self.skip_banner.grid_propagate(False)
        self.skip_banner.grid_columnconfigure(0, weight=1)

        self.skip_banner_label = ctk.CTkLabel(
            self.skip_banner,
            text="",
            text_color=T["text_on_accent"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.skip_banner_label.grid(row=0, column=0, sticky="w", padx=18)

        btns = ctk.CTkFrame(self.skip_banner, fg_color="transparent")
        btns.grid(row=0, column=1, sticky="e", padx=10, pady=4)
        ctk.CTkButton(
            btns,
            text="Plus tard",
            command=self._dismiss_skip_reason_banner,
            fg_color="transparent",
            hover_color=T["accent_bright"],
            text_color=T["text_on_accent"],
            border_width=0,
            width=80,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            btns,
            text="Aide",
            command=self._on_skip_reason_help,
            fg_color=T["text_on_accent"],
            hover_color=T["bg"],
            text_color=T["warn"],
            border_width=0,
            width=80,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="right", padx=4)

        self.skip_banner.grid_remove()

    def _maybe_show_skip_reason_banner(self) -> None:
        try:
            reason = updater.skip_reason()
        except Exception:
            return
        if reason not in self._SKIP_BANNER_REASONS:
            return
        # Defer to gold if it is already visible (it just arrived async).
        try:
            if self.update_banner.winfo_ismapped():
                return
            self.skip_banner_label.configure(text=self._SKIP_BANNER_REASONS[reason])
            self.skip_banner.grid()
        except Exception:
            pass

    def _dismiss_skip_reason_banner(self) -> None:
        try:
            self.skip_banner.grid_remove()
        except Exception:
            pass

    def _on_skip_reason_help(self) -> None:
        try:
            webbrowser.open(WIKI_UPDATING_URL, new=2)
        except Exception:
            messagebox.showinfo("Aide", WIKI_UPDATING_URL)

    def _on_update_restart(self) -> None:
        # Persist current form/state before re-execing, just like _on_close.
        if self.selected_id:
            try:
                self._collect_form_into_config(self.selected_id)
            except Exception:
                pass
        self._persist()
        save_settings(self.settings)

        def _do_git_restart() -> None:
            ok, msg = updater.apply_and_restart()
            if not ok:
                messagebox.showerror("Mise a jour", msg)

        def _do_zip_restart() -> None:
            # Network + extract can take seconds; run off the Tk thread.
            def _worker() -> None:
                ok, msg, new_sha = updater.apply_zip_update()
                if not ok or new_sha is None:
                    self.after(0, lambda: messagebox.showerror("Mise a jour", msg))
                    return
                # Record the new baseline BEFORE re-exec so the next launch
                # doesn't immediately re-prompt for the same update.
                self.settings["zip_install_sha"] = new_sha
                try:
                    save_settings(self.settings)
                except Exception:
                    pass
                updater._restart()

            threading.Thread(target=_worker, name="updater-zip-apply", daemon=True).start()

        finalize = _do_zip_restart if self._update_mode == "zip" else _do_git_restart
        # Stop bots off the Tk thread so the banner doesn't freeze before re-exec.
        self._stop_all_async(then=finalize)

    def _build_main_panel(self) -> None:
        T = self.theme
        main = ctk.CTkFrame(self, fg_color=T["bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        # --- Update banner (hidden until updater finds new commits) ---
        self._build_update_banner(main)
        # --- Skip-reason banner (hidden unless .exe / no-git install) ---
        self._build_skip_reason_banner(main)

        # --- Top bar ---
        top = ctk.CTkFrame(main, fg_color=T["panel"], corner_radius=0, height=72)
        top.grid(row=1, column=0, sticky="ew")
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)

        # Status indicator
        status_box = ctk.CTkFrame(top, fg_color="transparent")
        status_box.grid(row=0, column=0, padx=22, pady=18, sticky="w")
        self.status_dot = tk.Canvas(
            status_box, width=14, height=14, bg=T["panel"], highlightthickness=0, bd=0
        )
        self.status_dot_id = self.status_dot.create_oval(
            2, 2, 13, 13, fill=T["dot_off"], outline=""
        )
        self.status_dot.pack(side="left", padx=(0, 10), pady=10)
        self.status_label = ctk.CTkLabel(
            status_box,
            text="—",
            text_color=T["text_dim"],
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status_label.pack(side="left")

        # Theme controls (centre-droit)
        theme_box = ctk.CTkFrame(top, fg_color="transparent")
        theme_box.grid(row=0, column=1, padx=10, pady=18, sticky="e")
        toggle_text = "☀  Clair" if self.theme.mode == "dark" else "🌙  Sombre"
        self._mk_button(
            theme_box, toggle_text, command=self._toggle_theme, variant="default", width=100
        ).pack(side="right", padx=4)
        self._mk_button(
            theme_box,
            "🎨  Couleurs",
            command=self._open_theme_customizer,
            variant="ghost",
            width=110,
        ).pack(side="right", padx=4)
        self.check_updates_btn = self._mk_button(
            theme_box,
            "↻  MAJ",
            command=self._check_updates_now,
            variant="ghost",
            width=90,
        )
        self.check_updates_btn.pack(side="right", padx=4)

        # Action buttons
        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.grid(row=0, column=2, padx=20, pady=18, sticky="e")
        self.save_btn = self._mk_button(
            actions, "Sauvegarder", command=self._save_current, width=120
        )
        self.delete_btn = self._mk_button(
            actions, "Supprimer", command=self._delete_current, variant="danger", width=110
        )
        self.stop_btn = self._mk_button(
            actions, "■ Arrêter", command=self._stop_current, variant="danger", width=110
        )
        self.start_btn = self._mk_button(
            actions, "▶ Démarrer", command=self._start_current, variant="primary", width=130
        )
        self.start_btn.pack(side="right", padx=8)
        self.stop_btn.pack(side="right", padx=8)
        self.delete_btn.pack(side="right", padx=8)
        self.save_btn.pack(side="right", padx=(8, 0))

        # --- Tabview ---
        self.tabs = ctk.CTkTabview(
            main,
            fg_color=T["bg"],
            segmented_button_fg_color=T["panel"],
            segmented_button_selected_color=T["accent"],
            segmented_button_selected_hover_color=T["accent_bright"],
            segmented_button_unselected_color=T["panel"],
            segmented_button_unselected_hover_color=T["panel_hover"],
            text_color=T["text"],
            text_color_disabled=T["text_dim"],
        )
        self.tabs.grid(row=2, column=0, sticky="nsew", padx=24, pady=(18, 24))
        self.tabs.configure(command=self._on_tab_changed)

        self.tab_config = self.tabs.add("  Configuration  ")
        self.tab_wishlist = self.tabs.add("  Wishlist  ")
        self.tab_logs = self.tabs.add("  Logs  ")
        self.tab_stats = self.tabs.add("  Stats  ")

        self._stats_refresh_after_id: str | None = None
        self._build_config_tab()
        self._build_wishlist_tab()
        self._build_logs_tab()
        self._build_stats_tab()
        self._show_empty_state()

    # ---------- Config tab ----------

    def _build_config_tab(self) -> None:
        T = self.theme
        scroll = ctk.CTkScrollableFrame(
            self.tab_config,
            fg_color="transparent",
            scrollbar_button_color=T["accent_dim"],
            scrollbar_button_hover_color=T["accent"],
        )
        scroll.pack(fill="both", expand=True, padx=4, pady=10)

        sec = self._mk_section(scroll, "Identité")
        self._add_field(sec, "name", "Nom du bot", placeholder="ex: Mon compte principal")
        self._add_field(sec, "token", "Token Discord", placeholder="Coller le token ici", show="•")

        sec = self._mk_section(scroll, "Channels")
        self._add_field(
            sec,
            "drop_channel",
            "ID du salon de drop",
            placeholder="123456789012345678",
            numeric=True,
        )
        self._add_textarea(
            sec,
            "all_channels",
            "Salons écoutés (un ID par ligne — le drop channel est inclus auto)",
            height=110,
        )
        self._add_field(sec, "message", "Commande envoyée", placeholder="sd")

        sec = self._mk_section(scroll, "Timing des drops")
        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", pady=(4, 6))
        row.grid_columnconfigure((0, 1), weight=1, uniform="t")
        self._add_field_grid(row, 0, "interval_min", "Intervalle min (s)", numeric=True)
        self._add_field_grid(row, 1, "interval_max", "Intervalle max (s)", numeric=True)

        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure((0, 1), weight=1, uniform="t")
        self._add_field_grid(row, 0, "cooldown_extra_min", "Cooldown extra min (s)", numeric=True)
        self._add_field_grid(row, 1, "cooldown_extra_max", "Cooldown extra max (s)", numeric=True)

        sec = self._mk_section(scroll, "Pause nocturne")
        toggle_row = ctk.CTkFrame(sec, fg_color="transparent")
        toggle_row.pack(fill="x", pady=(2, 8))
        self.cfg_widgets["night_pause_enabled"] = ctk.CTkSwitch(
            toggle_row,
            text="Activer la pause nocturne (22h–01h)",
            text_color=T["text"],
            progress_color=T["accent"],
            button_color=T["accent_bright"],
            button_hover_color=T["accent"],
            fg_color=T["border"],
            font=ctk.CTkFont(size=12),
        )
        self.cfg_widgets["night_pause_enabled"].pack(anchor="w")

        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure((0, 1), weight=1, uniform="t")
        self._add_field_grid(row, 0, "pause_duration_min", "Durée min (h)", numeric=True)
        self._add_field_grid(row, 1, "pause_duration_max", "Durée max (h)", numeric=True)

        sec = self._mk_section(scroll, "Scoring")
        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure((0, 1), weight=1, uniform="t")
        self._add_field_grid(row, 0, "score_rarity_weight", "Poids rareté (0–1)", numeric=True)
        self._add_field_grid(row, 1, "score_hearts_weight", "Poids hearts (0–1)", numeric=True)

        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure((0, 1, 2), weight=1, uniform="t")
        self._add_field_grid(row, 0, "rarity_norm", "Norm rareté", numeric=True)
        self._add_field_grid(row, 1, "hearts_norm", "Norm hearts", numeric=True)
        self._add_field_grid(
            row, 2, "wishlist_override_threshold", "Seuil override wishlist", numeric=True
        )

    def _add_field(
        self,
        parent: Any,
        key: str,
        label: str,
        placeholder: str = "",
        show: str | None = None,
        numeric: bool = False,
    ) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=4)
        self._mk_label(wrap, label, dim=True, size=11).pack(anchor="w", pady=(0, 4))
        e = self._mk_entry(wrap, show=show, placeholder=placeholder)
        e.pack(fill="x")
        e._numeric = numeric
        self.cfg_widgets[key] = e

    def _add_field_grid(
        self, parent: Any, col: int, key: str, label: str, numeric: bool = False
    ) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.grid(row=0, column=col, padx=(0 if col == 0 else 8, 0), sticky="ew")
        self._mk_label(wrap, label, dim=True, size=11).pack(anchor="w", pady=(0, 4))
        e = self._mk_entry(wrap)
        e.pack(fill="x")
        e._numeric = numeric
        self.cfg_widgets[key] = e

    def _add_textarea(self, parent: Any, key: str, label: str, height: int = 120) -> None:
        wrap = ctk.CTkFrame(parent, fg_color="transparent")
        wrap.pack(fill="x", pady=4)
        self._mk_label(wrap, label, dim=True, size=11).pack(anchor="w", pady=(0, 4))
        t = self._mk_textbox(wrap, height=height)
        t.pack(fill="x")
        self.cfg_widgets[key] = t

    # ---------- Wishlist tab ----------

    def _build_wishlist_tab(self) -> None:
        T = self.theme
        wrap = ctk.CTkFrame(self.tab_wishlist, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=4, pady=10)
        wrap.grid_columnconfigure((0, 1), weight=1, uniform="w")
        wrap.grid_rowconfigure(0, weight=1)

        for col, (attr, title, hint) in enumerate(
            [
                (
                    "wishlist_persos",
                    "WISHLIST · PERSONNAGES",
                    "Un nom par ligne (trié auto à la sauvegarde)",
                ),
                (
                    "wishlist_series",
                    "WISHLIST · SÉRIES",
                    "Une série par ligne (trié auto à la sauvegarde)",
                ),
            ]
        ):
            col_frame = ctk.CTkFrame(
                wrap,
                fg_color=T["panel"],
                corner_radius=8,
                border_color=T["border"],
                border_width=1,
            )
            col_frame.grid(row=0, column=col, sticky="nsew", padx=(0, 8) if col == 0 else (8, 0))
            head = ctk.CTkFrame(col_frame, fg_color="transparent")
            head.pack(fill="x", padx=18, pady=(14, 6))
            ctk.CTkFrame(head, fg_color=T["accent"], width=3, height=16).pack(
                side="left", padx=(0, 10)
            )
            ctk.CTkLabel(
                head, text=title, text_color=T["accent"], font=ctk.CTkFont(size=12, weight="bold")
            ).pack(side="left")
            self._mk_label(col_frame, hint, dim=True, size=10).pack(
                anchor="w", padx=18, pady=(0, 4)
            )
            tb = self._mk_textbox(col_frame, height=400)
            tb.pack(fill="both", expand=True, padx=18, pady=(4, 16))
            setattr(self, attr, tb)

    # ---------- Logs tab ----------

    def _build_logs_tab(self) -> None:
        T = self.theme
        self.logs_container = ctk.CTkFrame(
            self.tab_logs,
            fg_color=T["panel"],
            corner_radius=8,
            border_color=T["border"],
            border_width=1,
        )
        self.logs_container.pack(fill="both", expand=True, padx=4, pady=10)

        head = ctk.CTkFrame(self.logs_container, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkFrame(head, fg_color=T["accent"], width=3, height=16).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            head,
            text="LOGS EN DIRECT",
            text_color=T["accent"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        self._mk_button(
            head, "Effacer", command=self._clear_current_logs, variant="ghost", width=80
        ).pack(side="right")

        self.logs_holder = ctk.CTkFrame(self.logs_container, fg_color="transparent")
        self.logs_holder.pack(fill="both", expand=True, padx=18, pady=(4, 16))

        self.logs_placeholder = ctk.CTkLabel(
            self.logs_holder,
            text="Sélectionnez un bot pour voir ses logs",
            text_color=T["text_dim"],
            font=ctk.CTkFont(size=12),
        )
        self.logs_placeholder.pack(expand=True)

    def _make_log_widget(self) -> tuple[tk.Text, ctk.CTkScrollbar]:
        T = self.theme
        tb = tk.Text(
            self.logs_holder,
            bg=T["log_bg"],
            fg=T["text"],
            insertbackground=T["accent"],
            selectbackground=T["accent_dim"],
            font=("Consolas", 11),
            wrap="word",
            relief="flat",
            borderwidth=0,
            padx=12,
            pady=10,
        )
        for level, key in LEVEL_KEYS.items():
            tb.tag_configure(level, foreground=T[key])
        tb.tag_configure("system", foreground=T["accent_bright"], font=("Consolas", 11, "bold"))

        sb = ctk.CTkScrollbar(
            self.logs_holder,
            command=tb.yview,
            button_color=T["accent_dim"],
            button_hover_color=T["accent"],
        )
        tb.configure(yscrollcommand=sb.set, state="disabled")
        return tb, sb

    # ---------- Stats tab ----------

    def _build_stats_tab(self) -> None:
        T = self.theme
        wrap = ctk.CTkFrame(self.tab_stats, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=4, pady=10)

        # Header
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", pady=(0, 12))
        ctk.CTkFrame(head, fg_color=T["accent"], width=3, height=16).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            head,
            text="STATISTIQUES DES GRABS",
            text_color=T["accent"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        # Reverse pack order: ↻ Refresh ends up rightmost, filter dropdown leftmost.
        self._mk_button(
            head,
            "↻  Refresh",
            command=self._refresh_stats,
            variant="ghost",
            width=90,
        ).pack(side="right")
        self._mk_button(
            head,
            "↓  CSV",
            command=self._export_stats_csv,
            variant="ghost",
            width=80,
        ).pack(side="right", padx=(0, 4))
        self._stats_filter_all = "Tous les bots"
        self.stats_bot_filter_var = tk.StringVar(value=self._stats_filter_all)
        self.stats_bot_filter = ctk.CTkOptionMenu(
            head,
            values=[self._stats_filter_all],
            variable=self.stats_bot_filter_var,
            command=lambda _v: self._refresh_stats(),
            width=180,
            height=28,
            corner_radius=4,
            fg_color=T["panel"],
            button_color=T["accent_dim"],
            button_hover_color=T["accent"],
            text_color=T["text"],
            dropdown_fg_color=T["panel"],
            dropdown_hover_color=T["panel_hover"],
            dropdown_text_color=T["text"],
            font=ctk.CTkFont(size=11),
            dropdown_font=ctk.CTkFont(size=11),
        )
        self.stats_bot_filter.pack(side="right", padx=(0, 8))

        # KPI row
        self.stats_kpi_widgets: dict[str, ctk.CTkLabel] = {}
        kpi_row = ctk.CTkFrame(wrap, fg_color="transparent")
        kpi_row.pack(fill="x", pady=(0, 14))
        for col, (key, title) in enumerate(
            [
                ("total", "TOTAL GRABS"),
                ("success_rate", "SUCCESS RATE"),
                ("top_series", "TOP 3 SÉRIES"),
                ("top_rarities", "TOP 3 RARETÉS"),
            ]
        ):
            kpi_row.grid_columnconfigure(col, weight=1, uniform="kpi")
            card = ctk.CTkFrame(
                kpi_row,
                fg_color=T["panel"],
                corner_radius=8,
                border_color=T["border"],
                border_width=1,
            )
            card.grid(row=0, column=col, sticky="nsew", padx=4, pady=0)
            ctk.CTkLabel(
                card,
                text=title,
                text_color=T["text_dim"],
                font=ctk.CTkFont(size=10, weight="bold"),
            ).pack(anchor="w", padx=14, pady=(12, 2))
            value = ctk.CTkLabel(
                card,
                text="—",
                text_color=T["accent"],
                font=ctk.CTkFont(size=22, weight="bold"),
                justify="left",
                anchor="w",
            )
            value.pack(anchor="w", fill="x", padx=14, pady=(0, 14))
            self.stats_kpi_widgets[key] = value

        # Chart panel
        chart_panel = ctk.CTkFrame(
            wrap,
            fg_color=T["panel"],
            corner_radius=8,
            border_color=T["border"],
            border_width=1,
        )
        chart_panel.pack(fill="both", expand=True, pady=(0, 0))

        chart_head = ctk.CTkFrame(chart_panel, fg_color="transparent")
        chart_head.pack(fill="x", padx=18, pady=(14, 6))
        ctk.CTkFrame(chart_head, fg_color=T["accent"], width=3, height=16).pack(
            side="left", padx=(0, 10)
        )
        ctk.CTkLabel(
            chart_head,
            text="GRABS / JOUR (14 DERNIERS JOURS)",
            text_color=T["accent"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            chart_head,
            text="cliquez une barre pour voir les grabs du jour",
            text_color=T["text_dim"],
            font=ctk.CTkFont(size=10, slant="italic"),
        ).pack(side="right")

        # Plain tk.Canvas — CustomTkinter has no chart widget. ~30 lines of
        # bar-drawing keeps the bundle slim (no matplotlib in PyInstaller).
        self.stats_canvas = tk.Canvas(
            chart_panel,
            bg=T["panel"],
            highlightthickness=0,
            height=240,
        )
        self.stats_canvas.pack(fill="both", expand=True, padx=18, pady=(4, 16))
        self.stats_canvas.bind("<Configure>", lambda _e: self._redraw_stats_chart())
        self.stats_canvas.bind("<Button-1>", self._on_stats_chart_click)

        # Cached so resizes / refreshes can redraw without re-querying SQLite.
        self._stats_last: storage.Stats | None = None
        # Hit-test boxes populated by _redraw_stats_chart: (x0, x1, bucket_ts).
        self._stats_bar_hits: list[tuple[float, float, int]] = []

    def _on_tab_changed(self) -> None:
        if not hasattr(self, "tabs"):
            return
        if self.tabs.get().strip() == "Stats":
            self._refresh_stats()
            self._schedule_stats_refresh()
        elif self._stats_refresh_after_id is not None:
            try:
                self.after_cancel(self._stats_refresh_after_id)
            except Exception:
                pass
            self._stats_refresh_after_id = None

    def _schedule_stats_refresh(self) -> None:
        if self._stats_refresh_after_id is not None:
            try:
                self.after_cancel(self._stats_refresh_after_id)
            except Exception:
                pass
        self._stats_refresh_after_id = self.after(30_000, self._tick_stats_refresh)

    def _tick_stats_refresh(self) -> None:
        self._stats_refresh_after_id = None
        if hasattr(self, "tabs") and self.tabs.get().strip() == "Stats":
            self._refresh_stats()
            self._schedule_stats_refresh()

    def _current_bot_filter(self) -> str | None:
        """`None` → tous les bots, sinon le label sélectionné dans le dropdown."""
        selected = self.stats_bot_filter_var.get()
        if selected == self._stats_filter_all:
            return None
        return selected

    def _sync_bot_filter_values(self) -> None:
        """Refresh dropdown options from the DB, preserving selection if possible."""
        try:
            labels = storage.distinct_bot_labels()
        except Exception:
            labels = []
        values = [self._stats_filter_all, *labels]
        current = self.stats_bot_filter_var.get()
        self.stats_bot_filter.configure(values=values)
        if current not in values:
            self.stats_bot_filter_var.set(self._stats_filter_all)

    def _refresh_stats(self) -> None:
        self._sync_bot_filter_values()
        bot_filter = self._current_bot_filter()
        try:
            records = list(storage.iter_grabs(bot_label=bot_filter))
        except Exception as e:
            self.stats_kpi_widgets["total"].configure(text="—")
            self.stats_kpi_widgets["success_rate"].configure(text=f"DB error\n{type(e).__name__}")
            self.stats_kpi_widgets["top_series"].configure(text="—")
            self.stats_kpi_widgets["top_rarities"].configure(text="—")
            self._stats_last = None
            self._redraw_stats_chart()
            return

        stats = storage.compute_stats(records)
        self._stats_last = stats

        if stats.total == 0:
            self.stats_kpi_widgets["total"].configure(text="0")
            self.stats_kpi_widgets["success_rate"].configure(text="—")
            self.stats_kpi_widgets["top_series"].configure(text="aucun grab\nenregistré")
            self.stats_kpi_widgets["top_rarities"].configure(text="—")
        else:
            self.stats_kpi_widgets["total"].configure(text=f"{stats.total}")
            self.stats_kpi_widgets["success_rate"].configure(
                text=f"{stats.success_rate * 100:.0f}%"
            )
            self.stats_kpi_widgets["top_series"].configure(
                text=self._format_top(stats.top_series),
            )
            self.stats_kpi_widgets["top_rarities"].configure(
                text=self._format_top(stats.top_rarities),
            )
        self._redraw_stats_chart()

    @staticmethod
    def _format_top(items: list[tuple[str, int]]) -> str:
        if not items:
            return "—"
        # Trim long series names so the KPI card stays compact.
        return "\n".join(
            f"{(name[:18] + '…') if len(name) > 19 else name} · {n}" for name, n in items
        )

    def _redraw_stats_chart(self) -> None:
        if not hasattr(self, "stats_canvas"):
            return
        canvas = self.stats_canvas
        canvas.delete("all")
        self._stats_bar_hits = []
        T = self.theme

        width = max(canvas.winfo_width(), 200)
        height = max(canvas.winfo_height(), 80)

        if self._stats_last is None or not self._stats_last.daily_counts:
            canvas.create_text(
                width / 2,
                height / 2,
                text="aucune donnée",
                fill=T["text_dim"],
                font=("Segoe UI", 11),
            )
            return

        daily = self._stats_last.daily_counts
        max_count = max((c for _, c in daily), default=0)

        pad_left, pad_right = 36, 16
        pad_top, pad_bottom = 16, 28
        plot_w = max(width - pad_left - pad_right, 50)
        plot_h = max(height - pad_top - pad_bottom, 40)
        n = len(daily)
        gap = 6
        bar_w = max((plot_w - gap * (n - 1)) / n, 4)

        # Y-axis baseline
        canvas.create_line(
            pad_left,
            pad_top + plot_h,
            pad_left + plot_w,
            pad_top + plot_h,
            fill=T["border"],
        )

        if max_count == 0:
            canvas.create_text(
                pad_left + plot_w / 2,
                pad_top + plot_h / 2,
                text="0 grab sur la fenêtre",
                fill=T["text_dim"],
                font=("Segoe UI", 11),
            )
            return

        for i, (bucket_ts, count) in enumerate(daily):
            x0 = pad_left + i * (bar_w + gap)
            x1 = x0 + bar_w
            bar_h = (count / max_count) * plot_h if max_count else 0
            y0 = pad_top + plot_h - bar_h
            y1 = pad_top + plot_h
            color = T["accent"] if count else T["panel_hover"]
            canvas.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
            # Hit-test box spans the full plot height — clicking above an empty
            # bar still opens the day modal ("aucun grab" is useful feedback).
            self._stats_bar_hits.append((x0, x1, bucket_ts))
            if count:
                canvas.create_text(
                    (x0 + x1) / 2,
                    y0 - 8,
                    text=str(count),
                    fill=T["text"],
                    font=("Segoe UI", 9, "bold"),
                )
            # X-axis label every other day to avoid crowding.
            if i % 2 == 0 or i == n - 1:
                label = datetime.fromtimestamp(bucket_ts).strftime("%d/%m")
                canvas.create_text(
                    (x0 + x1) / 2,
                    y1 + 12,
                    text=label,
                    fill=T["text_dim"],
                    font=("Segoe UI", 9),
                )

    def _on_stats_chart_click(self, event: tk.Event[tk.Misc]) -> None:
        for x0, x1, bucket_ts in self._stats_bar_hits:
            if x0 <= event.x <= x1:
                self._open_grabs_for_day(bucket_ts)
                return

    def _open_grabs_for_day(self, bucket_ts: int) -> None:
        T = self.theme
        day_start = bucket_ts
        day_end = bucket_ts + 86_399  # inclusive upper bound for iter_grabs
        day_str = datetime.fromtimestamp(bucket_ts).strftime("%d/%m/%Y")
        bot_filter = self._current_bot_filter()

        win = ctk.CTkToplevel(self)
        scope = bot_filter or "tous bots"
        win.title(f"Grabs du {day_str} — {scope}")
        win.geometry("720x460")
        win.configure(fg_color=T["bg"])
        win.transient(self)
        try:
            win.grab_set()
        except Exception:
            pass

        head = ctk.CTkFrame(win, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 6))
        ctk.CTkFrame(head, fg_color=T["accent"], width=3, height=16).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            head,
            text=f"GRABS DU {day_str}  ·  {scope.upper()}",
            text_color=T["accent"],
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        body = ctk.CTkTextbox(
            win,
            fg_color=T["panel"],
            text_color=T["text"],
            border_color=T["border"],
            border_width=1,
            corner_radius=6,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="none",
        )
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        try:
            records = list(
                storage.iter_grabs(
                    bot_label=bot_filter,
                    since_ts=day_start,
                    until_ts=day_end,
                )
            )
        except Exception as e:
            body.insert("end", f"Erreur DB : {type(e).__name__} — {e}\n")
            body.configure(state="disabled")
            return

        if not records:
            body.insert("end", "Aucun grab enregistré ce jour.\n")
            body.configure(state="disabled")
            return

        ok_count = sum(1 for r in records if r.success)
        body.insert(
            "end",
            f"{len(records)} tentatives — {ok_count} succès, {len(records) - ok_count} échecs\n",
        )
        body.insert("end", "-" * 96 + "\n")
        # iter_grabs returns newest first; flip to chronological for readability.
        for r in reversed(records):
            t = datetime.fromtimestamp(r.ts).strftime("%H:%M:%S")
            mark = "✓" if r.success else "✗"
            if r.success:
                body.insert(
                    "end",
                    f"{t}  {mark}  {r.bot_label:<10}  "
                    f"{(r.card_name or '-'):<26}  "
                    f"[{(r.series or '-'):<18}]  "
                    f"{(r.rarity or '-'):<4}  "
                    f"♥{r.hearts if r.hearts is not None else '-'}\n",
                )
            else:
                body.insert(
                    "end",
                    f"{t}  {mark}  {r.bot_label:<10}  err={r.error_code or '?'}\n",
                )
        body.configure(state="disabled")

    def _export_stats_csv(self) -> None:
        default_name = f"sofi-grabs-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        scope = self._current_bot_filter()
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Exporter les grabs en CSV",
            defaultextension=".csv",
            initialfile=default_name,
            filetypes=[("CSV", "*.csv"), ("Tous fichiers", "*.*")],
        )
        if not path:
            return
        try:
            records = list(storage.iter_grabs(bot_label=scope))
        except Exception as e:
            messagebox.showerror("Export CSV", f"Lecture DB impossible : {type(e).__name__}\n{e}")
            return
        try:
            # utf-8-sig so Excel detects the encoding without prompting.
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                n = storage.export_csv(records, f)
        except OSError as e:
            messagebox.showerror("Export CSV", f"Écriture impossible : {e}")
            return
        scope_str = scope or "tous bots"
        messagebox.showinfo(
            "Export CSV",
            f"{n} grabs exportés ({scope_str}).\n\n{path}",
        )

    # ---------- Empty / select state ----------

    def _show_empty_state(self) -> None:
        self.status_label.configure(
            text="—  Aucun bot sélectionné", text_color=self.theme["text_dim"]
        )
        self.status_dot.itemconfig(self.status_dot_id, fill=self.theme["dot_off"])
        for btn in (self.start_btn, self.stop_btn, self.delete_btn, self.save_btn):
            btn.configure(state="disabled")

    def _refresh_action_buttons(self) -> None:
        if not self.selected_id:
            self._show_empty_state()
            return
        bot = self.bots[self.selected_id]
        for btn in (self.start_btn, self.stop_btn, self.delete_btn, self.save_btn):
            btn.configure(state="normal")
        instance = bot.get("instance")
        running = instance and instance.status in (SelfBot.STATUS_RUNNING, SelfBot.STATUS_STARTING)
        self.start_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")

        status = instance.status if instance else "stopped"
        self._update_status_header(status)

    def _update_status_header(self, status: str) -> None:
        T = self.theme
        labels = {
            "running": ("●  EN MARCHE", T["success"]),
            "starting": ("●  CONNEXION…", T["warn"]),
            "error": ("●  ERREUR", T["error"]),
            "stopped": ("●  ARRÊTÉ", T["text_dim"]),
        }
        text, color = labels.get(status, ("—", T["text_dim"]))
        self.status_label.configure(text=text, text_color=color)
        dot_color = {
            "running": T["success"],
            "starting": T["warn"],
            "error": T["error"],
            "stopped": T["dot_off"],
        }.get(status, T["dot_off"])
        self.status_dot.itemconfig(self.status_dot_id, fill=dot_color)

    # ---------- Bot list & selection ----------

    def _load_existing_bots(self) -> None:
        for cfg in load_bots():
            # tri à l'import
            sanitize_config(cfg)
            cfg["wishlist"] = dedupe_sort(cfg.get("wishlist", []))
            cfg["wishlist_series"] = dedupe_sort(cfg.get("wishlist_series", []))
            self._register_bot(cfg)

    def _register_bot(
        self,
        cfg: dict[str, Any],
        log_buffer: list[tuple[str, str]] | None = None,
        instance: SelfBot | None = None,
    ) -> str:
        bot_id = cfg.get("_id") or str(uuid.uuid4())
        cfg["_id"] = bot_id

        entry = BotListEntry(self.bot_list, self.theme, bot_id, on_click=self._select_bot)
        entry.pack(fill="x", pady=4, padx=2)
        entry.set_name(cfg.get("name", "Sans nom"))
        if instance:
            entry.set_status(instance.status)
            instance.status_callback = lambda s, bid=bot_id: self.after(
                0, lambda: self._on_bot_status_change(bid, s)
            )

        self.bots[bot_id] = {
            "config": cfg,
            "instance": instance,
            "entry": entry,
            "log_widget": None,
            "log_scroll": None,
            "log_buffer": log_buffer if log_buffer is not None else [],
        }
        return bot_id

    def _add_bot(self) -> None:
        cfg = default_config()
        bot_id = self._register_bot(cfg)
        self._select_bot(bot_id)
        self._persist()

    def _select_bot(self, bot_id: str) -> None:
        if self.selected_id and self.selected_id in self.bots:
            self._collect_form_into_config(self.selected_id)
            self.bots[self.selected_id]["entry"].set_selected(False)

        self.selected_id = bot_id
        bot = self.bots[bot_id]
        bot["entry"].set_selected(True)

        self._populate_form(bot["config"])
        self._switch_log_widget(bot_id)
        self._refresh_action_buttons()

    def _switch_log_widget(self, bot_id: str) -> None:
        for child in self.logs_holder.winfo_children():
            child.pack_forget()

        bot = self.bots[bot_id]
        if bot["log_widget"] is None:
            tb, sb = self._make_log_widget()
            bot["log_widget"] = tb
            bot["log_scroll"] = sb
            tb.configure(state="normal")
            for level, line in bot["log_buffer"]:
                tb.insert("end", line + "\n", level)
            tb.see("end")
            tb.configure(state="disabled")

        bot["log_scroll"].pack(side="right", fill="y")
        bot["log_widget"].pack(side="left", fill="both", expand=True)

    # ---------- Form <-> config ----------

    def _populate_form(self, cfg: dict[str, Any]) -> None:
        for key, w in self.cfg_widgets.items():
            value = cfg.get(key, "")
            if isinstance(w, ctk.CTkSwitch):
                if bool(value):
                    w.select()
                else:
                    w.deselect()
            elif isinstance(w, ctk.CTkTextbox):
                w.delete("1.0", "end")
                if key == "all_channels":
                    w.insert("1.0", "\n".join(str(c) for c in (value or [])))
                else:
                    w.insert("1.0", str(value or ""))
            else:  # CTkEntry
                w.delete(0, "end")
                if key in ("pause_duration_min", "pause_duration_max"):
                    if value:
                        w.insert(0, str(round(float(value) / 3600, 2)))
                else:
                    if value not in (None, ""):
                        w.insert(0, str(value))

        self.wishlist_persos.delete("1.0", "end")
        self.wishlist_persos.insert("1.0", "\n".join(cfg.get("wishlist", [])))
        self.wishlist_series.delete("1.0", "end")
        self.wishlist_series.insert("1.0", "\n".join(cfg.get("wishlist_series", [])))

    def _collect_form_into_config(self, bot_id: str) -> None:
        cfg = self.bots[bot_id]["config"]
        for key, w in self.cfg_widgets.items():
            if isinstance(w, ctk.CTkSwitch):
                cfg[key] = bool(w.get())
            elif isinstance(w, ctk.CTkTextbox):
                raw = w.get("1.0", "end").strip()
                if key == "all_channels":
                    chans = []
                    for line in raw.splitlines():
                        line = line.strip()
                        if line:
                            try:
                                chans.append(int(line))
                            except ValueError:
                                pass
                    cfg[key] = chans
                else:
                    cfg[key] = raw
            else:
                raw = w.get().strip()
                if getattr(w, "_numeric", False):
                    try:
                        if key == "drop_channel":
                            cfg[key] = int(raw) if raw else 0
                        elif key in (
                            "cooldown_extra_min",
                            "cooldown_extra_max",
                            "rarity_norm",
                            "hearts_norm",
                        ):
                            cfg[key] = int(float(raw)) if raw else 0
                        elif key in ("pause_duration_min", "pause_duration_max"):
                            cfg[key] = float(raw) * 3600 if raw else 0
                        else:
                            cfg[key] = float(raw) if raw else 0
                    except ValueError:
                        pass
                else:
                    cfg[key] = raw

        cfg["wishlist"] = dedupe_sort(self.wishlist_persos.get("1.0", "end").splitlines())
        cfg["wishlist_series"] = dedupe_sort(self.wishlist_series.get("1.0", "end").splitlines())
        sanitize_config(cfg)

        self.bots[bot_id]["entry"].set_name(cfg.get("name", "Sans nom"))

    # ---------- Actions ----------

    def _save_current(self) -> None:
        if not self.selected_id:
            return
        self._collect_form_into_config(self.selected_id)
        self._persist()
        bot = self.bots[self.selected_id]
        if bot["instance"]:
            bot["instance"].config = bot["config"]

        # Re-affiche les wishlists triées
        cfg = bot["config"]
        self.wishlist_persos.delete("1.0", "end")
        self.wishlist_persos.insert("1.0", "\n".join(cfg["wishlist"]))
        self.wishlist_series.delete("1.0", "end")
        self.wishlist_series.insert("1.0", "\n".join(cfg["wishlist_series"]))

        self._append_log_line(self.selected_id, "system", "Configuration sauvegardée")

    def _persist(self) -> None:
        save_bots([b["config"] for b in self.bots.values()])

    def _start_current(self) -> None:
        if not self.selected_id:
            return
        self._collect_form_into_config(self.selected_id)
        self._persist()

        bot = self.bots[self.selected_id]
        if bot["instance"] and bot["instance"].status in (
            SelfBot.STATUS_RUNNING,
            SelfBot.STATUS_STARTING,
        ):
            return

        instance = SelfBot(bot["config"])
        bid = self.selected_id
        instance.status_callback = lambda s, bid=bid: self.after(
            0, lambda: self._on_bot_status_change(bid, s)
        )
        bot["instance"] = instance
        instance.start()
        self._refresh_action_buttons()
        self.tabs.set("  Logs  ")

    def _stop_bot_async(self, instance: SelfBot, on_done: Callable[[], None] | None = None) -> None:
        """Run instance.stop() in a daemon thread to keep the Tk loop responsive.
        on_done (if provided) is scheduled on the main thread once stop returns."""

        def _worker() -> None:
            try:
                instance.stop()
            except Exception:
                pass
            if on_done is not None:
                try:
                    self.after(0, on_done)
                except Exception:
                    pass

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_all_async(
        self, then: Callable[[], None] | None = None, max_wait: float = 6.0
    ) -> None:
        """Stop every live bot in parallel. Fire `then` on the main thread once
        all stops return, or after max_wait seconds — whichever comes first."""
        instances = [b["instance"] for b in self.bots.values() if b["instance"]]
        if not instances:
            if then is not None:
                self.after(0, then)
            return
        state: dict[str, Any] = {"remaining": len(instances), "fired": False}
        lock = threading.Lock()

        def _fire() -> None:
            if then is None or state["fired"]:
                return
            state["fired"] = True
            try:
                self.after(0, then)
            except Exception:
                pass

        def _one(inst: SelfBot) -> None:
            try:
                inst.stop()
            except Exception:
                pass
            with lock:
                state["remaining"] -= 1
                done = state["remaining"] == 0
            if done:
                _fire()

        for inst in instances:
            threading.Thread(target=_one, args=(inst,), daemon=True).start()
        # Hard ceiling in case bot_core's own timeout is exceeded.
        self.after(int(max_wait * 1000), _fire)

    def _stop_current(self) -> None:
        if not self.selected_id:
            return
        bot = self.bots[self.selected_id]
        if not bot["instance"]:
            return
        self.stop_btn.configure(state="disabled", text="■ Arrêt…")
        bid = self.selected_id

        def _restore() -> None:
            self.stop_btn.configure(text="■ Arrêter")
            if self.selected_id == bid:
                self._refresh_action_buttons()

        self._stop_bot_async(bot["instance"], on_done=_restore)

    def _delete_current(self) -> None:
        if not self.selected_id:
            return
        bot = self.bots[self.selected_id]
        name = bot["config"].get("name", "ce bot")
        if not messagebox.askyesno(
            "Supprimer", f"Supprimer « {name} » ? Cette action est définitive."
        ):
            return
        if bot["instance"]:
            self._stop_bot_async(bot["instance"])
        bot["entry"].destroy()
        del self.bots[self.selected_id]
        self.selected_id = None
        self._persist()

        for child in self.logs_holder.winfo_children():
            child.pack_forget()
        self.logs_placeholder.pack(expand=True)
        for w in self.cfg_widgets.values():
            if isinstance(w, ctk.CTkSwitch):
                w.deselect()
            elif isinstance(w, ctk.CTkTextbox):
                w.delete("1.0", "end")
            else:
                w.delete(0, "end")
        self.wishlist_persos.delete("1.0", "end")
        self.wishlist_series.delete("1.0", "end")
        self._show_empty_state()

    def _clear_current_logs(self) -> None:
        if not self.selected_id:
            return
        bot = self.bots[self.selected_id]
        bot["log_buffer"].clear()
        if bot["log_widget"]:
            bot["log_widget"].configure(state="normal")
            bot["log_widget"].delete("1.0", "end")
            bot["log_widget"].configure(state="disabled")

    # ---------- Logs polling ----------

    def _drain_logs(self) -> None:
        try:
            for bot_id, bot in self.bots.items():
                inst = bot["instance"]
                if not inst:
                    continue
                drained = 0
                while drained < 200:
                    try:
                        level, line = inst.log_queue.get_nowait()
                    except Exception:
                        break
                    self._append_log_line(bot_id, level, line)
                    drained += 1
        finally:
            self.after(120, self._drain_logs)

    def _append_log_line(self, bot_id: str, level: str, line: str) -> None:
        bot = self.bots.get(bot_id)
        if not bot:
            return
        bot["log_buffer"].append((level, line))
        if len(bot["log_buffer"]) > 2000:
            bot["log_buffer"] = bot["log_buffer"][-1500:]
            if bot["log_widget"]:
                bot["log_widget"].configure(state="normal")
                bot["log_widget"].delete("1.0", "end")
                for lv, ln in bot["log_buffer"]:
                    bot["log_widget"].insert("end", ln + "\n", lv)
                bot["log_widget"].configure(state="disabled")
                bot["log_widget"].see("end")
                return

        if bot["log_widget"]:
            tb = bot["log_widget"]
            tb.configure(state="normal")
            tb.insert("end", line + "\n", level)
            tb.see("end")
            tb.configure(state="disabled")

    def _on_bot_status_change(self, bot_id: str, status: str) -> None:
        bot = self.bots.get(bot_id)
        if not bot:
            return
        bot["entry"].set_status(status)
        if bot_id == self.selected_id:
            self._refresh_action_buttons()

    # ---------- Theme actions ----------

    def _toggle_theme(self) -> None:
        new_mode = "light" if self.theme.mode == "dark" else "dark"
        self.theme.mode = new_mode
        # Toggling preset = on garde les overrides custom si on veut, mais on
        # les efface pour que le preset soit visible immédiatement.
        self.theme.overrides = {}
        self.settings["theme"] = {"mode": new_mode, "overrides": {}}
        save_settings(self.settings)
        self._rebuild_ui()

    def _open_theme_customizer(self) -> None:
        T = self.theme
        win = ctk.CTkToplevel(self)
        win.title("Personnaliser les couleurs")
        win.geometry("560x680")
        win.configure(fg_color=T["bg"])
        win.transient(self)
        try:
            win.grab_set()
        except Exception:
            pass

        ctk.CTkLabel(
            win,
            text="PERSONNALISER LE THÈME",
            text_color=T["accent"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(
            win,
            text="Cliquez sur une couleur pour la modifier. "
            "Réinitialiser revient au preset actuel.",
            text_color=T["text_dim"],
            font=ctk.CTkFont(size=11),
            justify="left",
            anchor="w",
        ).pack(anchor="w", padx=24, pady=(0, 14))

        scroll = ctk.CTkScrollableFrame(
            win,
            fg_color="transparent",
            scrollbar_button_color=T["accent_dim"],
            scrollbar_button_hover_color=T["accent"],
        )
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        overrides = dict(self.theme.overrides)
        preview_buttons: dict[str, ctk.CTkButton] = {}

        def base_color(key: str) -> str:
            return overrides.get(key, PRESETS[self.theme.mode][key])

        def make_pick(key: str) -> Callable[[], None]:
            def pick() -> None:
                current = base_color(key)
                color = colorchooser.askcolor(
                    color=current,
                    parent=win,
                    title=f"Choisir : {dict(THEME_LABELS)[key]}",
                )
                if color and color[1]:
                    overrides[key] = color[1]
                    btn = preview_buttons[key]
                    btn.configure(
                        text=color[1],
                        fg_color=color[1],
                        hover_color=color[1],
                        text_color=contrast_text(color[1]),
                    )

            return pick

        for key, label in THEME_LABELS:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(
                row,
                text=label,
                text_color=T["text"],
                width=220,
                anchor="w",
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=4)
            current = base_color(key)
            btn = ctk.CTkButton(
                row,
                text=current,
                command=make_pick(key),
                fg_color=current,
                hover_color=current,
                text_color=contrast_text(current),
                border_color=T["border"],
                border_width=1,
                corner_radius=4,
                width=200,
                height=30,
                font=ctk.CTkFont(family="Consolas", size=11),
            )
            btn.pack(side="right", padx=4)
            preview_buttons[key] = btn

        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(8, 18))

        def reset() -> None:
            overrides.clear()
            for key, btn in preview_buttons.items():
                c = PRESETS[self.theme.mode][key]
                btn.configure(text=c, fg_color=c, hover_color=c, text_color=contrast_text(c))

        def apply() -> None:
            self.theme.overrides = dict(overrides)
            self.settings["theme"] = {
                "mode": self.theme.mode,
                "overrides": self.theme.overrides,
            }
            save_settings(self.settings)
            win.destroy()
            self._rebuild_ui()

        self._mk_button(bar, "Réinitialiser", command=reset, variant="default", width=130).pack(
            side="left"
        )
        self._mk_button(bar, "Annuler", command=win.destroy, variant="ghost", width=110).pack(
            side="right", padx=(8, 0)
        )
        self._mk_button(bar, "Appliquer", command=apply, variant="primary", width=130).pack(
            side="right", padx=(8, 0)
        )

    def _rebuild_ui(self) -> None:
        """Détruit toute l'UI et la reconstruit avec le thème courant.
        Préserve les bots, leurs threads, et les buffers de logs."""
        previously_selected = self.selected_id
        if previously_selected and previously_selected in self.bots:
            try:
                self._collect_form_into_config(previously_selected)
            except Exception:
                pass

        # Détacher les status_callbacks (seront rebranchés dans _register_bot)
        saved_bots = []  # [(cfg, log_buffer, instance), ...]
        for _bot_id, bot in self.bots.items():
            if bot["instance"]:
                bot["instance"].status_callback = None
            saved_bots.append((bot["config"], bot["log_buffer"], bot["instance"]))

        # Détruire tous les widgets enfants
        for child in self.winfo_children():
            child.destroy()
        self.cfg_widgets = {}
        self.bots = {}
        self.selected_id = None

        # Re-appliquer apparence et reconstruire
        self._apply_appearance()
        self._build_layout()

        # Re-enregistrer les bots
        for cfg, log_buffer, instance in saved_bots:
            self._register_bot(cfg, log_buffer=log_buffer, instance=instance)

        # Restaurer la sélection
        if previously_selected and previously_selected in self.bots:
            self._select_bot(previously_selected)

    # ---------- Close ----------

    def _on_close(self) -> None:
        if self.selected_id:
            try:
                self._collect_form_into_config(self.selected_id)
            except Exception:
                pass
        self._persist()
        save_settings(self.settings)
        # Don't let the auto-refresh fire post-destroy.
        if self._stats_refresh_after_id is not None:
            try:
                self.after_cancel(self._stats_refresh_after_id)
            except Exception:
                pass
            self._stats_refresh_after_id = None
        # Swallow further close clicks while shutdown is in flight.
        try:
            self.protocol("WM_DELETE_WINDOW", lambda: None)
        except Exception:
            pass
        self._stop_all_async(then=self.destroy)


def run() -> None:
    app = SelfbotManagerApp()
    app.mainloop()


if __name__ == "__main__":
    run()
