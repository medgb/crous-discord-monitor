"""Parser and URL normalizer for CROUS search requests and responses."""

import math
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from src.crous.models import Accommodation, SearchQuery

DEFAULT_TOOL_ID = 42
DEFAULT_FRANCE_BOUNDS = [-9.9079, 51.7087, 14.3224, 40.5721]  # [top_left_lon, top_left_lat, bottom_right_lon, bottom_right_lat]


class GeoPoint:
    """Helper for geographical distance computation matching CROUS frontend."""

    def __init__(self, lat: float, lon: float):
        self.lat = float(lat)
        self.lon = float(lon)
        self.rad_lat = math.radians(self.lat)
        self.rad_lon = math.radians(self.lon)

    def distance_to(self, other: "GeoPoint") -> float:
        """Great-circle distance in kilometers."""
        earth_radius_km = 6371.01
        try:
            val = (
                math.sin(self.rad_lat) * math.sin(other.rad_lat)
                + math.cos(self.rad_lat) * math.cos(other.rad_lat) * math.cos(self.rad_lon - other.rad_lon)
            )
            # Clamp to [-1, 1] to prevent floating point domain errors in acos
            val = max(-1.0, min(1.0, val))
            return math.acos(val) * earth_radius_km
        except Exception:
            return 0.0


def calculate_precision(bounds: List[float], threshold: int = 4) -> int:
    """
    Calculate grid precision integer based on bounding box extent.
    Capped at 4 as required by CROUS search backend API.
    """
    try:
        p1 = GeoPoint(lat=bounds[1], lon=bounds[0])
        p2 = GeoPoint(lat=bounds[3], lon=bounds[0])
        dist_m = p1.distance_to(p2) * 1000.0
        table = [
            (5003530, 1),
            (625441, 2),
            (123264, 3),
            (19545, 4),
        ]
        for dist_thresh, prec in table:
            if dist_m / dist_thresh >= threshold:
                return min(4, prec)
    except Exception:
        pass
    return 4


def extract_city_from_address(address: str) -> str:
    """Extract French city name from standard postal addresses (e.g. '20250 CORTE')."""
    if not address:
        return "France"
    # Match 5-digit postal code followed by city name (e.g. "38000 GRENOBLE" or "75005 PARIS CEDEX 05")
    match = re.search(r'\b\d{5}\s+([A-Za-zÀ-ÿ\s\-\'\d]+?)(?:,|$)', address)
    if match:
        city_str = match.group(1).strip()
        # Clean up any leftover punctuation
        return city_str
    # Fallback to the last comma-separated part without digits
    parts = address.split(",")
    if len(parts) > 1:
        last_part = re.sub(r'^\s*\d{5}\s*', '', parts[-1]).strip()
        if last_part:
            return last_part
    return address.strip()


def parse_search_url(url_str: str) -> SearchQuery:
    """
    Parse a user-supplied CROUS search URL into a normalized SearchQuery object.
    
    Example input:
    https://trouverunlogement.lescrous.fr/tools/42/search?bounds=4.9452443_45.2443315_6.2866978_45.8679317&maxPrice=500
    """
    parsed = urllib.parse.urlparse(url_str.strip())

    # Extract tool_id from URL path (e.g. /tools/42/search -> 42)
    tool_match = re.search(r'/tools/(\d+)/search', parsed.path)
    tool_id = int(tool_match.group(1)) if tool_match else DEFAULT_TOOL_ID

    params = urllib.parse.parse_qs(parsed.query)

    # Parse coordinates bounds
    bounds = DEFAULT_FRANCE_BOUNDS
    if "bounds" in params and params["bounds"]:
        try:
            parts = [float(x) for x in params["bounds"][0].split("_")]
            if len(parts) == 4:
                bounds = parts
        except (ValueError, IndexError):
            pass

    # Ensure top-left (min_lon, max_lat) and bottom-right (max_lon, min_lat)
    top_left_lon = min(bounds[0], bounds[2])
    top_left_lat = max(bounds[1], bounds[3])
    bottom_right_lon = max(bounds[0], bounds[2])
    bottom_right_lat = min(bounds[1], bounds[3])

    normalized_bounds = [top_left_lon, top_left_lat, bottom_right_lon, bottom_right_lat]
    precision = calculate_precision(normalized_bounds)

    # Parse maxPrice (converted to cents)
    max_price_cents = None
    if "maxPrice" in params and params["maxPrice"]:
        try:
            max_price_cents = int(float(params["maxPrice"][0])) * 100
        except ValueError:
            pass

    # Parse minArea
    min_area = None
    if "minArea" in params and params["minArea"]:
        try:
            min_area = float(params["minArea"][0])
        except ValueError:
            pass

    # Parse multi-value filters
    occupation_modes = params.get("occupationModes", [])
    equipments = params.get("equipments", [])
    adapted_pmr = "prm" in params.get("accessibility", [])

    return SearchQuery(
        tool_id=tool_id,
        top_left_lon=top_left_lon,
        top_left_lat=top_left_lat,
        bottom_right_lon=bottom_right_lon,
        bottom_right_lat=bottom_right_lat,
        precision=precision,
        max_price_cents=max_price_cents,
        min_area=min_area,
        occupation_modes=occupation_modes,
        equipments=equipments,
        adapted_pmr=adapted_pmr,
        raw_url=url_str,
    )


def parse_accommodation_item(item: Dict[str, Any], tool_id: int) -> Optional[Accommodation]:
    """
    Transform a raw item dict from the CROUS API results into a normalized Accommodation model.
    """
    try:
        raw_id = item.get("id")
        if raw_id is None:
            return None
        room_id = int(raw_id)

        residence = item.get("residence") or {}
        residence_name = (residence.get("label") or "Résidence CROUS").strip()
        address = (residence.get("address") or "").strip()
        city = extract_city_from_address(address)
        if not city and residence.get("entity", {}).get("name"):
            city = str(residence["entity"]["name"]).strip()

        accommodation_type = (item.get("label") or "Logement CROUS").strip()

        # Surface
        area = item.get("area") or {}
        surface_min = float(area["min"]) if area.get("min") is not None else None
        surface_max = float(area["max"]) if area.get("max") is not None else None

        # Price / Monthly Rent
        price_eur = 0.0
        occupation_modes = item.get("occupationModes") or []
        if occupation_modes and isinstance(occupation_modes, list):
            first_mode = occupation_modes[0]
            rent_obj = first_mode.get("rent") or {}
            min_rent_cents = rent_obj.get("min")
            if min_rent_cents is not None:
                price_eur = float(min_rent_cents) / 100.0

        available = bool(item.get("available", True))
        adapted_pmr = bool(item.get("adaptedPmr", False))
        high_demand = bool(item.get("highDemand", False))
        low_stock = bool(item.get("lowStock", False))

        labels: List[str] = []
        if adapted_pmr:
            labels.append("Accessible PMR")
        if low_stock:
            labels.append("Dernières places")
        if high_demand:
            labels.append("Forte demande")

        direct_url = f"https://trouverunlogement.lescrous.fr/tools/{tool_id}/accommodations/{room_id}"

        return Accommodation(
            id=room_id,
            tool_id=tool_id,
            residence_name=residence_name,
            address=address,
            city=city or "France",
            accommodation_type=accommodation_type,
            surface_min=surface_min,
            surface_max=surface_max,
            price_eur=price_eur,
            url=direct_url,
            available=available,
            adapted_pmr=adapted_pmr,
            high_demand=high_demand,
            low_stock=low_stock,
            labels=labels,
            raw_data=item,
        )
    except Exception:
        return None
