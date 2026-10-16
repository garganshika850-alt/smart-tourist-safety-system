# ============================================================
# Smart Tourist Safety and Emergency Response System
# Geofencing & Spatial Calculation Utilities
# ============================================================

import math
from typing import Any, Dict, List, Optional, Tuple

EARTH_RADIUS_KM = 6371.0

# Priority mapping for risk evaluation
RISK_LEVEL_PRIORITY = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}

def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes the great-circle distance between two geographic coordinates
    on Earth using the Haversine formula. Returns distance in kilometers.
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
    )
    # Ensure numerical stability against rounding errors exceeding 1.0
    c = 2.0 * math.atan2(math.sqrt(min(1.0, a)), math.sqrt(max(0.0, 1.0 - a)))

    return round(EARTH_RADIUS_KM * c, 4)

def is_point_in_zone(lat: float, lon: float, zone: Dict[str, Any]) -> Tuple[bool, float]:
    """
    Determines whether a coordinate point falls within a circular zone geofence.
    Returns (is_inside, distance_km).
    """
    center_lat = float(zone["center_lat"])
    center_lng = float(zone["center_lng"])
    radius_km = float(zone["radius_km"])

    dist_km = haversine_distance_km(lat, lon, center_lat, center_lng)
    return (dist_km <= radius_km), dist_km

def detect_primary_zone(
    lat: float, 
    lon: float, 
    zones: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Evaluates coordinates against a list of active zones.
    If the point falls inside one or more zones:
      - Prioritizes 'DANGEROUS' over 'SAFE' zones.
      - Within dangerous zones, prioritizes higher risk levels (CRITICAL > HIGH > MEDIUM > LOW).
      - If tied, chooses the closest zone centroid.
    Returns the primary matched zone with an added 'distance_km' attribute, or None.
    """
    matched_zones = []

    for z in zones:
        inside, dist = is_point_in_zone(lat, lon, z)
        if inside:
            z_copy = dict(z)
            z_copy["distance_km"] = dist
            matched_zones.append(z_copy)

    if not matched_zones:
        return None

    # Sorting key:
    # 1. Zone type: 'DANGEROUS' (0) before 'SAFE' (1)
    # 2. Risk level: -priority (so CRITICAL (-4) comes before HIGH (-3))
    # 3. Distance from center: smallest first
    def sort_key(zone: Dict[str, Any]):
        zone_type_order = 0 if zone.get("zone_type") == "DANGEROUS" else 1
        risk_score = RISK_LEVEL_PRIORITY.get(zone.get("risk_level", "LOW"), 0)
        return (zone_type_order, -risk_score, zone.get("distance_km", 0.0))

    matched_zones.sort(key=sort_key)
    return matched_zones[0]
