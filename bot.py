#!/usr/bin/env python3
"""
Trench FnF Nation — Telegram Bot (python-telegram-bot v21+)
- Préfixe: "!" (ex: !commandes, !tuto, !links, !gm, !gn)
- DM & Groupes (Topics OK)
- DEV: Polling | PROD: Webhook si PUBLIC_URL est défini

⚠️ Pour que "!" marche en groupe: BotFather → /setprivacy → Disable
"""

from __future__ import annotations
import os
import logging
import time
import random
import aiohttp
from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict, List, Tuple, Optional
from pathlib import Path

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
    CallbackQueryHandler,
)
from telegram.helpers import mention_html

# ──────────────────────────────
# Logging
# ──────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("trench-bot")

# ──────────────────────────────
# Config
# ──────────────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN", "").strip()
PUBLIC_URL  = os.getenv("PUBLIC_URL", "").strip()
PORT        = int(os.getenv("PORT", "3000"))
CMD_PREFIX  = os.getenv("CMD_PREFIX", "!")

if not BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN manquant. Définis BOT_TOKEN dans ton env.")

# ──────────────────────────────
# Liens fixes
# ──────────────────────────────
AXIOM_URL       = "https://axiom.trade/@noarcoins"
BLOOM_URL       = "https://t.me/BloomSolana_bot?start=ref_9SRKUGZABW"
UXENTO_URL      = "https://uxento.io/@noar"
RAYCYAN_URL     = "https://t.me/ray_cyan_bot?start=ref_OJzVoA"
MOCKAPE_URL     = "https://mockape.com"
INCINERATOR_URL = "https://sol-incinerator.com"
MAESTRO_URL     = "https://t.me/maestro?start=r-n0ar777"

# Tutos
T_PREMIERSPAS = os.getenv("T_PREMIERSPAS", "https://t.me/TrenchFnFNation/371")
T_SNIPRUG     = os.getenv("T_SNIPRUG",     "https://t.me/TrenchFnFNation/3469")
T_DEBUTANT    = os.getenv("T_DEBUTANT",    "https://t.me/TrenchFnFNation/362")
T_TRACKER     = os.getenv("T_TRACKER",     "https://t.me/TrenchFnFNation/375")
T_MEV         = os.getenv("T_MEV",         "https://t.me/TrenchFnFNation/362")
T_AXIOM       = os.getenv("T_AXIOM",       "https://t.me/TrenchFnFNation/983")

LEXIQUE_URL   = os.getenv("LEXIQUE_URL", "https://t.me/TrenchFnFNation/351")
# ──────────────────────────────
# Registry commandes + alias
# ──────────────────────────────
CommandFunc = Callable[[Update, ContextTypes.DEFAULT_TYPE, List[str]], Awaitable[None]]
COMMANDS: Dict[str, Tuple[CommandFunc, str]] = {}
ALIASES: Dict[str, str] = {}

def register_command(name: str, help_text: str, aliases: List[str] | None = None) -> Callable[[CommandFunc], CommandFunc]:
    def decorator(func: CommandFunc) -> CommandFunc:
        COMMANDS[name] = (func, help_text)
        for alias in aliases or []:
            ALIASES[alias] = name
        return func
    return decorator

# ──────────────────────────────
# Helpers
# ──────────────────────────────
RULES_TEXT = (
    "<b>📜 Règles du groupe</b>\n"
    "1) Respect de tous\n"
    "2) Pas de spam, pas de phishing\n"
    "3) Sois plus malin que les scammeurs\n"
    "<i>Tip:</i> Tape <code>!commandes</code> pour voir la liste."
)

def fmt_amount(x: float) -> str:
    absx = abs(x)
    if absx >= 1_000_000_000:
        return f"{x/1_000_000_000:.2f}b"
    if absx >= 1_000_000:
        return f"{x/1_000_000:.2f}m"
    if absx >= 1_000:
        return f"{x/1_000:.2f}k"
    return f"{x:.2f}"

def parse_amount(s: str) -> float:
    s = s.strip().lower().replace(",", "")
    mult = 1.0
    if s.endswith("k"):
        mult = 1e3
        s = s[:-1]
    elif s.endswith("m"):
        mult = 1e6
        s = s[:-1]
    elif s.endswith("b"):
        mult = 1e9
        s = s[:-1]
    return float(s) * mult

async def reply(update: Update, text: str, *, disable_web_preview: bool = True, reply_markup: Optional[InlineKeyboardMarkup] = None):
    msg = update.effective_message
    if not msg:
        return
    await msg.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=disable_web_preview,
        reply_markup=reply_markup,
    )

def parse_command(text: str) -> Optional[Tuple[str, List[str]]]:
    if not text or not text.startswith(CMD_PREFIX):
        return None
    content = text[len(CMD_PREFIX):].strip()
    if not content:
        return None
    parts = content.split()
    head = parts[0]
    if "@" in head:
        head = head.split("@", 1)[0]
    name = head.lower()
    args = parts[1:]
    return (name, args)

async def is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
    except Exception:
        return False

