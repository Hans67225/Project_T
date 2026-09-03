"""
Kinematic Anomaly and Spoofing Detection Pipeline
Section 5.1: High-Impact Software Enhancements (Defense-Grade Integration)

Guards against synthetic unauthenticated Mode-S injection (e.g., HackRF SDRs)
by enforcing continuous rigid-body physics validation:
1. Sequential State Vector Tracking: x_t = [x, y, z, vx, vy, vz]^T
2. Kinematic Differentiation: Acceleration a = dv/dt, Jerk j = da/dt
3. Threshold Gating: flags lateral acceleration > 30 m/s^2 or vertical climb > 6g
4. Atmospheric Pressure Validation: compares GPS geometric altitude vs barometric altitude (QNH divergence)
5. Automated Quarantine Layer
"""

import math
import time
from typing import Dict, Any, Optional, List, Tuple
from ..config import DefenseThresholds, GroundStationConfig

class KinematicStateTracker:
    """Maintains state history and calculates kinematic derivatives per aircraft."""
    
    def __init__(self, thresholds: Optional[DefenseThresholds] = None):
        self.thresholds = thresholds or DefenseThresholds()
        # History map: hex -> list of previous samples: (timestamp, x, y, z, vx, vy, vz, a, j, alt_geom, alt_baro)
        self.history: Dict[str, List[Dict[str, Any]]] = {}
        # Quarantined tracks map: hex -> reason
        self.quarantined_tracks: Dict[str, Dict[str, Any]] = {}
        
    @staticmethod
    def geodetic_to_enu(lat: float, lon: float, alt_m: float, ref_lat: float, ref_lon: float, ref_alt_m: float) -> Tuple[float, float, float]:
        """
        Converts geodetic (lat, lon, alt) to localized Cartesian East-North-Up (ENU) coordinates
        relative to the ground station (BIT Mesra).
        """
        r_earth = GroundStationConfig.EARTH_RADIUS_KM * 1000.0
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        ref_lat_rad = math.radians(ref_lat)
        ref_lon_rad = math.radians(ref_lon)
        
        # Spherical local tangent plane projection
        d_lat = lat_rad - ref_lat_rad
        d_lon = lon_rad - ref_lon_rad
        
        north = d_lat * r_earth
        east = d_lon * r_earth * math.cos(ref_lat_rad)
        up = alt_m - ref_alt_m
        return (east, north, up)

    def process_telemetry(self, aircraft: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates incoming ADS-B packet against rigid-body kinematics and atmospheric physics.
        Returns the aircraft state enriched with derivatives and validation verdicts.
        """
        hex_id = aircraft.get("hex", "UNKNOWN").upper()
        now = time.time()
        
        lat = aircraft.get("lat")
        lon = aircraft.get("lon")
        alt_baro = aircraft.get("alt_baro", 0.0) # ft
        alt_geom = aircraft.get("alt_geom", alt_baro) # ft
        speed_kts = aircraft.get("speed", 0.0) # knots
        track_deg = aircraft.get("track", 0.0) # degrees
        vert_rate_fpm = aircraft.get("vert_rate", 0.0) # ft/min
        
        if lat is None or lon is None:
            return {
                **aircraft,
                "kinematics": {"status": "UNVALIDATED", "reason": "Missing coordinate telemetry"}
            }
            
        alt_geom_m = alt_geom * 0.3048
        alt_baro_m = alt_baro * 0.3048
        
        # Convert to local ENU Cartesian coordinates centered at Mesra Ground Station
        east, north, up = self.geodetic_to_enu(
            lat, lon, alt_geom_m,
            GroundStationConfig.LATITUDE, GroundStationConfig.LONGITUDE, GroundStationConfig.ALTITUDE_M
        )
        
        # Velocity components from speed (knots to m/s), track, and vertical rate (fpm to m/s)
        speed_ms = speed_kts * 0.514444
        track_rad = math.radians(track_deg)
        vx = speed_ms * math.sin(track_rad) # East
        vy = speed_ms * math.cos(track_rad) # North
        vz = vert_rate_fpm * 0.00508        # Up
        
        current_sample = {
            "time": now,
            "x": east, "y": north, "z": up,
            "vx": vx, "vy": vy, "vz": vz,
            "ax": 0.0, "ay": 0.0, "az": 0.0,
            "accel_total": 0.0,
            "jerk_total": 0.0,
            "alt_geom_ft": alt_geom,
            "alt_baro_ft": alt_baro
        }
        
        # Check history
        history_list = self.history.setdefault(hex_id, [])
        anomalies: List[str] = []
        is_spoofed = False
        
        if history_list:
            prev = history_list[-1]
            dt = max(now - prev["time"], 0.1)
            
            # Kinematic differentiation
            ax = (vx - prev["vx"]) / dt
            ay = (vy - prev["vy"]) / dt
            az = (vz - prev["vz"]) / dt
            accel_lateral = math.sqrt(ax * ax + ay * ay)
            accel_total = math.sqrt(ax * ax + ay * ay + az * az)
            
            current_sample["ax"] = ax
            current_sample["ay"] = ay
            current_sample["az"] = az
            current_sample["accel_total"] = accel_total
            
            # Jerk calculation: da / dt
            if len(history_list) >= 2:
                jx = (ax - prev["ax"]) / dt
                jy = (ay - prev["ay"]) / dt
                jz = (az - prev["az"]) / dt
                jerk_total = math.sqrt(jx * jx + jy * jy + jz * jz)
                current_sample["jerk_total"] = jerk_total
            else:
                jerk_total = 0.0
                
            # Physics Validation Gating (Section 5.1):
            # 1. Lateral acceleration > 30 m/s^2 (~3g)
            if accel_lateral > self.thresholds.MAX_CIVIL_ACCELERATION_MS2:
                anomalies.append(f"Excessive lateral acceleration ({accel_lateral:.1f} m/s² > {self.thresholds.MAX_CIVIL_ACCELERATION_MS2} m/s²)")
                is_spoofed = True
                
            # 2. Vertical climb acceleration > 6g (~58.8 m/s^2)
            if abs(az) > self.thresholds.MAX_CIVIL_CLIMB_RATE_MS2:
                anomalies.append(f"Impossible vertical acceleration ({abs(az):.1f} m/s² > {self.thresholds.MAX_CIVIL_CLIMB_RATE_MS2} m/s² / 6g)")
                is_spoofed = True
                
            # 3. Excessive jerk > 25 m/s^3
            if jerk_total > self.thresholds.MAX_CIVIL_JERK_MS3:
                anomalies.append(f"Synthetic kinematic jerk ({jerk_total:.1f} m/s³ > {self.thresholds.MAX_CIVIL_JERK_MS3} m/s³)")
                is_spoofed = True
                
            # 4. Impossible civilian speed (> 620 kts)
            if speed_kts > self.thresholds.MAX_CIVIL_SPEED_KNOTS:
                anomalies.append(f"Supersonic civilian velocity anomaly ({speed_kts:.0f} kts > {self.thresholds.MAX_CIVIL_SPEED_KNOTS} kts)")
                is_spoofed = True
        else:
            accel_lateral = 0.0
            accel_total = 0.0
            jerk_total = 0.0
            
        # 5. Atmospheric Pressure Validation (QNH Altitude divergence)
        # In real aviation, geometric GPS height and barometric standard altitude diverge predictably with QNH.
        # Synthetic spoofers inject arbitrary altitudes without modeling atmosphere, yielding severe divergence.
        alt_divergence = abs(alt_geom - alt_baro)
        if alt_divergence > self.thresholds.MAX_ALTITUDE_DIVERGENCE_FT:
            anomalies.append(f"Atmospheric QNH divergence ({alt_divergence:.0f} ft > {self.thresholds.MAX_ALTITUDE_DIVERGENCE_FT} ft)")
            is_spoofed = True
            
        # Append to history, keeping last 30 samples
        history_list.append(current_sample)
        if len(history_list) > 30:
            history_list.pop(0)
            
        # Quarantine management
        if is_spoofed:
            self.quarantined_tracks[hex_id] = {
                "hex": hex_id,
                "flight": aircraft.get("flight", "SYNTHETIC"),
                "detected_at": now,
                "reasons": anomalies,
                "max_accel": round(accel_total, 2),
                "jerk": round(jerk_total, 2),
                "alt_divergence_ft": round(alt_divergence, 1)
            }
            status = "QUARANTINED_SPOOF"
        elif hex_id in self.quarantined_tracks:
            # Remained flagged if previously quarantined
            status = "QUARANTINED_SPOOF"
            anomalies = self.quarantined_tracks[hex_id]["reasons"]
        else:
            status = "VALID_COOPERATIVE"
            
        return {
            **aircraft,
            "kinematics": {
                "status": status,
                "is_spoofed": is_spoofed or (hex_id in self.quarantined_tracks),
                "accel_total_ms2": round(accel_total, 2),
                "accel_lateral_ms2": round(accel_lateral, 2),
                "accel_vertical_ms2": round(current_sample["az"], 2),
                "jerk_ms3": round(jerk_total, 2),
                "alt_divergence_ft": round(alt_divergence, 1),
                "anomalies": anomalies,
                "enu_x_km": round(east / 1000.0, 2),
                "enu_y_km": round(north / 1000.0, 2),
                "enu_z_km": round(up / 1000.0, 2)
            }
        }
        
    def reset_quarantine(self, hex_id: Optional[str] = None):
        """Clears quarantine flag for specific hex or all tracks."""
        if hex_id:
            self.quarantined_tracks.pop(hex_id.upper(), None)
            self.history.pop(hex_id.upper(), None)
        else:
            self.quarantined_tracks.clear()
            self.history.clear()
