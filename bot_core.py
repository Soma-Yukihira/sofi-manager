"""
bot_core.py
Logique d'un selfbot SOFI encapsulée dans une classe.
Chaque instance gère son propre client Discord, sa propre boucle asyncio
et expose ses logs via une queue thread-safe.

Pure helpers vivent ailleurs :
- `parsing.py`  : extraction et matching des messages SOFI
- `scoring.py`  : sélection de la carte à cliquer
- `storage.py`  : persistance SQLite des grabs
"""

import asyncio
import queue
import random
import threading
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta
from typing import Any

import discord

import storage
from parsing import (
    extract_full_text,
    format_drop_recipients,
    is_cooldown_message,
    is_drop_trigger,
    iter_component_children,
    parse_button_hearts,
    parse_cooldown_seconds,
    smart_parse_cards,
)
from scoring import choose_card, score_card

SOFI_ID = 853629533855809596


def _drain_and_close_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Cancel & await every pending task, then close the loop.

    Skipping the drain lets asyncio's Task GC emit "Task was destroyed but
    it is pending!" on app exit — Client.close() chained on a cancelled
    curl_cffi force-timeout task is the usual culprit. Must run only when
    the loop is stopped (not running).
    """
    try:
        pending = asyncio.all_tasks(loop)
        for t in pending:
            t.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass
    loop.close()


def default_config() -> dict[str, Any]:
    """Config par défaut pour un nouveau bot."""
    return {
        "name": "Nouveau bot",
        "token": "",
        "drop_channel": 0,
        "all_channels": [],
        "message": "sd",
        "interval_min": 510.0,
        "interval_max": 600.0,
        "cooldown_extra_min": 30,
        "cooldown_extra_max": 145,
        "pause_duration_min": 6.5 * 3600,
        "pause_duration_max": 9.0 * 3600,
        "night_pause_enabled": True,
        "score_rarity_weight": 0.30,
        "score_hearts_weight": 0.70,
        "rarity_norm": 2000,
        "hearts_norm": 500,
        "wishlist_override_threshold": 1.40,
        "wishlist": [],
        "wishlist_series": [],
        "sofi_id": SOFI_ID,
    }


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(default)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return int(default)
        try:
            return int(value)
        except ValueError:
            pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.strip().lower()
        if value in ("1", "true", "yes", "on", "oui"):
            return True
        if value in ("0", "false", "no", "off", "non"):
            return False
    return bool(default)


def sanitize_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Normalize runtime config in-place and return it.

    The GUI intentionally stays permissive while typing. This guard keeps the
    bot core from crashing or tight-looping if a saved numeric field is empty,
    zero, inverted, or otherwise malformed.
    """
    defaults = default_config()
    for key, value in defaults.items():
        cfg.setdefault(key, value)

    cfg["token"] = str(cfg.get("token") or "").strip()
    cfg["name"] = str(cfg.get("name") or defaults["name"]).strip() or defaults["name"]
    cfg["message"] = str(cfg.get("message") or defaults["message"]).strip() or defaults["message"]

    cfg["drop_channel"] = _as_int(cfg.get("drop_channel"), 0)
    cfg["sofi_id"] = _as_int(cfg.get("sofi_id"), SOFI_ID)

    channels: list[int] = []
    for raw in cfg.get("all_channels") or []:
        cid = _as_int(raw, 0)
        if cid and cid not in channels:
            channels.append(cid)
    if cfg["drop_channel"]:
        channels = [cfg["drop_channel"]] + [cid for cid in channels if cid != cfg["drop_channel"]]
    cfg["all_channels"] = channels

    for key in ("interval_min", "interval_max"):
        cfg[key] = max(30.0, _as_float(cfg.get(key), defaults[key]))
    if cfg["interval_min"] > cfg["interval_max"]:
        cfg["interval_min"], cfg["interval_max"] = cfg["interval_max"], cfg["interval_min"]

    for key in ("cooldown_extra_min", "cooldown_extra_max"):
        cfg[key] = max(0.0, _as_float(cfg.get(key), defaults[key]))
    if cfg["cooldown_extra_min"] > cfg["cooldown_extra_max"]:
        cfg["cooldown_extra_min"], cfg["cooldown_extra_max"] = (
            cfg["cooldown_extra_max"],
            cfg["cooldown_extra_min"],
        )

    for key in ("pause_duration_min", "pause_duration_max"):
        cfg[key] = max(60.0, _as_float(cfg.get(key), defaults[key]))
    if cfg["pause_duration_min"] > cfg["pause_duration_max"]:
        cfg["pause_duration_min"], cfg["pause_duration_max"] = (
            cfg["pause_duration_max"],
            cfg["pause_duration_min"],
        )

    cfg["rarity_norm"] = max(1.0, _as_float(cfg.get("rarity_norm"), defaults["rarity_norm"]))
    cfg["hearts_norm"] = max(1.0, _as_float(cfg.get("hearts_norm"), defaults["hearts_norm"]))
    cfg["score_rarity_weight"] = max(
        0.0, _as_float(cfg.get("score_rarity_weight"), defaults["score_rarity_weight"])
    )
    cfg["score_hearts_weight"] = max(
        0.0, _as_float(cfg.get("score_hearts_weight"), defaults["score_hearts_weight"])
    )
    cfg["wishlist_override_threshold"] = max(
        1.0,
        _as_float(cfg.get("wishlist_override_threshold"), defaults["wishlist_override_threshold"]),
    )

    for key in ("wishlist", "wishlist_series"):
        cfg[key] = [str(item).strip() for item in (cfg.get(key) or []) if str(item).strip()]

    cfg["night_pause_enabled"] = _as_bool(cfg.get("night_pause_enabled", True), True)
    return cfg


