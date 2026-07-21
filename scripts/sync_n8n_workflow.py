"""Copy n8n/build_call_log.js into voice_agent_actions.json (Build Call Log node)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "n8n" / "build_call_log.js"
WORKFLOW = ROOT / "n8n" / "voice_agent_actions.json"
NODE_NAME = "Build Call Log"


def main() -> None:
    if not JS.is_file():
        raise SystemExit(f"Missing {JS}")
    if not WORKFLOW.is_file():
        raise SystemExit(f"Missing {WORKFLOW}")
    code = JS.read_text(encoding="utf-8")
    data = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    updated = False
    for node in data.get("nodes", []):
        if node.get("name") == NODE_NAME:
            node.setdefault("parameters", {})["jsCode"] = code
            updated = True
            break
    if not updated:
        raise SystemExit(f"Node {NODE_NAME!r} not found in workflow")
    WORKFLOW.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {WORKFLOW.name} ← {JS.name}")


if __name__ == "__main__":
    main()
