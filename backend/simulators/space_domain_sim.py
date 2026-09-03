"""
Space Domain LEO Satellite Interception Simulator & Link Budget Engine
Section 3.1: Omnidirectional LEO Interception (VHF) & Section 4.2 Link Budget

1. LEO Meteorological Ephemeris & Pass Prediction (NOAA-15, NOAA-18, NOAA-19, Meteor-M N2-3).
2. Dynamic Doppler Shift Engine: f_rx = f_0 * (1 + v_r / c) with rigctl AFC simulation.
3. Theoretical RF Link Budget Calculator (Section 4.2):
   - Free Space Path Loss (L_fs) at slant range d
   - Total Received Power (P_r = P_t + G_t + G_r - L_c - L_fs)
   - Thermal Noise Floor (N = 10*log10(k*T*B) ~ -119 dBm)
   - Resultant SNR = P_r - N (~19.4 dB at 2000 km, >25 dB at zenith)
4. SatDump APT/LRPT Demodulator Simulation & Multi-Spectral Image Generator.
"""

import io
import math
import time
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from ..config import GroundStationConfig

class SatelliteTarget:
    """Represents a LEO weather satellite in Sun-Synchronous Orbit."""
    def __init__(self, name: str, norad_id: int, freq_mhz: float, downlink_type: str, tx_power_dbm: float = 37.0, ant_gain_dbi: float = 4.0):
        self.name = name
        self.norad_id = norad_id
        self.freq_mhz = freq_mhz
        self.downlink_type = downlink_type # "APT" or "LRPT"
        self.tx_power_dbm = tx_power_dbm   # 5 Watts = 37 dBm
        self.ant_gain_dbi = ant_gain_dbi   # 4 dBi crossed dipole
        self.altitude_km = 850.0           # Nominal circular LEO
        self.orbital_speed_kms = 7.45      # ~7.5 km/s
        self.period_min = 102.0            # ~102 minutes per orbit
        self.inclination_deg = 98.7        # Sun-synchronous retro

