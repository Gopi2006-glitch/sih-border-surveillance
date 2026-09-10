import os
import requests
import threading

# Replace with your actual credentials or configure in environment
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8846591302:AAHnO7uHb4kBNwy75yn8neOkUE6NOPYo__c")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8483954485")


def _send_telegram_worker(text: str, image_path: str = None):
    """Background worker to dispatch Telegram messages without blocking video inference."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        print("[TELEGRAM] Bot token not configured. Skipping alert.")
        return

    try:
        if image_path and os.path.exists(image_path):
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(image_path, "rb") as photo:
                data = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": text,
                    "parse_mode": "Markdown"
                }
                requests.post(url, data=data, files={"photo": photo}, timeout=4.0)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown"
            }
            requests.post(url, json=payload, timeout=4.0)
    except Exception as e:
        print(f"[TELEGRAM ERROR] Failed to deliver alert: {e}")


def send_telegram_alert_async(cam_id: str, sector: str, label: str, confidence: float, image_path: str = None):
    """Dispatch alert on a separate thread to keep streaming framerates at 30 FPS."""
    caption = (
        f"🚨 *SECURITY BREACH DETECTED*\n\n"
        f"• *Target:* `{label}`\n"
        f"• *Confidence:* `{int(confidence * 100)}%`\n"
        f"• *Camera:* `{cam_id}`\n"
        f"• *Sector:* `{sector}`\n"
        f"• *Action Required:* Operator review required immediately."
    )
    thread = threading.Thread(
        target=_send_telegram_worker,
        args=(caption, image_path),
        daemon=True
    )
    thread.start()