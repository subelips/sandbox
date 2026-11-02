#!/usr/bin/env python3
"""Telegram notifier. Stdlib only. The bot only SENDS - it never polls for commands."""
import json
import os
import sys
import urllib.parse
import urllib.request


def send(text: str, token: str | None = None, chat_id: str | None = None,
         silent: bool = True) -> dict:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        print("tg: missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID", file=sys.stderr)
        return {"ok": False, "description": "missing credentials"}
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
        "disable_notification": "true" if silent else "false",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.load(resp)
    except Exception as exc:  # network / 4xx - never fail the caller
        print(f"tg: send failed: {exc}", file=sys.stderr)
        return {"ok": False, "description": str(exc)}
    if not body.get("ok"):
        print(f"tg: api error: {body.get('description')}", file=sys.stderr)
    return body


if __name__ == "__main__":
    msg = sys.stdin.read() if len(sys.argv) < 2 else " ".join(sys.argv[1:])
    print(json.dumps(send(msg), ensure_ascii=False))
