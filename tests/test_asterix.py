"""
Unit tests for Eurocontrol ASTERIX Category 021 Serializer (Section 5.6).
"""

import unittest
from backend.protocols.asterix_cat021 import AsterixCat021Serializer

class TestAsterixCat021(unittest.TestCase):

    def test_asterix_cat021_record_serialization(self):
        aircraft = {
            "hex": "706034",
            "flight": "IGO6782",
            "lat": 23.4123,
            "lon": 85.4399,
            "alt_baro": 35000,
            "alt_geom": 35120
        }
        packet, hex_dump, breakdown = AsterixCat021Serializer.serialize_record(aircraft)
        
        # Category byte must be 0x15 (21 decimal)
        self.assertEqual(packet[0], 0x15)
        
        # Length in header (bytes 1 and 2) must match total packet length
        packet_len = (packet[1] << 8) | packet[2]
        self.assertEqual(packet_len, len(packet))
        
        # Hex string representation matches
        self.assertEqual(hex_dump, packet.hex().upper())
        self.assertEqual(breakdown["icao_hex"], "706034")
        self.assertEqual(breakdown["callsign"], "IGO6782")
        self.assertEqual(breakdown["flight_level"], 350.0)

    def test_callsign_encoding(self):
        encoded = AsterixCat021Serializer.encode_callsign("TRINETRA")
        self.assertEqual(len(encoded), 6) # 48 bits

if __name__ == "__main__":
    unittest.main()
