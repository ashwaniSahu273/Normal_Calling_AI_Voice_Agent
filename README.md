# AI Voice Receptionist — Core Bridge

Phone audio (Plivo) ↔ Gemini Live ↔ n8n / ResilioHub Node.

```
Caller → Plivo → Python (:5000) → Gemini
                    ↓
              n8n (Sheets/WA)  and/or  Node (DB + web/Flutter)
```

## Docs

| Doc | Use |
|-----|-----|
| **[docs/DEPLOY.md](docs/DEPLOY.md)** | **Upload next to Node** — nginx, env, Docker |
| **[docs/API_INTEGRATION.md](docs/API_INTEGRATION.md)** | Node + Web + Flutter API contract |
| **[docs/FLOW.md](docs/FLOW.md)** | How `/plivo/answer` connects to stream/tools |
| **[docs/PLIVO_SETUP.md](docs/PLIVO_SETUP.md)** | Plivo console after KYC |
| **[docs/GUIDE.md](docs/GUIDE.md)** | `.env`, voice, n8n, troubleshooting |
| **[docs/PRODUCT_MULTI_TENANT.md](docs/PRODUCT_MULTI_TENANT.md)** | Later: reseller / KYC / numbers |

## Quick start (dev)

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Tunnel: `cloudflared tunnel --url http://localhost:5000` → `PUBLIC_HOST` (no `https://`).

## Production (with ResilioHub)

1. Run Python on `:5000` (pm2 or Docker).
2. nginx: `/plivo/` + `/health` → `:5000`, rest → Node `:3000`.
3. Plivo Answer URL: `https://resiliohub.com/plivo/answer`.
4. When Node internal APIs exist, set `BACKEND_URL` + `BACKEND_SECRET`.

Details: **[docs/DEPLOY.md](docs/DEPLOY.md)**.

## Layout

```
app.py              HTTP + WebSocket (Plivo)
backend.py          Node client (tenant-config, call-ended)
bridge.py           Call switchboard
plivo_xml.py / plivo_client.py
knowledge.py        Prompts + RAG
tools.py            AI tools → n8n + Node
data/*.md           Knowledge bases
n8n/                Optional Sheets/WhatsApp workflow
Dockerfile
docs/DEPLOY.md
```

Leave `BACKEND_URL` empty until Node `GET /api/internal/voice/tenant-config` is ready. Voice still runs on `.env` + n8n.
