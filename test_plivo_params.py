"""Self-check: Plivo urlencoded body is parsed without python-multipart."""
from __future__ import annotations

from plivo_form import parse_plivo_payload, pick_plivo_value


def main() -> None:
    params = parse_plivo_payload(
        body=b"From=%2B916264904864&To=%2B912264233283&CallUUID=abc-1",
        content_type="application/x-www-form-urlencoded",
    )
    assert pick_plivo_value(params, "From", "from") == "+916264904864", params
    assert pick_plivo_value(params, "To", "to") == "+912264233283", params
    assert pick_plivo_value(params, "CallUUID") == "abc-1", params
    empty = parse_plivo_payload(body=b"")
    assert empty == {}
    print("ok")


if __name__ == "__main__":
    main()
