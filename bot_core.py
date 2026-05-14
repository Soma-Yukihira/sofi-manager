"""
bot_core.py
Logique d'un selfbot SOFI encapsulée dans une classe.
Chaque instance gère son propre client Discord, sa propre boucle asyncio
et expose ses logs via une queue thread-safe.
"""

import asyncio
import queue
import random
import re
import threading
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timedelta

import discord

SOFI_ID = 853629533855809596


def default_config() -> dict:
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


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _as_int(value, default):
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


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        value = value.strip().lower()
        if value in ("1", "true", "yes", "on", "oui"):
            return True
        if value in ("0", "false", "no", "off", "non"):
            return False
    return bool(default)


def sanitize_config(cfg: dict) -> dict:
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

    channels = []
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
    cfg["score_rarity_weight"] = max(0.0, _as_float(cfg.get("score_rarity_weight"), defaults["score_rarity_weight"]))
    cfg["score_hearts_weight"] = max(0.0, _as_float(cfg.get("score_hearts_weight"), defaults["score_hearts_weight"]))
    cfg["wishlist_override_threshold"] = max(
        1.0,
        _as_float(cfg.get("wishlist_override_threshold"), defaults["wishlist_override_threshold"]),
    )

    for key in ("wishlist", "wishlist_series"):
        cfg[key] = [str(item).strip() for item in (cfg.get(key) or []) if str(item).strip()]

    cfg["night_pause_enabled"] = _as_bool(cfg.get("night_pause_enabled", True), True)
    return cfg


# =============================================
# Helpers purs (parsing, scoring)
# =============================================

def parse_cards(content):
    cards = []
    pattern = r'G•`?\s*(\d+)\s*`?\s*\|\s*(.+?)\s*•\s*(.+?)(?=\s*`\d|$)'
    for i, m in enumerate(re.finditer(pattern, content)):
        cards.append({
            "index": i,
            "name": m.group(2).strip(),
            "series": m.group(3).strip(),
            "rarity": int(m.group(1)),
            "hearts": 0,
        })
    return cards


def parse_cards_with_hearts(content):
    cards = []
    pattern = r'G•`?\s*(\d+)\s*`?\s*\|\s*(.+?)\s*•\s*(.+?)\s*•\s*(\d+)'
    for i, m in enumerate(re.finditer(pattern, content)):
        cards.append({
            "index": i,
            "name": m.group(2).strip(),
            "series": m.group(3).strip(),
            "rarity": int(m.group(1)),
            "hearts": int(m.group(4)),
        })
    return cards


def smart_parse_cards(content):
    return parse_cards_with_hearts(content) or parse_cards(content)


def parse_button_hearts(label):
    """'43' → 43, '1.2k' → 1200, '1k' → 1000. None si invalide."""
    label = str(label).strip().lower()
    if label.endswith("k"):
        try:
            return int(float(label[:-1]) * 1000)
        except ValueError:
            return None
    try:
        return int(label)
    except ValueError:
        return None


def parse_cooldown_seconds(content):
    m = re.search(
        r'(?:pr[êe]t\s+dans|ready\s+in)\s*:?\s*(?:(\d+)\s*m\s*)?(\d+)\s*s',
        content, re.IGNORECASE,
    )
    if m:
        minutes = int(m.group(1)) if m.group(1) else 0
        seconds = int(m.group(2))
        return minutes * 60 + seconds
    return None


def extract_full_text(message):
    """Combine message.content + tous les embeds en un seul string.
    SOFI met parfois les cartes dans un embed plutôt qu'en texte brut."""
    parts = [message.content or ""]
    for emb in message.embeds:
        if emb.title:
            parts.append(emb.title)
        if emb.description:
            parts.append(emb.description)
        author = getattr(emb, "author", None)
        if author and getattr(author, "name", None):
            parts.append(author.name)
        for field in getattr(emb, "fields", []):
            if field.name:
                parts.append(field.name)
            if field.value:
                parts.append(field.value)
        footer = getattr(emb, "footer", None)
        if footer and getattr(footer, "text", None):
            parts.append(footer.text)
    return "\n".join(p for p in parts if p)


def iter_component_children(components):
    """Yield every child component, no matter how many action rows Discord uses."""
    for row in components or []:
        yield from getattr(row, "children", []) or []


def _format_drop_recipients(message, exclude_id):
    """Return '@name' or '@a, @b' for users mentioned in the drop, excluding self.

    Returns empty string if nobody else is mentioned (drop format we don't recognise)."""
    names = []
    for user in getattr(message, "mentions", None) or []:
        uid = getattr(user, "id", None)
        if uid == exclude_id:
            continue
        name = getattr(user, "display_name", None) or getattr(user, "name", None)
        if name:
            names.append(f"@{name}")
    return ", ".join(names)


# Patterns multilingues pour SOFI (FR + EN)
_DROP_TRIGGER_RE = re.compile(
    r'drop\s+des\s+cartes|dropping\s+cards?|drops?\s+cards?',
    re.IGNORECASE,
)
_COOLDOWN_RE = re.compile(
    r'pr[êe]t\s+dans|ready\s+in',
    re.IGNORECASE,
)


