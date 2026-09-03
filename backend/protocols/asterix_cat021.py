"""
Eurocontrol ASTERIX Category 021 (CAT 021) ADS-B Target Report Serializer
Section 5.6: ASTERIX Interoperability and 3D Tactical Visualization

Implements military and ATM interoperability binary format for Mode-S ADS-B reports.
Standard Reference: Eurocontrol Standard Document for Surveillance Data Exchange Part 12 (CAT 021).
"""

import time
import struct
from typing import Dict, Any, Tuple

class AsterixCat021Serializer:
    """Serializes validated ADS-B aircraft state into Eurocontrol ASTERIX CAT 021 binary frames."""
    
    SAC = 0x42  # System Area Code (India Region)
    SIC = 0x07  # System Identification Code (Mesra Ground Station 07)
    
    @staticmethod
    def encode_callsign(callsign: str) -> bytes:
        """Encodes up to 8 character callsign into 6-byte IA-5 6-bit packed format."""
        callsign = (callsign or "UNKNOWN").ljust(8)[:8].upper()
        # IA-5 6-bit character map (subset: ASCII code minus 48 for digits, etc.)
        def char_to_6bit(c: str) -> int:
            val = ord(c)
            if 65 <= val <= 90:  # A-Z -> 1-26
                return val - 64
            elif 48 <= val <= 57: # 0-9 -> 48-57
                return val
            elif val == 32:       # Space -> 32
                return 32
            return 0
        
        c = [char_to_6bit(ch) for ch in callsign]
        # Pack 8 x 6-bit chars = 48 bits = 6 bytes
        b0 = ((c[0] & 0x3F) << 2) | ((c[1] >> 4) & 0x03)
        b1 = ((c[1] & 0x0F) << 4) | ((c[2] >> 2) & 0x0F)
        b2 = ((c[2] & 0x03) << 6) | (c[3] & 0x3F)
        b3 = ((c[4] & 0x3F) << 2) | ((c[5] >> 4) & 0x03)
        b4 = ((c[5] & 0x0F) << 4) | ((c[6] >> 2) & 0x0F)
        b5 = ((c[6] & 0x03) << 6) | (c[7] & 0x3F)
        return bytes([b0, b1, b2, b3, b4, b5])

    @classmethod
    def serialize_record(cls, aircraft: Dict[str, Any]) -> Tuple[bytes, str, Dict[str, Any]]:
        """
        Serializes a single aircraft dictionary into CAT 021 binary record and hex dump.
        
        Record fields included:
        - I021/010: Data Source Identifier (SAC/SIC) [2 bytes]
        - I021/040: Target Report Descriptor [1 byte]
        - I021/073: Time of Message Reception [3 bytes, 1/128 sec UTC]
        - I021/130: Position in WGS-84 (Lat, Lon) [6 bytes, 180 / 2^23 deg]
        - I021/080: Target Address (ICAO 24-bit) [3 bytes]
        - I021/140: Geometric Height [2 bytes, LSB = 6.25 ft]
        - I021/145: Flight Level [2 bytes, LSB = 1/4 FL = 25 ft]
        - I021/170: Target Identification (Callsign) [6 bytes]
        """
        lat = float(aircraft.get("lat", 0.0))
        lon = float(aircraft.get("lon", 0.0))
        alt_geom = float(aircraft.get("alt_geom", aircraft.get("alt_baro", 0.0)))
        alt_baro = float(aircraft.get("alt_baro", 0.0))
        hex_id = str(aircraft.get("hex", "000000")).strip()
        callsign = str(aircraft.get("flight", "TRINETRA")).strip()
        
        # 1. I021/010: SAC / SIC
        item_010 = struct.pack("!BB", cls.SAC, cls.SIC)
        
        # 2. I021/040: Target Report Descriptor (Standard ADS-B broadcast)
        item_040 = bytes([0x01]) # DCR=0, GBS=0, SIM=0, TST=0, RAB=0, SAA=0, SPI=0, FX=1
        
        # 3. I021/073: Time of Day in 1/128 sec UTC
        t_sec = (time.time() % 86400) * 128.0
        t_int = int(t_sec) & 0xFFFFFF
        item_073 = struct.pack("!I", t_int)[1:] # 3 bytes
        
        # 4. I021/130: WGS-84 Position: LSB = 180 / 2^23 = 2.145767e-5 deg
        scale = (1 << 23) / 180.0
        lat_scaled = int(lat * scale)
        lon_scaled = int(lon * scale)
        item_130 = struct.pack("!ii", lat_scaled, lon_scaled)
        # Take 3 bytes for lat, 3 bytes for lon
        lat_3b = item_130[1:4]
        lon_3b = item_130[5:8]
        item_130_packed = lat_3b + lon_3b
        
        # 5. I021/080: Target Address (24-bit ICAO)
        try:
            icao_int = int(hex_id, 16)
        except ValueError:
            icao_int = 0
        item_080 = struct.pack("!I", icao_int)[1:] # 3 bytes
        
        # 6. I021/140: Geometric Height: LSB = 6.25 ft
        geom_h_scaled = int(alt_geom / 6.25)
        item_140 = struct.pack("!h", max(-32768, min(32767, geom_h_scaled)))
        
        # 7. I021/145: Flight Level: LSB = 25 ft (1/4 FL)
        fl_scaled = int(alt_baro / 25.0)
        item_145 = struct.pack("!h", max(-32768, min(32767, fl_scaled)))
        
        # 8. I021/170: Callsign (6 bytes)
        item_170 = cls.encode_callsign(callsign)
        
        # Assemble FSPEC (Field Specification):
        # Byte 1: [010, 040, 161, 130, 080, 140, 145, FX=1] -> 1 1 0 1 1 1 1 1 = 0xDF
        # Byte 2: [073, 170, 090, 210, 000, 000, 000, FX=0] -> 1 1 0 0 0 0 0 0 = 0xC0
        fspec = bytes([0xDF, 0xC0])
        
        # Assemble Record
        record_body = (
            fspec +
            item_010 +
            item_040 +
            item_130_packed +
            item_080 +
            item_140 +
            item_145 +
            item_073 +
            item_170
        )
        
        # Prepend Category (021 = 0x15) and Length (3 bytes header total)
        cat = 0x15
        total_len = 3 + len(record_body)
        header = struct.pack("!BH", cat, total_len)
        
        full_packet = header + record_body
        hex_dump = full_packet.hex().upper()
        
        breakdown = {
            "category": "ASTERIX CAT 021",
            "length_bytes": total_len,
            "hex_stream": hex_dump,
            "sac_sic": f"{cls.SAC}/{cls.SIC}",
            "icao_hex": hex_id.upper(),
            "callsign": callsign.upper(),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "flight_level": round(alt_baro / 100.0, 1),
            "geom_altitude_ft": round(alt_geom, 0)
        }
        
        return full_packet, hex_dump, breakdown
