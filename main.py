import asyncio
import hashlib
import os
import re
import feedparser
import random
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from aiohttp import web
from telegram import Bot
from telegram.error import RetryAfter

# =====================
# CONFIG
# =====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "-1003915302283"))
MAX_NEWS_PER_CYCLE = int(os.getenv("MAX_NEWS_PER_CYCLE", "6"))
MESSAGE_DELAY = float(os.getenv("MESSAGE_DELAY", "4"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))
POSTED_FILE = Path(os.getenv("POSTED_FILE", "posted_registry.txt"))
PORT = int(os.getenv("PORT", "10000"))

bot: Bot | None = None
posted: set[str] = set()

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid",
})

RSS_FEEDS = [
    "https://feeds.folha.uol.com.br/poder/rss091.xml",
    "https://rss.uol.com.br/feed/politica.xml",
    "https://www.estadao.com.br/rss/ultimas.xml",
    "https://www.cnnbrasil.com.br/politica/feed/",
    "https://www.gazetadopovo.com.br/feed/",
    "https://brasil.elpais.com/rss/brasil/politica.xml",
]

POLITICAL_KEYWORDS = [
    "governo", "bolsonaro", "lula", "stf", "congresso",
    "ministério", "eleição", "presidente", "senado",
    "política", "pt", "pl", "reforma", "economia",
]

RIGHT_INDICATORS = [
    "impostos", "segurança", "crime", "armas",
    "liberdade econômica", "mercado", "privatização",
    "stf", "corrupção", "corte de gastos",
]

def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t, flags=re.UNICODE)
    return re.sub(r"\s+", " ", t).strip()


def title_fingerprint(title: str) -> str:
    normalized = normalize_title(title)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def normalize_link(link: str) -> str:
    parsed = urlparse(link.strip())
    if not parsed.scheme:
        return link.strip().rstrip("/").lower()

    query = parse_qs(parsed.query, keep_blank_values=False)
    filtered = {
        k: v for k, v in query.items()
        if k.lower() not in _TRACKING_PARAMS
    }
    clean_query = urlencode(filtered, doseq=True)
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        "",
        clean_query,
        "",
    ))


def entry_keys(entry) -> list[str]:
    keys = []
    link = getattr(entry, "link", None)
    if link:
        keys.append(f"link:{normalize_link(link)}")

    feed_id = getattr(entry, "id", None)
    if feed_id:
        keys.append(f"id:{feed_id.strip()}")

    title = getattr(entry, "title", None)
    if title:
        fp = title_fingerprint(title)
        if fp:
            keys.append(f"title:{fp}")

    return keys


def is_duplicate(entry) -> bool:
    keys = entry_keys(entry)
    return bool(keys) and any(k in posted for k in keys)


def mark_posted(entry):
    keys = entry_keys(entry)
    new_keys = [k for k in keys if k not in posted]
    if not new_keys:
        return

    posted.update(new_keys)
    with POSTED_FILE.open("a", encoding="utf-8") as f:
        for key in new_keys:
            f.write(key + "\n")


def load_posted():
    if not POSTED_FILE.exists():
        legacy = Path("posted_links.txt")
        if legacy.exists():
            POSTED_FILE.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            return

    for line in POSTED_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            posted.add(line)
        else:
            posted.add(f"link:{normalize_link(line)}")


def is_political(title):
    t = title.lower()
    return any(k in t for k in POLITICAL_KEYWORDS)


def estimate_bias(title):
    t = title.lower()
    score = sum(1 for k in RIGHT_INDICATORS if k in t)
    return "direita" if score >= 1 else "neutro/político geral"


def fetch_news():
    items = []
    batch_links: set[str] = set()
    batch_titles: set[str] = set()

    for url in RSS_FEEDS:
        feed = feedparser.parse(url)

        for entry in feed.entries:
            if len(items) >= MAX_NEWS_PER_CYCLE:
                return items

            if not is_political(entry.title):
                continue

            if is_duplicate(entry):
                continue

            keys = entry_keys(entry)
            link_keys = [k for k in keys if k.startswith("link:")]
            title_keys = [k for k in keys if k.startswith("title:")]

            if link_keys and any(k in batch_links for k in link_keys):
                continue
            if title_keys and any(k in batch_titles for k in title_keys):
                continue

            batch_links.update(link_keys)
            batch_titles.update(title_keys)
            items.append(entry)

    return items


async def telegram_call(coro_factory):
    while True:
        try:
            return await coro_factory()
        except RetryAfter as e:
            wait = e.retry_after + 1
            print(f"Flood control: aguardando {wait}s...")
            await asyncio.sleep(wait)


async def post_news(items):
    for item in items[:MAX_NEWS_PER_CYCLE]:
        if is_duplicate(item):
            continue

        mark_posted(item)

        bias = estimate_bias(item.title)

        msg = (
            f"📰 {item.title}\n\n"
            f"🏷 Tema: política\n"
            f"📊 Classificação: {bias}\n\n"
            f"🔗 {item.link}"
        )

        await telegram_call(
            lambda m=msg: bot.send_message(chat_id=GROUP_ID, text=m)
        )

        await asyncio.sleep(MESSAGE_DELAY)


async def send_poll():
    polls = [
        "O governo está no rumo certo?",
        "O STF tem poder demais hoje?",
        "O Brasil precisa de menos impostos?",
        "Segurança pública deve ser prioridade do governo?",
    ]

    question = random.choice(polls)

    await telegram_call(
        lambda: bot.send_poll(
            chat_id=GROUP_ID,
            question=question,
            options=["Sim", "Não", "Depende"],
            is_anonymous=False,
        )
    )


async def bot_loop():
    global bot
    bot = Bot(token=BOT_TOKEN)
    load_posted()
    print("Bot iniciado...")

    while True:
        try:
            news = fetch_news()

            if news:
                print(f"Publicando {len(news[:MAX_NEWS_PER_CYCLE])} notícia(s)...")
                await post_news(news)
            else:
                print("Nenhuma notícia nova.")

            await send_poll()

        except Exception as e:
            print("Erro:", e)

        await asyncio.sleep(POLL_INTERVAL)


async def health_handler(_request):
    return web.Response(text="ok", content_type="text/plain")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"Servidor HTTP em 0.0.0.0:{PORT} (/health)")


async def main():
    await start_web_server()
    asyncio.create_task(bot_loop())
    await asyncio.Event().wait()


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Defina BOT_TOKEN no ambiente.")
        raise SystemExit(1)

    asyncio.run(main())
