"""
Unit tests for Kinematic Anomaly and Spoofing Detection Pipeline (Section 5.1).
"""

import unittest
import time
from backend.analytics.kinematics import KinematicStateTracker

class TestKinematicSpoofing(unittest.TestCase):
    
    def setUp(self):
        self.tracker = KinematicStateTracker()

    def test_normal_airliner_flight(self):
        """Standard commercial flight maintaining 460 kts straight and level."""
        t0 = time.time()
        # Initial point
        ac1 = {
            "hex": "706034", "flight": "IGO6782",
            "lat": 23.90, "lon": 84.80,
            "alt_baro": 35000, "alt_geom": 35100,
            "track": 90.0, "speed": 460.0, "vert_rate": 0.0
        }
        res1 = self.tracker.process_telemetry(ac1)
        self.assertEqual(res1["kinematics"]["status"], "VALID_COOPERATIVE")
        self.assertFalse(res1["kinematics"]["is_spoofed"])
        
        # Second point 1 second later: advanced along track
        time.sleep(0.05) # Tiny delay for dt
        ac2 = {
            "hex": "706034", "flight": "IGO6782",
            "lat": 23.90, "lon": 84.802,
            "alt_baro": 35000, "alt_geom": 35100,
            "track": 90.0, "speed": 460.0, "vert_rate": 0.0
        }
        res2 = self.tracker.process_telemetry(ac2)
        self.assertEqual(res2["kinematics"]["status"], "VALID_COOPERATIVE")
        self.assertFalse(res2["kinematics"]["is_spoofed"])

    def test_impossible_lateral_acceleration_spoof(self):
        """Simulates HackRF injection causing instantaneous 50 m/s^2 lateral acceleration."""
        hex_id = "A0FFEE"
        ac1 = {
            "hex": hex_id, "flight": "GHOST-1",
            "lat": 23.40, "lon": 85.40,
            "alt_baro": 15000, "alt_geom": 15050,
            "track": 0.0, "speed": 250.0, "vert_rate": 0.0
        }
        self.tracker.process_telemetry(ac1)
        
        # Next second: sudden 180° turn and surge to 550 kts (delta v ~ 400 m/s!)
        ac2 = {
            "hex": hex_id, "flight": "GHOST-1",
            "lat": 23.40, "lon": 85.40,
            "alt_baro": 15000, "alt_geom": 15050,
            "track": 180.0, "speed": 550.0, "vert_rate": 0.0
        }
        res2 = self.tracker.process_telemetry(ac2)
        self.assertEqual(res2["kinematics"]["status"], "QUARANTINED_SPOOF")
        self.assertTrue(res2["kinematics"]["is_spoofed"])
        self.assertIn(hex_id, self.tracker.quarantined_tracks)

    def test_impossible_vertical_climb_6g(self):
        """Simulates synthetic packet with impossible 6g vertical climb rate surge."""
        hex_id = "A0FF02"
        ac1 = {
            "hex": hex_id, "flight": "GHOST-2",
            "lat": 23.40, "lon": 85.40,
            "alt_baro": 10000, "alt_geom": 10050,
            "track": 90.0, "speed": 300.0, "vert_rate": 500.0
        }
        self.tracker.process_telemetry(ac1)
        
        # Next packet: vertical rate jumps to 15,000 ft/min (~76 m/s vertical speed!)
        ac2 = {
            "hex": hex_id, "flight": "GHOST-2",
            "lat": 23.40, "lon": 85.40,
            "alt_baro": 10500, "alt_geom": 10550,
            "track": 90.0, "speed": 300.0, "vert_rate": 15000.0
        }
        res2 = self.tracker.process_telemetry(ac2)
        self.assertEqual(res2["kinematics"]["status"], "QUARANTINED_SPOOF")
        self.assertTrue(res2["kinematics"]["is_spoofed"])

    def test_qnh_altitude_divergence_spoof(self):
        """Simulates spoofer who failed to model barometric pressure gradient (|h_geom - h_baro| > 800 ft)."""
        hex_id = "B166AD"
        ac = {
            "hex": hex_id, "flight": "TAMPER-QNH",
            "lat": 23.35, "lon": 85.20,
            "alt_baro": 10000, "alt_geom": 12500, # 2500 ft divergence!
            "track": 45.0, "speed": 350.0, "vert_rate": 0.0
        }
        res = self.tracker.process_telemetry(ac)
        self.assertEqual(res["kinematics"]["status"], "QUARANTINED_SPOOF")
        self.assertTrue(res["kinematics"]["is_spoofed"])
        self.assertIn("Atmospheric QNH divergence", str(res["kinematics"]["anomalies"]))

if __name__ == "__main__":
    unittest.main()
