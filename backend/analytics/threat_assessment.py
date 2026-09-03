"""
Tactical Threat Assessment and Trajectory Prediction Engine
Section 5.4: Tactical Threat Assessment and Trajectory Prediction

1. Linear Vector Extrapolation: Simultaneous pairwise Closest Point of Approach (CPA)
   and Time to CPA (TCPA) for all active tracks in the airspace.
2. Automated Separation Alerting: Loss of standard civil/military separation thresholds
   (< 5 NM horizontal, < 1000 ft vertical).
3. Perimeter Defense & Geofencing: Detects immediate encroachment into restricted
   flight zones (Birsa Munda Airport VERC CTR and Mesra Ground Station Security Perimeter).
"""

import math
from typing import List, Dict, Any, Tuple
from ..config import DefenseThresholds, GroundStationConfig

class ThreatAssessmentEngine:
    """Computes pairwise CPA/TCPA, separation conflicts, and geofence alerts."""
    
    def __init__(self, thresholds: Optional[DefenseThresholds] = None):
        self.thresholds = thresholds or DefenseThresholds()
        self.NM_TO_KM = 1.852
        self.KM_TO_NM = 1.0 / 1.852
        
    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculates great-circle distance between two geodetic coordinates in km."""
        r = GroundStationConfig.EARTH_RADIUS_KM
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = math.sin(dphi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0)**2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return r * c

    def point_in_polygon(self, lat: float, lon: float, polygon: Tuple[Tuple[float, float], ...]) -> bool:
        """Ray-casting algorithm to determine if a point is inside a polygon boundary."""
        inside = False
        n = len(polygon)
        j = n - 1
        for i in range(n):
            lat_i, lon_i = polygon[i]
            lat_j, lon_j = polygon[j]
            if ((lat_i > lat) != (lat_j > lat)) and (lon < (lon_j - lon_i) * (lat - lat_i) / (lat_j - lat_i) + lon_i):
                inside = not inside
            j = i
        return inside

    def compute_cpa_tcpa(self, ac1: Dict[str, Any], ac2: Dict[str, Any]) -> Tuple[float, float, float]:
        """
        Calculates Closest Point of Approach (CPA in NM), Time to CPA (TCPA in sec),
        and vertical separation at CPA (ft) using relative velocity vectors.
        """
        lat1, lon1 = ac1.get("lat"), ac1.get("lon")
        lat2, lon2 = ac2.get("lat"), ac2.get("lon")
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            return 999.0, -1.0, 99999.0
            
        # Current distance
        dist_km = self.haversine_km(lat1, lon1, lat2, lon2)
        dist_nm = dist_km * self.KM_TO_NM
        alt_diff_ft = abs(ac1.get("alt_baro", 0.0) - ac2.get("alt_baro", 0.0))
        
        # Heading & ground speeds
        spd1_ms = ac1.get("speed", 0.0) * 0.514444
        spd2_ms = ac2.get("speed", 0.0) * 0.514444
        trk1_rad = math.radians(ac1.get("track", 0.0))
        trk2_rad = math.radians(ac2.get("track", 0.0))
        
        # Velocity vectors (m/s) in East-North
        v1x, v1y = spd1_ms * math.sin(trk1_rad), spd1_ms * math.cos(trk1_rad)
        v2x, v2y = spd2_ms * math.sin(trk2_rad), spd2_ms * math.cos(trk2_rad)
        
        # Relative position vector r = p2 - p1 (approximate local flat Earth)
        r_earth = GroundStationConfig.EARTH_RADIUS_KM * 1000.0
        rx = math.radians(lon2 - lon1) * r_earth * math.cos(math.radians((lat1 + lat2) / 2.0))
        ry = math.radians(lat2 - lat1) * r_earth
        
        # Relative velocity vector v = v2 - v1
        vx = v2x - v1x
        vy = v2y - v1y
        v_rel_sq = vx * vx + vy * vy
        
        if v_rel_sq < 1e-4:
            # Parallel or hovering tracks
            return dist_nm, 0.0, alt_diff_ft
            
        # Time to CPA: t = - (r . v) / (v . v)
        tcpa_sec = - (rx * vx + ry * vy) / v_rel_sq
        
        if tcpa_sec < 0:
            # Diverging tracks (past CPA)
            cpa_nm = dist_nm
            tcpa_sec = 0.0
        else:
            # Predicted minimum distance
            r_cpa_x = rx + vx * tcpa_sec
            r_cpa_y = ry + vy * tcpa_sec
            cpa_dist_m = math.sqrt(r_cpa_x * r_cpa_x + r_cpa_y * r_cpa_y)
            cpa_nm = (cpa_dist_m / 1000.0) * self.KM_TO_NM
            
        # Vertical rate projection
        vr1_fps = ac1.get("vert_rate", 0.0) / 60.0
        vr2_fps = ac2.get("vert_rate", 0.0) / 60.0
        alt_cpa_diff_ft = abs((ac1.get("alt_baro", 0.0) + vr1_fps * tcpa_sec) -
                              (ac2.get("alt_baro", 0.0) + vr2_fps * tcpa_sec))
                              
        return cpa_nm, tcpa_sec, alt_cpa_diff_ft

    def assess_airspace(self, aircraft_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Performs exhaustive tactical threat assessment across all active air targets."""
        alerts: List[Dict[str, Any]] = []
        geofence_violations: List[Dict[str, Any]] = []
        n = len(aircraft_list)
        
        # 1. Geofence checks
        for ac in aircraft_list:
            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None:
                continue
                
            hex_id = ac.get("hex", "UNKNOWN")
            flight = ac.get("flight", "UNKNOWN")
            
            # Check Mesra Ground Station Perimeter (< 5 km)
            dist_to_mesra_km = self.haversine_km(
                lat, lon, GroundStationConfig.LATITUDE, GroundStationConfig.LONGITUDE
            )
            if dist_to_mesra_km <= self.thresholds.MESRA_SECURITY_RADIUS_KM:
                geofence_violations.append({
                    "type": "PERIMETER_ENCROACHMENT",
                    "zone": "MESRA-BASE-5KM",
                    "hex": hex_id,
                    "flight": flight,
                    "dist_km": round(dist_to_mesra_km, 2),
                    "alt_ft": ac.get("alt_baro", 0),
                    "severity": "CRITICAL" if dist_to_mesra_km < 2.0 else "WARNING"
                })
                
            # Check Ranchi VERC CTR airspace
            if self.point_in_polygon(lat, lon, self.thresholds.VERC_CTR_BOUNDS):
                geofence_violations.append({
                    "type": "RESTRICTED_AIRSPACE",
                    "zone": "RANCHI-VERC-CTR",
                    "hex": hex_id,
                    "flight": flight,
                    "alt_ft": ac.get("alt_baro", 0),
                    "severity": "WARNING"
                })
                
        # 2. Pairwise CPA / TCPA and Separation checks
        conflict_pairs = []
        for i in range(n):
            for j in range(i + 1, n):
                ac1 = aircraft_list[i]
                ac2 = aircraft_list[j]
                
                cpa_nm, tcpa_sec, alt_cpa_ft = self.compute_cpa_tcpa(ac1, ac2)
                
                # Check current separation
                lat1, lon1 = ac1.get("lat"), ac1.get("lon")
                lat2, lon2 = ac2.get("lat"), ac2.get("lon")
                if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
                    continue
                    
                cur_dist_nm = self.haversine_km(lat1, lon1, lat2, lon2) * self.KM_TO_NM
                cur_alt_diff = abs(ac1.get("alt_baro", 0.0) - ac2.get("alt_baro", 0.0))
                
                # Separation violation condition: Horiz < 5 NM AND Vert < 1000 ft
                is_current_violation = (cur_dist_nm < self.thresholds.MIN_HORIZONTAL_SEPARATION_NM and 
                                        cur_alt_diff < self.thresholds.MIN_VERTICAL_SEPARATION_FT)
                                        
                is_predicted_conflict = (cpa_nm < self.thresholds.MIN_HORIZONTAL_SEPARATION_NM and 
                                         alt_cpa_ft < self.thresholds.MIN_VERTICAL_SEPARATION_FT and 
                                         0 < tcpa_sec <= self.thresholds.CPA_LOOKAHEAD_SECONDS)
                                         
                if is_current_violation or is_predicted_conflict:
                    severity = "CRITICAL_CONFLICT" if is_current_violation else "WARNING_APPROACHING"
                    conflict_pairs.append({
                        "ac1_hex": ac1.get("hex"),
                        "ac1_flight": ac1.get("flight"),
                        "ac2_hex": ac2.get("hex"),
                        "ac2_flight": ac2.get("flight"),
                        "current_dist_nm": round(cur_dist_nm, 2),
                        "current_alt_diff_ft": round(cur_alt_diff, 0),
                        "cpa_nm": round(cpa_nm, 2),
                        "tcpa_sec": round(tcpa_sec, 1),
                        "cpa_alt_diff_ft": round(alt_cpa_ft, 0),
                        "severity": severity
                    })
                    
        return {
            "total_tracks": n,
            "conflicts_count": len(conflict_pairs),
            "conflicts": conflict_pairs,
            "geofence_violations_count": len(geofence_violations),
            "geofence_violations": geofence_violations
        }