def Kb(*rows: List[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(list(rows))

def _mention_user(update: Update) -> str:
    u = update.effective_user
    if not u:
        return "trader"
    return mention_html(u.id, u.full_name if u.full_name else "trader")

# ──────────────────────────────
# Conversion utils (CoinGecko)
# ──────────────────────────────
CG_IDS = {
    "sol": "solana",
    "eth": "ethereum",
    "avax": "avalanche-2",
    "base": "base-protocol",  # BASE token (logo carré bleu) — pas le L2
    "btc": "bitcoin",
    "usdt": "tether",
    "usdc": "usd-coin",
}
FIATS = {"usd", "eur"}

_prices_cache = {"t": 0, "data": {}}

async def get_prices(ids: list[str], vs: list[str]) -> dict:
    """
    Retourne {coingecko_id: {vs: price, ...}, ...} avec un cache ~60s.
    """
    now = time.time()
    key = (tuple(sorted(ids)), tuple(sorted(vs)))
    cached = _prices_cache["data"].get(key)
    if cached and (now - _prices_cache["t"] < 60):
        return cached
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": ",".join(ids), "vs_currencies": ",".join(vs)}
    async with aiohttp.ClientSession() as s:
        async with s.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            r.raise_for_status()
            data = await r.json()
    _prices_cache["t"] = now
    _prices_cache["data"][key] = data
    return data

def _norm_sym(s: str) -> str:
    return (s or "").strip().lower()

# ──────────────────────────────
# PANELS (callbacks)
# ──────────────────────────────
async def panel_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "<b>🧰 Trench FnF Panel</b>\nAccède rapidement à nos sections :"
    markup = Kb(
        [InlineKeyboardButton("🔗 Liens utiles", callback_data="panel:links")],
        [InlineKeyboardButton("📒 Tutos", callback_data="panel:tutos")],
        [InlineKeyboardButton("📜 Commandes", callback_data="panel:cmds")],
    )
    await reply(update, text, reply_markup=markup)

async def panel_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "<b>🔗 Liens utiles</b>\nBoutons ci-dessous :"
    markup = Kb(
        [InlineKeyboardButton("💠 Axiom (−20% fees)", url=AXIOM_URL)],
        [InlineKeyboardButton("🌸 Bloom Bot", url=BLOOM_URL), InlineKeyboardButton("🤖 Ray Cyan Bot", url=RAYCYAN_URL)],
        [InlineKeyboardButton("🎼 Maestro Bot", url=MAESTRO_URL)],
        [InlineKeyboardButton("🧠 uXento / uxtension", url=UXENTO_URL)],
        [InlineKeyboardButton("🐒 MockApe", url=MOCKAPE_URL), InlineKeyboardButton("🔥 Sol Incinerator", url=INCINERATOR_URL)],
    )
    await reply(update, text, reply_markup=markup)

async def panel_tutos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "<b>📒 Tutos</b>\nRaccourcis vers les sujets Telegram + résumés :"
    markup = Kb(
        [InlineKeyboardButton("🚀 Premiers pas", url=T_PREMIERSPAS), InlineKeyboardButton("📝 Résumé", callback_data="show:premierspas")],
        [InlineKeyboardButton("📖 Lexique", url=LEXIQUE_URL)],
        [InlineKeyboardButton("🧠 Débutant", url=T_DEBUTANT), InlineKeyboardButton("📝 Résumé", callback_data="show:debutant")],
        [InlineKeyboardButton("⚙️ MEV (info)", url=T_MEV), InlineKeyboardButton("📝 Résumé", callback_data="show:mev")],
        [InlineKeyboardButton("📘 Tuto Axiom", url=T_AXIOM), InlineKeyboardButton("📝 Résumé", callback_data="show:axiom")],
        [InlineKeyboardButton("📈 Bonding curve", callback_data="show:bcurve")],
        [InlineKeyboardButton("🧭 Tracker", url=T_TRACKER), InlineKeyboardButton("📝 Résumé", callback_data="show:tracker")],
        [InlineKeyboardButton("🎯 Snip Rug", url=T_SNIPRUG), InlineKeyboardButton("📝 Résumé", callback_data="show:sniprug")],
    )
    await reply(update, text, reply_markup=markup)

async def on_panel_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq:
        return
    data = cq.data or ""
    await cq.answer()
    if data == "panel:links":
        await panel_links(update, context)
    elif data == "panel:tutos":
        await panel_tutos(update, context)
    elif data == "panel:cmds":
        await cmd_commandes(update, context, [])
    elif data.startswith("show:"):
        name = data.split(":", 1)[1]
        mapping: Dict[str, CommandFunc] = {
            "premierspas": cmd_premierspas,
            "debutant": cmd_debutant,
            "mev": cmd_mev,
            "axiom": cmd_tutoaxiom,
            "bcurve": cmd_bcurve,
            "tracker": cmd_tracker,
            "sniprug": cmd_sniprug,
        }
        func = mapping.get(name)
        if func:
            await func(update, context, [])

# ──────────────────────────────
# CORE / AIDE
# ──────────────────────────────
@register_command(
    name="commandes",
    help_text="Menu complet de toutes les commandes",
    aliases=["cmd", "help", "aide"],
)
async def cmd_commandes(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    lines = [
        "<b>📚 Menu complet</b>",
        "\n<b>🧰 Panel</b>",
        "• <code>/start</code> → ouvre le <b>Panel</b> (boutons Liens & Tutos)",
        "• <code>!start</code> → ouvre le <b>Panel</b> (même chose, pratique en groupe)",
        "\n<b>ℹ️ Core/Aide</b>",
        "• <code>!about</code>, <code>!id</code>, <code>!topic</code>, <code>!ping</code>, <code>!gm</code> (alias <code>!bonjour</code>), <code>!gn</code> (alias <code>!bonnenuit</code>)",
        "\n<b>🔗 Liens</b>",
        "• <code>!links</code> (boutons)",
        "• <code>!axiom</code>, <code>!bloom</code> (alias <code>!bloombot</code>), <code>!uxento</code>, <code>!raycyan</code> (alias <code>!ray</code>), <code>!mockape</code> (alias <code>!ma</code>), <code>!solincinerator</code>",
        "\n<b>📈 Marché (rapide)</b>",
        "• <code>!dex</code> — ce que signifie « payer le DEX » (bannière + réseaux sociaux, ≈1.5 SOL)",
        "• <code>!fees</code> — slippage/priority/bribe conseillés",
        "• <code>!bond</code> — explication de la migration (bond vers DEX)\n• <code>!convert</code> — conversions USD/EUR ⇄ SOL/ETH/AVAX/BASE/BTC/USDT/USDC",
        "\n<b>⚠️ Warning</b>",
        "• <code>!pnl</code> — mise en garde sur les cartes PnL (fausses captures, manipulations, etc.)",
        " \n<b>📒 Tutos</b>",
        "• <code>!tuto</code> (hub)\n• <code>!roadmap</code> — parcours conseillé",
        "• <code>!premierspas</code>, <code>!lexique</code> (alias <code>!lx</code>), <code>!bcurve</code> (alias <code>!bondingcurve</code>, <code>!bc</code>), <code>!mev</code>, <code>!tutoaxiom</code>, <code>!debutant</code>, <code>!tracker</code>, <code>!sniprug</code>",
        "\n<b>🛰️ Tracker (Wallet temps réel)</b>",
        "• <code>!watch &lt;adresse&gt; [alias]</code> (alias <code>!wallet</code>) — suivre un wallet (image en haut, CA copiable, ticker/nom)",
        "• <code>!unwatch &lt;adresse&gt;</code> — arrêter le suivi",
        "• <code>!unwatchall</code> — vider tout",
        "• <code>!list</code> — liste compacte | <code>!listdetail</code> — alias, date, launchonly, minSOL",
        "• <code>!setrpc &lt;http_url&gt;</code> — endpoint HTTP (pour <i>getTransaction</i>)",
        "• <code>!setws &lt;wss_url&gt;</code> — endpoint WebSocket (sinon auto à partir du HTTP)",
        "• <code>!launchonly &lt;adresse&gt; on|off</code> — notifier seulement la <u>première</u> fois par token",
        "• <code>!minsol &lt;adresse&gt; &lt;montant_SOL&gt;</code> — filtrer les achats &lt; seuil de SOL",
        "• <code>!silent on/off</code> — notifications silencieuses (par chat)",
    ]
    await reply(update, "\n".join(lines))

async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /start ouvre un panneau visuel
    await panel_root(update, context)


@register_command(name="start", help_text="Ouvre le panel (comme /start)")
async def cmd_start_alias(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    # "!start" en groupe pour éviter de ping tous les bots avec "/start"
    await panel_root(update, context)

@register_command(name="about", help_text="À propos du bot", aliases=["info"])
async def cmd_about(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    me = await context.bot.get_me()
    txt = (
        f"<b>🤖 {me.first_name}</b> (@{me.username})\n"
        f"Préfixe: <code>{CMD_PREFIX}</code>\n"
        "• Panel via /start\n"
        "• Liens cliquables + Tutos\n"
        "• DM & Groupes (Topics OK)"
    )
    await reply(update, txt)

@register_command(name="id", help_text="ID utilisateur & chat", aliases=["whoami"])
async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    u = update.effective_user
    c = update.effective_chat
    if not u or not c:
        await reply(update, "Contexte utilisateur/chat indisponible.")
        return
    await reply(update, f"<b>User ID:</b> <code>{u.id}</code>\n<b>Chat ID:</b> <code>{c.id}</code>")

@register_command(name="topic", help_text="ID du topic courant", aliases=["thread"])
async def cmd_topic(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    msg = update.effective_message
    thr = getattr(msg, "message_thread_id", None) if msg else None
    await reply(update, f"🧵 <b>Topic ID:</b> <code>{thr}</code>" if thr else "(Pas de topic ici)")

# Ping avec latence + bouton supprimer
@register_command(name="ping", help_text="Ping + latence (ms)", aliases=["p"])
async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    base = "🛰️ <b>Signal reçu</b> — <code>P O N G</code>"
    markup = Kb([InlineKeyboardButton("🗑 Supprimer", callback_data="pong:del")])
    t0 = time.perf_counter()
    msg = update.effective_message
    sent = None
    if msg:
        sent = await msg.reply_text(base, parse_mode=ParseMode.HTML, reply_markup=markup)
    api_ms = int((time.perf_counter() - t0) * 1000)
    since_user_ms = api_ms
    if msg and msg.date:
        try:
            since_user_ms = int((datetime.now(timezone.utc) - msg.date).total_seconds() * 1000)
        except Exception:
            pass
    txt = base + f"\n⏱️ ~{api_ms} ms API, ~{since_user_ms} ms total"
    if sent:
        try:
            await sent.edit_text(txt, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception:
            pass

async def on_pong_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cq = update.callback_query
    if not cq:
        return
    await cq.answer()
    # supprimer la réponse et le message d'origine via bot.delete_message (typage sûr)
    try:
        msg = cq.message
        if msg:
            try:
                await context.bot.delete_message(chat_id=msg.chat.id, message_id=msg.message_id)
            except Exception:
                pass
            original = getattr(msg, "reply_to_message", None)
            if original:
                try:
                    await context.bot.delete_message(chat_id=original.chat.id, message_id=original.message_id)
                except Exception:
                    pass
    except Exception:
        logger.exception("pong delete")

# ──────────────────────────────
# LIENS
# ──────────────────────────────
@register_command(name="links", help_text="Raccourcis liens (boutons)", aliases=["liens"])
async def cmd_links(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await panel_links(update, context)

@register_command(name="axiom", help_text="Axiom — #1 memecoins Solana")
async def cmd_axiom(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = "<b>Axiom</b>\n#1 plateforme pour trader des memecoins sur Solana.\n👉 <a href=\"%s\">%s</a>\n<i>(−20%% de fees via ce lien)</i>" % (AXIOM_URL, AXIOM_URL)
    await reply(update, text, reply_markup=Kb([InlineKeyboardButton("💠 Ouvrir Axiom", url=AXIOM_URL)]))

@register_command(name="bloom", help_text="Bloom Bot (Telegram)", aliases=["bloombot"])
async def cmd_bloom(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(update, "<b>Bloom Bot</b>\nBot sur Solana pour, rug alerts, sniper, copytrade, etc...\n👉 <a href=\"%s\">%s</a>" % (BLOOM_URL, BLOOM_URL),
                reply_markup=Kb([InlineKeyboardButton("🌸 Ouvrir Bloom Bot", url=BLOOM_URL)]))


@register_command(name="maestro", help_text="Maestro Bot (multi‑chain: Base/Avax/Eth/…)")
async def cmd_maestro(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    txt = (
        "<b>Maestro Bot</b>\n"
        "Bot multi‑chain (Base, AVAX, ETH, etc.) pour trader/track rapidement.\n"
        f"👉 <a href=\"{MAESTRO_URL}\">{MAESTRO_URL}</a>"
    )
    await reply(update, txt, reply_markup=Kb([InlineKeyboardButton("🎼 Ouvrir Maestro Bot", url=MAESTRO_URL)]))

@register_command(name="uxento", help_text="uXento / uxtension", aliases=["uxtension"])
async def cmd_uxento(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(update, "<b>uXento / uxtension</b>\nExtension Chrome: tendances & insights du marché.\n👉 <a href=\"%s\">%s</a>" % (UXENTO_URL, UXENTO_URL),
                reply_markup=Kb([InlineKeyboardButton("🧠 Ouvrir uXento", url=UXENTO_URL)]))

@register_command(name="raycyan", help_text="Ray Cyan Bot (alias !ray)", aliases=["ray"])
async def cmd_raycyan(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(update, "<b>Ray Cyan</b>\nBot pour suivi de marché & tendances en temps réel.\n👉 <a href=\"%s\">%s</a>" % (RAYCYAN_URL, RAYCYAN_URL),
                reply_markup=Kb([InlineKeyboardButton("🤖 Ouvrir Ray Cyan Bot", url=RAYCYAN_URL)]))

@register_command(name="mockape", help_text="MockApe", aliases=["ma"])
async def cmd_mockape(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(update, "<b>MockApe</b>\nOutil pratique pour paper trade sur axiom (Faux Solana).\n👉 <a href=\"%s\">%s</a>" % (MOCKAPE_URL, MOCKAPE_URL),
                reply_markup=Kb([InlineKeyboardButton("🐒 Ouvrir MockApe", url=MOCKAPE_URL)]))

@register_command(name="solincinerator", help_text="Sol Incinerator")
async def cmd_solincinerator(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(update, "<b>Sol Incinerator</b>\nRécupère une partie de tes frais de transaction.\n👉 <a href=\"%s\">%s</a>" % (INCINERATOR_URL, INCINERATOR_URL),
                reply_markup=Kb([InlineKeyboardButton("🔥 Ouvrir Sol Incinerator", url=INCINERATOR_URL)]))

# ──────────────────────────────
# PÉDAGO (hub + commandes)
# ──────────────────────────────
@register_command(name="tuto", help_text="Hub des tutoriels")
async def cmd_tuto(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>📒 Hub Tutos</b>\n"
        "Choisis un sujet ci-dessous ou tape la commande dédiée:\n"
        "• <code>!premierspas</code> — setup & outils de base\n"
        "• <code>!bcurve</code> (alias <code>!bondingcurve</code>, <code>!bc</code>) — logique de prix\n"
        "• <code>!mev</code> — (info uniquement) comprendre les bots MEV et les risques\n"
        "• <code>!tutoaxiom</code> — guide Axiom détaillé (outils, protections, exemples)\n"
        "• <code>!debutant</code> — conseils rapides\n"
        "• <code>!tracker</code> — wallet & twitter tracker\n"
        "• <code>!sniprug</code> — tuto scanner/sniper les ruggers"
    )
    markup = Kb(
        [InlineKeyboardButton("🚀 Premiers pas", url=T_PREMIERSPAS), InlineKeyboardButton("📝 Résumé", callback_data="show:premierspas")],
        [InlineKeyboardButton("📖 Lexique", url=LEXIQUE_URL)],
        [InlineKeyboardButton("🧠 Débutant", url=T_DEBUTANT), InlineKeyboardButton("📝 Résumé", callback_data="show:debutant")],
        [InlineKeyboardButton("⚙️ MEV (info)", url=T_MEV), InlineKeyboardButton("📝 Résumé", callback_data="show:mev")],
        [InlineKeyboardButton("📘 Tuto Axiom", url=T_AXIOM), InlineKeyboardButton("📝 Résumé", callback_data="show:axiom")],
        [InlineKeyboardButton("📈 Bonding curve", callback_data="show:bcurve")],
        [InlineKeyboardButton("🧭 Tracker", url=T_TRACKER), InlineKeyboardButton("📝 Résumé", callback_data="show:tracker")],
        [InlineKeyboardButton("🎯 Snip Rug", url=T_SNIPRUG), InlineKeyboardButton("📝 Résumé", callback_data="show:sniprug")],
    )
    await reply(update, text, reply_markup=markup)


@register_command(name="lexique", help_text="Lexique des termes", aliases=["lx"])
async def cmd_lexique(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(
        update,
        "<b>📖 Lexique</b>\nToutes les définitions utiles (CT, LP, MC, slippage, etc.).\n👉 <a href=\"%s\">%s</a>" % (LEXIQUE_URL, LEXIQUE_URL)
    )


@register_command(name="roadmap", help_text="Parcours conseillé (étapes & liens)")
async def cmd_roadmap(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    txt = (
        "<b>🧭 Roadmap Apprentissage</b>\n"
        "1) <code>!premierspas</code> — setup & outils de base\n"
        "2) <code>!debutant</code> — conseils rapides & hygiène\n"
        "3) <code>!tutoaxiom</code> — guide Axiom détaillé\n"
        "4) <code>!tracker</code> — suivre wallets & actus\n"
        "5) <b>Outils utiles</b> — <code>!fees</code>, <code>!dex</code>, <code>!bond</code>, <code>!convert</code>, <code>!pnl</code>, <code>!lexique</code>\n"
        f"\n👉 <u>Liens directs</u>: Premiers pas: <a href=\"{T_PREMIERSPAS}\">post</a> • Débutant: <a href=\"{T_DEBUTANT}\">post</a> • Axiom: <a href=\"{T_AXIOM}\">tuto</a> • Tracker: <a href=\"{T_TRACKER}\">post</a>"
    )
    await reply(update, txt)
@register_command(name="tutoaxiom", help_text="Tuto Axiom détaillé")
async def cmd_tutoaxiom(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>📘 Tuto Axiom</b>\n"
        "Pas-à-pas pour bien utiliser Axiom : vues, filtres, protections anti-rug, bonnes pratiques.\n"
        f"👉 Lien : <a href=\"{T_AXIOM}\">{T_AXIOM}</a>"
    )
    await reply(update, text)

@register_command(name="premierspas", help_text="Bien démarrer dans les memecoins")
async def cmd_premierspas(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>🚀 Premiers pas</b>\n"
        "• Installe les outils: Axiom, uXento, Bloom Bot, Ray Cyan Bot\n"
        "• Configure ton wallet: seed <u>jamais</u> partagée, clés séparées, budget test\n"
        "• Apprends les bases: filtres, volumes, LP, timing\n\n"
        f"👉 Sujet détaillé: <a href=\"{T_PREMIERSPAS}\">{T_PREMIERSPAS}</a>"
    )
    await reply(update, text)

@register_command(name="bcurve", help_text="Bonding curve", aliases=["bondingcurve","bc"])
async def cmd_bcurve(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>📈 Bonding curve</b>\n"
        "La courbe relie le prix à la quantité achetée/vendue.\n"
        "• Early = prix bas\n"
        "• Chaque achat pousse le prix (exponentiel)\n"
        "<i>Conséquence:</i> entrer tôt = moins cher, mais très volatil."
    )
    await reply(update, text)

@register_command(name="mev", help_text="(Info) Comprendre les bots MEV et leurs risques")
async def cmd_mev(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>⚙️ MEV bots — Informations uniquement</b>\n"
        "Ce contenu est <u>éducatif</u> (pas une incitation à utiliser des bots).\n"
        "• Concepts: arbitrage, priorisation de tx, <i>sandwich</i>\n"
        "• Risques: pertes, frais élevés, front-run, impacts éthiques/juridiques\n"
        "• Objectif: identifier ces comportements et s'en protéger\n\n"
        f"👉 Hub astuce et anti-rug : <a href=\"{T_MEV}\">{T_MEV}</a>\n"
        f"👉 📘 Tuto Axiom et MEV : <a href=\"{T_AXIOM}\">{T_AXIOM}</a>"
    )
    await reply(update, text)

@register_command(name="debutant", help_text="Conseils rapides + liens utiles")
async def cmd_debutant(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>🧠 Conseils débutant</b>\n"
        "• N'investis que ce que tu peux perdre\n"
        "• Commence petit, observe les volumes\n"
        "• Vérifie les flags (mint, LP, blacklist)\n"
        "• Anti-rug: lis les conseils & exemples visuels\n"
        f"👉 Sujet Débutant : <a href=\"{T_DEBUTANT}\">{T_DEBUTANT}</a>\n"
        f"👉 📘 Tuto Axiom : <a href=\"{T_AXIOM}\">{T_AXIOM}</a>"
    )
    await reply(update, text)

@register_command(name="tracker", help_text="Wallet & Twitter tracker (Trench #375)")
async def cmd_tracker(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>🧭 Trackers</b>\n"
        "• Wallet tracker: suivez des portefeuilles clés\n"
        "• Twitter tracker: alertes sur comptes CT\n"
        f"👉 Sujet & téléchargement: <a href=\"{T_TRACKER}\">{T_TRACKER}</a>"
    )
    await reply(update, text)

@register_command(name="sniprug", help_text="Tuto scanner/sniper les ruggers (alias: !rug)", aliases=["rug"])
async def cmd_sniprug(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(update, f"<b>🎯 Sniper les ruggers</b>\nÉtapes et outils recommandés.\n👉 <a href=\"{T_SNIPRUG}\">{T_SNIPRUG}</a>")

@register_command(name="fees", help_text="Frais conseillés (slippage/priority/bribe)")
async def cmd_fees(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>💸 Fees recommandés</b>\n"
        "• Slippage: <b>10%</b>\n"
        "• Priority fee: <b>0.001</b>\n"
        "• Bribe: <b>0.001</b>\n\n"
        "<i>Astuce:</i> ajuste selon le rush. Trop bas = tx lente/ratée, trop haut = tu surpayes."
    )
    await reply(update, text)

@register_command(name="bond", help_text="Qu'est-ce que la migration (bond) ?")
async def cmd_bond(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>🔄 Migration (Bond)</b>\n"
        "Passage d'un token d'un modèle initial (ex: pump.fun) vers une LP DEX stable.\n"
        "• Les jetons restants sur la bonding curve sont migrés/convertis\n"
        "• Création/renforcement de LP, nouvelles règles (taxes, ownership)\n"
        "• Objectif: prix plus stable, meilleure liquidité"
    )
    await reply(update, text)

@register_command(name="dex", help_text="Payer le DEX — explication rapide")
async def cmd_dex(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>🏦 Payer le DEX</b>\n"
        "Dans le langage courant, « payer le DEX » signifie <u>payer des frais fixes (≈1.5 SOL selon la plate‑forme)</u>\n"
        "pour <b>ajouter une bannière et des réseaux sociaux</b> à la page du coin sur le DEX/agrégateur.\n"
        "• <b>Ce paiement peut être fait par le dev ou n\'importe qui</b>\n"
        "• <b>Ça ne change pas les fondamentaux</b> (tokenomics/liquidité), c\'est juste de la mise en vitrine\n"
        "• Utile pour la crédibilité/visibilité, mais <i>ne remplace aucune due diligence</i>"
    )
    await reply(update, text)


@register_command(name="convert", help_text="Conversion: !convert 100 usd-sol (ou 2.5 sol-eur, 1 avax-base, 50 eur-usd)")
async def cmd_convert(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    if not args:
        await reply(update, "Usage: <code>!convert 100 usd-sol</code> • <code>!convert 2.5 sol-eur</code> • <code>!convert 1 avax-base</code> • <code>!convert 50 eur-usd</code>")
        return
    raw = " ".join(args).strip()
    # Accept both "100 usd->sol" and "100usd->sol"
    import re as _re
    m = _re.match(r"^\s*([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Z]+)\s*-\s*([a-zA-Z]+)\s*$", raw)
    if not m:
        await reply(update, "Format invalide. Ex: <code>!convert 100 usd-sol</code>")
        return
    amount = float(m.group(1).replace(",", "."))
    base = _norm_sym(m.group(2))
    quote = _norm_sym(m.group(3))

    def sym_to_id(sym: str):
        if sym in FIATS:
            return None
        return CG_IDS.get(sym)

    b_id = sym_to_id(base)
    q_id = sym_to_id(quote)
    # Validate symbols
    if base not in FIATS and not b_id:
        await reply(update, f"Symbole inconnu: <code>{base}</code>")
        return
    if quote not in FIATS and not q_id:
        await reply(update, f"Symbole inconnu: <code>{quote}</code>")
        return

    ids = [x for x in {b_id, q_id} if x]
    vs = list(FIATS | ({quote} if quote in FIATS else set()) | ({base} if base in FIATS else set()))
    if not ids:
        ids = ["bitcoin"]  # dummy for fiat->fiat (not handled ultimately)
    prices = await get_prices(ids, vs)

    def price_in(sym: str, fiat: str) -> float | None:
        # returns price of sym in fiat (sym can be fiat -> 1 if same fiat)
        if sym in FIATS:
            return 1.0 if sym == fiat else None
        cid = CG_IDS.get(sym)
        if not cid:
            return None
        p = prices.get(cid) or {}
        val = p.get(fiat)
        return float(val) if val is not None else None

    note_base = ""
    if base == "base" or quote == "base":
        note_base = "\n<i>Note:</i> <b>BASE</b> = token <u>Base Protocol</u>, pas le réseau L2 \"Base\"."

    # Cases
    if base in FIATS and quote not in FIATS:
        px = price_in(quote, base)
        if not px:
            await reply(update, "Prix indisponible actuellement.")
            return
        qty = amount / px
        await reply(update, f"{amount:g} <b>{base.upper()}</b> ≈ <code>{qty:.6f}</code> <b>{quote.upper()}</b>{note_base}")
        return
    if base not in FIATS and quote in FIATS:
        px = price_in(base, quote)
        if not px:
            await reply(update, "Prix indisponible actuellement.")
            return
        val = amount * px
        await reply(update, f"{amount:g} <b>{base.upper()}</b> ≈ <code>{val:.2f}</code> <b>{quote.upper()}</b>{note_base}")
        return
    if base not in FIATS and quote not in FIATS:
        px_b = price_in(base, "usd")
        px_q = price_in(quote, "usd")
        if not (px_b and px_q):
            await reply(update, "Prix croisés indisponibles.")
            return
        qty = amount * (px_b / px_q)
        await reply(update, f"{amount:g} <b>{base.upper()}</b> ≈ <code>{qty:.6f}</code> <b>{quote.upper()}</b>{note_base}")
        return

    
    # Fiat ↔ Fiat via cross-rate from BTC
    if base in FIATS and quote in FIATS:
        if base == quote:
            await reply(update, f"{amount:g} <b>{base.upper()}</b> = <code>{amount:g}</code> <b>{quote.upper()}</b>")
            return
        prices_fx = await get_prices(["bitcoin"], list(FIATS))
        btc_map = prices_fx.get("bitcoin", {})
        if not btc_map or base not in btc_map or quote not in btc_map:
            await reply(update, "Taux fiat indisponible actuellement.")
            return
        rate = float(btc_map[quote]) / float(btc_map[base])
        val = amount * rate
        await reply(update, f"{amount:g} <b>{base.upper()}</b> ≈ <code>{val:.2f}</code> <b>{quote.upper()}</b>")
        return

    await reply(update, "Paire non prise en charge.")
@register_command(name="pnl", help_text="Mise en garde sur les cartes PnL")
async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    text = (
        "<b>📈 À propos des cartes PnL (bots Telegram / Axiom)</b>\n\n"
        "<b>Attention aux fausses apparences !</b>\n\n"
        "<b>• Ce sont des PnL théoriques</b>\n"
        "Aucune preuve réelle (wallet, tx hash, historique) n'est liée à ces cartes.\n\n"
        "<b>• Elles peuvent être manipulées</b>\n"
        "Données saisies à la main, faux calls, retouches.\n\n"
        "<b>• Elles ne prouvent rien</b>\n"
        "Une jolie carte ≠ un bon trader.\n\n"
        "Même une carte PnL Axiom peut être falsifiée :\n"
        "• Générer sur n'importe quel token en se greffant à une tx publique\n"
        "• IA/retouche pour embellir\n\n"
        "<b>Conseil</b> : privilégie les preuves vérifiables (wallets publics, tx, historique réel).\n"
        "Reste critique, reste malin."
    )
    await reply(update, text)

# ──────────────────────────────
# FUN: GM / GN
# ──────────────────────────────
GM_MESSAGES = [
    "GM {name} ☀️ Prêt à farmer les memecoins ?",
    "GM {name} 🚀 On vise des entrées propres et des sorties disciplinées.",
    "GM {name} 💎 Pas de FOMO, que des plans.",
    "GM {name} 📊 Café, filtres Axiom, et on décolle.",
    "GM {name} 🎯 Today: moins de rug, plus de R:R.",
]
GN_MESSAGES = [
    "GN {name} 🌙 Ferme le terminal, garde tes clés au chaud.",
    "GN {name} 😴 Le meilleur trade maintenant, c’est le sommeil.",
    "GN {name} 🛡️ Demain on reroll des filtres propres.",
    "GN {name} 🌌 Reste safe, no FOMO de nuit.",
    "GN {name} 💤 Les ruggers dorment jamais, toi oui.",
]

@register_command(name="gm", help_text="Souhaite un bonjour trading", aliases=["bonjour"])
async def cmd_gm(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    name = _mention_user(update)
    msg = random.choice(GM_MESSAGES).format(name=name)
    await reply(update, msg)

@register_command(name="gn", help_text="Souhaite une bonne nuit trading", aliases=["bonnenuit"])
async def cmd_gn(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    name = _mention_user(update)
    msg = random.choice(GN_MESSAGES).format(name=name)
    await reply(update, msg)

# ──────────────────────────────
# UTILITAIRES
# ──────────────────────────────
@register_command(name="setrules", help_text="(Admin) Modifier les règles")
async def cmd_setrules(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    global RULES_TEXT
    if not args:
        await reply(update, "Usage: <code>!setrules Ton nouveau texte (HTML autorisé)</code>")
        return
    chat = update.effective_chat
    user = update.effective_user
    if not (chat and user):
        await reply(update, "Contexte indisponible.")
        return
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER):
            await reply(update, "⛔ Seuls les admins peuvent modifier les règles.")
            return
    except Exception:
        pass
    RULES_TEXT = " ".join(args)
    await reply(update, "✅ Règles mises à jour. Tape <code>!regles</code> pour vérifier.")

@register_command(name="regles", help_text="Affiche les règles", aliases=["rules","r"])
async def cmd_regles(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    await reply(update, RULES_TEXT)

@register_command(name="vote", help_text="Créer un sondage: !vote Question ? | Option1 | Option2 | ...")
async def cmd_vote(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    raw = " ".join(args).strip()
    if "|" not in raw:
        await reply(update, "Usage: <code>!vote Question ? | Oui | Non</code> (sépare par <code>|</code>)")
        return
    parts = [p.strip() for p in raw.split("|")]
    question = parts[0] if parts else ""
    options = [o for o in parts[1:] if o]
    if len(options) < 2:
        await reply(update, "Donne au moins 2 options.")
        return
    chat = update.effective_chat
    msg = update.effective_message
    if not chat:
        await reply(update, "Chat introuvable.")
        return
    try:
        await context.bot.send_poll(
            chat_id=chat.id,
            question=question[:300],
            options=options[:10],
            is_anonymous=True,
            allows_multiple_answers=False,
            message_thread_id=(msg.message_thread_id if msg and hasattr(msg, "message_thread_id") else None),
        )
    except Exception:
        await reply(update, "❌ Impossible de créer le sondage (droits ?)")

@register_command(name="riskcalc", help_text="SL/TP en Market Cap: !riskcalc <mc> <sl%> <tp%> (ex: 1.2m 10 25)")
async def cmd_riskcalc(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    if len(args) < 3:
        await reply(update, "Usage: <code>!riskcalc 1.2m 10 25</code> (MC d'entrée, SL% baisse, TP% hausse). Suffixes: k/m/b")
        return
    try:
        mc_entry = parse_amount(args[0])
        slp = float(args[1].replace(",", ".")) / 100.0
        tpp = float(args[2].replace(",", ".")) / 100.0
        mc_sl = mc_entry * (1 - slp)
        mc_tp = mc_entry * (1 + tpp)
        texte = (
            "<b>🎯 Risk Calc (Market Cap)</b>\n"
            f"Entrée: <code>{fmt_amount(mc_entry)}</code>\n"
            f"SL ({args[1]}%): <code>{fmt_amount(mc_sl)}</code>\n"
            f"TP ({args[2]}%): <code>{fmt_amount(mc_tp)}</code>"
        )
        await reply(update, texte)
    except Exception:
        await reply(update, "⚠️ Arguments invalides. Exemple: <code>!riskcalc 1.2m 10 25</code> (k/m/b ok)")


# ──────────────────────────────
# ROUTER & BOOTSTRAP
# ──────────────────────────────
def parse_prefix(update: Update) -> Optional[Tuple[str, List[str]]]:
    msg = update.effective_message
    if not msg:
        return None
    text = msg.text or msg.caption or ""
    if not text.startswith(CMD_PREFIX):
        return None
    return parse_command(text)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = parse_prefix(update)
    if not parsed:
        return
    name, args = parsed
    real = ALIASES.get(name, name)
    if real not in COMMANDS:
        await reply(update, f"❓ Commande inconnue: <code>!{name}</code> — tape <code>!commandes</code>")
        return
    handler, _help = COMMANDS[real]
    try:
        await handler(update, context, args)
    except Exception:
        logger.exception("Erreur !%s", real)
        await reply(update, "⚠️ Erreur pendant la commande. Regarde les logs.")

# Wrappers pour éviter les lambdas (Pyright)
async def _show_cmds(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await cmd_commandes(u, c, [])

async def _show_help(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await cmd_commandes(u, c, [])

def build_app() -> Application:
    app: Application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CommandHandler("commandes", _show_cmds))
    app.add_handler(CommandHandler("help", _show_help))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_pong_delete, pattern="^pong:del$"))
    app.add_handler(CallbackQueryHandler(on_panel_click, pattern="^(panel:|show:)"))
    return app

if __name__ == "__main__":
    app = build_app()
    if PUBLIC_URL:
        webhook_path = "/webhook"
        full_url = f"{PUBLIC_URL.rstrip('/')}{webhook_path}"
        logger.info("WEBHOOK sur %s (port %s)", full_url, PORT)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path.strip("/"),
            webhook_url=full_url,
            drop_pending_updates=True,
        )
    else:
        logger.info("Polling (LOCAL/DEV)")
        app.run_polling(drop_pending_updates=True)


# =========================
# TRACKER (Wallet real-time)
# PID-less, images, launchonly, minSOL, silent, aliases
# =========================
import aiohttp
from telegram import Update
from telegram.ext import Application, ContextTypes

# Fallbacks if the host bot doesn't define them (won't override if already present)


# ── Persistence ───────────────────────────────────────────────────────────────
TRACKER_STORE = os.getenv("TRACKER_STORE", "./tracker_state.json")
TRACKER_STATE: Dict[int, Dict[str, object]] = {}  # chat_id -> config
_ws_task = None  # background WS task handle

def _default_chat_cfg():
    return {
        "http_rpc": os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com"),
        "ws_rpc": os.getenv("SOLANA_WS", ""),
        "silent": False,
        "subs": {}  # addr -> {alias, added_at, launchonly, seen_mints, min_sol}
    }

def load_state():
    global TRACKER_STATE
    if not os.path.exists(TRACKER_STORE):
        TRACKER_STATE = {}
        return
    try:
        with open(TRACKER_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        out = {}
        for chat_id_str, cfg in data.items():
            cfg = cfg or {}
            cfg.setdefault("http_rpc", _default_chat_cfg()["http_rpc"])
            cfg.setdefault("ws_rpc", _default_chat_cfg()["ws_rpc"])
            cfg.setdefault("silent", False)
            subs = cfg.get("subs") or {}
            for addr, meta in subs.items():
                meta.setdefault("alias", "")
                meta.setdefault("added_at", datetime.now(timezone.utc).isoformat())
                meta.setdefault("launchonly", False)
                meta.setdefault("seen_mints", [])
                meta.setdefault("min_sol", 0.0)
            cfg["subs"] = subs
            out[int(chat_id_str)] = cfg
        TRACKER_STATE = out
    except Exception as e:
        logger.exception("load_state failed: %s", e)
        TRACKER_STATE = {}

async def save_state():
    try:
        tmp = {str(chat_id): cfg for chat_id, cfg in TRACKER_STATE.items()}
        Path(TRACKER_STORE).write_text(json.dumps(tmp, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.exception("save_state failed: %s", e)

# ── Helpers ───────────────────────────────────────────────────────────────────
BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
BADGE_LAUNCH_ON  = "🚀"
BADGE_LAUNCH_OFF = "🟢"
BADGE_SILENT_ON  = "🔕"
BADGE_SILENT_OFF = "🔔"

def is_valid_pubkey(s: str) -> bool:
    return bool(BASE58_RE.match((s or "").strip()))

def short_pk(pk: str) -> str:
    return pk[:4] + "…" + pk[-4:]

def display_name(addr: str, meta: dict) -> str:
    alias = (meta or {}).get("alias", "").strip()
    return alias if alias else short_pk(addr)

def launch_badge(meta: dict) -> str:
    return BADGE_LAUNCH_ON if (meta or {}).get("launchonly") else BADGE_LAUNCH_OFF

def solscan_tx(signature: str) -> str:
    return f"https://solscan.io/tx/{signature}"

def solscan_addr(addr: str) -> str:
    return f"https://solscan.io/address/{addr}"

def infer_ws_from_http(http_url: str) -> str:
    if http_url.startswith("https://"):
        return "wss://" + http_url[len("https://"):]
    if http_url.startswith("http://"):
        return "ws://" + http_url[len("http://"):]
    if http_url.startswith(("wss://", "ws://")):
        return http_url
    return "wss://api.mainnet-beta.solana.com"

def tracker_chat_state(chat_id: int) -> Dict[str, object]:
    if chat_id not in TRACKER_STATE:
        TRACKER_STATE[chat_id] = _default_chat_cfg()
    return TRACKER_STATE[chat_id]

# ── Token metadata (Jupiter + optional Helius) ────────────────────────────────
class TokenMetaCache:
    def __init__(self):
        self.by_mint: Dict[str, dict] = {}
        self.ready = False
        self.helius_key = os.getenv("HELIUS_API_KEY", "")

    async def warm(self, session: aiohttp.ClientSession):
        if self.ready:
            return
        try:
            async with session.get("https://token.jup.ag/all", timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for t in data:
                        mint = t.get("address")
                        if mint:
                            self.by_mint[mint] = {
                                "symbol": t.get("symbol") or "",
                                "name": t.get("name") or "",
                                "logo": t.get("logoURI") or "",
                                "decimals": t.get("decimals"),
                            }
        except Exception as e:
            logger.warning("Jupiter list load failed: %s", e)
        self.ready = True

    async def get(self, session: aiohttp.ClientSession, mint: str) -> dict:
        if mint in self.by_mint:
            return self.by_mint[mint]
        if self.helius_key:
            try:
                url = f"https://api.helius.xyz/v0/tokens/metadata?api-key={self.helius_key}"
                async with session.post(url, json={"mintAccounts": [mint]}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                    if resp.status == 200:
                        arr = await resp.json()
                        if arr and isinstance(arr, list) and arr[0]:
                            md = arr[0]
                            out = {"symbol": (md.get("symbol") or "")[:16], "name": (md.get("name") or "")[:64], "logo": md.get("logo") or ""}
                            self.by_mint[mint] = out
                            return out
            except Exception as e:
                logger.warning("Helius metadata failed: %s", e)
        out = {"symbol": "", "name": "", "logo": ""}
        self.by_mint[mint] = out
        return out

TOKENS = TokenMetaCache()

# ── Delta computation ─────────────────────────────────────────────────────────
def _ui_to_float(ui_amount: dict) -> float:
    try:
        return float(ui_amount.get("uiAmount", 0.0))
    except Exception:
        try:
            amount = int(ui_amount.get("amount", "0"))
            decimals = int(ui_amount.get("decimals", 0))
            return amount / (10 ** decimals)
        except Exception:
            return 0.0

def compute_deltas_and_new(tx: dict, owner: str):
    """Return (token_deltas_by_mint: Dict[mint,float], sol_delta_in_SOL: float, newly_received_mints: Set[mint])."""
    meta = tx.get("meta") or {}
    transaction = tx.get("transaction") or {}
    message = transaction.get("message") or {}
    account_keys = message.get("accountKeys") or []

    owner_index = None
    for i, k in enumerate(account_keys):
        if (isinstance(k, str) and k == owner) or (isinstance(k, dict) and k.get("pubkey") == owner):
            owner_index = i; break

    sol_delta = 0.0
    pre_balances = meta.get("preBalances") or []
    post_balances = meta.get("postBalances") or []
    if owner_index is not None and owner_index < len(pre_balances) and owner_index < len(post_balances):
        lamport_delta = (post_balances[owner_index] or 0) - (pre_balances[owner_index] or 0)
        sol_delta = lamport_delta / 1_000_000_000.0

    token_deltas: Dict[str, float] = {}
    newly_received: set[str] = set()

    pre_tb = meta.get("preTokenBalances") or []
    post_tb = meta.get("postTokenBalances") or []

    def map_idx(tb_list: List[dict]):
        m = {}
        for e in tb_list:
            m[(e.get("accountIndex"), e.get("mint"))] = e
        return m

    pre_map = map_idx(pre_tb)
    post_map = map_idx(post_tb)
    keys = set(pre_map.keys()) | set(post_map.keys())

    for (acct_idx, mint) in keys:
        pre = pre_map.get((acct_idx, mint))
        post = post_map.get((acct_idx, mint))
        if (pre or {}).get("owner") != owner and (post or {}).get("owner") != owner:
            continue
        pre_amt = _ui_to_float((pre or {}).get("uiTokenAmount", {}))
        post_amt = _ui_to_float((post or {}).get("uiTokenAmount", {}))
        delta = post_amt - pre_amt
        if abs(delta) > 0:
            token_deltas[mint] = token_deltas.get(mint, 0.0) + delta
        if post_amt > 0 and (pre is None or pre_amt <= 0):
            newly_received.add(mint)

    return token_deltas, sol_delta, newly_received

async def build_summary_and_media(session: aiohttp.ClientSession, owner: str, tx: dict, st_chat_cfg: dict):
    token_deltas, sol_delta, newly_received = compute_deltas_and_new(tx, owner)
    positives = {m: a for m, a in token_deltas.items() if a > 0}
    negatives = {m: -a for m, a in token_deltas.items() if a < 0}

    if not positives and abs(sol_delta) < 1e-12 and not newly_received:
        return None, None, None, None

    # Biggest positive as bought
    bought_mint, bought_amt = (None, 0.0)
    if positives:
        bought_mint, bought_amt = max(positives.items(), key=lambda x: x[1])

    # sold in SOL or token
    sold_desc = None
    if sol_delta < -1e-9:
        sold_desc = f"{abs(sol_delta):.6f} SOL"
    elif negatives:
        s_mint, s_amt = max(negatives.items(), key=lambda x: x[1])
        sold_desc = f"{s_amt:.6f} (mint: {s_mint})"

    # choose target mint for metadata & image
    target_mint = bought_mint or (next(iter(newly_received)) if newly_received else None)
    logo_url = None
    meta_line = ""
    if target_mint:
        md = await TOKENS.get(session, target_mint)
        sym, name, logo = md.get("symbol") or "", md.get("name") or "", md.get("logo") or ""
        if logo: logo_url = logo
        parts = []
        if sym: parts.append(f"${sym}")
        if name: parts.append(name)
        if parts:
            meta_line = " | " + " — ".join(parts)

    # decide title
    is_new_for_wallet = False
    if target_mint and owner in (st_chat_cfg.get("subs") or {}):
        seen = (st_chat_cfg["subs"][owner] or {}).get("seen_mints", [])
        is_new_for_wallet = target_mint not in seen

    title = "⚡ <b>Swap détecté</b>"
    if is_new_for_wallet:
        title = "🚀 <b>Nouvelle pool détectée</b>"

    # build body
    lines = [title, f"Wallet: <code>{owner}</code>"]
    if bought_mint and sold_desc:
        lines.append(f"SWAP | Acheté: <code>{bought_amt:.6f}</code> (mint/CA: <code>{bought_mint}</code>) | Vendu: <code>{sold_desc}</code>{meta_line}")
    elif bought_mint:
        lines.append(f"SWAP | Reçu: <code>{bought_amt:.6f}</code> (mint/CA: <code>{bought_mint}</code>){meta_line}")
    elif is_new_for_wallet and target_mint:
        lines.append(f"NOUVEAU | Reçu: (mint/CA: <code>{target_mint}</code>){meta_line}")

    sig = (tx.get("transaction", {}).get("signatures") or [None])[0]
    if sig:
        lines.append(solscan_tx(sig))

    return "\n".join(lines), logo_url, target_mint, sol_delta

# ── RPC helpers ───────────────────────────────────────────────────────────────
async def rpc_post(session: aiohttp.ClientSession, url: str, method: str, params: list):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.json()

async def fetch_tx(session: aiohttp.ClientSession, http_url: str, signature: str):
    try:
        data = await rpc_post(session, http_url, "getTransaction",
                              [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])
        return data.get("result")
    except Exception:
        return None

# ── WS loop ───────────────────────────────────────────────────────────────────
async def tracker_ws_loop(app: Application):
    await asyncio.sleep(1.0)
    while True:
        # pick a WS endpoint
        ws_url = None
        for cfg in TRACKER_STATE.values():
            ws = (cfg.get("ws_rpc") or "") if isinstance(cfg, dict) else ""
            if ws:
                ws_url = ws; break
        if ws_url is None:
            any_http = next(iter(TRACKER_STATE.values())).get("http_rpc") if TRACKER_STATE else os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
            ws_url = infer_ws_from_http(str(any_http))

        try:
            async with aiohttp.ClientSession() as session:
                await TOKENS.warm(session)
                async with session.ws_connect(ws_url, heartbeat=20, autoping=True) as ws:
                    # subscribe all current
                    watched_all: set[str] = set()
                    for cfg in TRACKER_STATE.values():
                        subs = (cfg.get("subs") or {})
                        watched_all |= set(subs.keys())
                    for addr in watched_all:
                        await ws.send_json({"jsonrpc":"2.0","id":id(("logsSubscribe",addr)) & 0x7fffffff,
                                            "method":"logsSubscribe","params":[{"mentions":addr},{"commitment":"confirmed"}]})

                    last_sync = asyncio.get_running_loop().time()

                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if data.get("method") == "logsNotification":
                                params = data.get("params", {})
                                result = params.get("result", {})
                                sig = result.get("signature")
                                # get any HTTP endpoint
                                any_http = next(iter(TRACKER_STATE.values())).get("http_rpc") if TRACKER_STATE else os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
                                tx = await fetch_tx(session, str(any_http), sig)
                                if not tx:
                                    continue
                                # mentioned pubkeys from logs
                                logs = result.get("value", {}).get("logs", []) or []
                                mentioned = set()
                                for line in logs:
                                    for tok in line.split():
                                        if is_valid_pubkey(tok): mentioned.add(tok)

                                # route to each chat
                                for chat_id, cfg in TRACKER_STATE.items():
                                    subs = cfg.get("subs") or {}
                                    owners_hit = set(subs.keys()).intersection(mentioned)
                                    if not owners_hit:
                                        continue
                                    for owner in owners_hit:
                                        text, logo_url, target_mint, sol_delta = await build_summary_and_media(session, owner, tx, cfg)
                                        if not text:
                                            continue

                                        # filters: launchonly & min_sol (per wallet)
                                        wmeta = subs.get(owner, {})
                                        is_new = False
                                        if target_mint:
                                            seen = wmeta.get("seen_mints", [])
                                            is_new = target_mint not in seen
                                        if wmeta.get("launchonly") and not is_new:
                                            continue
                                        min_sol = float(wmeta.get("min_sol", 0.0) or 0.0)
                                        if sol_delta is not None and sol_delta < 0 and min_sol > 0 and abs(sol_delta) < min_sol:
                                            continue

                                        disable_notif = bool(cfg.get("silent", False))
                                        try:
                                            if logo_url:
                                                await app.bot.send_photo(chat_id=chat_id, photo=logo_url, caption=text,
                                                                         parse_mode="HTML", disable_notification=disable_notif)
                                            else:
                                                await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML",
                                                                           disable_web_page_preview=True, disable_notification=disable_notif)
                                            # mark seen if new
                                            if target_mint and is_new:
                                                seen.append(target_mint)
                                                wmeta["seen_mints"] = seen
                                                await save_state()
                                        except Exception as e:
                                            logger.warning("send notif failed: %s", e)

                            # resubscribe for new watches every ~20s
                            now = asyncio.get_running_loop().time()
                            if now - last_sync > 20:
                                last_sync = now
                                current: set[str] = set()
                                for cfg in TRACKER_STATE.values():
                                    subs = (cfg.get("subs") or {})
                                    current |= set(subs.keys())
                                new_to_sub = current - watched_all
                                if new_to_sub:
                                    for a in new_to_sub:
                                        await ws.send_json({"jsonrpc":"2.0","id":id(("logsSubscribe",a)) & 0x7fffffff,
                                                            "method":"logsSubscribe","params":[{"mentions":a},{"commitment":"confirmed"}]})
                                    watched_all |= new_to_sub
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
        except Exception as e:
            logger.warning("WS loop error: %s", e)
            await asyncio.sleep(3.0)
            continue
        await asyncio.sleep(1.0)

def ensure_ws_loop(app: Application):
    global _ws_task
    if _ws_task is None:
        _ws_task = asyncio.create_task(tracker_ws_loop(app))
        logger.info("Tracker WS loop started.")

# ── Commands (all with "!") ───────────────────────────────────────────────────
@register_command(name="watch", help_text="!watch <adresse> [alias] — suivre un wallet (temps réel)", aliases=["wallet"])
async def cmd_watch(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    if not args:
        await reply(update, "Usage: <code>!watch &lt;adresse&gt; [alias]</code>"); return
    addr = args[0].strip()
    if not is_valid_pubkey(addr):
        await reply(update, "❌ Adresse Solana invalide."); return
    alias = " ".join(args[1:]).strip() if len(args) > 1 else ""
    subs: Dict[str, dict] = st["subs"]  # type: ignore
    if addr not in subs:
        subs[addr] = {"alias": alias, "added_at": datetime.now(timezone.utc).isoformat(),
                      "launchonly": False, "seen_mints": [], "min_sol": 0.0}
    else:
        if alias: subs[addr]["alias"] = alias
    await save_state()
    ensure_ws_loop(context.application)
    name = display_name(addr, subs[addr])
    lbadge = launch_badge(subs[addr])
    sbadge = BADGE_SILENT_ON if st.get("silent") else BADGE_SILENT_OFF
    await reply(update, f"📡 <b>Watch activé</b>\n{sbadge} {lbadge}  <b>{name}</b>\nAdresse : <code>{addr}</code>\n{solscan_addr(addr)}")

@register_command(name="unwatch", help_text="!unwatch <adresse> — arrêter de suivre")
async def cmd_unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    if not args:
        await reply(update, "Usage: <code>!unwatch &lt;adresse&gt;</code>"); return
    addr = args[0].strip()
    subs: Dict[str, dict] = st["subs"]  # type: ignore
    if addr in subs:
        name = display_name(addr, subs[addr])
        subs.pop(addr, None); await save_state()
        await reply(update, f"🛑 Suivi arrêté pour <b>{name}</b>")
    else:
        await reply(update, "Cette adresse n'était pas suivie.")

@register_command(name="unwatchall", help_text="!unwatchall — vider tous les wallets suivis")
async def cmd_unwatchall(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    subs: Dict[str, dict] = st["subs"]  # type: ignore
    count = len(subs)
    subs.clear(); await save_state()
    await reply(update, f"🗑️ Liste vidée (<b>{count}</b> wallet(s) retiré(s)).")

@register_command(name="list", help_text="!list — liste compacte des wallets suivis (liens)")
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    subs: Dict[str, dict] = st["subs"]  # type: ignore
    if not subs:
        await reply(update, "Aucune adresse suivie. <code>!watch &lt;adresse&gt; [alias]</code> pour commencer."); return
    items = sorted(subs.items(), key=lambda kv: ((kv[1].get("alias") or ""), kv[0].lower()))
    lines = ["📋 <b>Wallets suivis</b>"]
    for addr, meta in items:
        lines.append(f"• <a href=\"{solscan_addr(addr)}\">{short_pk(addr)}</a>")
    await reply(update, "\n".join(lines))

@register_command(name="listdetail", help_text="!listdetail — liste détaillée (alias, date, launchonly, minSOL)")
async def cmd_listdetail(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    subs: Dict[str, dict] = st["subs"]  # type: ignore
    if not subs:
        await reply(update, "Aucune adresse suivie. <code>!watch &lt;adresse&gt; [alias]</code> pour commencer."); return
    items = sorted(subs.items(), key=lambda kv: ((kv[1].get("alias") or ""), kv[0].lower()))
    sbadge = BADGE_SILENT_ON if st.get("silent") else BADGE_SILENT_OFF
    out = [f"📋 <b>Wallets suivis</b>  {sbadge}\n"]
    for i, (addr, meta) in enumerate(items, 1):
        name   = display_name(addr, meta)
        added  = (meta.get("added_at","") or "")[:10]
        lbadge = launch_badge(meta)
        minsol = float(meta.get("min_sol", 0.0) or 0.0)
        extra  = f" — minSOL: <code>{minsol}</code>" if minsol > 0 else ""
        out.append(f"{i}️⃣ {lbadge} <a href=\"{solscan_addr(addr)}\">{name}</a> — ajouté le <i>{added}</i> — <b>launchonly</b>: <code>{'ON' if meta.get('launchonly') else 'OFF'}</code>{extra}")
    await reply(update, "\n".join(out))

@register_command(name="setrpc", help_text="!setrpc <http_url> — définit l'endpoint HTTP RPC")
async def cmd_setrpc(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    if not args:
        await reply(update, f"HTTP RPC actuel: <code>{st['http_rpc']}</code>"); return
    st["http_rpc"] = args[0].strip()
    await save_state()
    await reply(update, f"✅ HTTP RPC mis à jour:\n<code>{st['http_rpc']}</code>")

@register_command(name="setws", help_text="!setws <wss_url> — définit l'endpoint WebSocket RPC (sinon auto)")
async def cmd_setws(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    if not args:
        ws_url = st["ws_rpc"] or infer_ws_from_http(st["http_rpc"])  # type: ignore
        await reply(update, f"WS actuel: <code>{ws_url}</code>"); return
    st["ws_rpc"] = args[0].strip()
    await save_state()
    ensure_ws_loop(context.application)
    await reply(update, f"✅ WebSocket RPC mis à jour:\n<code>{st['ws_rpc']}</code>")

@register_command(name="launchonly", help_text="!launchonly <adresse> on|off — ne notifier que la 1ère fois par token (wallet)")
async def cmd_launchonly(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    if len(args) != 2 or args[1].lower() not in ("on","off"):
        await reply(update, "Usage: <code>!launchonly &lt;adresse&gt; on|off</code>"); return
    addr = args[0].strip()
    if not is_valid_pubkey(addr):
        await reply(update, "❌ Adresse Solana invalide."); return
    subs: Dict[str, dict] = st["subs"]  # type: ignore
    if addr not in subs:
        await reply(update, "Adresse non suivie. Ajoute-la d'abord avec <code>!watch</code>."); return
    subs[addr]["launchonly"] = (args[1].lower() == "on")
    await save_state()
    name = display_name(addr, subs[addr])
    await reply(update, f"⚙️ <b>launchonly</b> pour <b>{name}</b> → <code>{args[1].upper()}</code>")

@register_command(name="silent", help_text="!silent on|off — envoyer les notifs en silencieux (par chat)")
async def cmd_silent(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    if len(args) != 1 or args[0].lower() not in ("on","off"):
        await reply(update, "Usage: <code>!silent on|off</code>"); return
    st["silent"] = (args[0].lower() == "on")
    await save_state()
    bad = BADGE_SILENT_ON if st["silent"] else BADGE_SILENT_OFF
    await reply(update, f"{bad} <b>Silent</b> → <code>{args[0].upper()}</code>")

@register_command(name="minsol", help_text="!minsol <adresse> <montant_SOL> — seuil min de SOL dépensé pour notifier (par wallet)")
async def cmd_minsol(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    st = tracker_chat_state(update.effective_chat.id)
    if len(args) != 2:
        await reply(update, "Usage: <code>!minsol &lt;adresse&gt; &lt;montant_SOL&gt;</code>"); return
    addr = args[0].strip()
    if not is_valid_pubkey(addr):
        await reply(update, "❌ Adresse Solana invalide."); return
    try:
        val = float(args[1].replace(",", "."))
        if val < 0: raise ValueError()
    except Exception:
        await reply(update, "❌ Montant invalide. Exemple: <code>!minsol 3jxZ... 0.25</code>"); return
    subs: Dict[str, dict] = st["subs"]  # type: ignore
    if addr not in subs:
        await reply(update, "Adresse non suivie. Ajoute-la d'abord avec <code>!watch</code>."); return
    subs[addr]["min_sol"] = val
    await save_state()
    name = display_name(addr, subs[addr])
    await reply(update, f"⚙️ <b>Filtre minimum SOL</b> pour <b>{name}</b> → <code>≥ {val} SOL</code>")

# ── Menu !commandes (inclut catégorie Tracker) ────────────────────────────────
@register_command(
    name="commandes",
    help_text="Menu complet de toutes les commandes (mis à jour avec Tracker)",
    aliases=["cmd","help","aide"],
)
async def cmd_commandes(update: Update, context: ContextTypes.DEFAULT_TYPE, args: List[str]):
    lines = [
        "<b>📚 Menu complet</b>",
        "\n<b>🧰 Panel</b>",
        "• <code>/start</code> ou <code>!start</code> → ouvre le Panel (boutons Liens/Tutos)",
        "\n<b>ℹ️ Core/Aide</b>",
        "• <code>!about</code>, <code>!id</code>, <code>!topic</code>, <code>!ping</code>, <code>!gm</code>, <code>!gn</code>",
        "\n<b>🔗 Liens</b>",
        "• <code>!links</code> + raccourcis <code>!axiom</code>, <code>!bloom</code>, <code>!uxento</code>, <code>!raycyan</code>, <code>!mockape</code>, <code>!solincinerator</code>",
        "\n<b>📈 Marché</b>",
        "• <code>!dex</code>, <code>!fees</code>, <code>!bond</code>, <code>!convert</code>",
        "\n<b>⚠️ Warning</b>",
        "• <code>!pnl</code> — mise en garde sur les cartes PnL",
        "\n<b>📒 Tutos</b>",
        "• <code>!tuto</code>, <code>!premierspas</code>, <code>!lexique</code>, <code>!bcurve</code>, <code>!mev</code>, <code>!tutoaxiom</code>, <code>!debutant</code>, <code>!tracker</code>, <code>!sniprug</code>",
        "\n<b>🛰️ Tracker (Wallet temps réel)</b>",
        "• <code>!watch &lt;adresse&gt; [alias]</code> (alias <code>!wallet</code>) — suivre un wallet (image en haut, CA copiable, ticker/nom)",
        "• <code>!unwatch &lt;adresse&gt;</code> — arrêter le suivi",
        "• <code>!unwatchall</code> — vider tout",
        "• <code>!list</code> — liste compacte | <code>!listdetail</code> — alias, date, launchonly, minSOL",
        "• <code>!setrpc &lt;http_url&gt;</code> — endpoint HTTP (pour <i>getTransaction</i>)",
        "• <code>!setws &lt;wss_url&gt;</code> — endpoint WebSocket (sinon auto à partir du HTTP)",
        "• <code>!launchonly &lt;adresse&gt; on|off</code> — notifier seulement la <u>première</u> fois par token",
        "• <code>!minsol &lt;adresse&gt; &lt;montant_SOL&gt;</code> — filtrer les achats &lt; seuil de SOL",
        "• <code>!silent on/off</code> — notifications silencieuses (par chat)",
        "\n<i>Bio rapide</i> : <u>launchonly</u> coupe le spam — tu ne vois que la <b>première entrée</b> du wallet sur chaque token. "
        "<u>minSOL</u> n’applique un filtre que si tu mets une valeur &gt; 0. "
        "Les données sont <b>persistées</b> en JSON (variable <code>TRACKER_STORE</code>).",
    ]
    await reply(update, "\n".join(lines))

# Auto-load state at import
load_state()
