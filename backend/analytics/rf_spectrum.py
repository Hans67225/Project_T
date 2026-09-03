"""
Wideband Spectral Monitoring and Jammer Detection Engine
Section 5.5: Wideband Spectral Monitoring and Jammer Detection

Simulates and analyzes RF spectrum across the 1090 MHz Mode-S and 137 MHz VHF bands.
Computes real-time FFT bins, estimates dynamic noise floor, and triggers alerts
for Electronic Warfare (EW) jamming attacks (broadband noise, CW spikes, sweep jammers).
"""

import math
import time
import numpy as np
from typing import Dict, Any, List, Optional
from ..config import DefenseThresholds, GroundStationConfig

class RFSpectrumMonitor:
    """Monitors RF spectrum health and detects electronic warfare / jammer interference."""
    
    def __init__(self, thresholds: Optional[DefenseThresholds] = None):
        self.thresholds = thresholds or DefenseThresholds()
        self.fft_bins = 64
        self.is_jamming_injected = False
        self.jamming_type = "NONE" # "BROADBAND", "CW_CARRIER", "SWEEP"
        
    def inject_jamming(self, mode: str = "BROADBAND"):
        """Simulates intentional electronic attack / jamming."""
        self.is_jamming_injected = True
        self.jamming_type = mode
        
    def clear_jamming(self):
        """Restores normal clean electromagnetic environment."""
        self.is_jamming_injected = False
        self.jamming_type = "NONE"

    def sweep_band(self, center_freq_mhz: float, span_mhz: float = 2.0) -> Dict[str, Any]:
        """
        Synthesizes an FFT power spectrum sweep around a center frequency (1090 MHz or 137 MHz).
        Returns frequency axis, power spectrum in dBm, estimated noise floor, and jammer status.
        """
        now = time.time()
        freqs = np.linspace(center_freq_mhz - span_mhz / 2.0, center_freq_mhz + span_mhz / 2.0, self.fft_bins)
        
        # Nominal thermal noise floor around -119 dBm with small random fluctuations
        base_noise = self.thresholds.NOMINAL_NOISE_FLOOR_DBM + np.random.normal(0.0, 1.2, self.fft_bins)
        
        # Normal operational signals:
        if abs(center_freq_mhz - 1090.0) < 1.0:
            # Mode-S pulse emissions around 1090 MHz (center spike)
            idx_center = self.fft_bins // 2
            # Intermittent ADS-B pulses peaking at -75 dBm to -60 dBm
            pulse_power = -65.0 + np.sin(now * 3.0) * 10.0
            base_noise[idx_center - 1 : idx_center + 2] += pulse_power - self.thresholds.NOMINAL_NOISE_FLOOR_DBM
        elif abs(center_freq_mhz - 137.0) < 2.0:
            # NOAA APT carrier around 137.1 / 137.62 / 137.91 MHz
            idx_center = self.fft_bins // 2
            # Satellite signal with FM sidebands ~ -99.6 dBm (link budget)
            base_noise[idx_center - 3 : idx_center + 4] += 18.0
            
        # Apply jamming if active
        jammer_detected = False
        alert_message = "SPECTRUM_NOMINAL"
        
        if self.is_jamming_injected:
            jammer_detected = True
            if self.jamming_type == "BROADBAND":
                # Broadband noise elevates entire spectrum by 25-35 dB
                jam_elev = 28.0 + np.random.normal(0, 2.0, self.fft_bins)
                base_noise += jam_elev
                alert_message = "HIGH_POWER_BROADBAND_NOISE_JAMMER"
            elif self.jamming_type == "CW_CARRIER":
                # High-power continuous wave tone spike at center
                idx_center = self.fft_bins // 2
                base_noise[idx_center] = -45.0 # Severe CW override
                alert_message = "CONTINUOUS_WAVE_CW_CO_CHANNEL_INTERFERENCE"
            elif self.jamming_type == "SWEEP":
                # Sweeping interference peak
                sweep_idx = int((math.sin(now * 2.0) * 0.5 + 0.5) * (self.fft_bins - 1))
                base_noise[sweep_idx] = -50.0
                alert_message = "FAST_SWEEP_FREQUENCY_JAMMER"
                
        # Estimate median noise floor from bottom 30% of bins
        sorted_powers = np.sort(base_noise)
        estimated_noise_floor = float(np.mean(sorted_powers[: self.fft_bins // 3]))
        noise_rise = estimated_noise_floor - self.thresholds.NOMINAL_NOISE_FLOOR_DBM
        
        if noise_rise > self.thresholds.JAMMER_DETECTION_THRESHOLD_DB:
            jammer_detected = True
            
        return {
            "center_freq_mhz": center_freq_mhz,
            "span_mhz": span_mhz,
            "freq_points": [round(float(f), 3) for f in freqs],
            "power_dbm": [round(float(p), 1) for p in base_noise],
            "estimated_noise_floor_dbm": round(estimated_noise_floor, 1),
            "nominal_noise_floor_dbm": self.thresholds.NOMINAL_NOISE_FLOOR_DBM,
            "noise_rise_db": round(noise_rise, 1),
            "jammer_detected": jammer_detected,
            "jammer_classification": alert_message,
            "timestamp": now
        }
