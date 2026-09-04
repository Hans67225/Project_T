"""
Weather Satellite Meteorological Telemetry & Data Acquisition Simulator
Section 3.1: 137 MHz VHF Weather Satellite Interception & Meteorological Downlink

Simulates the reception, DSP demodulation, and meteorological sensor extraction
for polar-orbiting meteorological satellites (NOAA-19 AVHRR / Meteor-M MSU-MR):
1. Receiver Downlink Status (Carrier Lock, APT Line Sync, Frame Sync, SNR, RSSI).
2. AVHRR Radiometer Multi-Spectral Channels (Visible 0.63 µm, Near-IR 0.86 µm, Thermal IR 10.8 µm).
3. Derived Atmospheric & Meteorological Telemetry:
   - Cloud-Top Temperatures (convective storm cell detection)
   - Surface Skin Temperatures (ground infrared radiative scan)
   - Atmospheric Precipitable Water / Moisture Index
   - Regional Cloud Cover Density
4. High-Resolution SatDump Multi-Spectral Composite Weather Imagery.
"""

import io
import math
import time
import random
from typing import Dict, Any, List, Optional
from PIL import Image, ImageDraw, ImageFont
from ..config import GroundStationConfig

class WeatherSatelliteDataProcessor:
    """Processes real-time meteorological sensor feeds and demodulated weather satellite telemetry."""
    
    def __init__(self):
        self.station_name = GroundStationConfig.NAME
        self.station_lat = GroundStationConfig.LATITUDE
        self.station_lon = GroundStationConfig.LONGITUDE
        
        # Primary operational weather satellite profile
        self.satellite_name = "NOAA 19"
        self.instrument_payload = "AVHRR/3 (Advanced Very High Resolution Radiometer)"
        self.downlink_freq_mhz = 137.1000
        self.transmission_standard = "APT (Automatic Picture Transmission)"
        
        # Nominal meteorological baselines over Eastern India / Chota Nagpur
        self.base_cloud_temp_c = -48.5
        self.base_surface_temp_c = 31.4
        self.base_moisture_mm = 52.8
        self.base_cloud_cover_pct = 62.0
        
        self._cached_image_bytes: Optional[bytes] = None
        self._generate_synthetic_apt_composite()

    def get_meteorological_telemetry(self) -> Dict[str, Any]:
        """
        Returns structured meteorological data stream received and decoded
        from the 137.100 MHz weather satellite downlink.
        """
        now = time.time()
        
        # Subtle real-time atmospheric micro-variations
        t_phase = now / 30.0
        cloud_temp = round(self.base_cloud_temp_c + 3.0 * math.sin(t_phase) + random.uniform(-0.4, 0.4), 1)
        surface_temp = round(self.base_surface_temp_c + 1.2 * math.cos(t_phase * 0.5) + random.uniform(-0.2, 0.2), 1)
        moisture_index = round(self.base_moisture_mm + 2.5 * math.sin(t_phase * 0.7) + random.uniform(-0.3, 0.3), 1)
        cloud_cover = round(min(98.0, max(20.0, self.base_cloud_cover_pct + 5.0 * math.cos(t_phase) + random.uniform(-1.0, 1.0))), 1)
        
        # Multi-spectral radiometer channel reflectance / emission values
        vis_albedo = round(74.0 + 8.0 * math.sin(t_phase) + random.uniform(-0.5, 0.5), 1)
        ndvi_index = round(0.58 + 0.05 * math.cos(t_phase * 0.4), 2)
        
        # Convective storm formation gating based on cloud-top temperature
        if cloud_temp < -52.0:
            storm_status = "SEVERE_CONVECTIVE_STORM_CELLS"
            storm_alert_level = "WARNING"
        elif cloud_temp < -45.0:
            storm_status = "ELEVATED_CUMULONIMBUS_ACTIVITY"
            storm_alert_level = "ADVISORY"
        else:
            storm_status = "STABLE_STRATIFORM_DECK"
            storm_alert_level = "NOMINAL"
            
        # Receiver & Ingestion DSP Metrics
        snr_db = round(19.4 + 0.6 * math.sin(now / 10.0) + random.uniform(-0.2, 0.2), 1)
        recv_power_dbm = round(-99.6 + 0.8 * math.sin(now / 10.0), 1)

        return {
            "satellite_id": self.satellite_name,
            "sensor_payload": self.instrument_payload,
            "downlink": {
                "frequency_mhz": self.downlink_freq_mhz,
                "modulation": self.transmission_standard,
                "carrier_state": "LOCKED_RECEIVING",
                "line_sync_state": "2080 px/line (100% FRAME SYNC)",
                "line_rate": "2.0 lines/sec",
                "snr_db": snr_db,
                "received_power_dbm": recv_power_dbm,
                "noise_floor_dbm": -119.0,
                "antenna": "120° V-Dipole (L=53.4cm)"
            },
            "sensor_channels": {
                "ch1_visible": {
                    "wavelength_um": 0.63,
                    "spectral_band": "Visible Red",
                    "measured_albedo_pct": vis_albedo,
                    "utility": "Cloud Albedo & Aerosol Reflectance"
                },
                "ch2_near_ir": {
                    "wavelength_um": 0.86,
                    "spectral_band": "Near-Infrared",
                    "ndvi_index": ndvi_index,
                    "utility": "Vegetation / Land-Water Boundary Contrast"
                },
                "ch4_thermal_ir": {
                    "wavelength_um": 10.8,
                    "spectral_band": "Thermal Infrared",
                    "brightness_temp_c": cloud_temp,
                    "utility": "Cloud-Top & Surface Thermal Radiation"
                }
            },
            "meteorological_telemetry": {
                "cloud_top_temperature_c": cloud_temp,
                "surface_skin_temperature_c": surface_temp,
                "precipitable_water_moisture_mm": moisture_index,
                "regional_cloud_cover_pct": cloud_cover,
                "convective_status": storm_status,
                "alert_level": storm_alert_level,
                "coverage_corridor": "Eastern India / Jharkhand / Bay of Bengal (4 km/px)"
            },
            "timestamp": now
        }

    def _generate_synthetic_apt_composite(self):
        """
        Synthesizes a realistic 2-channel NOAA APT weather composite image
        (Channel A Visible + Channel B Thermal Infrared) spanning
        Himalayas to Sri Lanka across Eastern India.
        """
        width, height = 909, 600
        img = Image.new("RGB", (width, height), color=(15, 23, 42))
        draw = ImageDraw.Draw(img)
        
        ch_width = width // 2 - 20
        
        # Channel A (Visible 0.63 um - Greyscale with cloud albedo)
        for y in range(height):
            grad = int(35 + 80 * math.sin(y / 150.0))
            draw.line([(0, y), (ch_width, y)], fill=(grad, grad, grad))
            
        # Draw Indian landmass & Bay of Bengal silhouette in Channel A
        draw.polygon([(80, 120), (320, 110), (380, 220), (280, 480), (180, 520), (120, 360)], fill=(70, 85, 75))
        # Cloud swirl (Monsoon / tropical depression over Bay of Bengal)
        for r in range(120, 30, -10):
            alpha_col = 140 + (120 - r)
            draw.arc([(220 - r, 300 - r), (220 + r, 300 + r)], start=40, end=290, fill=(alpha_col, alpha_col, alpha_col), width=6)
            
        # Channel B (Thermal IR 10.8 um - Inverted temperatures: white = cold cloud tops, dark = warm land/sea)
        offset_x = width // 2 + 10
        for y in range(height):
            grad_b = int(180 - 60 * math.cos(y / 180.0))
            draw.line([(offset_x, y), (offset_x + ch_width, y)], fill=(grad_b, grad_b - 20, grad_b - 40))
            
        # Cold high-altitude cloud tops (bright white in thermal IR)
        draw.ellipse([(offset_x + 100, 180), (offset_x + 280, 320)], fill=(245, 245, 255))
        draw.ellipse([(offset_x + 60, 80), (offset_x + 360, 140)], fill=(255, 255, 255)) # Himalayan snow/high cloud
        
        # Sync Pulses & Telemetry wedges (authentic NOAA APT structure)
        for i in range(39):
            x_sync = int(i * 1.5)
            draw.line([(x_sync, 0), (x_sync, height)], fill=(255, 255, 255) if i % 2 == 0 else (0, 0, 0))
            
        for i in range(7):
            x_sync_b = offset_x + int(i * 5)
            draw.line([(x_sync_b, 0), (x_sync_b, height)], fill=(255, 255, 255) if i % 2 == 0 else (0, 0, 0))
            
        # Overlay Tactical Telemetry Text
        draw.text((15, 15), "PROJECT TRINETRA - NOAA 19 APT (137.100 MHz)", fill=(0, 255, 180))
        draw.text((15, 32), "CH-A VISIBLE (0.63 um) | RESOLUTION: 4 km/px", fill=(200, 200, 200))
        draw.text((15, 48), "GROUND STATION: MESRA (23.41N, 85.44E) | SNR: 19.4 dB", fill=(0, 220, 255))
        
        draw.text((offset_x + 15, 15), "CH-B THERMAL IR (10.8 um) | CLOUD TOP TEMP: -48.5 C", fill=(255, 180, 0))
        draw.text((offset_x + 15, 32), "SATDUMP DSP DEMODULATED | V-DIPOLE L=53.4cm", fill=(200, 200, 200))
        draw.text((offset_x + 15, 48), "COVERAGE: HIMALAYAS -> SRI LANKA (2500 km)", fill=(0, 255, 180))
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self._cached_image_bytes = buf.getvalue()

    def get_latest_apt_image(self) -> bytes:
        """Returns binary PNG of latest demodulated weather satellite pass image."""
        if self._cached_image_bytes is None:
            self._generate_synthetic_apt_composite()
        return self._cached_image_bytes

# Backward-compatible alias for existing imports
SpaceDomainSimulator = WeatherSatelliteDataProcessor
