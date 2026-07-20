"""Generate Voice Agent Complete Flow Guide PDF."""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY

OUT = Path(__file__).resolve().parent / "Voice_Agent_Complete_Flow_Guide.pdf"

NAVY = HexColor("#0F2744")
TEAL = HexColor("#0D7377")
LIGHT = HexColor("#F4F7FA")
ORANGE = HexColor("#E85D04")
GRAY = HexColor("#4A5568")
SOFT = HexColor("#E8EEF5")

styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "DocTitle",
    parent=styles["Title"],
    fontSize=22,
    textColor=NAVY,
    spaceAfter=6,
    leading=26,
    alignment=TA_CENTER,
)
subtitle = ParagraphStyle(
    "SubTitle",
    parent=styles["Normal"],
    fontSize=11,
    textColor=GRAY,
    spaceAfter=18,
    alignment=TA_CENTER,
    leading=14,
)
h1 = ParagraphStyle(
    "H1",
    parent=styles["Heading1"],
    fontSize=14,
    textColor=NAVY,
    spaceBefore=16,
    spaceAfter=8,
    leading=18,
)
h2 = ParagraphStyle(
    "H2",
    parent=styles["Heading2"],
    fontSize=12,
    textColor=TEAL,
    spaceBefore=12,
    spaceAfter=6,
    leading=15,
)
body = ParagraphStyle(
    "Body",
    parent=styles["Normal"],
    fontSize=9.5,
    textColor=black,
    spaceAfter=6,
    leading=13,
    alignment=TA_JUSTIFY,
)
bullet = ParagraphStyle(
    "Bullet",
    parent=styles["Normal"],
    fontSize=9.5,
    textColor=black,
    spaceAfter=3,
    leading=12,
    leftIndent=12,
)
example = ParagraphStyle(
    "Example",
    parent=styles["Normal"],
    fontSize=9.5,
    textColor=NAVY,
    spaceAfter=6,
    leading=13,
    backColor=SOFT,
    borderPadding=6,
    leftIndent=4,
    rightIndent=4,
)
mono = ParagraphStyle(
    "Mono",
    parent=styles["Code"],
    fontSize=8,
    textColor=HexColor("#1A202C"),
    spaceAfter=6,
    leading=11,
    fontName="Courier",
    backColor=LIGHT,
    borderPadding=4,
)
caption = ParagraphStyle(
    "Caption",
    parent=styles["Normal"],
    fontSize=8.5,
    textColor=GRAY,
    spaceAfter=10,
    alignment=TA_CENTER,
    leading=11,
)


def cell(text, header=False, mono_font=False, size=8.5):
    return Paragraph(
        str(text),
        ParagraphStyle(
            "cell",
            parent=bullet,
            fontSize=size if not header else 9,
            textColor=white if header else black,
            fontName=("Courier" if mono_font and not header else "Helvetica-Bold")
            if (header or mono_font)
            else "Helvetica",
            leftIndent=0,
        ),
    )


