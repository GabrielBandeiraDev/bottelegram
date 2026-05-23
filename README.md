# Bot Telegram — notícias RSS

Bot que publica notícias políticas e enquetes em um grupo/canal do Telegram.

## Deploy no Render (Web Service — plano Free)

1. Faça push deste repositório para o GitHub.
2. No [Render](https://render.com): **New → Web Service** → conecte o repo.
3. Configuração:
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `python main.py`
4. Variáveis de ambiente:
   - `BOT_TOKEN` — token do [@BotFather](https://t.me/Botfather)
   - `GROUP_ID` — ID do grupo/canal (ex.: `-1003915302283`)
5. O bot precisa ser **admin** no grupo com permissão para enviar mensagens e enquetes.

Após o deploy, teste: `https://SEU-APP.onrender.com/health` → deve retornar `ok`.

## Keepalive (obrigatório no plano Free)

O Render Free hiberna sem tráfego HTTP. Configure o GitHub Actions:

1. No GitHub: **Settings → Secrets and variables → Actions → New repository secret**
2. Nome: `RENDER_HEALTH_URL`
3. Valor: `https://SEU-APP.onrender.com/health` (URL real do Render)

O workflow `.github/workflows/keepalive.yml` faz GET a cada **10 minutos**.

Alternativa: [cron-job.org](https://cron-job.org) apontando para a mesma URL (intervalo 10 min).

Script manual: `RENDER_HEALTH_URL=https://... python keepalive.py`

## Variáveis opcionais

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `MAX_NEWS_PER_CYCLE` | `6` | Máximo de notícias por ciclo |
| `MESSAGE_DELAY` | `4` | Segundos entre cada mensagem |
| `POLL_INTERVAL` | `300` | Segundos entre ciclos (5 min) |

## Local

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export BOT_TOKEN="seu_token"
export GROUP_ID="-100..."
python main.py
```
