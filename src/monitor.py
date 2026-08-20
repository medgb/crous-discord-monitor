"""Availability monitor orchestrator supporting multiple channels and targets."""

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from src.config import Config, MonitorTarget
from src.crous.client import CrousClient, CrousNetworkError, CrousApiError
from src.crous.models import SearchQuery
from src.crous.parser import parse_search_url
from src.notifier.discord import DiscordNotifier
from src.storage.database import Database

logger = logging.getLogger(__name__)


class TargetRunner:
    """Manages monitoring state for a specific target channel."""

    def __init__(self, target: MonitorTarget, client: CrousClient, db: Database, timeout_seconds: int = 15):
        self.target = target
        self.query: SearchQuery = parse_search_url(target.search_url)
        self.client = client
        self.db = db
        self.notifier = DiscordNotifier(
            webhook_url=target.webhook_url,
            user_id=target.mention,
            timeout_seconds=timeout_seconds,
        )

    def check(self, is_baseline_override: bool = False, notify_on_startup: bool = False, notify_on_removal: bool = False) -> Tuple[int, int, int]:
        """
        Execute one check for this target.
        Returns: (total_available, newly_added_count, disappeared_count)
        """
        is_fresh_db = self.db.is_empty(target_name=self.target.name)
        is_baseline = (is_fresh_db and not notify_on_startup) or is_baseline_override

        logger.debug(
            "[%s] Querying CROUS (tool_id=%d, bounds=[%.4f, %.4f, %.4f, %.4f])...",
            self.target.name, self.query.tool_id, self.query.top_left_lon, self.query.top_left_lat,
            self.query.bottom_right_lon, self.query.bottom_right_lat
        )

        current_items, total_reported = self.client.fetch_all(self.query)

        newly_available, disappeared_items, maintained_cnt = self.db.sync_snapshot(
            current_items=current_items,
            target_name=self.target.name,
            is_baseline=is_baseline,
        )

        total_available = len(current_items)

        if is_baseline:
            logger.info(
                "[%s] INITIAL BASELINE RECORDED: %d existing accommodations saved. Alerts are now active.",
                self.target.name, total_available
            )
            return total_available, 0, 0

        # 1. Notify newly available
        if newly_available:
            logger.info(
                "[%s] 🚨 %d NEW ACCOMMODATION(S) DETECTED! Sending Discord alert to #%s...",
                self.target.name, len(newly_available), self.target.name
            )
            self.notifier.notify_accommodations(newly_available)

        # 2. Notify removals
        if disappeared_items and notify_on_removal:
            logger.info(
                "[%s] ❌ %d ACCOMMODATION(S) REMOVED! Sending removal notification to #%s...",
                self.target.name, len(disappeared_items), self.target.name
            )
            self.notifier.notify_disappeared_accommodations(disappeared_items)

        return total_available, len(newly_available), len(disappeared_items)


class AvailabilityMonitor:
    """Orchestrates continuous availability checks across all configured targets."""

    def __init__(
        self,
        config: Config,
        crous_client: Optional[CrousClient] = None,
        database: Optional[Database] = None,
        notifier: Optional[DiscordNotifier] = None,
    ):
        self.config = config
        self.client = crous_client or CrousClient(timeout_seconds=config.request_timeout_seconds)
        self.db = database or Database(db_path=config.database_path)

        self.runners: List[TargetRunner] = [
            TargetRunner(
                target=t,
                client=self.client,
                db=self.db,
                timeout_seconds=config.request_timeout_seconds,
            )
            for t in config.targets
        ]

        # Health metrics
        self.total_checks = 0
        self.successful_checks = 0
        self.consecutive_errors = 0
        self.last_successful_check: Optional[datetime] = None

    def check_once(self, force_notify_all: bool = False) -> Tuple[int, int]:
        """Execute a single polling check across all targets."""
        self.total_checks += 1
        total_avail_sum = 0
        total_new_sum = 0

        for runner in self.runners:
            try:
                avail, new_cnt, rem_cnt = runner.check(
                    is_baseline_override=False if force_notify_all else False,
                    notify_on_startup=self.config.notify_on_startup or force_notify_all,
                    notify_on_removal=self.config.notify_on_removal,
                )
                total_avail_sum += avail
                total_new_sum += new_cnt
                self.consecutive_errors = 0
                self.successful_checks += 1
                self.last_successful_check = datetime.now(timezone.utc)
            except (CrousNetworkError, CrousApiError) as err:
                self.consecutive_errors += 1
                logger.warning(
                    "[%s] CROUS check failed (consecutive failures: %d): %s. Preserving last known database state.",
                    runner.target.name, self.consecutive_errors, err
                )

        return total_avail_sum, total_new_sum

    def run_forever(self) -> None:
        """Run the continuous multi-target monitoring loop."""
        logger.info(
            "Starting CROUS Availability Monitor (Poll interval: %ds, DB: %s)...",
            self.config.poll_interval_seconds, self.config.database_path
        )
        for t in self.config.targets:
            logger.info(
                " • Target '%s': %s -> Webhook: %s (Mention: %s)",
                t.name, t.search_url, t.masked_webhook_url(), t.mention
            )

        while True:
            try:
                self.check_once()
            except Exception as e:
                logger.error("Unexpected error during monitoring cycle: %s", e, exc_info=True)

            sleep_duration = self.config.poll_interval_seconds
            if self.consecutive_errors > 0:
                backoff = min(300, self.consecutive_errors * 10)
                sleep_duration += backoff
                logger.info("Consecutive errors (%d). Sleeping for %ds before retry...", self.consecutive_errors, sleep_duration)

            time.sleep(sleep_duration)
