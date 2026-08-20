"""Unit tests for the availability monitor loop and error handling."""

from unittest.mock import MagicMock
import pytest

from src.config import Config
from src.crous.client import CrousClient, CrousNetworkError, CrousApiError
from src.monitor import AvailabilityMonitor
from src.notifier.discord import DiscordNotifier
from src.storage.database import Database


def test_monitor_baseline_run_no_discord_spam(temp_db, sample_accommodation_1, sample_accommodation_2):
    config = Config(
        crous_search_url="https://trouverunlogement.lescrous.fr/tools/42/search",
        discord_webhook_url="https://discord.com/api/webhooks/123/mocktoken",
        notify_on_startup=False,
    )
    mock_client = MagicMock(spec=CrousClient)
    mock_client.fetch_all.return_value = ([sample_accommodation_1, sample_accommodation_2], 2)

    monitor = AvailabilityMonitor(
        config=config,
        crous_client=mock_client,
        database=temp_db,
    )
    # Mock notifier on the target runner
    mock_notifier = MagicMock(spec=DiscordNotifier)
    monitor.runners[0].notifier = mock_notifier

    total_avail, new_cnt = monitor.check_once()
    assert total_avail == 2
    assert new_cnt == 0
    mock_notifier.notify_accommodations.assert_not_called()
    assert temp_db.get_currently_available_count(target_name="Default") == 2


def test_monitor_detects_new_room_and_notifies(temp_db, sample_accommodation_1, sample_accommodation_2, sample_accommodation_3):
    config = Config(
        crous_search_url="https://trouverunlogement.lescrous.fr/tools/42/search",
        discord_webhook_url="https://discord.com/api/webhooks/123/mocktoken",
        notify_on_startup=False,
    )
    mock_client = MagicMock(spec=CrousClient)
    mock_client.fetch_all.return_value = ([sample_accommodation_1, sample_accommodation_2], 2)

    monitor = AvailabilityMonitor(
        config=config,
        crous_client=mock_client,
        database=temp_db,
    )
    mock_notifier = MagicMock(spec=DiscordNotifier)
    mock_notifier.notify_accommodations.return_value = True
    monitor.runners[0].notifier = mock_notifier

    # 1. Baseline
    monitor.check_once()
    mock_notifier.notify_accommodations.assert_not_called()

    # 2. Next check with new room 3
    mock_client.fetch_all.return_value = (
        [sample_accommodation_1, sample_accommodation_2, sample_accommodation_3], 3
    )
    total_avail, new_cnt = monitor.check_once()

    assert total_avail == 3
    assert new_cnt == 1
    mock_notifier.notify_accommodations.assert_called_once()
    notified_items = mock_notifier.notify_accommodations.call_args[0][0]
    assert len(notified_items) == 1
    assert notified_items[0].id == sample_accommodation_3.id


def test_monitor_crous_failure_does_not_clear_db(temp_db, sample_accommodation_1, sample_accommodation_2):
    config = Config(
        crous_search_url="https://trouverunlogement.lescrous.fr/tools/42/search",
        discord_webhook_url="https://discord.com/api/webhooks/123/mocktoken",
    )
    mock_client = MagicMock(spec=CrousClient)
    mock_client.fetch_all.return_value = ([sample_accommodation_1, sample_accommodation_2], 2)

    monitor = AvailabilityMonitor(
        config=config,
        crous_client=mock_client,
        database=temp_db,
    )
    mock_notifier = MagicMock(spec=DiscordNotifier)
    monitor.runners[0].notifier = mock_notifier

    monitor.check_once()
    assert temp_db.get_currently_available_count(target_name="Default") == 2

    # 2. Next check raises network error
    mock_client.fetch_all.side_effect = CrousNetworkError("Connection timed out")
    total_avail, new_cnt = monitor.check_once()

    # DB must still preserve records
    assert temp_db.get_currently_available_count(target_name="Default") == 2
    assert monitor.consecutive_errors == 1
    mock_notifier.notify_accommodations.assert_not_called()


def test_monitor_notify_on_startup_override(temp_db, sample_accommodation_1):
    config = Config(
        crous_search_url="https://trouverunlogement.lescrous.fr/tools/42/search",
        discord_webhook_url="https://discord.com/api/webhooks/123/mocktoken",
        notify_on_startup=True,
    )
    mock_client = MagicMock(spec=CrousClient)
    mock_client.fetch_all.return_value = ([sample_accommodation_1], 1)

    monitor = AvailabilityMonitor(
        config=config,
        crous_client=mock_client,
        database=temp_db,
    )
    mock_notifier = MagicMock(spec=DiscordNotifier)
    mock_notifier.notify_accommodations.return_value = True
    monitor.runners[0].notifier = mock_notifier

    total_avail, new_cnt = monitor.check_once()
    assert new_cnt == 1
    mock_notifier.notify_accommodations.assert_called_once()
