"""
bot_core.py
Logique d'un selfbot SOFI encapsulée dans une classe.
Chaque instance gère son propre client Discord, sa propre boucle asyncio
et expose ses logs via une queue thread-safe.
"""

import asyncio
import re
import random
import threading
import queue
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
    rarity_score = max(0.0, 1.0 - card["rarity"] / cfg["rarity_norm"])
    hearts_score = min(1.0, card["hearts"] / cfg["hearts_norm"])
    return round(
        cfg["score_rarity_weight"] * rarity_score
        + cfg["score_hearts_weight"] * hearts_score,
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
        for wish in cfg["wishlist"]:
            if wish.lower() in card["name"].lower():
                if wishlist_card is None:
                    wishlist_card, wishlist_score = card, score
                    wishlist_label = "🌟 Wishlist perso"

    if wishlist_card is None:
        for card, score in scored:
            for series in cfg["wishlist_series"]:
                if series.lower() in card["series"].lower():
                    if wishlist_card is None:
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
        self.config = config
        self.log_queue: queue.Queue = queue.Queue()
        self.status = self.STATUS_STOPPED
        self.status_callback = None  # appelé avec le nouveau statut

        self._client = None
        self._loop = None
        self._thread = None
        self._drop_task = None
        self._cooldown_task = None
        self._night_task = None

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

    def stop(self):
        if self.status == self.STATUS_STOPPED:
            return
        if not self._loop or not self._client:
            self._set_status(self.STATUS_STOPPED)
            return

        async def _close():
            for task in (self._drop_task, self._cooldown_task, self._night_task):
                if task and not task.done():
                    task.cancel()
            try:
                await self._client.close()
            except Exception:
                pass

        try:
            asyncio.run_coroutine_threadsafe(_close(), self._loop)
        except Exception as e:
            self.log("error", f"Erreur arrêt: {e}")

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

        # Mention de mon user (couvre <@id>, <@!id>, et message.mentions)
        my_id = client.user.id
        mentioned = (
            client.user.mentioned_in(message)
            or f"<@{my_id}>" in message.content
            or f"<@!{my_id}>" in message.content
        )
        if not mentioned:
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
        for attempt in range(10):
            await asyncio.sleep(0.5)
            try:
                target_message = await message.channel.fetch_message(message.id)
            except Exception as e:
                self.log("error", f"Erreur fetch : {e}")
                continue

            if not target_message.components:
                continue

            all_buttons = target_message.components[0].children
            heart_buttons = [
                b for b in all_buttons
                if hasattr(b, "label") and parse_button_hearts(b.label) is not None
            ]

            if heart_buttons and not heart_buttons[0].disabled:
                self.log("success", "Boutons actifs")
                break
        else:
            self.log("error", "Boutons toujours disabled")
            return

        for i, card in enumerate(cards):
            if i < len(heart_buttons):
                card["hearts"] = parse_button_hearts(heart_buttons[i].label)

        button_index = choose_card(cards, cfg, self.log)

        delay = random.uniform(0, 5.5)
        self.log("info", f"⏳ Attente aléatoire : {delay:.2f}s")
        await asyncio.sleep(delay)

        try:
            await heart_buttons[button_index].click()
            self.log("success", f"💖 Cliqué bouton {button_index+1} ({heart_buttons[button_index].label}❤️)")
        except Exception as e:
            self.log("error", f"Erreur clic : {e}")
