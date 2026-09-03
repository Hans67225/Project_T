"""
Project TRINETRA - Phase 1 Master C2 Backend Service
Tactical Radio Intelligence Network for Electromagnetic Tracking Reconnaissance & Analysis

Coordinates Air Domain (1090 MHz ADS-B), Space Domain (137 MHz VHF LEO),
Kinematic Spoofing Defense, Tactical Threat Assessment, RF Spectrum Monitoring,
and ASTERIX CAT 021 Serialization with zero-latency WebSocket feeds.
"""

import asyncio
import os
import time
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import GroundStationConfig, DefenseThresholds
from .simulators.air_domain_sim import AirDomainSimulator
from .simulators.space_domain_sim import SpaceDomainSimulator
from .analytics.rf_spectrum import RFSpectrumMonitor

app = FastAPI(
    title="Project TRINETRA Phase 1 - Tactical ASDA C2",
    description="Tactical Radio Intelligence Network for Electromagnetic Tracking Reconnaissance & Analysis",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Core Engines
air_sim = AirDomainSimulator(mode="SIMULATION")
space_sim = SpaceDomainSimulator()
rf_monitor = RFSpectrumMonitor()

start_time = time.time()

class ScenarioRequest(BaseModel):
    scenario: str # "HACKRF_SPOOF", "QNH_TAMPER", "SEPARATION_CONFLICT", "GEOFENCE_INCURSION", "JAMMER_BROADBAND", "CLEAR"

class ModeRequest(BaseModel):
    mode: str # "SIMULATION" or "HARDWARE"

@app.get("/api/health")
async def health_check():
    """System health, hardware state, and tmpfs RAM disk status."""
    uptime_sec = time.time() - start_time
    return {
        "status": "OPERATIONAL",
        "station": GroundStationConfig.NAME,
        "callsign": GroundStationConfig.CALLSIGN,
        "coordinates": {
            "latitude": GroundStationConfig.LATITUDE,
            "longitude": GroundStationConfig.LONGITUDE,
            "altitude_m": GroundStationConfig.ALTITUDE_M
        },
        "mode": air_sim.mode,
        "uptime_sec": round(uptime_sec, 1),
        "hardware_nodes": {
            "air_sdr": {
                "model": GroundStationConfig.AIR_SDR_MODEL,
                "frequency_mhz": GroundStationConfig.AIR_FREQ_MHZ,
                "sampling_rate_msps": GroundStationConfig.AIR_SAMPLING_RATE_MSPS,
                "status": "ACTIVE_SIMULATED" if air_sim.mode == "SIMULATION" else "PHYSICAL_DMA"
            },
            "space_sdr": {
                "model": GroundStationConfig.SPACE_SDR_MODEL,
                "frequency_mhz": GroundStationConfig.SPACE_FREQ_MHZ,
                "antenna": "120° V-Dipole (L=53.4cm)",
                "status": "ACTIVE_SIMULATED"
            },
            "tmpfs_ram_disk": {
                "mount": "/run/readsb",
                "wear_leveling_protection": "ENABLED",
                "status": "HEALTHY"
            }
        }
    }

@app.get("/api/air/aircraft")
async def get_aircraft():
    """Returns readsb-compatible aircraft.json feed enriched with defense kinematics and ASTERIX."""
    return air_sim.get_readsb_feed()

@app.get("/api/space/telemetry")
async def get_space_telemetry():
    """Returns real-time LEO weather satellite tracking, Doppler curves, and Friis link budget."""
    return space_sim.get_live_space_state()

@app.get("/api/space/passes")
async def get_upcoming_passes():
    """Returns predicted pass schedules for NOAA 15/18/19 and Meteor-M N2-3."""
    return space_sim.predict_upcoming_passes()

@app.get("/api/space/imagery/latest")
async def get_latest_satellite_image():
    """Returns latest demodulated NOAA APT multi-spectral composite image."""
    img_bytes = space_sim.get_latest_apt_image()
    return Response(content=img_bytes, media_type="image/png")

@app.get("/api/rf/spectrum")
async def get_rf_spectrum():
    """Returns wideband FFT sweeps for 1090 MHz ADS-B and 137 MHz VHF bands."""
    sweep_1090 = rf_monitor.sweep_band(1090.0, span_mhz=3.0)
    sweep_137 = rf_monitor.sweep_band(137.0, span_mhz=1.5)
    return {
        "adsb_1090": sweep_1090,
        "vhf_space_137": sweep_137
    }

@app.post("/api/scenario/inject")
async def inject_scenario(req: ScenarioRequest):
    """Triggers interactive defense threat scenarios for demonstration."""
    scen = req.scenario.upper()
    if scen == "HACKRF_SPOOF":
        res = air_sim.inject_hackrf_spoof()
    elif scen == "QNH_TAMPER":
        res = air_sim.inject_qnh_tamper()
    elif scen == "SEPARATION_CONFLICT":
        res = air_sim.inject_separation_conflict()
    elif scen == "GEOFENCE_INCURSION":
        res = air_sim.inject_geofence_incursion()
    elif scen == "JAMMER_BROADBAND":
        rf_monitor.inject_jamming(mode="BROADBAND")
        res = {"status": "INJECTED", "type": "BROADBAND_NOISE_JAMMER"}
    elif scen == "JAMMER_CW":
        rf_monitor.inject_jamming(mode="CW_CARRIER")
        res = {"status": "INJECTED", "type": "CONTINUOUS_WAVE_JAMMER"}
    elif scen == "CLEAR":
        air_sim.clear_injected_scenarios()
        rf_monitor.clear_jamming()
        res = {"status": "CLEARED", "message": "All threat injections reset to baseline"}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario}")
    return res

@app.post("/api/config/mode")
async def set_mode(req: ModeRequest):
    """Switches system between SIMULATION mode and HARDWARE (/run/readsb) ingestion."""
    mode = req.mode.upper()
    if mode in ["SIMULATION", "HARDWARE"]:
        air_sim.mode = mode
        return {"status": "SUCCESS", "current_mode": mode}
    raise HTTPException(status_code=400, detail="Mode must be SIMULATION or HARDWARE")

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    Streams consolidated tactical radar, satellite intercept,
    threat warnings, and RF spectrum data at 1 Hz.
    """
    await websocket.accept()
    try:
        while True:
            air_data = air_sim.get_readsb_feed()
            space_data = space_sim.get_live_space_state()
            spectrum_1090 = rf_monitor.sweep_band(1090.0, span_mhz=2.0)
            spectrum_137 = rf_monitor.sweep_band(137.0, span_mhz=1.0)
            
            payload = {
                "timestamp": time.time(),
                "station": GroundStationConfig.NAME,
                "mode": air_sim.mode,
                "air_domain": air_data,
                "space_domain": space_data,
                "rf_spectrum": {
                    "adsb_1090": spectrum_1090,
                    "vhf_space_137": spectrum_137
                },
                "alerts": {
                    "quarantined_spoofs": list(air_sim.kinematic_tracker.quarantined_tracks.values()),
                    "airspace_conflicts": air_data["threat_summary"]["conflicts"],
                    "geofence_breaches": air_data["threat_summary"]["geofence_violations"],
                    "rf_jammer_alert": spectrum_1090["jammer_detected"] or spectrum_137["jammer_detected"],
                    "jammer_details": spectrum_1090["jammer_classification"] if spectrum_1090["jammer_detected"] else spectrum_137["jammer_classification"]
                }
            }
            
            await websocket.send_json(payload)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        pass

# Mount static frontend directory
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
