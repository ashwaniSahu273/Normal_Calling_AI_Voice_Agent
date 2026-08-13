# Deploy voice agent next to ResilioHub (Node + nginx)

Python stays a **separate process**. Node owns tenants, JWT, DB. Python owns live audio.

```
Web / Flutter  →  Node (:3000)
                      │
                      │ BACKEND_URL + x-voice-secret
                      ▼
                 Voice Python (:5000)  ← Plivo /plivo/*
                      │
                      ▼
                 Gemini Live
```

## 1. VPS layout

| Process | Port | Role |
|---------|------|------|
| Node (ResilioHub) | 3000 | App APIs, DB, JWT |
| Voice (`python app.py`) | 5000 | Plivo XML + WebSocket + Gemini |
| nginx | 443 | TLS + route `/plivo/` → 5000, everything else → 3000 |

Keep n8n for Sheets/WhatsApp until Node `call-ended` is live. Then you can drop n8n.

## 2. Voice `.env` (production)

```env
AI_PROVIDER=gemini
TELEPHONY_PROVIDER=plivo
PUBLIC_HOST=resiliohub.com
PORT=5000

GEMINI_API_KEY=...
PLIVO_AUTH_ID=MA...
PLIVO_AUTH_TOKEN=...
PLIVO_FROM_NUMBER=+91...
OUTBOUND_API_SECRET=<same as Node VOICE_BRIDGE_SECRET>

# Node integration (leave empty until Node internal APIs exist)
BACKEND_URL=https://resiliohub.com
BACKEND_SECRET=<same as Node VOICE_WEBHOOK_SECRET>

N8N_WEBHOOK_URL=https://...   # optional once Node stores calls
KNOWLEDGE_PROFILE=resiliohub
```

`PUBLIC_HOST` = public host **without** `https://`. Plivo Answer URL:

`https://resiliohub.com/plivo/answer`

## 3. nginx

```nginx
# WebSocket upgrade for Plivo stream
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 443 ssl;
    server_name resiliohub.com;

    # Voice bridge — Plivo + health + outbound
    location /plivo/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    location /health {
        proxy_pass http://127.0.0.1:5000/health;
    }

    # ResilioHub Node
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 4. Run Python

```bash
cd /opt/voice-agent
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
# systemd or pm2:
pm2 start "python app.py" --name voice-agent --cwd /opt/voice-agent
```

Docker:

```bash
docker build -t voice-agent .
docker run -d --env-file .env -p 5000:5000 --name voice-agent voice-agent
```

## 5. Node must implement (minimum)

Spec: **[API_INTEGRATION.md](API_INTEGRATION.md)** §4.

| When | Node endpoint | Who calls |
|------|---------------|-----------|
| Call start | `GET /api/internal/voice/tenant-config?number=` | Python (`backend.py`) |
| Call end | `POST /api/internal/voice/call-ended` | Python |
| Lead / booking | `POST /api/internal/voice/action` | Python |
| Outbound from CRM | Node → `POST /plivo/outbound` | Node → Python |

Until those exist, leave `BACKEND_URL` empty. Voice still works with `.env` + n8n.

## 6. Scale later (do not build now)

- One Python process handles many concurrent WS calls (asyncio).
- Multi-tenant = Node returns different `knowledge_text` per number. No extra Python instances.
- Add a second voice host only if CPU/RAM from Gemini+audio saturates one box.

## 7. Check

```bash
curl https://resiliohub.com/health
# telephony=plivo, backend=true once BACKEND_URL is set
```
