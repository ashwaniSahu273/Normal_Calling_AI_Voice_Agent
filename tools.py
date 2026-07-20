"""Business-action tools the AI can call. Most post to n8n; end_call is local."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

import config

log = logging.getLogger("voice-agent.tools")

TOOL_DEFS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "book_appointment",
        "description": "Book an appointment once the caller has given a date and time.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Caller's full name."},
                "date": {"type": "string", "description": "Requested date."},
                "time": {"type": "string", "description": "Requested time."},
                "service": {"type": "string", "description": "Service requested."},
            },
            "required": ["date", "time"],
        },
    },
    {
        "type": "function",
        "name": "create_lead",
        "description": "Capture a sales lead when the caller is interested but not booking yet.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "phone": {"type": "string"},
                "interest": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["interest"],
        },
    },
    {
        "type": "function",
        "name": "lookup_knowledge",
        "description": (
            "Search company knowledge for specific facts (pricing, services, policies, timelines). "
            "Use when the caller asks something not clearly in your short memory. "
            "Pass a short search phrase, then answer from the tool result only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Short search phrase e.g. 'website development pricing' or 'CRM features'",
                },
            },
            "required": ["query"],
        },
    },
    {
        "type": "function",
        "name": "send_notification",
        "description": "Notify the business team about a message or callback request.",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
    {
        "type": "function",
        "name": "end_call",
        "description": (
            "End the call when the caller says thanks, goodbye, or does not want to continue. "
            "Say one short farewell first, then call this tool in the same turn. "
            "Do NOT keep asking questions after they want to hang up."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": (
                        "Plain language summary for the business owner, 2-4 sentences. "
                        "Include what the caller wanted and any follow-up needed."
                    ),
                },
                "reason": {
                    "type": "string",
                    "description": "thanks | goodbye | completed | other",
                },
                "caller_intent": {
                    "type": "string",
                    "description": "Short label e.g. website quote, app demo, callback, general enquiry",
                },
            },
            "required": ["summary"],
        },
    },
    {
        "type": "function",
        "name": "trigger_business_action",
        "description": "Generic escape hatch for other business actions.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["action"],
        },
    },
]


async def dispatch_tool(name: str, arguments: dict[str, Any], ctx: dict[str, Any]) -> str:
    if name == "end_call":
        return json.dumps(
            {
                "status": "ending",
                "message": "Call will hang up after your farewell.",
                "reason": arguments.get("reason") or "completed",
            }
        )
    if name == "lookup_knowledge":
        query = str(arguments.get("query") or "").strip()
        if config.KNOWLEDGE_SEARCH_LOCAL_FIRST and query:
            from knowledge import search_knowledge

            local = search_knowledge(query)
            if local:
                return json.dumps(
                    {
                        "status": "ok",
                        "source": "local",
                        "query": query,
                        "results": local,
                        "message": "Use these facts in your spoken reply. Do not read verbatim lists.",
                    }
                )
        return await call_n8n("lookup_knowledge", arguments, ctx)
    if name == "trigger_business_action":
        action = str(arguments.get("action", "unknown"))
        args = arguments.get("details", {}) or {}
    else:
        action = name
        args = arguments
    return await call_n8n(action, args, ctx)


async def call_n8n(action: str, args: dict[str, Any], ctx: dict[str, Any]) -> str:
    if not config.N8N_WEBHOOK_URL:
        log.warning("N8N_WEBHOOK_URL not set; stub for action=%s", action)
        return json.dumps({"status": "ok", "note": "n8n webhook not configured (stub)"})

    payload = {
        "action": action,
        "args": args,
        "call_id": ctx.get("call_id"),
        "from": ctx.get("from"),
        "direction": ctx.get("direction", "inbound"),
        "language": ctx.get("language"),
        "notify_whatsapp": config.NOTIFY_WHATSAPP or None,
        "business_name": config.BUSINESS_NAME,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(config.N8N_WEBHOOK_URL, json=payload)
            resp.raise_for_status()
            try:
                data = resp.json()
            except ValueError:
                data = {"result": resp.text}
        log.info("n8n action=%s -> %s", action, data)
        return json.dumps(data)
    except Exception as exc:  # noqa: BLE001
        log.exception("n8n call failed for action=%s", action)
        return json.dumps({"status": "error", "message": str(exc)})
