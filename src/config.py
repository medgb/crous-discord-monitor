"""Configuration management and validation for CROUS Discord Monitor."""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv


@dataclass(frozen=True)
class MonitorTarget:
    """A specific search destination paired with its Discord webhook channel."""
    name: str
    search_url: str
    webhook_url: str
    mention: str = "@everyone"

    def masked_webhook_url(self) -> str:
        """Return masked webhook URL for safe logging."""
        if not self.webhook_url:
            return "<unset>"
        parts = self.webhook_url.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:-1]) + "/***REDACTED***"
        return "***REDACTED***"


@dataclass
class Config:
    """Application configuration container supporting multiple channels/targets."""
    targets: List[MonitorTarget] = field(default_factory=list)
    poll_interval_seconds: int = 30
    request_timeout_seconds: int = 30
    log_level: str = "INFO"
    notify_on_startup: bool = False
    notify_on_removal: bool = False
    database_path: str = "data/crous_monitor.db"
    crous_email: Optional[str] = None
    crous_password: Optional[str] = None
    headless: bool = True

    def __init__(
        self,
        targets: Optional[List[MonitorTarget]] = None,
        crous_search_url: Optional[str] = None,
        discord_webhook_url: Optional[str] = None,
        discord_user_id: Optional[str] = None,
        poll_interval_seconds: int = 30,
        request_timeout_seconds: int = 30,
        log_level: str = "INFO",
        notify_on_startup: bool = False,
        notify_on_removal: bool = False,
        database_path: str = "data/crous_monitor.db",
        crous_email: Optional[str] = None,
        crous_password: Optional[str] = None,
        headless: bool = True,
    ):
        if targets is not None:
            self.targets = list(targets)
        elif crous_search_url or discord_webhook_url:
            self.targets = [
                MonitorTarget(
                    name="Default",
                    search_url=crous_search_url or "https://trouverunlogement.lescrous.fr/tools/47/search",
                    webhook_url=discord_webhook_url or "",
                    mention=discord_user_id or "@everyone",
                )
            ]
        else:
            self.targets = []

        self.poll_interval_seconds = poll_interval_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.log_level = log_level
        self.notify_on_startup = notify_on_startup
        self.notify_on_removal = notify_on_removal
        self.database_path = database_path
        self.crous_email = crous_email
        self.crous_password = crous_password
        self.headless = headless

    @property
    def crous_search_url(self) -> str:
        return self.targets[0].search_url if self.targets else ""

    @property
    def discord_webhook_url(self) -> str:
        return self.targets[0].webhook_url if self.targets else ""

    @property
    def discord_user_id(self) -> str:
        return self.targets[0].mention if self.targets else ""

    @classmethod
    def load(cls, env_path: Optional[str] = None) -> "Config":
        """Load configuration from environment variables with .env file fallback."""
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()

        global_mention = os.getenv("DISCORD_MENTION", "").strip() or os.getenv("DISCORD_USER_ID", "").strip() or "@everyone"
        targets: List[MonitorTarget] = []
        discovered_prefixes = set()

        # 1. Dynamically discover any named city/channel target from environment
        # e.g., PARIS_DISCORD_WEBHOOK_URL, GRENOBLE_DISCORD_WEBHOOK_URL, LYON_WEBHOOK_URL
        for key, value in os.environ.items():
            key_upper = key.upper()
            if not value.strip():
                continue

            prefix = None
            if key_upper.endswith("_DISCORD_WEBHOOK_URL"):
                prefix = key_upper[:-20]  # strip '_DISCORD_WEBHOOK_URL'
            elif key_upper.endswith("_WEBHOOK_URL") and not key_upper.startswith("DISCORD"):
                prefix = key_upper[:-12]  # strip '_WEBHOOK_URL'
            elif key_upper.startswith("TARGET_") and key_upper.endswith("_WEBHOOK"):
                prefix = key_upper[7:-8]

            if prefix and prefix not in discovered_prefixes:
                discovered_prefixes.add(prefix)
                webhook_url = value.strip()
                search_url = (
                    os.getenv(f"{prefix}_SEARCH_URL", "").strip()
                    or os.getenv(f"{prefix}_CROUS_SEARCH_URL", "").strip()
                    or "https://trouverunlogement.lescrous.fr/tools/47/search"
                )
                target_mention = os.getenv(f"{prefix}_MENTION", "").strip() or global_mention
                
                # Format friendly display name (e.g. GRENOBLE -> Grenoble, GENERAL -> General France)
                if prefix == "GENERAL":
                    display_name = "General France"
                else:
                    display_name = prefix.replace("_", " ").title()

                targets.append(MonitorTarget(
                    name=display_name,
                    search_url=search_url,
                    webhook_url=webhook_url,
                    mention=target_mention,
                ))

        # 2. Fallback to default single-target variables if no named channels provided
        if not targets:
            default_search = os.getenv("CROUS_SEARCH_URL", "https://trouverunlogement.lescrous.fr/tools/47/search").strip()
            default_webhook = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
            targets.append(MonitorTarget(
                name="Default",
                search_url=default_search,
                webhook_url=default_webhook,
                mention=global_mention,
            ))

        poll_interval_raw = os.getenv("POLL_INTERVAL_SECONDS", "30").strip()
        try:
            poll_interval = max(5, int(poll_interval_raw))
        except ValueError:
            poll_interval = 30

        timeout_raw = os.getenv("REQUEST_TIMEOUT_SECONDS", "30").strip()
        try:
            request_timeout = max(5, int(timeout_raw))
        except ValueError:
            request_timeout = 30

        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            log_level = "INFO"

        notify_startup_str = os.getenv("NOTIFY_ON_STARTUP", "false").strip().lower()
        notify_on_startup = notify_startup_str in ("true", "1", "yes")

        notify_removal_str = os.getenv("NOTIFY_ON_REMOVAL", "false").strip().lower()
        notify_on_removal = notify_removal_str in ("true", "1", "yes")

        db_path = os.getenv("DATABASE_PATH", "data/crous_monitor.db").strip()
        email = os.getenv("CROUS_EMAIL", "").strip() or None
        password = os.getenv("CROUS_PASSWORD", "").strip() or None

        headless_str = os.getenv("HEADLESS", "true").strip().lower()
        headless = headless_str not in ("false", "0", "no")

        return cls(
            targets=targets,
            poll_interval_seconds=poll_interval,
            request_timeout_seconds=request_timeout,
            log_level=log_level,
            notify_on_startup=notify_on_startup,
            notify_on_removal=notify_on_removal,
            database_path=db_path,
            crous_email=email,
            crous_password=password,
            headless=headless,
        )

    def validate_for_monitoring(self) -> None:
        """Validate that all targets have valid search URLs and webhooks."""
        errors = []
        if not self.targets:
            errors.append("No monitor targets configured.")

        for target in self.targets:
            if not target.search_url or not target.search_url.startswith("http"):
                errors.append(f"Target '{target.name}' has invalid search URL: {target.search_url}")
            if not target.webhook_url or not target.webhook_url.startswith("https://discord.com/api/webhooks/"):
                errors.append(f"Target '{target.name}' missing valid Discord Webhook URL.")

        if errors:
            raise ValueError("Configuration Error:\n - " + "\n - ".join(errors))

    def validate_for_discord_only(self) -> None:
        """Validate that at least one webhook is configured for testing."""
        valid_webhooks = [t for t in self.targets if t.webhook_url.startswith("https://discord.com/api/webhooks/")]
        if not valid_webhooks:
            raise ValueError("No valid Discord Webhook URL found in configuration.")

    def validate_for_crous_only(self) -> None:
        """Validate that targets have search URLs."""
        valid_searches = [t for t in self.targets if t.search_url.startswith("http")]
        if not valid_searches:
            raise ValueError("No valid CROUS search URL configured.")

    def masked_webhook_url(self) -> str:
        """Mask all target webhook URLs."""
        return ", ".join(f"{t.name}: {t.masked_webhook_url()}" for t in self.targets)
