# n8n workflows

## Import

1. Import **`voice_agent_actions.json`** in n8n and activate.
2. Set `N8N_WEBHOOK_URL` in `.env` to the production webhook URL.

## Google Sheets

Create a spreadsheet with three tabs. Row 1 headers — copy from:

- `voice_calls_headers.csv`
- `voice_transcripts_headers.csv`
- `voice_actions_headers.csv`

Sheet nodes use **auto-map input data**; header names must match exactly.

## Maintaining `Build Call Log` code

Edit **`build_call_log.js`**, then sync into the workflow JSON:

```bash
python scripts/sync_n8n_workflow.py
```

Re-import or save `voice_agent_actions.json` in n8n if you deploy from file.