def score_card(card, cfg):
    rarity_norm = max(1.0, _as_float(cfg.get("rarity_norm"), default_config()["rarity_norm"]))
    hearts_norm = max(1.0, _as_float(cfg.get("hearts_norm"), default_config()["hearts_norm"]))
    rarity_weight = max(0.0, _as_float(cfg.get("score_rarity_weight"), 0.30))
    hearts_weight = max(0.0, _as_float(cfg.get("score_hearts_weight"), 0.70))

    rarity_score = max(0.0, 1.0 - _as_float(card.get("rarity"), 0) / rarity_norm)
    hearts_score = min(1.0, max(0.0, _as_float(card.get("hearts"), 0) / hearts_norm))
    return round(
        rarity_weight * rarity_score
        + hearts_weight * hearts_score,
        3,
    )


def choose_card(cards, cfg, log):
    """Retourne l'index de la carte à cliquer, en logguant le raisonnement."""
    scored = [(c, score_card(c, cfg)) for c in cards]
    best_card, best_score = max(scored, key=lambda x: x[1])

    wishlist_card = None
    wishlist_score = 0
    wishlist_label = ""

    for card, score in scored:
        for wish in cfg.get("wishlist", []):
            if wish.lower() in card["name"].lower():
                if wishlist_card is None or score > wishlist_score:
                    wishlist_card, wishlist_score = card, score
                    wishlist_label = "🌟 Wishlist perso"

    if wishlist_card is None:
        for card, score in scored:
            for series in cfg.get("wishlist_series", []):
                if series.lower() in card["series"].lower():
                    if wishlist_card is None or score > wishlist_score:
                        wishlist_card, wishlist_score = card, score
                        wishlist_label = "📺 Wishlist série"

    if wishlist_card is not None:
        for card, score in scored:
            log("info", f"  {card['name']} • {card['series']} → score {score} (G•{card['rarity']} | {card['hearts']}❤️)")
        if best_score >= wishlist_score * cfg["wishlist_override_threshold"] and best_card != wishlist_card:
            log("warn", f"⚡ {wishlist_label} ignoré : {wishlist_card['name']} (score {wishlist_score}) "
                        f"< {best_card['name']} (score {best_score})")
            log("success", f"💡 Meilleur score retenu : {best_card['name']} • {best_card['series']}")
            return best_card["index"]
        log("success", f"{wishlist_label} : {wishlist_card['name']} • {wishlist_card['series']} "
                      f"(G•{wishlist_card['rarity']} | {wishlist_card['hearts']}❤️ | score {wishlist_score})")
        return wishlist_card["index"]

    for card, score in scored:
        log("info", f"  {card['name']} • {card['series']} → score {score} (G•{card['rarity']} | {card['hearts']}❤️)")
    log("success", f"💡 Meilleur score : {best_card['name']} • {best_card['series']} (score {best_score})")
    return best_card["index"]