def make_table(rows, col_widths, header_color=NAVY):
    data = []
    for i, row in enumerate(rows):
        data.append(
            [
                cell(c, header=(i == 0), mono_font=(i > 0 and j == 0 and len(row) == 2))
                if False
                else cell(c, header=(i == 0))
                for j, c in enumerate(row)
            ]
        )
    # Rebuild cleanly
    data = []
    for i, row in enumerate(rows):
        data.append([cell(c, header=(i == 0)) for c in row])
    t = Table(data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), header_color),
                ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#CBD5E0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, white]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(18 * mm, A4[1] - 9 * mm, "AI Voice Receptionist — Complete Flow Guide")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 9 * mm, "ResilioHub / voice-agent")
    canvas.setFillColor(SOFT)
    canvas.rect(0, 0, A4[0], 12 * mm, fill=1, stroke=0)
    canvas.setFillColor(GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(
        A4[0] / 2, 5 * mm, f"Page {doc.page}  |  Easy explanation with real-life examples"
    )
    canvas.restoreState()


def build():
    story = []

    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph("AI Voice Receptionist", title_style))
    story.append(Paragraph("Complete Flow Guide — How Everything Connects", subtitle))
    story.append(
        Paragraph(
            "A simple, real-life explanation of your phone AI system: "
            "who talks to whom, what each piece does, and what happens when someone calls.",
            body,
        )
    )
    story.append(Spacer(1, 3 * mm))

    box_data = [
        [
            Paragraph(
                "<b>One-line idea</b><br/>"
                "A customer dials your Exotel number → audio streams to your Python bridge → "
                "Gemini AI talks live → when needed, n8n does business work (book, log, WhatsApp) → "
                "call ends and a summary is saved.",
                body,
            )
        ]
    ]
    t = Table(box_data, colWidths=[170 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 1, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(t)

    # Section 1
    story.append(Paragraph("1. Real-life analogy (easiest way to understand)", h1))
    story.append(
        Paragraph(
            "Think of a busy clinic front desk. Several roles work together:",
            body,
        )
    )
    analogy = [
        ["Role in real life", "In your system", "Job"],
        [
            "Reception phone line (Exotel number)",
            "Exotel (telephony)",
            "Brings the call into the office. Carries voice both ways.",
        ],
        [
            "Smart receptionist who listens &amp; speaks",
            "Gemini Live AI",
            "Understands speech, replies naturally, decides when to use tools.",
        ],
        [
            "Back-office clerk (files, WhatsApp, sheets)",
            "n8n workflows",
            "Books slots, writes Google Sheet, sends WhatsApp — does not chat on the call.",
        ],
        [
            "Switchboard operator connecting everyone",
            "Python voice-agent (bridge.py + app.py)",
            "Converts audio formats, relays streams, hang-up rules, tool calls.",
        ],
        [
            "Public front door of the office",
            "Cloudflare tunnel (cloudflared)",
            "Lets Exotel reach your laptop/server on the internet safely.",
        ],
    ]
    story.append(make_table(analogy, [50 * mm, 48 * mm, 72 * mm]))
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "<b>Example:</b> Priya calls Bright Smile Dental. Exotel is the phone company cable. "
            "Gemini is the receptionist on the line. n8n is the person who writes the appointment "
            "in the diary and texts the owner on WhatsApp. Your Python app is the headset mixer "
            "that keeps everyone in sync.",
            example,
        )
    )

    # Section 2
    story.append(Paragraph("2. What pieces are used (inventory)", h1))

    story.append(Paragraph("2.1 Telephony — Exotel (primary) / Plivo (fallback)", h2))
    story.append(
        Paragraph(
            "<b>What:</b> Cloud phone system. Gives you a virtual number people can dial. "
            "Supports <b>bidirectional WebSocket audio</b> (Voicebot on Exotel, Stream on Plivo).",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>Why Exotel now:</b> Plivo needs Indian KYC documents (incorporation + tax). "
            "Exotel lets you start sooner. Plivo stays as code fallback — flip one env flag later.",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>Audio formats:</b> Exotel = raw PCM 16-bit mono (usually 8 kHz). "
            "Plivo = G.711 mu-law 8 kHz. Your <font face='Courier'>audio.py</font> converts "
            "between them and what the AI expects.",
            body,
        )
    )

    story.append(Paragraph("2.2 AI brain — Gemini Live (now) / OpenAI Realtime (optional)", h2))
    story.append(
        Paragraph(
            "<b>What:</b> Real-time speech-to-speech model. Caller speaks → AI hears audio → "
            "AI speaks audio back. No separate STT + TTS pipeline for the main talk path.",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>Gemini specifics:</b> Free-tier friendly API key from Google AI Studio. "
            "Native audio model. Tuned with short silence detection and thinking_budget=0 "
            "for faster replies.",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>Tools:</b> AI can call functions (book_appointment, end_call, etc.). "
            "Your code runs them and feeds results back so the AI can say "
            "“Done, Tuesday at 3 PM.”",
            body,
        )
    )

    story.append(Paragraph("2.3 Orchestration — n8n", h2))
    story.append(
        Paragraph(
            "<b>What:</b> Visual workflow engine. Webhook receives JSON from the bridge. "
            "Routes by action: mid-call business actions OR post-call logging.",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>After call ends:</b> Append row to Google Sheet (<font face='Courier'>voice_calls</font>), "
            "optionally send WhatsApp summary via ResilioHub API.",
            body,
        )
    )

    story.append(Paragraph("2.4 Your Python voice-agent (the switchboard)", h2))
    files = [
        ["File", "Role"],
        ["app.py", "FastAPI: /health, Exotel WS URL, /exotel/stream, /plivo/answer + /plivo/stream"],
        ["bridge.py", "Main call loop: audio relay, barge-in, hang-up watchdog, n8n notify on end"],
        ["provider_gemini.py", "Connects to Gemini Live, sends/receives audio + transcripts + tools"],
        ["provider_openai.py", "Same interface for OpenAI Realtime (swap via AI_PROVIDER)"],
        ["provider_base.py", "Shared events: AudioDelta, SpeechStarted, ToolCall, EndCallRequested"],
        ["audio.py", "mu-law ↔ PCM, resample, RMS speech energy, Exotel FrameBuffer"],
        ["tools.py", "Tool definitions + dispatch to n8n (end_call handled locally)"],
        ["config.py", "Loads .env: keys, timeouts, prompts, providers"],
        ["plivo_xml.py", "XML that tells Plivo to open the bidirectional stream"],
    ]
    story.append(make_table(files, [42 * mm, 128 * mm], header_color=TEAL))

    story.append(Paragraph("2.5 Tunnel — cloudflared", h2))
    story.append(
        Paragraph(
            "Your app runs on <font face='Courier'>localhost:5000</font>. Exotel cannot dial localhost. "
            "Cloudflare Tunnel gives a public HTTPS/WSS host. You put that host (no https://) into "
            "<font face='Courier'>PUBLIC_HOST</font>.",
            body,
        )
    )

    story.append(Paragraph("2.6 Google Sheet + WhatsApp", h2))
    story.append(
        Paragraph(
            "Sheet tab <b>voice_calls</b> columns: call_id, from_phone, ended_at, reason, summary, "
            "transcript, duration_sec, business_name. WhatsApp goes to owner number in "
            "<font face='Courier'>NOTIFY_WHATSAPP</font> via ResilioHub send-message API.",
            body,
        )
    )

    # Section 3
    story.append(PageBreak())
    story.append(Paragraph("3. How things are connected (wiring diagram in words)", h1))
    story.append(Paragraph("Read this top → bottom like a phone call journey:", body))
    story.append(
        Paragraph(
            "Caller phone<br/>"
            "&nbsp;&nbsp;↓ PSTN / mobile network<br/>"
            "Exotel virtual number + Voicebot applet<br/>"
            "&nbsp;&nbsp;↓ WebSocket (wss://PUBLIC_HOST/exotel/stream)<br/>"
            "Cloudflare tunnel → your PC → FastAPI app.py<br/>"
            "&nbsp;&nbsp;↓ bridge.py opens AI session<br/>"
            "Gemini Live (or OpenAI) — live audio in/out<br/>"
            "&nbsp;&nbsp;↓ when AI needs business action<br/>"
            "tools.py → HTTP POST → n8n webhook /voice-agent<br/>"
            "&nbsp;&nbsp;↓ mid-call: JSON result spoken by AI<br/>"
            "&nbsp;&nbsp;↓ call end: call_ended → Sheet + WhatsApp",
            mono,
        )
    )

    conn = [
        ["From", "To", "Protocol / path", "Carries"],
        ["Exotel", "voice-agent", "WSS /exotel/stream", "PCM audio frames + events"],
        ["Plivo", "voice-agent", "HTTPS /plivo/answer then WSS /plivo/stream", "XML then mu-law audio"],
        ["voice-agent", "Gemini", "SDK Live WebSocket", "PCM 16k in / 24k out + tools"],
        ["voice-agent", "n8n", "HTTPS POST N8N_WEBHOOK_URL", "action JSON + call_ended"],
        ["n8n", "Google Sheets", "Google Sheets node", "one log row per call"],
        ["n8n", "ResilioHub WA", "HTTP API", "WhatsApp summary text"],
        ["cloudflared", "Internet", "public trycloudflare host", "HTTPS + WSS to port 5000"],
    ]
    story.append(make_table(conn, [28 * mm, 32 * mm, 58 * mm, 52 * mm]))

    # Section 4
    story.append(Paragraph("4. Full call flow — second by second (real example)", h1))
    story.append(
        Paragraph(
            "<b>Scene:</b> Customer Ravi calls ResilioHub WhatsApp CRM number at 11:02 AM. "
            "He wants a product demo tomorrow.",
            example,
        )
    )

    steps = [
        (
            "T+0s — Dial",
            "Ravi dials Exotel number. Telecom network rings Exotel. Exotel starts your Voicebot call flow.",
        ),
        (
            "T+1s — WebSocket open",
            "Exotel connects to wss://YOUR_HOST/exotel/stream?sample-rate=8000. "
            "Cloudflare forwards to localhost:5000. FastAPI accepts WebSocket. "
            "bridge.run(telephony=exotel) starts.",
        ),
        (
            "T+1–2s — AI connect",
            "Bridge creates Gemini provider session with system prompt + greeting instruction. "
            "Also starts silence / max-duration watchdog timer.",
        ),
        (
            "T+2–4s — Greeting",
            "Gemini speaks: “Thank you for calling ResilioHub… How can I help?” "
            "Bridge resamples 24 kHz AI audio → 8 kHz PCM, packs ~100 ms frames, sends media "
            "events to Exotel. Ravi hears it.",
        ),
        (
            "T+5–20s — Conversation",
            "Ravi talks. Exotel sends media chunks. Bridge converts/resamples to Gemini input rate, "
            "updates last-activity time when speech energy (RMS) is heard. Gemini replies in short sentences.",
        ),
        (
            "T+20s — Barge-in",
            "If Ravi interrupts while AI talks, Gemini signals interrupted. Bridge sends Exotel "
            "<font face='Courier'>clear</font> (or Plivo clearAudio) so leftover AI audio is flushed — "
            "no talking over the caller.",
        ),
        (
            "T+35s — Tool use (optional)",
            "Ravi: “Book a demo tomorrow 3 PM.” AI calls a tool → tools.py POSTs to n8n → "
            "n8n returns confirmation → AI says “Booked for tomorrow at 3.”",
        ),
        (
            "T+50s — End intent",
            "Ravi: “Thanks, that’s all.” Prompt teaches AI to say a one-line farewell and call "
            "<font face='Courier'>end_call</font> with a short summary. Bridge schedules hang-up "
            "after END_CALL_GRACE_SEC (~2.5s) so farewell audio can finish.",
        ),
        (
            "Or — Silence hang-up",
            "If nobody speaks for SILENCE_TIMEOUT_SEC (e.g. 20s) after AI finished, watchdog ends "
            "the call. Also hard stop at MAX_CALL_DURATION_SEC (e.g. 300s).",
        ),
        (
            "Teardown — Post-call",
            "Bridge POSTs action=call_ended with transcript snippets, summary, reason, duration, "
            "from_phone. n8n: Build Call Log → Append Google Sheet → if NOTIFY_WHATSAPP set → "
            "Send WhatsApp Summary. WebSockets close. Done.",
        ),
    ]
    for title, text in steps:
        story.append(Paragraph(f"<b>{title}</b>", h2))
        story.append(Paragraph(text, body))

    # Section 5
    story.append(PageBreak())
    story.append(Paragraph("5. How each major component is used day-to-day", h1))

    story.append(Paragraph("5.1 Starting the stack (morning checklist)", h2))
    story.append(Paragraph("1. Activate venv, run <font face='Courier'>python app.py</font> (port 5000).", bullet))
    story.append(
        Paragraph(
            "2. Run <font face='Courier'>cloudflared tunnel --url http://localhost:5000</font>.",
            bullet,
        )
    )
    story.append(
        Paragraph(
            "3. Copy new tunnel host into <font face='Courier'>PUBLIC_HOST</font> if it changed; restart app.",
            bullet,
        )
    )
    story.append(
        Paragraph(
            "4. Confirm <font face='Courier'>https://PUBLIC_HOST/health</font> returns status ok.",
            bullet,
        )
    )
    story.append(Paragraph("5. n8n workflow active; Exotel Voicebot pointing at your WSS URL.", bullet))

    story.append(Paragraph("5.2 Config knobs that change behavior", h2))
    knobs = [
        ["Setting", "Effect in real life"],
        ["AI_PROVIDER / TELEPHONY_PROVIDER", "Which brain / which phone company"],
        ["GEMINI_SILENCE_MS (~500)", "How long after you stop talking before AI answers — lower = snappier"],
        ["GEMINI_THINKING_BUDGET=0", "Less “thinking delay” before speech"],
        ["SILENCE_TIMEOUT_SEC", "Auto hang-up if caller goes quiet"],
        ["MAX_CALL_DURATION_SEC", "Hard max call length"],
        ["END_CALL_GRACE_SEC", "Time for goodbye audio to finish"],
        ["SYSTEM_PROMPT / GREETING", "Personality + when to end_call"],
        ["N8N_WEBHOOK_URL", "Where business actions + call logs go"],
        ["NOTIFY_WHATSAPP", "Owner phone for summary WhatsApp"],
    ]
    story.append(make_table(knobs, [58 * mm, 112 * mm], header_color=TEAL))

    story.append(Paragraph("5.3 Mid-call tools vs post-call automation", h2))
    story.append(
        Paragraph(
            "<b>Mid-call:</b> AI still on the phone. Tool result must come back quickly so AI can "
            "speak it. Example: check_availability → “We have 3 PM free.”",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>Post-call (call_ended):</b> Caller already hung up. No need to speak. "
            "Write sheet + WhatsApp. Example: Owner gets “Ravi wanted demo tomorrow 3 PM; call 4m12s.”",
            body,
        )
    )
    story.append(
        Paragraph(
            "<b>end_call tool:</b> Handled inside Python (does not need n8n). It only tells the bridge: "
            "hang up soon, here is the summary string to include in call_ended.",
            body,
        )
    )

    # Section 6
    story.append(Paragraph("6. Audio path explained simply", h1))
    story.append(
        Paragraph(
            "Phones and AIs do not speak the same “audio language.” The bridge is a translator.",
            body,
        )
    )
    audio_rows = [
        ["Direction", "What happens"],
        [
            "Caller → AI (Exotel)",
            "PCM 8 kHz from Exotel → resample to Gemini input (16 kHz) → send_realtime_input",
        ],
        [
            "AI → Caller (Exotel)",
            "Gemini PCM 24 kHz → resample to 8 kHz → FrameBuffer (~3200 bytes) → Exotel media",
        ],
        [
            "Caller → AI (Plivo)",
            "mu-law 8 kHz → PCM → then to AI provider format",
        ],
        [
            "Barge-in",
            "Stop playing leftover AI audio: Exotel event clear / Plivo clearAudio",
        ],
    ]
    story.append(make_table(audio_rows, [42 * mm, 128 * mm]))
    story.append(
        Paragraph(
            "<b>Kitchen analogy:</b> Exotel sends chopped tomatoes (8 kHz PCM). Gemini wants puree "
            "(16 kHz). Gemini returns soup (24 kHz). You re-chop to tomato size before serving the "
            "caller. FrameBuffer = don’t send half a spoonful — Exotel wants full spoonfuls (~100 ms).",
            example,
        )
    )

    # Section 7
    story.append(Paragraph("7. n8n workflow roles", h1))
    story.append(
        Paragraph(
            "Imported from <font face='Courier'>n8n/voice_agent_actions.json</font>:",
            body,
        )
    )
    story.append(Paragraph("• Webhook trigger receives every POST from voice-agent.", bullet))
    story.append(
        Paragraph(
            "• <b>Is Call Ended?</b> — if yes → Build Call Log → Google Sheet → maybe WhatsApp.",
            bullet,
        )
    )
    story.append(
        Paragraph(
            "• If not ended → Handle Action (book, lead, FAQ, etc.) → return JSON for AI to speak.",
            bullet,
        )
    )
    story.append(
        Paragraph(
            "There is no “AI chat node” inside n8n for the live call. The live AI is Gemini/OpenAI "
            "in Python. n8n is the back office only. That is why you do not see an AI conversation "
            "node in the call path.",
            example,
        )
    )

    # Section 8
    story.append(Paragraph("8. Swapping providers later (no rewrite)", h1))
    story.append(Paragraph("Architecture uses a provider interface. Same bridge code.", body))
    story.append(
        Paragraph(
            "• Want OpenAI voice: set <font face='Courier'>AI_PROVIDER=openai</font> + API key.",
            bullet,
        )
    )
    story.append(
        Paragraph(
            "• Want Plivo after KYC: set <font face='Courier'>TELEPHONY_PROVIDER=plivo</font>, "
            "Answer URL = https://PUBLIC_HOST/plivo/answer.",
            bullet,
        )
    )
    story.append(
        Paragraph(
            "<b>Example:</b> Like changing SIM cards in the same phone — the “phone” (bridge) stays; "
            "only the network (Exotel/Plivo) or the brain (Gemini/OpenAI) changes.",
            example,
        )
    )

    # Section 9
    story.append(PageBreak())
    story.append(Paragraph("9. End-to-end story cards (practice understanding)", h1))

    stories = [
        (
            "Story A — Quick FAQ, then goodbye",
            "Caller asks clinic hours. AI answers from prompt (no tool). Caller says thanks. "
            "AI farewell + end_call. Sheet row: reason=thanks, short summary. Owner WhatsApp optional.",
        ),
        (
            "Story B — Book appointment",
            "Caller wants cleaning Tuesday. AI calls book tool → n8n checks/writes calendar or CRM → "
            "returns confirmation → AI speaks it → caller bye → call_ended logs transcript.",
        ),
        (
            "Story C — Ghost silence",
            "Caller puts phone down. After ~20s silence (configurable), watchdog hangs up. "
            "Summary may say silence timeout. Still logged to sheet.",
        ),
        (
            "Story D — Long monologue problem (why prompts matter)",
            "If SYSTEM_PROMPT allows long speeches, Ravi waits forever for AI to finish. "
            "That is why prompt says: max 2 short sentences, one question at a time, thinking_budget=0.",
        ),
    ]
    for title, text in stories:
        story.append(Paragraph(f"<b>{title}</b>", h2))
        story.append(Paragraph(text, body))

    # Section 10
    story.append(Paragraph("10. Quick mental map (memorize this)", h1))
    story.append(
        Paragraph(
            "<b>Phone company</b> moves sound. <b>AI</b> understands &amp; talks. "
            "<b>Python bridge</b> translates &amp; enforces hang-up. <b>n8n</b> does paperwork. "
            "<b>Cloudflare</b> opens the door to your machine. <b>Sheet/WhatsApp</b> remember what happened.",
            example,
        )
    )

    memorize = [
        ["If this breaks…", "Check this first"],
        [
            "Exotel can’t connect",
            "cloudflared running? PUBLIC_HOST match? /health OK? Voicebot WSS URL?",
        ],
        [
            "AI silent / slow",
            "GEMINI_API_KEY, model name, SILENCE_MS, SYSTEM_PROMPT length",
        ],
        [
            "Call never ends",
            "end_call in prompt? SILENCE_TIMEOUT_SEC? bridge logs hangup?",
        ],
        [
            "No sheet / WhatsApp",
            "n8n active? action=call_ended path? Sheet credentials? NOTIFY_WHATSAPP?",
        ],
        [
            "Audio choppy",
            "EXOTEL_SAMPLE_RATE match? FrameBuffer / network lag / tunnel",
        ],
    ]
    story.append(make_table(memorize, [42 * mm, 128 * mm], header_color=ORANGE))

    story.append(Spacer(1, 8 * mm))
    story.append(HRFlowable(width="100%", thickness=1, color=TEAL))
    story.append(Spacer(1, 3 * mm))
    story.append(
        Paragraph(
            "Document generated for the voice-agent project. "
            "Stack: Exotel + Gemini Live + FastAPI bridge + n8n + Google Sheets + WhatsApp "
            "(ResilioHub) + cloudflared.",
            caption,
        )
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
        title="AI Voice Receptionist — Complete Flow Guide",
        author="voice-agent",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"Wrote {OUT}")
    print(f"Size {OUT.stat().st_size} bytes")


if __name__ == "__main__":
    build()
