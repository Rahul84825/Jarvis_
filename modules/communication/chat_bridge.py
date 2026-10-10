import os
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional
from config import config

logger = logging.getLogger("Jarvis.ChatBridge")

class ChatBridge:
    """Communication bridge for Telegram Bot, WhatsApp notification dispatcher,
    and mobile push notifications.
    """

    def __init__(self):
        self.telegram_bot_token = getattr(config, "telegram_bot_token", os.getenv("TELEGRAM_BOT_TOKEN", ""))
        self.telegram_chat_id = getattr(config, "telegram_chat_id", os.getenv("TELEGRAM_CHAT_ID", ""))
        self.webhook_url = getattr(config, "notification_webhook_url", os.getenv("NOTIFICATION_WEBHOOK_URL", ""))

    def send_telegram_message(self, message: str) -> Dict[str, Any]:
        """Sends a message via Telegram Bot API."""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.info(f"[SIMULATED TELEGRAM] To Chat {self.telegram_chat_id or 'DemoUser'}: {message}")
            return {
                "success": True,
                "simulated": True,
                "message": f"Simulated Telegram notification: '{message}'"
            }

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }).encode('utf-8')

        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get("ok"):
                    logger.info("Telegram notification delivered successfully.")
                    return {"success": True, "message": "Telegram message delivered."}
                else:
                    return {"success": False, "message": data.get("description", "Unknown Telegram error")}
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return {"success": False, "message": f"Telegram API error: {str(e)}"}

    def send_whatsapp_message(self, phone_number: str, message: str) -> Dict[str, Any]:
        """Dispatches a WhatsApp message or prepares web automation."""
        clean_num = phone_number.strip().replace(" ", "").replace("-", "")
        logger.info(f"Preparing WhatsApp message to {clean_num}: '{message}'")
        
        # Formulate direct WhatsApp web deep link for immediate browser dispatch
        wa_url = f"https://web.whatsapp.com/send?phone={urllib.parse.quote(clean_num)}&text={urllib.parse.quote(message)}"
        
        return {
            "success": True,
            "target": clean_num,
            "dispatch_url": wa_url,
            "message": f"WhatsApp dispatch initiated for recipient {clean_num}."
        }

# Singleton instance
chat_bridge = ChatBridge()
