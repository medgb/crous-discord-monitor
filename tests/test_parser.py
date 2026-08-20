"""Unit tests for URL and API response parsing."""

from src.crous.parser import (
    calculate_precision,
    extract_city_from_address,
    parse_accommodation_item,
    parse_search_url,
)


def test_parse_search_url_default():
    url = "https://trouverunlogement.lescrous.fr/tools/42/search"
    query = parse_search_url(url)
    assert query.tool_id == 42
    assert query.max_price_cents is None
    assert query.min_area is None
    assert query.adapted_pmr is False
    assert len(query.occupation_modes) == 0


def test_parse_search_url_with_parameters():
    url = (
        "https://trouverunlogement.lescrous.fr/tools/47/search"
        "?bounds=4.9452443_45.2443315_6.2866978_45.8679317"
        "&maxPrice=450"
        "&minArea=15"
        "&occupationModes=alone"
        "&accessibility=prm"
    )
    query = parse_search_url(url)
    assert query.tool_id == 47
    assert query.max_price_cents == 45000  # 450 * 100
    assert query.min_area == 15.0
    assert query.adapted_pmr is True
    assert query.occupation_modes == ["alone"]
    # Verify coordinate normalization: top_left_lat >= bottom_right_lat
    assert query.top_left_lat > query.bottom_right_lat
    assert query.top_left_lon < query.bottom_right_lon


def test_precision_calculation():
    # Whole France bounds
    bounds_france = [-9.9079, 51.7087, 14.3224, 40.5721]
    prec = calculate_precision(bounds_france)
    assert prec >= 1

    # Small city bounds
    bounds_city = [5.6, 45.3, 5.8, 45.1]
    prec_city = calculate_precision(bounds_city)
    assert prec_city >= prec


def test_extract_city_from_address():
    assert extract_city_from_address("22 avenue Jean Nicoli, BP 55, 20250 CORTE") == "CORTE"
    assert extract_city_from_address("15 Rue de l'Université, 38000 GRENOBLE") == "GRENOBLE"
    assert extract_city_from_address("10 Rue Berlioz, 75005 PARIS CEDEX 05") == "PARIS CEDEX 05"
    assert extract_city_from_address("") == "France"


def test_parse_accommodation_item_valid(sample_crous_item_raw):
    acc = parse_accommodation_item(sample_crous_item_raw, tool_id=42)
    assert acc is not None
    assert acc.id == 718
    assert acc.tool_id == 42
    assert acc.residence_name == "Residence Christophe GARELLI"
    assert acc.city == "CORTE"
    assert acc.accommodation_type == "G023 STUDIO"
    assert acc.surface_min == 16.0
    assert acc.surface_max == 18.0
    assert acc.price_eur == 394.0
    assert acc.url == "https://trouverunlogement.lescrous.fr/tools/42/accommodations/718"
    assert acc.available is True
    assert acc.adapted_pmr is False
    assert acc.low_stock is True
    assert "Dernières places" in acc.labels
    assert acc.surface_display == "16 - 18 m²"
    assert acc.price_display == "394 € / mois"


def test_parse_accommodation_item_pmr(sample_crous_item_pmr):
    acc = parse_accommodation_item(sample_crous_item_pmr, tool_id=47)
    assert acc is not None
    assert acc.id == 516
    assert acc.tool_id == 47
    assert acc.residence_name == "LE VELUM"
    assert acc.city == "GRENOBLE"
    assert acc.accommodation_type == "T1BIS PMR"
    assert acc.surface_min == 24.5
    assert acc.surface_max == 24.5
    assert acc.surface_display == "24.5 m²"
    assert acc.price_eur == 493.20
    assert acc.price_display == "493.20 € / mois"
    assert acc.adapted_pmr is True
    assert "Accessible PMR" in acc.labels


def test_parse_accommodation_item_missing_id():
    bad_item = {"label": "Mystery Room"}
    acc = parse_accommodation_item(bad_item, tool_id=42)
    assert acc is None
