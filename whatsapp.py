"""
WhatsApp Business (Meta Cloud API) Client

Sendet Textnachrichten an eine Liste von Empfängern.

Dokumentation: https://developers.facebook.com/docs/whatsapp/cloud-api/messages/text-messages

WICHTIGE HINWEISE:
  - Die Meta Cloud API erlaubt das direkte Schreiben in Gruppen-Chats NICHT.
    Nachrichten werden an individuelle Nummern gesendet.
  - Empfänger müssen dem Bot vorher eine Nachricht geschickt haben (24h-Fenster),
    ODER du verwendest einen genehmigten Template-Message-Typ.
  - Für Produktions-Use: System-User-Token statt temporären Token verwenden.
"""

import logging
from typing import List, Optional

import requests

import config

logger = logging.getLogger(__name__)


class WhatsAppClient:
    def __init__(self):
        self.cfg = config.whatsapp
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.cfg.access_token}",
            "Content-Type": "application/json",
        })

    def send_text(self, recipient_id: str, message: str) -> bool:
        """
        Sendet eine Textnachricht an eine einzelne Nummer.

        Args:
            recipient_id: Handynummer mit Ländervorwahl ohne + (z.B. "4917600000000")
            message:      Nachrichtentext (max. 4096 Zeichen)

        Returns:
            True bei Erfolg, False bei Fehler
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_id,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message[:4096],  # WhatsApp-Limit
            },
        }

        try:
            resp = self.session.post(self.cfg.messages_url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            msg_id = data.get("messages", [{}])[0].get("id", "?")
            logger.info("Nachricht gesendet an %s (msg_id: %s)", recipient_id, msg_id)
            return True
        except requests.HTTPError as e:
            logger.error(
                "HTTP-Fehler beim Senden an %s: %s – %s",
                recipient_id, e, e.response.text if e.response else "",
            )
            return False
        except requests.RequestException as e:
            logger.error("Netzwerkfehler beim Senden an %s: %s", recipient_id, e)
            return False

    def broadcast(self, message: str, recipients: Optional[List[str]] = None) -> int:
        """
        Sendet eine Nachricht an alle konfigurierten Empfänger.

        Args:
            message:    Nachrichtentext
            recipients: Optionale Override-Liste; Standard = config.whatsapp.recipient_ids

        Returns:
            Anzahl erfolgreich gesendeter Nachrichten
        """
        targets = recipients or self.cfg.recipient_ids
        if not targets:
            logger.warning("Keine Empfänger konfiguriert – Nachricht nicht gesendet.")
            return 0

        success_count = 0
        for recipient in targets:
            if self.send_text(recipient, message):
                success_count += 1
        return success_count

    def send_alert(self, message: str) -> int:
        """Alias für broadcast – für Preisalerts gedacht."""
        return self.broadcast(message)

    # ──────────────────────────────────────────────────────────
    # Webhook-Validierung (für Produktionsbetrieb)
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def verify_webhook(verify_token: str, hub_mode: str, hub_token: str, hub_challenge: str) -> Optional[str]:
        """
        Verifiziert den Meta-Webhook-Handshake.
        In Flask/FastAPI-Route aufrufen:

            @app.get("/webhook")
            def webhook_get():
                challenge = WhatsAppClient.verify_webhook(
                    verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN"),
                    hub_mode=request.args.get("hub.mode"),
                    hub_token=request.args.get("hub.verify_token"),
                    hub_challenge=request.args.get("hub.challenge"),
                )
                return challenge if challenge else ("Forbidden", 403)
        """
        expected_token = verify_token or config.whatsapp.access_token[:10]
        if hub_mode == "subscribe" and hub_token == expected_token:
            logger.info("Webhook verifiziert.")
            return hub_challenge
        logger.warning("Webhook-Verifikation fehlgeschlagen.")
        return None
