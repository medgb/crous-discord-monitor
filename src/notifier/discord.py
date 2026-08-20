"""Discord Webhook notification sender with rich embeds and user pinging."""

import logging
import time
from typing import Dict, List, Optional
import requests

from src.crous.models import Accommodation

logger = logging.getLogger(__name__)

COLOR_AVAILABLE = 0x2ECC71  # Emerald Green
COLOR_BATCH = 0x3498DB      # Blue
COLOR_TEST = 0x9B59B6       # Purple
COLOR_REMOVED = 0xE74C3C    # Alizarin Red


class DiscordError(Exception):
    """Exception raised when Discord webhook request fails."""
    pass


class DiscordNotifier:
    """Sends rich availability alerts to Discord channels via Webhook."""

    def __init__(
        self,
        webhook_url: str,
        user_id: Optional[str] = None,
        timeout_seconds: int = 15,
    ):
        self.webhook_url = webhook_url
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds

    def _get_mention_text(self) -> str:
        """Return Discord user or group mention string if configured."""
        if not self.user_id:
            return ""
        val = self.user_id.strip()
        if val.lower() in ("@everyone", "@all", "everyone", "all"):
            return "@everyone "
        if val.lower() in ("@here", "here"):
            return "@here "
        # Numeric Discord User ID
        clean_id = val.strip("<@!>")
        return f"<@{clean_id}> "

    def _send_payload(self, payload: Dict) -> bool:
        """Send JSON payload to Discord webhook with rate limit backoff."""
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=self.timeout_seconds,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 2.0))
                    logger.warning("Discord rate limited. Backing off for %.1fs...", retry_after)
                    time.sleep(retry_after + 0.5)
                    continue

                if response.status_code in (200, 204):
                    logger.debug("Discord webhook delivered successfully.")
                    return True

                logger.error(
                    "Discord webhook returned status %d: %s",
                    response.status_code, response.text
                )
                return False

            except requests.exceptions.RequestException as e:
                logger.warning("Network error sending Discord notification (attempt %d/3): %s", attempt, e)
                time.sleep(attempt * 1.5)

        logger.error("Failed to send Discord webhook after 3 attempts.")
        return False

    def build_accommodation_embed(self, item: Accommodation) -> Dict:
        """Create a single Discord rich embed for an accommodation offer."""
        fields = [
            {"name": "🏠 Résidence", "value": item.residence_name, "inline": True},
            {"name": "📍 Ville / Adresse", "value": f"{item.city}\n*{item.address}*" if item.address else item.city, "inline": True},
            {"name": "🛏️ Type", "value": item.accommodation_type, "inline": True},
            {"name": "📐 Surface", "value": item.surface_display, "inline": True},
            {"name": "💰 Loyer", "value": item.price_display, "inline": True},
        ]

        if item.labels:
            fields.append({"name": "🏷️ Caractéristiques", "value": " • ".join(item.labels), "inline": True})

        fields.append({
            "name": "⚡ Postuler",
            "value": f"[👉 Ouvrir l'offre CROUS sur votre téléphone]({item.url})",
            "inline": False,
        })

        return {
            "title": f"🚨 LOGEMENT CROUS DISPONIBLE (#{item.id})",
            "description": f"Un nouveau logement est disponible à **{item.residence_name}** !",
            "url": item.url,
            "color": COLOR_AVAILABLE,
            "fields": fields,
            "footer": {
                "text": "CROUS Room Availability Monitor • Cliquez sur le lien pour faire votre demande"
            }
        }

    def build_disappeared_embed(self, item: Accommodation) -> Dict:
        """Create a single Discord rich embed for a removed/taken room."""
        fields = [
            {"name": "🏠 Résidence", "value": item.residence_name, "inline": True},
            {"name": "📍 Ville", "value": item.city, "inline": True},
            {"name": "🛏️ Type", "value": item.accommodation_type, "inline": True},
            {"name": "💰 Loyer", "value": item.price_display, "inline": True},
        ]

        return {
            "title": f"❌ LOGEMENT CROUS INDISPONIBLE (#{item.id})",
            "description": f"Le logement à **{item.residence_name}** ({item.city}) n'est plus disponible (réservé ou expiré).",
            "color": COLOR_REMOVED,
            "fields": fields,
            "footer": {
                "text": "CROUS Room Availability Monitor • Statut mis à jour"
            }
        }

    def notify_accommodations(self, items: List[Accommodation]) -> bool:
        """
        Send notification for newly available accommodations.
        Sends individual embeds for up to 25 rooms, or a grouped digest for very large bursts.
        """
        if not items:
            return True

        mention = self._get_mention_text()

        # Send individual detailed embeds (up to 25 rooms)
        if len(items) <= 25:
            all_success = True
            for item in items:
                content = f"{mention}🚨 **NOUVEAU LOGEMENT CROUS DISPONIBLE !**" if mention else "🚨 **NOUVEAU LOGEMENT CROUS DISPONIBLE !**"
                payload = {
                    "content": content,
                    "embeds": [self.build_accommodation_embed(item)],
                }
                if not self._send_payload(payload):
                    all_success = False
                time.sleep(0.6)  # 600ms delay to smoothly respect Discord's rate limits
            return all_success

        # Very large batch (> 25 rooms): Group into a digest message
        logger.info("Sending batch digest notification for %d rooms...", len(items))
        fields = []
        for it in items[:15]:
            fields.append({
                "name": f"🏠 {it.residence_name} - {it.accommodation_type}",
                "value": f"{it.city} | {it.surface_display} | {it.price_display}\n[🔗 Lien direct]({it.url})",
                "inline": False,
            })

        if len(items) > 15:
            fields.append({
                "name": "...",
                "value": f"*+ {len(items) - 15} autres logements disponibles.*",
                "inline": False,
            })

        payload = {
            "content": f"{mention}🚨 **{len(items)} NOUVEAUX LOGEMENTS CROUS DISPONIBLES !**",
            "embeds": [
                {
                    "title": f"🚨 {len(items)} NOUVEAUX LOGEMENTS CROUS DÉTECTÉS",
                    "description": "Plusieurs logements viennent de devenir disponibles dans votre recherche.",
                    "color": COLOR_BATCH,
                    "fields": fields,
                    "footer": {
                        "text": "CROUS Room Availability Monitor • Connectez-vous rapidement pour postuler"
                    }
                }
            ],
        }
        return self._send_payload(payload)

    def notify_disappeared_accommodations(self, items: List[Accommodation]) -> bool:
        """
        Send notification when rooms are removed or taken (if configured).
        """
        if not items:
            return True

        mention = self._get_mention_text()

        if len(items) <= 5:
            all_success = True
            for item in items:
                content = f"{mention}❌ **LOGEMENT CROUS RETIRÉ / RÉSERVÉ**" if mention else "❌ **LOGEMENT CROUS RETIRÉ / RÉSERVÉ**"
                payload = {
                    "content": content,
                    "embeds": [self.build_disappeared_embed(item)],
                }
                if not self._send_payload(payload):
                    all_success = False
                time.sleep(0.5)
            return all_success

        # Grouped summary for multiple removed rooms
        fields = []
        for it in items[:15]:
            fields.append({
                "name": f"❌ {it.residence_name} - {it.accommodation_type}",
                "value": f"{it.city} | {it.price_display}",
                "inline": True,
            })

        payload = {
            "content": f"{mention}❌ **{len(items)} LOGEMENTS NE SONT PLUS DISPONIBLES**",
            "embeds": [
                {
                    "title": f"❌ {len(items)} LOGEMENTS CROUS RETIRÉS",
                    "description": "Ces logements ont été réservés ou ne sont plus listés sur le site du CROUS.",
                    "color": COLOR_REMOVED,
                    "fields": fields,
                    "footer": {
                        "text": "CROUS Room Availability Monitor • Mise à jour du statut"
                    }
                }
            ],
        }
        return self._send_payload(payload)

    def send_test_notification(self) -> bool:
        """Send a test notification to verify webhook configuration and user mention."""
        mention = self._get_mention_text()
        content = f"{mention}🔔 **Notification de test - CROUS Monitor**" if mention else "🔔 **Notification de test - CROUS Monitor**"

        payload = {
            "content": content,
            "embeds": [
                {
                    "title": "✅ CROUS Monitor - Test de connexion réussi",
                    "description": (
                        "Le webhook Discord est correctement configuré !\n"
                        "Vous recevrez une notification ici dès qu'un nouveau logement sera détecté."
                    ),
                    "color": COLOR_TEST,
                    "fields": [
                        {"name": "Statut", "value": "🟢 Opérationnel", "inline": True},
                        {"name": "Notification mobile", "value": "Activée" if self.user_id else "Désactivée (DISCORD_USER_ID non configuré)", "inline": True},
                    ],
                    "footer": {
                        "text": "CROUS Room Availability Monitor • Test Mode"
                    }
                }
            ],
        }
        logger.info("Sending test notification to Discord...")
        success = self._send_payload(payload)
        if success:
            logger.info("Test notification delivered successfully to Discord!")
        else:
            logger.error("Failed to send test notification to Discord.")
        return success
