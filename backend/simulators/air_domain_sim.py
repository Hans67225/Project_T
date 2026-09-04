"""
Air Domain ADS-B Telemetry Simulator & readsb Ingestion Engine
Section 2.1: Cooperative Reception (1090 MHz ADS-B) & Section 5 High-Impact Enhancements

Provides dual-mode operation:
1. SIMULATION MODE: High-fidelity Mode-S Extended Squitter generator replicating readsb
   DMA JSON stream across Eastern Indian airspace (Ranchi VERC, Kolkata CCU, Patna, Delhi routes)
   with controllable threat injection (HackRF spoofing, high-g climb, QNH divergence, CPA conflict).
2. HARDWARE MODE: Direct ingestion from /run/readsb/aircraft.json (RAM disk tmpfs)
   when physical AirNav RadarBox FlightStick SDR is connected.
"""

import json
import math
import os
import random
import time
from typing import Dict, Any, List, Optional
from ..config import GroundStationConfig, DefenseThresholds, READSB_JSON_DIR
from ..analytics.kinematics import KinematicStateTracker
from ..analytics.threat_assessment import ThreatAssessmentEngine
from ..protocols.asterix_cat021 import AsterixCat021Serializer

class AirDomainSimulator:
    """Manages aircraft state, movement, anomaly injection, and readsb JSON generation."""
    
    def __init__(self, mode: str = "SIMULATION"):
        self.mode = mode
        self.kinematic_tracker = KinematicStateTracker()
        self.threat_engine = ThreatAssessmentEngine()
        self.aircraft_pool: Dict[str, Dict[str, Any]] = {}
        self.total_messages = 142850
        self.last_update_time = time.time()
        self._init_baseline_fleet()
        
    def _init_baseline_fleet(self):
        """Initializes a realistic fleet of commercial aircraft traversing Jharkhand/Eastern India."""
        base_traffic = [
            {
                "hex": "706034",
                "flight": "IGO6782",
                "lat": 23.95, "lon": 84.80,
                "alt_baro": 35000, "alt_geom": 35250,
                "track": 122.0, "speed": 460.0, "vert_rate": 0.0,
                "squawk": "2104", "category": "A3", "rssi": -14.2
            },
            {
                "hex": "7061A2",
                "flight": "AIC415",
                "lat": 22.80, "lon": 84.95,
                "alt_baro": 37000, "alt_geom": 37180,
                "track": 65.0, "speed": 480.0, "vert_rate": 0.0,
                "squawk": "4521", "category": "A3", "rssi": -18.5
            },
            {
                "hex": "7063EF",
                "flight": "SEJ8192",
                "lat": 23.10, "lon": 86.20,
                "alt_baro": 36000, "alt_geom": 36150,
                "track": 302.0, "speed": 450.0, "vert_rate": -64.0,
                "squawk": "3312", "category": "A3", "rssi": -12.8
            },
            {
                "hex": "7065C1",
                "flight": "VTI724",
                "lat": 22.50, "lon": 85.10,
                "alt_baro": 39000, "alt_geom": 39220,
                "track": 42.0, "speed": 490.0, "vert_rate": 0.0,
                "squawk": "1675", "category": "A3", "rssi": -21.4
            },
            {
                "hex": "70691B",
                "flight": "6E215",
                "lat": 23.48, "lon": 85.60,
                "alt_baro": 8500, "alt_geom": 8620,
                "track": 240.0, "speed": 215.0, "vert_rate": -1200.0,
                "squawk": "0420", "category": "A2", "rssi": -7.5
            },
            {
                "hex": "89642A",
                "flight": "UAE334",
                "lat": 24.20, "lon": 84.40,
                "alt_baro": 38000, "alt_geom": 38300,
                "track": 105.0, "speed": 510.0, "vert_rate": 0.0,
                "squawk": "7101", "category": "A5", "rssi": -24.1
            },
            {
                "hex": "88019C",
                "flight": "THA316",
                "lat": 23.65, "lon": 86.70,
                "alt_baro": 33000, "alt_geom": 33140,
                "track": 118.0, "speed": 475.0, "vert_rate": 0.0,
                "squawk": "5244", "category": "A4", "rssi": -16.9
            }
        ]
        for ac in base_traffic:
            ac["messages"] = random.randint(120, 850)
            ac["seen"] = 0.2
            self.aircraft_pool[ac["hex"]] = ac

    def inject_hackrf_spoof(self) -> Dict[str, Any]:
        """Injects a synthetic Mode-S target exhibiting impossible kinematic acceleration (> 45 m/s²)."""
        spoof_hex = "A0FFEE"
        self.aircraft_pool[spoof_hex] = {
            "hex": spoof_hex,
            "flight": "GHOST-X",
            "lat": 23.43, "lon": 85.45,
            "alt_baro": 14000, "alt_geom": 14050,
            "track": 90.0, "speed": 350.0, "vert_rate": 0.0,
            "squawk": "7777", "category": "B1", "rssi": -5.0,
            "messages": 10, "seen": 0.1,
            "_inject_type": "HACKRF_SPOOF_ACCEL",
            "_step": 0
        }
        return {"status": "INJECTED", "type": "HACKRF_KINEMATIC_SPOOF", "target_hex": spoof_hex}

    def inject_qnh_tamper(self) -> Dict[str, Any]:
        """Injects an aircraft with severe geometric vs barometric altitude divergence."""
        tamper_hex = "B166AD"
        self.aircraft_pool[tamper_hex] = {
            "hex": tamper_hex,
            "flight": "DEV-ALT",
            "lat": 23.35, "lon": 85.20,
            "alt_baro": 12000, "alt_geom": 14200, # 2200 ft delta!
            "track": 45.0, "speed": 380.0, "vert_rate": 0.0,
            "squawk": "2000", "category": "A3", "rssi": -11.0,
            "messages": 45, "seen": 0.2,
            "_inject_type": "QNH_TAMPER"
        }
        return {"status": "INJECTED", "type": "QNH_ALTITUDE_TAMPER", "target_hex": tamper_hex}

    def inject_separation_conflict(self) -> Dict[str, Any]:
        """Spawns two converging aircraft destined for immediate CPA conflict (< 2 NM, < 500 ft)."""
        hex1 = "C011AA"
        hex2 = "C022BB"
        self.aircraft_pool[hex1] = {
            "hex": hex1, "flight": "VT-CON1",
            "lat": 23.50, "lon": 85.25,
            "alt_baro": 18000, "alt_geom": 18050,
            "track": 90.0, "speed": 400.0, "vert_rate": 0.0,
            "squawk": "1122", "category": "A3", "rssi": -9.0,
            "messages": 50, "seen": 0.1
        }
        self.aircraft_pool[hex2] = {
            "hex": hex2, "flight": "VT-CON2",
            "lat": 23.49, "lon": 85.60,
            "alt_baro": 18200, "alt_geom": 18250, # 200 ft separation!
            "track": 270.0, "speed": 400.0, "vert_rate": 0.0, # Head-on converging!
            "squawk": "2233", "category": "A3", "rssi": -8.5,
            "messages": 50, "seen": 0.1
        }
        return {"status": "INJECTED", "type": "AIRSPACE_SEPARATION_CONFLICT", "targets": [hex1, hex2]}

    def inject_geofence_incursion(self) -> Dict[str, Any]:
        """Spawns an unauthorized target breaching Mesra Security Perimeter (< 3 km)."""
        geo_hex = "D99999"
        self.aircraft_pool[geo_hex] = {
            "hex": geo_hex, "flight": "UAV-TGT",
            "lat": 23.42, "lon": 85.44, # < 1.5 km from BIT Mesra!
            "alt_baro": 1200, "alt_geom": 1250,
            "track": 180.0, "speed": 120.0, "vert_rate": -150.0,
            "squawk": "0044", "category": "B2", "rssi": -4.2,
            "messages": 80, "seen": 0.1
        }
        return {"status": "INJECTED", "type": "GEOFENCE_INCURSION", "target_hex": geo_hex}

    def clear_injected_scenarios(self):
        """Removes all injected test tracks and clears quarantine state."""
        injected = [h for h in list(self.aircraft_pool.keys()) if h.startswith(("A0", "B1", "C0", "D9")) or self.aircraft_pool[h].get("_inject_type")]
        for h in injected:
            self.aircraft_pool.pop(h, None)
        self.kinematic_tracker.reset_quarantine()

    def update_simulation(self, dt: float):
        """Propagates aircraft state vectors forward by dt seconds."""
        r_earth = GroundStationConfig.EARTH_RADIUS_KM * 1000.0
        
        for hex_id, ac in list(self.aircraft_pool.items()):
            # Check for special injection physics
            inject_type = ac.get("_inject_type")
            if inject_type == "HACKRF_SPOOF_ACCEL":
                ac["_step"] = ac.get("_step", 0) + 1
                if ac["_step"] >= 2:
                    # Execute impossible 55 m/s² lateral jump and 8g vertical spike!
                    ac["speed"] += 180.0 # Instant speed surge
                    ac["vert_rate"] += 12000.0 # 8g climb
                    ac["lat"] += 0.05
                    ac["lon"] += 0.05
            else:
                # Normal aerodynamic kinematics
                speed_ms = ac["speed"] * 0.514444
                track_rad = math.radians(ac["track"])
                vx = speed_ms * math.sin(track_rad)
                vy = speed_ms * math.cos(track_rad)
                vz = ac["vert_rate"] * 0.00508 # m/s
                
                # Coordinate updates
                d_lat = (vy * dt) / r_earth
                d_lon = (vx * dt) / (r_earth * math.cos(math.radians(ac["lat"])))
                ac["lat"] += math.degrees(d_lat)
                ac["lon"] += math.degrees(d_lon)
                
                # Altitude bounds: level off descending flights at safe approach altitude
                ac["alt_baro"] += (ac["vert_rate"] / 60.0) * dt
                if ac["flight"] == "6E215" and ac["alt_baro"] < 4200.0:
                    ac["alt_baro"] = 4200.0
                    ac["vert_rate"] = 0.0 # Level off at approach altitude
                
                # Keep geom altitude linked unless tampered
                if inject_type != "QNH_TAMPER":
                    ac["alt_geom"] = ac["alt_baro"] + random.uniform(50, 150)
                
            # Message stats & telemetry noise
            ac["messages"] += random.randint(1, 4)
            ac["seen"] = round(random.uniform(0.1, 0.4), 1)
            self.total_messages += ac["messages"]
            
            # Boundary management: gentle commercial turn or seamless corridor wrap
            dist_from_station = ThreatAssessmentEngine.haversine_km(
                ac["lat"], ac["lon"], GroundStationConfig.LATITUDE, GroundStationConfig.LONGITUDE
            )
            if dist_from_station > 400.0:
                # Calculate bearing back towards Mesra ground station
                y = math.sin(math.radians(GroundStationConfig.LONGITUDE - ac["lon"])) * math.cos(math.radians(GroundStationConfig.LATITUDE))
                x = (math.cos(math.radians(ac["lat"])) * math.sin(math.radians(GroundStationConfig.LATITUDE)) -
                     math.sin(math.radians(ac["lat"])) * math.cos(math.radians(GroundStationConfig.LATITUDE)) *
                     math.cos(math.radians(GroundStationConfig.LONGITUDE - ac["lon"])))
                bearing_to_station = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
                
                # Turn smoothly at standard commercial rate (max 1.5 deg/sec = ~0.2g, strictly civil)
                diff = (bearing_to_station - ac["track"] + 180.0) % 360.0 - 180.0
                turn_step = max(-1.5 * dt, min(1.5 * dt, diff))
                ac["track"] = (ac["track"] + turn_step) % 360.0

    def get_readsb_feed(self) -> Dict[str, Any]:
        """
        Generates or reads standard readsb aircraft.json format.
        Enriches each record with Kinematic Validation and ASTERIX CAT 021 serialization.
        """
        now = time.time()
        
        # Check Hardware Mode
        if self.mode == "HARDWARE":
            filepath = os.path.join(READSB_JSON_DIR, "aircraft.json")
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    raw_aircraft = data.get("aircraft", [])
                except Exception as e:
                    raw_aircraft = list(self.aircraft_pool.values())
            else:
                # Fallback to internal pool if file not yet written
                raw_aircraft = list(self.aircraft_pool.values())
        else:
            dt = max(now - self.last_update_time, 0.1)
            self.update_simulation(dt)
            self.last_update_time = now
            raw_aircraft = list(self.aircraft_pool.values())
            
        # Enrich each aircraft through Defense Pipelines
        enriched_aircraft = []
        for ac in raw_aircraft:
            # 1. Kinematic Anomaly & Spoofing Detection
            validated_ac = self.kinematic_tracker.process_telemetry(ac)
            
            # 2. Eurocontrol ASTERIX CAT 021 Serialization
            _, hex_dump, breakdown = AsterixCat021Serializer.serialize_record(ac)
            validated_ac["asterix_cat021"] = {
                "hex_stream": hex_dump,
                "breakdown": breakdown
            }
            enriched_aircraft.append(validated_ac)
            
        # 3. Airspace Threat Assessment (CPA, Separation, Geofences)
        threat_summary = self.threat_engine.assess_airspace(enriched_aircraft)
        
        # Assemble standard readsb schema
        return {
            "now": round(now, 2),
            "messages": self.total_messages,
            "station": GroundStationConfig.NAME,
            "mode": self.mode,
            "total_tracks": len(enriched_aircraft),
            "quarantined_count": len(self.kinematic_tracker.quarantined_tracks),
            "threat_summary": threat_summary,
            "aircraft": enriched_aircraft
        }
