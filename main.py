import asyncio
import os
import feedparser
import random
from pathlib import Path

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
POSTED_FILE = Path(os.getenv("POSTED_FILE", "posted_links.txt"))

bot: Bot | None = None

# =====================
# RSS DE GRANDES JORNAIS BRASILEIROS
# =====================
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

posted: set[str] = set()


def load_posted():
    if not POSTED_FILE.exists():
        return
    posted.update(
        line.strip()
        for line in POSTED_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def save_posted_link(link: str):
    with POSTED_FILE.open("a", encoding="utf-8") as f:
        f.write(link + "\n")


# =====================
# FILTROS
# =====================

def is_political(title):
    t = title.lower()
    return any(k in t for k in POLITICAL_KEYWORDS)


def estimate_bias(title):
    t = title.lower()
    score = sum(1 for k in RIGHT_INDICATORS if k in t)
    return "direita" if score >= 1 else "neutro/político geral"


# =====================
# RSS FETCH
# =====================

def fetch_news():
    items = []

    for url in RSS_FEEDS:
        feed = feedparser.parse(url)

        for entry in feed.entries:
            if len(items) >= MAX_NEWS_PER_CYCLE:
                return items

            if entry.link in posted:
                continue

            if is_political(entry.title):
                items.append(entry)

    return items


# =====================
# TELEGRAM
# =====================

async def telegram_call(coro_factory):
    """Executa chamada à API e respeita RetryAfter do Telegram."""
    while True:
        try:
            return await coro_factory()
        except RetryAfter as e:
            wait = e.retry_after + 1
            print(f"Flood control: aguardando {wait}s...")
            await asyncio.sleep(wait)


async def post_news(items):
    for item in items[:MAX_NEWS_PER_CYCLE]:
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

        posted.add(item.link)
        save_posted_link(item.link)
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


# =====================
# LOOP
# =====================

async def run():
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


if __name__ == "__main__":
    if not BOT_TOKEN:
        print('Defina BOT_TOKEN no ambiente.')
        raise SystemExit(1)

    asyncio.run(run())
