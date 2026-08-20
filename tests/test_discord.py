"""Unit tests for Discord Webhook formatter and notification logic."""

from unittest.mock import MagicMock, patch
from src.notifier.discord import DiscordNotifier, COLOR_AVAILABLE, COLOR_BATCH


def test_build_accommodation_embed(sample_accommodation_1):
    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/123/token",
        user_id="987654321",
    )
    embed = notifier.build_accommodation_embed(sample_accommodation_1)

    assert embed["color"] == COLOR_AVAILABLE
    assert "718" in embed["title"]
    assert embed["url"] == sample_accommodation_1.url

    # Check fields
    field_dict = {f["name"]: f["value"] for f in embed["fields"]}
    assert "Residence Christophe GARELLI" in field_dict["🏠 Résidence"]
    assert "CORTE" in field_dict["📍 Ville / Adresse"]
    assert "G023 STUDIO" in field_dict["🛏️ Type"]
    assert "16 - 18 m²" in field_dict["📐 Surface"]
    assert "394 € / mois" in field_dict["💰 Loyer"]
    assert "Dernières places" in field_dict["🏷️ Caractéristiques"]
    assert sample_accommodation_1.url in field_dict["⚡ Postuler"]


def test_discord_user_mention_included(sample_accommodation_1):
    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/123/token",
        user_id="123456789012345678",
    )
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        notifier.notify_accommodations([sample_accommodation_1])

        mock_post.assert_called_once()
        sent_payload = mock_post.call_args[1]["json"]
        assert "<@123456789012345678>" in sent_payload["content"]


def test_discord_no_user_mention_when_unset(sample_accommodation_1):
    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/123/token",
        user_id=None,
    )
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        notifier.notify_accommodations([sample_accommodation_1])

        sent_payload = mock_post.call_args[1]["json"]
        assert "<@" not in sent_payload["content"]


def test_large_batch_grouped_notification(sample_accommodation_1):
    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/123/token",
        user_id="12345",
    )
    # Create 30 dummy accommodations to trigger grouped digest
    from copy import deepcopy
    items = []
    for i in range(1, 31):
        item = deepcopy(sample_accommodation_1)
        item.id = 1000 + i
        item.residence_name = f"Residence {i}"
        items.append(item)

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        notifier.notify_accommodations(items)

        # Large batch should send 1 grouped message
        mock_post.assert_called_once()
        sent_payload = mock_post.call_args[1]["json"]
        assert "30 NOUVEAUX LOGEMENTS" in sent_payload["content"]
        assert len(sent_payload["embeds"]) == 1
        assert sent_payload["embeds"][0]["color"] == COLOR_BATCH


def test_send_test_notification():
    notifier = DiscordNotifier(
        webhook_url="https://discord.com/api/webhooks/123/token",
        user_id="12345",
    )
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 204
        success = notifier.send_test_notification()
        assert success is True
        mock_post.assert_called_once()
        sent_payload = mock_post.call_args[1]["json"]
        assert "Test" in sent_payload["embeds"][0]["title"]
