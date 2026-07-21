# Voice and persona

## Gemini voices (`.env` → `VOICE`)

| Name | Character |
|------|-----------|
| **Erinome** | Clear, professional |
| **Kore** | Firm, confident |
| **Aoede** | Breezy, friendly (default in `.env.example`) |
| **Achernar** | Soft, calm |

## Persona

- `AGENT_NAME` — optional name the agent uses (“This is Priya…”).
- `VOICE_PERSONA` — one line on tone (warm, short sentences, etc.). Appended in `knowledge.build_system_prompt()`.
- `GREETING` — first-turn hint; keep one sentence plus English/Hindi offer if needed.
- `SYSTEM_PROMPT` / `SYSTEM_PROMPT_BASE` — core rules (brevity, tools, hang-up).

## AI provider swap

| Provider | Env |
|----------|-----|
| Gemini Live (default) | `AI_PROVIDER=gemini`, `GEMINI_API_KEY` |
| OpenAI Realtime | `AI_PROVIDER=openai`, `OPENAI_API_KEY` |

No code change beyond `.env` and restart.
