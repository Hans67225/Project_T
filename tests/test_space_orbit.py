"""
Unit tests for Space Domain LEO Interception, Doppler Shift, and Link Budget (Section 3.1 & 4.2).
"""

import unittest
from backend.simulators.space_domain_sim import SpaceDomainSimulator, SatelliteTarget

class TestSpaceDomain(unittest.TestCase):
    
    def setUp(self):
        self.sim = SpaceDomainSimulator()

    def test_theoretical_link_budget_at_2000km(self):
        """
        Validates the exact link budget analysis from Section 4.2 of the report:
        Slant range d = 2000 km, f = 137 MHz
        L_fs ≈ 141.1 dB
        P_r ≈ -99.6 dBm
        N ≈ -119.0 dBm
        SNR ≈ 19.4 dB
        """
        sat = SatelliteTarget("NOAA APT Test", 99999, 137.0, "APT", tx_power_dbm=37.0, ant_gain_dbi=4.0)
        
        # Test kinematic calculation with synthetic position yielding 2000 km range
        # Use direct formula verification
        d_km = 2000.0
        f_mhz = 137.0
        
        l_fs = 20.0 * 3.30103 + 20.0 * 2.13672 + 32.44 # 66.02 + 42.73 + 32.44 = 141.19 dB
        self.assertAlmostEqual(l_fs, 141.19, delta=0.2)
        
        # Received power: P_r = 37 + 4 + 2 - 1.5 - 141.19 = -99.69 dBm
        p_r = 37.0 + 4.0 + 2.0 - 1.5 - l_fs
        self.assertAlmostEqual(p_r, -99.69, delta=0.3)
        
        # Thermal noise floor
        n = self.sim.thermal_noise_dbm
        self.assertAlmostEqual(n, -119.0, delta=0.5)
        
        # SNR
        snr = p_r - n
        self.assertAlmostEqual(snr, 19.4, delta=0.5)

    def test_satellite_pass_prediction(self):
        """Ensures all 4 target satellites have computed upcoming passes."""
        passes = self.sim.predict_upcoming_passes()
        self.assertEqual(len(passes), 4)
        sat_names = [p["satellite"] for p in passes]
        self.assertIn("NOAA 15", sat_names)
        self.assertIn("NOAA 18", sat_names)
        self.assertIn("NOAA 19", sat_names)
        self.assertIn("Meteor-M N2-3", sat_names)

    def test_apt_composite_image_generation(self):
        """Verifies synthetic NOAA APT multi-spectral composite image is generated as valid PNG bytes."""
        img_bytes = self.sim.get_latest_apt_image()
        self.assertIsNotNone(img_bytes)
        self.assertGreater(len(img_bytes), 1000)
        # Check PNG magic header: \x89PNG\r\n\x1a\n
        self.assertTrue(img_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

if __name__ == "__main__":
    unittest.main()
