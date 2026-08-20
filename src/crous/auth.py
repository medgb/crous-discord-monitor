"""Session and authentication manager for CROUS and MesServices Étudiant."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

SESSION_FILE_PATH = Path("data/storage_state.json")
MSE_LOGIN_URL = "https://trouverunlogement.lescrous.fr/mse/discovery/connect"


class AuthManager:
    """Manages persistent browser and HTTP session cookies."""

    def __init__(self, session_path: Optional[Path] = None):
        self.session_path = session_path or SESSION_FILE_PATH

    def load_session_cookies(self) -> Dict[str, str]:
        """Load cookies from persisted storage state for HTTP requests."""
        if not self.session_path.exists():
            return {}

        try:
            with open(self.session_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            cookies: Dict[str, str] = {}
            # Handle Playwright storage_state format
            if isinstance(data, dict) and "cookies" in data:
                for c in data["cookies"]:
                    if isinstance(c, dict) and "name" in c and "value" in c:
                        cookies[c["name"]] = c["value"]
            # Handle simple key-value format
            elif isinstance(data, dict):
                cookies = {str(k): str(v) for k, v in data.items()}

            logger.debug("Loaded %d session cookies from %s", len(cookies), self.session_path)
            return cookies
        except Exception as e:
            logger.warning("Failed to load session cookies from %s: %s", self.session_path, e)
            return {}

    def save_session_cookies(self, cookies: Dict[str, str]) -> None:
        """Save cookies to session file."""
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.session_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
        logger.info("Saved %d session cookies to %s", len(cookies), self.session_path)

    def interactive_login(self, headless: bool = False) -> bool:
        """
        Open a browser window using Playwright so the user can log in manually (MFA/CAPTCHA),
        and persist the resulting authenticated storage state.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error(
                "Playwright is not installed. To use interactive login, install Playwright: "
                "pip install playwright && playwright install chromium"
            )
            return False

        logger.info("Starting interactive browser session for CROUS / MesServices login...")
        print("\n=======================================================")
        print("Please log in to your CROUS account in the opened browser window.")
        print("Complete any 2FA / CAPTCHA if prompted.")
        print("Once you are logged in and see the housing portal, close the browser or press ENTER.")
        print("=======================================================\n")

        self.session_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=headless)
                context = browser.new_context()
                page = context.new_page()
                page.goto(MSE_LOGIN_URL, timeout=60000)

                # Wait for user to complete login
                input("Press ENTER in this console once you have finished logging in...")

                # Save authenticated storage state
                context.storage_state(path=str(self.session_path))
                browser.close()

            logger.info("Authentication session successfully saved to %s!", self.session_path)
            return True
        except Exception as e:
            logger.error("Interactive login failed: %s", e)
            return False
