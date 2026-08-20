"""Normalized data models for CROUS accommodations and queries."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Accommodation:
    """Normalized CROUS accommodation offer."""
    id: int
    tool_id: int
    residence_name: str
    address: str
    city: str
    accommodation_type: str
    price_eur: float
    url: str
    available: bool = True
    surface_min: Optional[float] = None
    surface_max: Optional[float] = None
    adapted_pmr: bool = False
    high_demand: bool = False
    low_stock: bool = False
    labels: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def surface_display(self) -> str:
        """Formatted surface string."""
        if self.surface_min is not None and self.surface_max is not None:
            if abs(self.surface_min - self.surface_max) < 0.1:
                return f"{int(self.surface_min) if self.surface_min.is_integer() else self.surface_min} m²"
            min_str = int(self.surface_min) if self.surface_min.is_integer() else self.surface_min
            max_str = int(self.surface_max) if self.surface_max.is_integer() else self.surface_max
            return f"{min_str} - {max_str} m²"
        elif self.surface_min is not None:
            min_str = int(self.surface_min) if self.surface_min.is_integer() else self.surface_min
            return f"≥ {min_str} m²"
        return "Non spécifiée"

    @property
    def price_display(self) -> str:
        """Formatted price string in Euros."""
        if self.price_eur > 0:
            if self.price_eur.is_integer():
                return f"{int(self.price_eur)} € / mois"
            return f"{self.price_eur:.2f} € / mois"
        return "Prix non communiqué"

    def summary(self) -> str:
        """Short readable summary of the accommodation."""
        return (
            f"[#{self.id}] {self.residence_name} ({self.city}) | "
            f"{self.accommodation_type} | {self.surface_display} | {self.price_display}"
        )


@dataclass
class SearchQuery:
    """Parsed and normalized CROUS search parameters."""
    tool_id: int
    top_left_lon: float
    top_left_lat: float
    bottom_right_lon: float
    bottom_right_lat: float
    precision: int = 4
    max_price_cents: Optional[int] = None
    min_area: Optional[float] = None
    occupation_modes: List[str] = field(default_factory=list)
    equipments: List[str] = field(default_factory=list)
    adapted_pmr: bool = False
    raw_url: str = ""

    def to_api_payload(self, page: int = 1, page_size: int = 24) -> Dict[str, Any]:
        """Generate the JSON payload expected by the CROUS search API."""
        payload: Dict[str, Any] = {
            "need_aggregation": False,
            "page": page,
            "pageSize": page_size,
            "occupationModes": self.occupation_modes,
            "location": [
                {"lon": self.top_left_lon, "lat": self.top_left_lat},
                {"lon": self.bottom_right_lon, "lat": self.bottom_right_lat}
            ],
            "precision": self.precision,
            "equipment": self.equipments,
            "price": {"max": self.max_price_cents if self.max_price_cents is not None else 10000000},
            "area": {"min": self.min_area if self.min_area is not None else 0},
            "adaptedPmr": self.adapted_pmr
        }
        return payload
