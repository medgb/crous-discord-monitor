"""HTTP Client for querying the CROUS Trouver un Logement API."""

import logging
import time
from typing import Dict, List, Optional, Tuple
import requests

from src.crous.models import Accommodation, SearchQuery
from src.crous.parser import parse_accommodation_item

logger = logging.getLogger(__name__)

CROUS_BASE_URL = "https://trouverunlogement.lescrous.fr"
PAGE_SIZE = 24


class CrousApiError(Exception):
    """Exception raised when CROUS API returns an error status or malformed response."""
    pass


class CrousNetworkError(Exception):
    """Exception raised when network or timeout errors occur contacting CROUS."""
    pass


class CrousClient:
    """Production client for querying CROUS housing availability."""

    def __init__(
        self,
        timeout_seconds: int = 30,
        max_retries: int = 3,
        session_cookies: Optional[Dict[str, str]] = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/json",
            "Origin": CROUS_BASE_URL,
        })
        if session_cookies:
            self.session.cookies.update(session_cookies)

    def _post_page(self, tool_id: int, payload: Dict, referer: str) -> Dict:
        """Send a single search page request with retry and backoff."""
        url = f"{CROUS_BASE_URL}/api/fr/search/{tool_id}"
        headers = {"Referer": referer or f"{CROUS_BASE_URL}/tools/{tool_id}/search"}

        last_err: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "Requesting CROUS API tool_id=%d page=%d (attempt %d/%d)",
                    tool_id, payload.get("page", 1), attempt, self.max_retries
                )
                response = self.session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning("CROUS rate limited (HTTP 429). Backing off for %ds...", retry_after)
                    time.sleep(retry_after)
                    continue

                if response.status_code >= 500:
                    logger.warning(
                        "CROUS server error (HTTP %d). Attempt %d/%d.",
                        response.status_code, attempt, self.max_retries
                    )
                    time.sleep(attempt * 2)
                    continue

                if response.status_code != 200:
                    logger.debug("Failed payload: %s", payload)
                    raise CrousApiError(
                        f"CROUS API HTTP {response.status_code}: {response.text[:300]}"
                    )

                try:
                    data = response.json()
                    return data
                except Exception as json_err:
                    raise CrousApiError(f"Malformed JSON response from CROUS: {json_err}") from json_err

            except requests.exceptions.RequestException as req_err:
                last_err = req_err
                logger.warning(
                    "Network error connecting to CROUS (attempt %d/%d): %s",
                    attempt, self.max_retries, req_err
                )
                time.sleep(attempt * 2)

        raise CrousNetworkError(
            f"Failed to reach CROUS API after {self.max_retries} attempts: {last_err}"
        )

    def fetch_all(self, query: SearchQuery) -> Tuple[List[Accommodation], int]:
        """
        Fetch all pages of matching accommodations for the given query.
        Returns (accommodations_list, total_count).
        """
        all_accommodations: List[Accommodation] = []
        page = 1
        total_count = 0
        seen_ids = set()

        while True:
            payload = query.to_api_payload(page=page, page_size=PAGE_SIZE)
            data = self._post_page(query.tool_id, payload, query.raw_url)

            results = data.get("results") or {}
            total_obj = results.get("total") or {}
            total_count = int(total_obj.get("value", 0)) if isinstance(total_obj, dict) else int(total_obj or 0)
            items = results.get("items") or []

            if not items:
                logger.debug("Page %d returned 0 items. Stopping pagination.", page)
                break

            for item in items:
                accommodation = parse_accommodation_item(item, query.tool_id)
                if accommodation and accommodation.id not in seen_ids:
                    seen_ids.add(accommodation.id)
                    all_accommodations.append(accommodation)

            logger.debug(
                "Page %d fetched %d items. Total collected: %d / %d",
                page, len(items), len(all_accommodations), total_count
            )

            # Stop condition: we collected all items or received a partial page
            if len(items) < PAGE_SIZE or len(all_accommodations) >= total_count:
                break

            page += 1

        logger.info(
            "CROUS fetch completed. Found %d available accommodations (total reported: %d).",
            len(all_accommodations), total_count
        )
        return all_accommodations, total_count
