"""
Project TRINETRA - Phase 1 Configuration
Tactical Radio Intelligence Network for Electromagnetic Tracking Reconnaissance & Analysis
Ground Station: Mesra, Ranchi, Jharkhand, India
"""

import os
from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class GroundStationConfig:
    NAME: str = "TRINETRA-GS-MESRA"
    CALLSIGN: str = "MESRA-ASDA-01"
    LATITUDE: float = 23.4123     # Degrees North (BIT Mesra, Ranchi)
    LONGITUDE: float = 85.4399    # Degrees East
    ALTITUDE_M: float = 650.0     # Elevation ASL (meters)
    
    # Air Domain Hardware specs (Phase 1)
    AIR_FREQ_MHZ: float = 1090.0
    AIR_ANTENNA_GAIN_DBI: float = 5.5   # 5.5 dBi vertical collinear
    AIR_SDR_MODEL: str = "AirNav RadarBox FlightStick"
    AIR_SAMPLING_RATE_MSPS: float = 2.4
    
    # Space Domain Hardware specs (Phase 1)
    SPACE_FREQ_MHZ: float = 137.0       # Center VHF weather band
    SPACE_ANTENNA_GAIN_DBI: float = 2.0 # 120° V-Dipole horizontal
    SPACE_CABLE_LOSS_DB: float = 1.5    # LMR-400 / RG-58 loss
    SPACE_SDR_MODEL: str = "RTL-SDR Blog V4 (TCXO)"
    
    # Link Budget Constants (Section 4.2)
    BOLTZMANN_K: float = 1.380649e-23   # J/K
    NOISE_TEMP_K: float = 290.0         # Standard reference noise temp
    NOAA_BANDWIDTH_HZ: float = 40000.0  # 40 kHz channel bandwidth
    SPEED_OF_LIGHT: float = 299792458.0 # m/s
    EARTH_RADIUS_KM: float = 6371.0     # Mean radius

@dataclass(frozen=True)
class DefenseThresholds:
    # Section 5.1: Kinematic Anomaly and Spoofing Detection
    MAX_CIVIL_ACCELERATION_MS2: float = 30.0    # Commercial airliner limit (~3g)
    MAX_CIVIL_JERK_MS3: float = 25.0            # Max rate of acceleration change
    MAX_CIVIL_CLIMB_RATE_MS2: float = 58.8      # 6g vertical climb ceiling
    MAX_CIVIL_SPEED_KNOTS: float = 620.0        # Max subsonic cruising speed (~Mach 0.92)
    MAX_ALTITUDE_DIVERGENCE_FT: float = 800.0   # |h_geom - h_baro| QNH anomaly threshold
    
    # Section 5.4: Tactical Threat Assessment & Separation
    MIN_HORIZONTAL_SEPARATION_NM: float = 5.0   # Standard ATM loss of separation
    MIN_VERTICAL_SEPARATION_FT: float = 1000.0  # Reduced Vertical Separation Minimum (RVSM)
    CPA_LOOKAHEAD_SECONDS: float = 180.0        # 3 minute trajectory extrapolation
    
    # Restricted Zones / Geofences (Polygon list: (lat, lon))
    # 1. Birsa Munda Airport Ranchi (VERC) CTR Zone
    VERC_CTR_BOUNDS: Tuple[Tuple[float, float], ...] = (
        (23.36, 85.27),
        (23.36, 85.38),
        (23.28, 85.38),
        (23.28, 85.27),
    )
    # 2. Mesra Ground Station Security Perimeter (5 km buffer)
    MESRA_SECURITY_RADIUS_KM: float = 5.0
    
    # Section 5.5: Wideband Spectral Monitoring & Jammer Detection
    NOMINAL_NOISE_FLOOR_DBM: float = -119.0
    JAMMER_DETECTION_THRESHOLD_DB: float = 12.0 # Spike above noise floor flagging jamming

# Default operational modes
STREAM_MODE: str = os.getenv("TRINETRA_MODE", "SIMULATION") # "SIMULATION" or "HARDWARE"
READSB_JSON_DIR: str = os.getenv("TRINETRA_READSB_PATH", "/run/readsb")
TELEMETRY_INTERVAL_SEC: float = 1.0
