"""Shared pytest fixtures and mock CROUS data."""

import pytest
from typing import Any, Dict, List
from src.crous.models import Accommodation
from src.storage.database import Database


@pytest.fixture
def sample_crous_item_raw() -> Dict[str, Any]:
    """Sample raw CROUS API item representing a studio in Corte."""
    return {
        "id": 718,
        "code": 8,
        "reference": "2",
        "bedroomCount": 1,
        "label": "G023 STUDIO",
        "residence": {
            "id": "4f7afc7f-1227-11e8-89ed-005056940822",
            "label": "Residence Christophe GARELLI",
            "address": "22 avenue Jean Nicoli, BP 55, 20250 CORTE",
            "code": 5,
            "entity": {"name": "Corse", "id": 12},
            "location": {"lon": 9.152, "lat": 42.299}
        },
        "area": {"min": 16.0, "max": 18.0},
        "adaptedPmr": False,
        "highDemand": False,
        "lowStock": True,
        "available": True,
        "occupationModes": [
            {
                "type": "alone",
                "rent": {"min": 39400, "max": 39400}
            }
        ]
    }


@pytest.fixture
def sample_crous_item_pmr() -> Dict[str, Any]:
    """Sample raw CROUS API item representing a PMR room."""
    return {
        "id": 516,
        "code": 12,
        "label": "T1BIS PMR",
        "residence": {
            "id": "res-516",
            "label": "LE VELUM",
            "address": "15 Rue de l'Université, 38000 GRENOBLE",
            "entity": {"name": "Grenoble", "id": 8},
        },
        "area": {"min": 24.5, "max": 24.5},
        "adaptedPmr": True,
        "highDemand": True,
        "lowStock": False,
        "available": True,
        "occupationModes": [
            {
                "type": "alone",
                "rent": {"min": 49320, "max": 49320}
            }
        ]
    }


@pytest.fixture
def sample_accommodation_1() -> Accommodation:
    """Pre-parsed Accommodation instance 1."""
    return Accommodation(
        id=718,
        tool_id=42,
        residence_name="Residence Christophe GARELLI",
        address="22 avenue Jean Nicoli, 20250 CORTE",
        city="CORTE",
        accommodation_type="G023 STUDIO",
        surface_min=16.0,
        surface_max=18.0,
        price_eur=394.0,
        url="https://trouverunlogement.lescrous.fr/tools/42/accommodations/718",
        available=True,
        adapted_pmr=False,
        low_stock=True,
        labels=["Dernières places"],
    )


@pytest.fixture
def sample_accommodation_2() -> Accommodation:
    """Pre-parsed Accommodation instance 2."""
    return Accommodation(
        id=516,
        tool_id=42,
        residence_name="LE VELUM",
        address="15 Rue de l'Université, 38000 GRENOBLE",
        city="GRENOBLE",
        accommodation_type="T1BIS PMR",
        surface_min=24.5,
        surface_max=24.5,
        price_eur=493.20,
        url="https://trouverunlogement.lescrous.fr/tools/42/accommodations/516",
        available=True,
        adapted_pmr=True,
    )


@pytest.fixture
def sample_accommodation_3() -> Accommodation:
    """Pre-parsed Accommodation instance 3."""
    return Accommodation(
        id=999,
        tool_id=42,
        residence_name="Résidence Berlioz",
        address="10 Rue Berlioz, 38400 SAINT-MARTIN-D'HERES",
        city="SAINT-MARTIN-D'HERES",
        accommodation_type="Chambre Individuelle",
        surface_min=10.0,
        surface_max=12.0,
        price_eur=250.0,
        url="https://trouverunlogement.lescrous.fr/tools/42/accommodations/999",
        available=True,
    )


@pytest.fixture
def temp_db(tmp_path) -> Database:
    """Provide a fresh SQLite database instance in temporary directory."""
    db_file = tmp_path / "test_monitor.db"
    return Database(str(db_file))
