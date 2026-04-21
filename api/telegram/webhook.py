import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

import requests


WELCOME_MESSAGE = "Welcome to the stock market alerts for Mutual Funds"
STOP_MESSAGE = "You have unsubscribed from stock market alerts."
SUBSCRIBERS_TABLE = "telegram_subscribers"


def _require_env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _send_telegram_text(chat_id, text):
    bot_token = _require_env("TELEGRAM_BOT_TOKEN")
    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": text},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram send failed: {payload}")


def _upsert_subscriber(chat, is_active):
    supabase_url = _require_env("SUPABASE_URL").rstrip("/")
    service_role_key = _require_env("SUPABASE_SERVICE_ROLE_KEY")
    chat_id = str(chat["id"])
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "chat_id": chat_id,
        "username": chat.get("username"),
        "first_name": chat.get("first_name"),
        "last_name": chat.get("last_name"),
        "chat_type": chat.get("type"),
        "is_active": is_active,
        "updated_at": now,
    }
    if is_active:
        payload["subscribed_at"] = now
    else:
        payload["unsubscribed_at"] = now

    response = requests.post(
        f"{supabase_url}/rest/v1/{SUBSCRIBERS_TABLE}",
        params={"on_conflict": "chat_id"},
        headers={
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()


def _process_update(update):
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = str(message.get("text", "")).strip().lower()

    if chat_id is None:
        return {"ok": True, "ignored": True}

    if text.startswith("/stop"):
        _upsert_subscriber(chat, is_active=False)
        _send_telegram_text(chat_id, STOP_MESSAGE)
        return {"ok": True, "action": "unsubscribed"}

    if text.startswith("/start"):
        _upsert_subscriber(chat, is_active=True)
        _send_telegram_text(chat_id, WELCOME_MESSAGE)
        return {"ok": True, "action": "subscribed"}

    return {"ok": True, "ignored": True}


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _is_authorized(self):
        expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        if not expected_secret:
            return True
        provided_secret = self.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        return provided_secret == expected_secret

    def do_GET(self):
        self._send_json(200, {"ok": True, "service": "telegram-webhook"})

    def do_POST(self):
        if not self._is_authorized():
            self._send_json(401, {"ok": False, "error": "Unauthorized"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            update = json.loads(raw_body or "{}")
        except Exception:
            self._send_json(400, {"ok": False, "error": "Invalid JSON"})
            return

        try:
            self._send_json(200, _process_update(update))
        except Exception as exc:
            self._send_json(500, {"ok": False, "error": str(exc)})
