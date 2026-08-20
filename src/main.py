"""Command-line interface and main entrypoint for the CROUS Discord Monitor."""

import argparse
import sys

# Ensure UTF-8 output encoding on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.config import Config
from src.crous.auth import AuthManager
from src.crous.client import CrousClient
from src.crous.parser import parse_search_url
from src.logging_config import setup_logging
from src.monitor import AvailabilityMonitor
from src.notifier.discord import DiscordNotifier
from src.storage.database import Database


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="CROUS Discord Room Availability Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                           # Continuous monitoring mode (all targets)
  python -m src.main --once                    # Run a single check across all targets and print results
  python -m src.main --test-notification       # Send a test notification to all configured Discord Webhooks
  python -m src.main --login                   # Open interactive browser to log in and save session
  python -m src.main --notify-startup          # Enable alerts for existing rooms on initial run
        """
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one check, print detected accommodations, and exit without infinite loop.",
    )
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="Send a test notification to all configured Discord Webhooks to verify connectivity and pinging.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open an interactive browser window to log in to MesServices / CROUS and save authenticated session.",
    )
    parser.add_argument(
        "--notify-startup",
        action="store_true",
        help="Override baseline silence and send notifications for all existing rooms on startup.",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to custom .env configuration file (default: .env in current directory).",
    )
    return parser.parse_args()


def main() -> None:
    """Main execution function."""
    args = parse_args()

    # Load configuration
    config = Config.load(env_path=args.env_file)
    logger = setup_logging(config.log_level)

    # 1. Mode: Interactive Login
    if args.login:
        logger.info("Launching interactive browser login...")
        auth = AuthManager()
        success = auth.interactive_login(headless=False)
        sys.exit(0 if success else 1)

    # 2. Mode: Test Notification
    if args.test_notification:
        try:
            config.validate_for_discord_only()
        except ValueError as err:
            logger.error("%s", err)
            sys.exit(1)

        all_ok = True
        for target in config.targets:
            if target.webhook_url:
                logger.info("Testing Discord webhook for target '%s'...", target.name)
                notifier = DiscordNotifier(
                    webhook_url=target.webhook_url,
                    user_id=target.mention,
                    timeout_seconds=config.request_timeout_seconds,
                )
                success = notifier.send_test_notification()
                if not success:
                    all_ok = False
        sys.exit(0 if all_ok else 1)

    # 3. Mode: Single Check or Continuous Monitoring
    try:
        if args.once:
            config.validate_for_crous_only()
        else:
            config.validate_for_monitoring()
    except ValueError as err:
        logger.error("%s", err)
        print("\nPlease configure your .env file (see .env.example for details).", file=sys.stderr)
        sys.exit(1)

    # Setup dependencies
    auth_manager = AuthManager()
    session_cookies = auth_manager.load_session_cookies()
    crous_client = CrousClient(
        timeout_seconds=config.request_timeout_seconds,
        session_cookies=session_cookies,
    )
    database = Database(db_path=config.database_path)

    monitor = AvailabilityMonitor(
        config=config,
        crous_client=crous_client,
        database=database,
    )

    if args.once:
        logger.info("Executing single check mode (--once)...")
        for target in config.targets:
            query = parse_search_url(target.search_url)
            items, total_count = crous_client.fetch_all(query)
            print(f"\n=======================================================")
            print(f"[{target.name}] CROUS RESULTS ({len(items)} items available / {total_count} total):")
            print(f"Search URL: {target.search_url}")
            print(f"=======================================================")
            for it in items[:10]:
                print(f" • {it.summary()}")
                print(f"   🔗 Direct Link: {it.url}")
                if it.labels:
                    print(f"   🏷️  Tags: {', '.join(it.labels)}")
                print()
            if len(items) > 10:
                print(f"   ... and {len(items) - 10} more accommodations.")
        
        total_avail, new_cnt = monitor.check_once(force_notify_all=args.notify_startup)
        print(f"\nDatabase synced across all targets. Total available: {total_avail}")
        sys.exit(0)

    # Continuous monitoring mode
    try:
        monitor.run_forever()
    except KeyboardInterrupt:
        logger.info("Monitor interrupted by user. Exiting gracefully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