def _seconds_until(hour, minute=0):
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

    def __init__(self, config: dict):
        self.config = sanitize_config(config)
        self.log_queue: queue.Queue = queue.Queue()
        self.status = self.STATUS_STOPPED
        self.status_callback = None  # appelé avec le nouveau statut

        self._client = None
        self._loop = None
        self._thread: threading.Thread | None = None
        self._drop_task = None
        self._cooldown_task = None
        self._night_task = None
        self._sd_watchdogs: dict[int, asyncio.Task] = {}
        self._sd_watchdog_timeout = 60.0

    # ---------- API publique ----------

    def log(self, level, text):
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

    def stop(self, timeout=5):
        if self.status == self.STATUS_STOPPED:
            return
        if not self._loop or not self._client or self._loop.is_closed():
            self._set_status(self.STATUS_STOPPED)
            return

        async def _close():
            for task in (self._drop_task, self._cooldown_task, self._night_task):
                if task and not task.done():
                    task.cancel()
            for task in list(self._sd_watchdogs.values()):
                if task and not task.done():
                    task.cancel()
            self._sd_watchdogs.clear()
            try:
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
            if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
                self._thread.join(timeout=timeout)

    # ---------- internes ----------

    def _set_status(self, status):
        self.status = status
        if self.status_callback:
            try:
                self.status_callback(status)
            except Exception:
                pass

    def _run(self):
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
                    self._loop.close()
            except Exception:
                pass
            if self.status != self.STATUS_ERROR:
                self._set_status(self.STATUS_STOPPED)
                self.log("system", "Bot arrêté")

    def _setup_events(self):
        client = self._client
        cfg = self.config

        @client.event
        async def on_ready():
            self.log("success", f"Connecté en tant que {client.user}")
            self._set_status(self.STATUS_RUNNING)
            for cid in cfg["all_channels"]:
                ch = client.get_channel(cid)
                if ch:
                    self.log("info", f"Salon écouté : #{ch.name}")
                else:
                    self.log("warn", f"Salon introuvable : {cid}")
            self._restart_drop_loop()
            if cfg.get("night_pause_enabled", True):
                self._night_task = asyncio.create_task(self._night_pause_loop())

        @client.event
        async def on_message(message):
            await self._on_message(message)

    async def _drop_loop(self):
        cfg = self.config
        channel = self._client.get_channel(cfg["drop_channel"])
        if not channel:
            self.log("error", f"DROP_CHANNEL introuvable : {cfg['drop_channel']}")
            return
        while True:
            try:
                await channel.send(cfg["message"])
                self.log("info", f"Drop envoyé dans #{channel.name}")
                self._arm_sd_watchdog(channel)
                interval = random.uniform(cfg["interval_min"], cfg["interval_max"])
                self.log("info", f"⏳ Prochain drop dans {interval/60:.1f} min")
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log("error", f"Erreur drop: {e}")
                await asyncio.sleep(30)

    def _restart_drop_loop(self):
        if self._drop_task and not self._drop_task.done():
            self._drop_task.cancel()
        self._drop_task = asyncio.create_task(self._drop_loop())

    def _arm_sd_watchdog(self, channel):
        existing = self._sd_watchdogs.get(channel.id)
        if existing and not existing.done():
            existing.cancel()
        self._sd_watchdogs[channel.id] = asyncio.create_task(
            self._sd_watchdog_coro(channel)
        )

    def _cancel_sd_watchdog(self, channel_id):
        task = self._sd_watchdogs.pop(channel_id, None)
        if task and not task.done():
            task.cancel()

    async def _sd_watchdog_coro(self, channel):
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

    async def _handle_cooldown(self, wait):
        cfg = self.config
        extra = random.uniform(cfg["cooldown_extra_min"], cfg["cooldown_extra_max"])
        total = wait + extra
        self.log("info", f"⏳ Cooldown SOFI : {wait//60}m {wait%60}s + {extra:.0f}s extra → relance dans {total/60:.1f} min")
        try:
            await asyncio.sleep(total)
            self._restart_drop_loop()
        except asyncio.CancelledError:
            pass

    async def _night_pause_loop(self):
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
                self.log("info", f"🌙 Pause nocturne prévue à {start_hour:02d}h{start_minute:02d} (dans {wait/3600:.1f}h)")
                await asyncio.sleep(wait)

                if self._cooldown_task and not self._cooldown_task.done():
                    self._cooldown_task.cancel()
                if self._drop_task and not self._drop_task.done():
                    self._drop_task.cancel()

                duration = random.uniform(cfg["pause_duration_min"], cfg["pause_duration_max"])
                resume_time = (datetime.now() + timedelta(seconds=duration)).strftime("%H:%M")
                self.log("info", f"😴 Pause nocturne : {duration/3600:.1f}h — reprise vers {resume_time}")
                await asyncio.sleep(duration)
                self.log("info", "☀️ Reprise après pause nocturne")
                self._restart_drop_loop()
            except asyncio.CancelledError:
                raise

    async def _on_message(self, message):
        cfg = self.config
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
        if _COOLDOWN_RE.search(content_clean):
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
        if not _DROP_TRIGGER_RE.search(content_clean):
            return

        if not mentions_me:
            other = _format_drop_recipients(message, my_id)
            if other:
                self.log("info", f"⏭️ Drop pour {other}")
            else:
                self.log("info", "⏭️ Drop ignoré (pas le tien)")
            return

        self.log("system", f"🎴 Drop détecté dans #{message.channel.name}")
        cards = smart_parse_cards(full_text)
        if not cards:
            self.log("error", "Aucune carte parsée — voir log SOFI au-dessus")
            return

        self.log("info", "Cartes détectées :")
        for c in cards:
            self.log("info", f"  [{c['index']+1}] {c['name']} • {c['series']} | G•{c['rarity']} | {c['hearts']}❤️")

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
                b for b in all_buttons
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
            self.log("error", f"Bouton {button_index+1} introuvable ({len(heart_buttons)} bouton(s) détecté(s))")
            return

        button = heart_buttons[button_index]
        if getattr(button, "disabled", False):
            self.log("error", f"Bouton {button_index+1} encore désactivé")
            return

        delay = random.uniform(0, 5.5)
        self.log("info", f"⏳ Attente aléatoire : {delay:.2f}s")
        await asyncio.sleep(delay)

        try:
            await button.click()
            self.log("success", f"💖 Cliqué bouton {button_index+1} ({button.label}❤️)")
        except discord.HTTPException as e:
            # Codes courants : 10008 message gone, 40060 interaction already acked,
            # 50001 missing access, 429 rate limit
            code = getattr(e, "code", "?")
            status = getattr(e, "status", "?")
            text = getattr(e, "text", "") or str(e)
            self.log("error", f"Erreur clic HTTP {status} (code {code}) : {text}")
        except Exception as e:
            self.log("error", f"Erreur clic ({type(e).__name__}) : {e}")