def _seconds_until(hour: int, minute: int = 0) -> float:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


# =============================================
# SelfBot
# =============================================


class SelfBot:
    STATUS_STOPPED = "stopped"
    STATUS_STARTING = "starting"
    STATUS_RUNNING = "running"
    STATUS_ERROR = "error"

    def __init__(self, config: dict[str, Any]):
        self.config = sanitize_config(config)
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.status = self.STATUS_STOPPED
        self.status_callback: Callable[[str], None] | None = None  # appelé avec le nouveau statut

        self._client: discord.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._drop_task: asyncio.Task[Any] | None = None
        self._cooldown_task: asyncio.Task[Any] | None = None
        self._night_task: asyncio.Task[Any] | None = None
        self._sd_watchdogs: dict[int, asyncio.Task[Any]] = {}
        self._sd_watchdog_timeout = 60.0

    # ---------- API publique ----------

    def log(self, level: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put((level, f"[{ts}] {text}"))

    def start(self) -> bool:
        if self.status in (self.STATUS_RUNNING, self.STATUS_STARTING):
            return False
        if not self.config.get("token"):
            self.log("error", "Token manquant — impossible de démarrer")
            return False
        if not self.config.get("drop_channel"):
            self.log("error", "Drop channel manquant — impossible de démarrer")
            return False

        # S'assurer que drop_channel ∈ all_channels
        ac = list(self.config.get("all_channels", []))
        if self.config["drop_channel"] not in ac:
            ac.insert(0, self.config["drop_channel"])
            self.config["all_channels"] = ac

        self._set_status(self.STATUS_STARTING)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 5) -> None:
        if self.status == self.STATUS_STOPPED:
            return
        if not self._loop or not self._client or self._loop.is_closed():
            self._set_status(self.STATUS_STOPPED)
            return

        async def _close() -> None:
            for task in (self._drop_task, self._cooldown_task, self._night_task):
                if task and not task.done():
                    task.cancel()
            for task in list(self._sd_watchdogs.values()):
                if task and not task.done():
                    task.cancel()
            self._sd_watchdogs.clear()
            try:
                assert self._client is not None
                await self._client.close()
            except Exception:
                pass

        try:
            future = asyncio.run_coroutine_threadsafe(_close(), self._loop)
            try:
                future.result(timeout=timeout)
            except FutureTimeoutError:
                self.log("warn", "Arrêt Discord trop long — fermeture en arrière-plan")
        except Exception as e:
            self.log("error", f"Erreur arrêt: {e}")
        finally:
            if (
                self._thread
                and self._thread.is_alive()
                and threading.current_thread() is not self._thread
            ):
                self._thread.join(timeout=timeout)

    # ---------- internes ----------

    def _set_status(self, status: str) -> None:
        self.status = status
        if self.status_callback:
            try:
                self.status_callback(status)
            except Exception:
                pass

    def _run(self) -> None:
        try:
            sanitize_config(self.config)
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._client = discord.Client()
            self._setup_events()
            self.log("system", "Connexion en cours…")
            self._loop.run_until_complete(self._client.start(self.config["token"]))
        except discord.LoginFailure:
            self.log("error", "Token invalide")
            self._set_status(self.STATUS_ERROR)
            return
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.log("error", f"Erreur fatale: {e}")
            self._set_status(self.STATUS_ERROR)
            return
        finally:
            try:
                if self._loop and not self._loop.is_closed():
                    _drain_and_close_loop(self._loop)
            except Exception:
                pass
            if self.status != self.STATUS_ERROR:
                self._set_status(self.STATUS_STOPPED)
                self.log("system", "Bot arrêté")

    def _setup_events(self) -> None:
        assert self._client is not None
        client = self._client
        cfg = self.config

        @client.event
        async def on_ready() -> None:
            self.log("success", f"Connecté en tant que {client.user}")
            self._set_status(self.STATUS_RUNNING)
            for cid in cfg["all_channels"]:
                ch = client.get_channel(cid)
                if ch:
                    name = getattr(ch, "name", str(cid))
                    self.log("info", f"Salon écouté : #{name}")
                else:
                    self.log("warn", f"Salon introuvable : {cid}")
            self._restart_drop_loop()
            if cfg.get("night_pause_enabled", True):
                self._night_task = asyncio.create_task(self._night_pause_loop())

        @client.event
        async def on_message(message: discord.Message) -> None:
            await self._on_message(message)

    async def _drop_loop(self) -> None:
        cfg = self.config
        assert self._client is not None
        channel: Any = self._client.get_channel(cfg["drop_channel"])
        if not channel:
            self.log("error", f"DROP_CHANNEL introuvable : {cfg['drop_channel']}")
            return
        while True:
            try:
                await channel.send(cfg["message"])
                self.log("info", f"Drop envoyé dans #{channel.name}")
                self._arm_sd_watchdog(channel)
                interval = random.uniform(cfg["interval_min"], cfg["interval_max"])
                self.log("info", f"⏳ Prochain drop dans {interval / 60:.1f} min")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log("error", f"Erreur drop: {e}")
                await asyncio.sleep(30)

    def _restart_drop_loop(self) -> None:
        if self._drop_task and not self._drop_task.done():
            self._drop_task.cancel()
        self._drop_task = asyncio.create_task(self._drop_loop())

    def _arm_sd_watchdog(self, channel: Any) -> None:
        existing = self._sd_watchdogs.get(channel.id)
        if existing and not existing.done():
            existing.cancel()
        self._sd_watchdogs[channel.id] = asyncio.create_task(self._sd_watchdog_coro(channel))

    def _cancel_sd_watchdog(self, channel_id: int) -> None:
        task = self._sd_watchdogs.pop(channel_id, None)
        if task and not task.done():
            task.cancel()

    async def _sd_watchdog_coro(self, channel: Any) -> None:
        timeout = self._sd_watchdog_timeout
        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return
        # Si on est encore le watchdog actif pour ce channel, SOFI n'a rien répondu.
        if self._sd_watchdogs.get(channel.id) is asyncio.current_task():
            self._sd_watchdogs.pop(channel.id, None)
            self.log(
                "warn",
                f"⚠️ sd envoyé dans #{channel.name} sans réponse SOFI en {timeout:.0f}s "
                f"(SOFI down, salon saturé, ou drop pris par un autre user ?)",
            )

    async def _handle_cooldown(self, wait: float) -> None:
        cfg = self.config
        extra = random.uniform(cfg["cooldown_extra_min"], cfg["cooldown_extra_max"])
        total = wait + extra
        self.log(
            "info",
            f"⏳ Cooldown SOFI : {wait // 60}m {wait % 60}s + {extra:.0f}s extra → relance dans {total / 60:.1f} min",
        )
        try:
            await asyncio.sleep(total)
            self._restart_drop_loop()
        except asyncio.CancelledError:
            pass

    async def _night_pause_loop(self) -> None:
        cfg = self.config
        random.seed()
        while True:
            try:
                offset_minutes = random.randint(0, 180)
                start_hour = (22 * 60 + offset_minutes) // 60 % 24
                start_minute = (22 * 60 + offset_minutes) % 60
                wait = _seconds_until(start_hour, start_minute)
                if wait > 24 * 3600:
                    wait -= 24 * 3600
                self.log(
                    "info",
                    f"🌙 Pause nocturne prévue à {start_hour:02d}h{start_minute:02d} (dans {wait / 3600:.1f}h)",
                )
                await asyncio.sleep(wait)

                if self._cooldown_task and not self._cooldown_task.done():
                    self._cooldown_task.cancel()
                if self._drop_task and not self._drop_task.done():
                    self._drop_task.cancel()

                duration = random.uniform(cfg["pause_duration_min"], cfg["pause_duration_max"])
                resume_time = (datetime.now() + timedelta(seconds=duration)).strftime("%H:%M")
                self.log(
                    "info",
                    f"😴 Pause nocturne : {duration / 3600:.1f}h — reprise vers {resume_time}",
                )
                await asyncio.sleep(duration)
                self.log("info", "☀️ Reprise après pause nocturne")
                self._restart_drop_loop()
            except asyncio.CancelledError:
                raise

    def _record_grab_safe(
        self,
        card: dict[str, Any],
        channel_id: int,
        success: bool,
        error_code: str | None,
    ) -> None:
        """Persist a grab attempt — never let DB errors propagate into the bot."""
        try:
            storage.record_grab(
                storage.GrabRecord(
                    bot_label=self.config.get("name", ""),
                    channel_id=channel_id,
                    card_name=card.get("name"),
                    series=card.get("series"),
                    rarity=str(card.get("rarity")) if card.get("rarity") is not None else None,
                    hearts=card.get("hearts"),
                    score=score_card(card, self.config),
                    success=success,
                    error_code=error_code,
                )
            )
        except Exception as e:
            self.log("warn", f"⚠️ DB grabs indisponible ({type(e).__name__}: {e})")

    async def _on_message(self, message: discord.Message) -> None:
        cfg = self.config
        assert self._client is not None
        client = self._client
        if message.author.id != cfg.get("sofi_id", SOFI_ID):
            return
        if message.channel.id not in cfg["all_channels"]:
            return

        full_text = extract_full_text(message)
        content_clean = full_text.replace("**", "")

        # Diagnostic : log tronqué de tout message SOFI dans les salons écoutés
        preview = content_clean.strip().replace("\n", " ⏎ ")[:160] or "(vide)"
        self.log("info", f"📥 SOFI: {preview}")

        assert client.user is not None  # on_message only fires after login
        my_id = client.user.id
        mentions_me = (
            client.user.mentioned_in(message)
            or f"<@{my_id}>" in message.content
            or f"<@!{my_id}>" in message.content
        )
        # SOFI a répondu à notre sd (drop ou cooldown), le watchdog n'a plus à crier.
        if mentions_me:
            self._cancel_sd_watchdog(message.channel.id)

        # Cooldown
        if is_cooldown_message(content_clean):
            wait = parse_cooldown_seconds(content_clean)
            if wait:
                if self._drop_task and not self._drop_task.done():
                    self._drop_task.cancel()
                    self.log("warn", "drop_loop annulé")
                if self._cooldown_task and not self._cooldown_task.done():
                    self._cooldown_task.cancel()
                    self.log("warn", "Cooldown précédent remplacé")
                self._cooldown_task = asyncio.create_task(self._handle_cooldown(wait))
            return

        # Drop ?
        if not is_drop_trigger(content_clean):
            return

        if not mentions_me:
            other = format_drop_recipients(message, my_id)
            if other:
                self.log("info", f"⏭️ Drop pour {other}")
            else:
                self.log("info", "⏭️ Drop ignoré (pas le tien)")
            return

        channel_name = getattr(message.channel, "name", str(message.channel.id))
        self.log("system", f"🎴 Drop détecté dans #{channel_name}")
        cards = smart_parse_cards(full_text)
        if not cards:
            self.log("error", "Aucune carte parsée — voir log SOFI au-dessus")
            return

        self.log("info", "Cartes détectées :")
        for c in cards:
            self.log(
                "info",
                f"  [{c['index'] + 1}] {c['name']} • {c['series']} | G•{c['rarity']} | {c['hearts']}❤️",
            )

        choose_card(cards, cfg, self.log)  # 1ère sélection

        heart_buttons = []
        for _attempt in range(10):
            await asyncio.sleep(0.5)
            try:
                target_message = await message.channel.fetch_message(message.id)
            except Exception as e:
                self.log("error", f"Erreur fetch : {e}")
                continue

            if not target_message.components:
                continue

            all_buttons = list(iter_component_children(target_message.components))
            heart_buttons = [
                b
                for b in all_buttons
                if hasattr(b, "label") and parse_button_hearts(b.label) is not None
            ]

            if heart_buttons and all(not getattr(b, "disabled", False) for b in heart_buttons):
                self.log("success", "Boutons actifs")
                break
        else:
            self.log("error", "Boutons toujours disabled")
            return

        for i, card in enumerate(cards):
            if i < len(heart_buttons):
                card["hearts"] = parse_button_hearts(heart_buttons[i].label)

        button_index = choose_card(cards, cfg, self.log)
        if button_index >= len(heart_buttons):
            self.log(
                "error",
                f"Bouton {button_index + 1} introuvable ({len(heart_buttons)} bouton(s) détecté(s))",
            )
            return

        button = heart_buttons[button_index]
        if getattr(button, "disabled", False):
            self.log("error", f"Bouton {button_index + 1} encore désactivé")
            return

        delay = random.uniform(0, 5.5)
        self.log("info", f"⏳ Attente aléatoire : {delay:.2f}s")
        await asyncio.sleep(delay)

        chosen = cards[button_index]
        success = False
        error_code: str | None = None
        try:
            await button.click()
            success = True
            self.log("success", f"💖 Cliqué bouton {button_index + 1} ({button.label}❤️)")
        except discord.HTTPException as e:
            # Codes courants : 10008 message gone, 40060 interaction already acked,
            # 50001 missing access, 429 rate limit
            code = getattr(e, "code", "?")
            status = getattr(e, "status", "?")
            text = getattr(e, "text", "") or str(e)
            error_code = str(code)
            self.log("error", f"Erreur clic HTTP {status} (code {code}) : {text}")
        except Exception as e:
            error_code = type(e).__name__
            self.log("error", f"Erreur clic ({type(e).__name__}) : {e}")

        self._record_grab_safe(chosen, message.channel.id, success, error_code)
