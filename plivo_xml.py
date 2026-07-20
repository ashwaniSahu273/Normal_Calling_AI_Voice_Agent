"""Builds the Plivo answer XML that opens a bidirectional mu-law audio stream."""
from __future__ import annotations

import config


def answer_xml() -> str:
    """Return XML telling Plivo to stream call audio to our /stream WebSocket.

    contentType mu-law 8kHz matches OpenAI Realtime's g711_ulaw, so audio passes
    through without transcoding. keepCallAlive keeps the call up for the stream's life.
    """
    ws_url = f"wss://{config.PUBLIC_HOST}/plivo/stream"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Response>\n"
        '  <Stream bidirectional="true" keepCallAlive="true" '
        f'contentType="{config.PLIVO_CONTENT_TYPE};rate={config.PLIVO_SAMPLE_RATE}">'
        f"{ws_url}</Stream>\n"
        "</Response>\n"
    )
