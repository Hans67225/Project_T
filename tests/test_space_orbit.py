"""
Unit tests for Weather Satellite Telemetry & Meteorological Data Processing.
"""

import unittest
from backend.simulators.space_domain_sim import WeatherSatelliteDataProcessor

class TestWeatherSatelliteDomain(unittest.TestCase):
    
    def setUp(self):
        self.processor = WeatherSatelliteDataProcessor()

    def test_downlink_telemetry_structure(self):
        """Verifies weather satellite downlink telemetry parameters."""
        data = self.processor.get_meteorological_telemetry()
        self.assertEqual(data["satellite_id"], "NOAA 19")
        self.assertIn("AVHRR", data["sensor_payload"])
        
        dl = data["downlink"]
        self.assertEqual(dl["frequency_mhz"], 137.1000)
        self.assertEqual(dl["carrier_state"], "LOCKED_RECEIVING")
        self.assertIn("2080 px/line", dl["line_sync_state"])
        self.assertGreater(dl["snr_db"], 10.0)

    def test_meteorological_telemetry_ranges(self):
        """Verifies received atmospheric and cloud telemetry is within valid physical ranges."""
        data = self.processor.get_meteorological_telemetry()
        met = data["meteorological_telemetry"]
        
        # Cloud-top temperature should be sub-zero cold high altitude (-70C to -10C)
        self.assertLess(met["cloud_top_temperature_c"], -10.0)
        self.assertGreater(met["cloud_top_temperature_c"], -75.0)
        
        # Surface temperature should be realistic tropical ground temp (20C to 45C)
        self.assertGreater(met["surface_skin_temperature_c"], 20.0)
        self.assertLess(met["surface_skin_temperature_c"], 45.0)
        
        # Moisture index & cloud cover
        self.assertGreater(met["precipitable_water_moisture_mm"], 10.0)
        self.assertGreaterEqual(met["regional_cloud_cover_pct"], 0.0)
        self.assertLessEqual(met["regional_cloud_cover_pct"], 100.0)

    def test_multispectral_radiometer_channels(self):
        """Verifies AVHRR radiometer channels (Ch1 Visible, Ch2 Near-IR, Ch4 Thermal IR)."""
        data = self.processor.get_meteorological_telemetry()
        ch = data["sensor_channels"]
        
        self.assertIn("ch1_visible", ch)
        self.assertIn("ch2_near_ir", ch)
        self.assertIn("ch4_thermal_ir", ch)
        
        self.assertEqual(ch["ch1_visible"]["wavelength_um"], 0.63)
        self.assertEqual(ch["ch2_near_ir"]["wavelength_um"], 0.86)
        self.assertEqual(ch["ch4_thermal_ir"]["wavelength_um"], 10.8)

    def test_apt_composite_weather_image(self):
        """Verifies synthetic NOAA APT multi-spectral weather composite image is generated as valid PNG bytes."""
        img_bytes = self.processor.get_latest_apt_image()
        self.assertIsNotNone(img_bytes)
        self.assertGreater(len(img_bytes), 1000)
        # Check PNG magic header: \x89PNG\r\n\x1a\n
        self.assertTrue(img_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

if __name__ == "__main__":
    unittest.main()