class SpaceDomainSimulator:
    """Computes real-time satellite positions, passes, Doppler shift, link budgets, and APT demodulation."""
    
    def __init__(self):
        self.station_lat = GroundStationConfig.LATITUDE
        self.station_lon = GroundStationConfig.LONGITUDE
        self.station_alt_km = GroundStationConfig.ALTITUDE_M / 1000.0
        self.r_earth_km = GroundStationConfig.EARTH_RADIUS_KM
        
        # Section 3.1 Satellites
        self.satellites = [
            SatelliteTarget("NOAA 15", 25338, 137.6200, "APT"),
            SatelliteTarget("NOAA 18", 28654, 137.9125, "APT"),
            SatelliteTarget("NOAA 19", 33591, 137.1000, "APT"),
            SatelliteTarget("Meteor-M N2-3", 57166, 137.9000, "LRPT"),
        ]
        
        # Link budget constants (Section 4.2)
        # N = 10*log10(k*T*B) + NF ≈ -119.0 dBm (accounting for front-end noise figure)
        # Yields SNR = Pr - N = -99.6 - (-119.0) = 19.4 dB
        self.thermal_noise_dbm = -119.0
        self.rx_ant_gain_dbi = GroundStationConfig.SPACE_ANTENNA_GAIN_DBI # 2.0 dBi
        self.cable_loss_db = GroundStationConfig.SPACE_CABLE_LOSS_DB      # 1.5 dB
        self.c_kms = GroundStationConfig.SPEED_OF_LIGHT / 1000.0
        
        # Active tracked satellite (default NOAA 19)
        self.active_sat_idx = 2
        self.start_epoch = time.time()
        self._cached_image_bytes: Optional[bytes] = None
        self._generate_synthetic_apt_composite()

    def get_satellite(self, name: str) -> Optional[SatelliteTarget]:
        for s in self.satellites:
            if s.name.lower() == name.lower():
                return s
        return None

    def calculate_subsatellite_point(self, sat: SatelliteTarget, t_now: float) -> Tuple[float, float, float]:
        """
        Computes sub-satellite point (Lat, Lon) and true anomaly from orbital kinematics.
        Period ~ 102 minutes. Orbit precesses ~25.5 degrees per orbit due to Earth rotation.
        """
        elapsed_sec = t_now - self.start_epoch
        # Add offset so NOAA 19 passes close to Mesra
        offset_sec = 1800.0 if sat.name == "NOAA 19" else 4200.0
        t_phase = elapsed_sec + offset_sec
        
        omega = (2.0 * math.pi) / (sat.period_min * 60.0)
        mean_anomaly = (omega * t_phase) % (2.0 * math.pi)
        
        # Latitude from inclination
        lat = math.degrees(math.asin(math.sin(math.radians(sat.inclination_deg)) * math.sin(mean_anomaly)))
        
        # Longitude accounts for orbit nodal progression + Earth rotation (360 deg / 86400 sec)
        earth_rot_rate = 360.0 / 86400.0 # deg/sec
        lon = (self.station_lon + math.degrees(math.cos(mean_anomaly) * 0.8) - (earth_rot_rate * t_phase))
        lon = ((lon + 180.0) % 360.0) - 180.0 # Normalize -180 to 180
        
        return lat, lon, sat.altitude_km

    def calculate_topo_kinematics(self, sat: SatelliteTarget, sat_lat: float, sat_lon: float, sat_alt_km: float) -> Dict[str, Any]:
        """
        Computes topocentric Azimuth, Elevation, Slant Range, and Radial Velocity
        from Mesra Ground Station.
        """
        # Great-circle angular separation sigma
        phi1 = math.radians(self.station_lat)
        lam1 = math.radians(self.station_lon)
        phi2 = math.radians(sat_lat)
        lam2 = math.radians(sat_lon)
        
        cos_sigma = math.sin(phi1) * math.sin(phi2) + math.cos(phi1) * math.cos(phi2) * math.cos(lam2 - lam1)
        cos_sigma = max(-1.0, min(1.0, cos_sigma))
        sigma = math.acos(cos_sigma) # Radians
        
        # Law of cosines for slant range d
        r_sta = self.r_earth_km + self.station_alt_km
        r_sat = self.r_earth_km + sat_alt_km
        
        d_sq = r_sta * r_sta + r_sat * r_sat - 2.0 * r_sta * r_sat * cos_sigma
        slant_range_km = math.sqrt(max(0.0, d_sq))
        
        # Elevation angle: sin(el) = (r_sat * cos(sigma) - r_sta) / d
        sin_el = (r_sat * cos_sigma - r_sta) / max(slant_range_km, 1.0)
        sin_el = max(-1.0, min(1.0, sin_el))
        el_deg = math.degrees(math.asin(sin_el))
        
        # Azimuth angle: bearing from station to sub-satellite point
        y = math.sin(lam2 - lam1) * math.cos(phi2)
        x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(lam2 - lam1)
        az_deg = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
        
        # Radial velocity v_r(t) = d(slant_range)/dt
        # Modeled from satellite velocity vector relative to line-of-sight
        # Radial velocity peaks around +/- 6.8 km/s at horizon and 0 at TCA (closest approach)
        v_radial_kms = sat.orbital_speed_kms * math.sin(sigma) * math.sin(math.radians(az_deg - 180.0))
        
        # Doppler shift: f_rx = f_0 * (1 - v_r / c) [negative v_r is approaching]
        # Approaching (v_r < 0) -> f_rx > f_0 (+3 to +4.5 kHz)
        # Receding (v_r > 0) -> f_rx < f_0 (-3 to -4.5 kHz)
        doppler_shift_hz = - (v_radial_kms / self.c_kms) * (sat.freq_mhz * 1e6)
        rx_freq_mhz = sat.freq_mhz + (doppler_shift_hz / 1e6)
        
        # Section 4.2 Theoretical RF Link Budget
        # Free Space Path Loss (L_fs) = 20*log10(d) + 20*log10(f_MHz) + 32.44 dB
        d_km_clamped = max(slant_range_km, sat_alt_km)
        l_fs = 20.0 * math.log10(d_km_clamped) + 20.0 * math.log10(sat.freq_mhz) + 32.44
        
        # P_r = P_t + G_t + G_r - L_c - L_fs
        p_r_dbm = sat.tx_power_dbm + sat.ant_gain_dbi + self.rx_ant_gain_dbi - self.cable_loss_db - l_fs
        
        # SNR = P_r - N
        snr_db = p_r_dbm - self.thermal_noise_dbm
        
        is_visible = el_deg > 0.0 # Above optical/radio horizon
        
        return {
            "elevation_deg": round(el_deg, 2),
            "azimuth_deg": round(az_deg, 2),
            "slant_range_km": round(slant_range_km, 1),
            "radial_velocity_kms": round(v_radial_kms, 3),
            "doppler_shift_hz": round(doppler_shift_hz, 1),
            "nominal_freq_mhz": sat.freq_mhz,
            "rx_corrected_freq_mhz": round(rx_freq_mhz, 6),
            "rigctl_step_khz": round(doppler_shift_hz / 1000.0, 2),
            "free_space_loss_db": round(l_fs, 2),
            "received_power_dbm": round(p_r_dbm, 2),
            "thermal_noise_dbm": round(self.thermal_noise_dbm, 2),
            "snr_db": round(snr_db, 2),
            "is_visible": is_visible
        }

    def predict_upcoming_passes(self) -> List[Dict[str, Any]]:
        """Generates pass schedules for the 4 key weather satellites over Mesra."""
        passes = []
        now = time.time()
        for idx, sat in enumerate(self.satellites):
            # Pass timing simulation relative to now
            time_to_aos = 180.0 if idx == self.active_sat_idx else (idx + 1) * 3600.0 - 1200.0
            duration_sec = 840.0 # ~14 minute pass duration
            max_el = 68.5 if idx == self.active_sat_idx else (35.0 + idx * 12.0)
            
            passes.append({
                "satellite": sat.name,
                "norad_id": sat.norad_id,
                "frequency_mhz": sat.freq_mhz,
                "mode": sat.downlink_type,
                "aos_timestamp": round(now + time_to_aos),
                "tca_timestamp": round(now + time_to_aos + duration_sec / 2.0),
                "los_timestamp": round(now + time_to_aos + duration_sec),
                "duration_seconds": duration_sec,
                "max_elevation_deg": max_el,
                "status": "PASS_IN_PROGRESS" if idx == self.active_sat_idx else "SCHEDULED"
            })
        return passes

    def get_live_space_state(self) -> Dict[str, Any]:
        """Provides full real-time telemetry snapshot for active satellite interception."""
        now = time.time()
        sat = self.satellites[self.active_sat_idx]
        
        sat_lat, sat_lon, sat_alt = self.calculate_subsatellite_point(sat, now)
        kinematics = self.calculate_topo_kinematics(sat, sat_lat, sat_lon, sat_alt)
        
        all_sats = []
        for s in self.satellites:
            s_lat, s_lon, s_alt = self.calculate_subsatellite_point(s, now)
            s_kine = self.calculate_topo_kinematics(s, s_lat, s_lon, s_alt)
            all_sats.append({
                "name": s.name,
                "norad_id": s.norad_id,
                "freq_mhz": s.freq_mhz,
                "mode": s.downlink_type,
                "lat": round(s_lat, 4),
                "lon": round(s_lon, 4),
                "elevation_deg": s_kine["elevation_deg"],
                "azimuth_deg": s_kine["azimuth_deg"],
                "is_visible": s_kine["is_visible"],
                "snr_db": s_kine["snr_db"]
            })
            
        return {
            "timestamp": now,
            "active_satellite": sat.name,
            "norad_id": sat.norad_id,
            "mode": sat.downlink_type,
            "subsatellite_lat": round(sat_lat, 4),
            "subsatellite_lon": round(sat_lon, 4),
            "altitude_km": sat_alt,
            "kinematics": kinematics,
            "all_satellites": all_sats,
            "ground_station": {
                "name": GroundStationConfig.NAME,
                "lat": self.station_lat,
                "lon": self.station_lon,
                "alt_m": GroundStationConfig.ALTITUDE_M
            },
            "satdump_status": {
                "demodulator": "SatDump v1.2 / APT-Demod",
                "v_dipole_resonance_cm": 53.4, # Section 3.1: 143/137 MHz
                "sync_subcarrier_hz": 2400.0,
                "viterbi_ber": 0.00012,
                "scanlines_decoded": int((now % 120) * 16),
                "frame_lock": True
            }
        }

    def _generate_synthetic_apt_composite(self):
        """
        Synthesizes a realistic 2-channel NOAA APT composite image
        (Channel A Visible + Channel B Thermal Infrared) spanning
        Himalayas to Sri Lanka across Eastern India.
        """
        width, height = 909, 600
        img = Image.new("RGB", (width, height), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)
        
        # Split into Channel A (Left: Visible) and Channel B (Right: Thermal IR)
        ch_width = width // 2 - 20
        
        # Draw Channel A (Visible 0.63 um - Greyscale with cloud albedo)
        for y in range(height):
            grad = int(35 + 80 * math.sin(y / 150.0))
            draw.line([(0, y), (ch_width, y)], fill=(grad, grad, grad))
            
        # Draw Indian landmass & Bay of Bengal silhouette in Channel A
        # Central Gangetic plain & Chota Nagpur plateau (Jharkhand)
        draw.polygon([(80, 120), (320, 110), (380, 220), (280, 480), (180, 520), (120, 360)], fill=(70, 85, 75))
        # Cloud swirl (Monsoon / tropical depression over Bay of Bengal)
        for r in range(120, 30, -10):
            alpha_col = 140 + (120 - r)
            draw.arc([(220 - r, 300 - r), (220 + r, 300 + r)], start=40, end=290, fill=(alpha_col, alpha_col, alpha_col), width=6)
            
        # Draw Channel B (Thermal IR 10.8 um - Inverted temperatures: white = cold cloud tops, dark = warm land/sea)
        offset_x = width // 2 + 10
        for y in range(height):
            grad_b = int(180 - 60 * math.cos(y / 180.0))
            draw.line([(offset_x, y), (offset_x + ch_width, y)], fill=(grad_b, grad_b - 20, grad_b - 40))
            
        # Cold high-altitude cloud tops (bright white in thermal IR)
        draw.ellipse([(offset_x + 100, 180), (offset_x + 280, 320)], fill=(245, 245, 255))
        draw.ellipse([(offset_x + 60, 80), (offset_x + 360, 140)], fill=(255, 255, 255)) # Himalayan snow/high cloud
        
        # Sync Pulses & Telemetry wedges (authentic NOAA APT structure)
        # Channel A Sync (39 pulses)
        for i in range(39):
            x_sync = int(i * 1.5)
            draw.line([(x_sync, 0), (x_sync, height)], fill=(255, 255, 255) if i % 2 == 0 else (0, 0, 0))
            
        # Channel B Sync (7 pulses)
        for i in range(7):
            x_sync_b = offset_x + int(i * 5)
            draw.line([(x_sync_b, 0), (x_sync_b, height)], fill=(255, 255, 255) if i % 2 == 0 else (0, 0, 0))
            
        # Overlay Tactical Telemetry Text
        draw.text((15, 15), "PROJECT TRINETRA - NOAA 19 APT (137.100 MHz)", fill=(0, 255, 180))
        draw.text((15, 32), "CH-A VISIBLE (0.63 um) | RESOLUTION: 4 km/px", fill=(200, 200, 200))
        draw.text((15, 48), "GROUND STATION: MESRA (23.41N, 85.44E) | SNR: 19.4 dB", fill=(0, 220, 255))
        
        draw.text((offset_x + 15, 15), "CH-B THERMAL IR (10.8 um) | CLOUD TOP TEMP", fill=(255, 180, 0))
        draw.text((offset_x + 15, 32), "SATDUMP DSP DEMODULATED | V-DIPOLE L=53.4cm", fill=(200, 200, 200))
        draw.text((offset_x + 15, 48), "COVERAGE: HIMALAYAS -> SRI LANKA (2500 km)", fill=(0, 255, 180))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self._cached_image_bytes = buf.getvalue()

    def get_latest_apt_image(self) -> bytes:
        """Returns binary PNG of latest demodulated satellite pass image."""
        if self._cached_image_bytes is None:
            self._generate_synthetic_apt_composite()
        return self._cached_image_bytes
