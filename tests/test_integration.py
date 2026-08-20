"""Live integration test against the real CROUS Trouver un Logement API."""

import pytest
from src.crous.client import CrousClient
from src.crous.parser import parse_search_url


@pytest.mark.integration
def test_live_crous_api_search():
    """Verify that the parser and client successfully fetch live results from CROUS."""
    search_url = "https://trouverunlogement.lescrous.fr/tools/47/search"
    query = parse_search_url(search_url)

    client = CrousClient(timeout_seconds=20)
    items, total = client.fetch_all(query)

    assert total > 0, "Live CROUS website should report available rooms across France"
    assert len(items) > 0, "Should retrieve at least one page of live items"
    assert all(it.id > 0 for it in items), "All items must have valid IDs"
    assert all(it.url.startswith("https://trouverunlogement.lescrous.fr/tools/47/accommodations/") for it in items)
