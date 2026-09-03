# Project TRINETRA (Phase 1)
## Tactical Radio Intelligence Network for Electromagnetic Tracking Reconnaissance & Analysis
### Ground Station: Mesra, Ranchi, Jharkhand, India (23.4123° N, 85.4399° E, 650m ASL)

TRINETRA Phase 1 provides an autonomous, localized, multi-modal **Air and Space Domain Awareness (ASDA)** platform. It integrates cooperative civilian flight tracking (1090 MHz ADS-B), LEO meteorological satellite interception (137 MHz VHF), rigid-body kinematic spoofing defense, tactical airspace threat assessment, and Eurocontrol ASTERIX CAT 021 military radar interoperability.

Because physical SDRs (AirNav FlightStick, RTL-SDR Blog V4) and antennas (120° V-dipole, 5.5 dBi collinear) are not yet connected, the system incorporates a **high-fidelity simulation engine** that replicates live hardware outputs with mathematical and physics accuracy. When hardware arrives, toggling `MODE=HARDWARE` seamlessly reads from `/run/readsb/aircraft.json` without modifying downstream defense modules.

---

## Key System Modules (Phase 1)

### 1. Air Domain Tracking Pipeline (Section 2.1)
- **RF Standard**: 1090 MHz Mode-S Extended Squitter (Pulse-Position Modulation, 2.4 MSPS ADC baseband).
- **readsb Ingestion**: Emulates DMA buffers and CRC-24 decoded JSON output (`aircraft.json`, `stats.json`).
- **RAM Disk Wear-Leveling**: Simulates `/run/readsb` mounted as `tmpfs` to protect MicroSD storage from continuous I/O degradation.
- **Dynamic Traffic Model**: Authentic commercial air routes over Eastern India (Delhi-Kolkata, Mumbai-Patna, Bengaluru-Guwahati, Ranchi VERC terminal traffic).

### 2. Space Domain Interceptor (Section 3.1 & 4.2)
- **Downlink Targets**: Sun-Synchronous LEO weather satellites:
  - **NOAA 15** (137.6200 MHz APT)
  - **NOAA 18** (137.9125 MHz APT)
  - **NOAA 19** (137.1000 MHz APT)
  - **Meteor-M N2-3** (137.9000 MHz LRPT QPSK)
- **Doppler Shift Engine**: Computes radial velocity $v_r(t)$ and $f_{rx} = f_0 (1 + v_r/c)$, simulating the $\pm 4.5\text{ kHz}$ S-curve and continuous `rigctl` automated frequency correction (AFC).
- **Theoretical RF Link Budget (Section 4.2)**:
  - Free Space Path Loss: $L_{fs} = 20\log_{10}(d) + 20\log_{10}(137) + 32.44\text{ dB} \approx 141.1\text{ dB}$ at 2000 km slant range.
  - Received Power: $P_r = P_t (37\text{ dBm}) + G_t (4\text{ dBi}) + G_r (2\text{ dBi}) - L_c (1.5\text{ dB}) - L_{fs} \approx -99.6\text{ dBm}$.
  - Thermal Noise Floor: $N = 10\log_{10}(k T B) \approx -119.0\text{ dBm}$ ($B=40\text{ kHz}, T=290\text{ K}$).
  - Resultant SNR: $\text{SNR} = P_r - N \approx 19.4\text{ dB}$.
- **SatDump APT Demodulation**: Generates calibrated 2-channel multi-spectral composite imagery (Channel A Visible 0.63 $\mu$m + Channel B Thermal IR 10.8 $\mu$m) spanning the Himalayas to Sri Lanka.

### 3. Kinematic Anomaly & Spoofing Detection (Section 5.1)
- **Continuous State Vector Tracking**: Tracks $\mathbf{x}_t = [x, y, z, \dot{x}, \dot{y}, \dot{z}]^T$ in local East-North-Up (ENU) Cartesian coordinates relative to Mesra.
- **Kinematic Derivatives**: Computes acceleration $\mathbf{a} = \frac{\Delta \mathbf{v}}{\Delta t}$ and jerk $\mathbf{j} = \frac{\Delta \mathbf{a}}{\Delta t}$.
- **Threshold Gating**:
  - Lateral acceleration $> 30\text{ m/s}^2$ (~3g).
  - Vertical acceleration $> 6g$ ($> 58.8\text{ m/s}^2$).
  - Speed anomaly $> 620\text{ kts}$.
  - Instantly quarantines synthetic HackRF-injected tracks.
- **Atmospheric Pressure Validation**: Compares geometric GPS altitude ($h_{\text{geom}}$) against barometric pressure altitude ($h_{\text{baro}}$), flagging synthetic QNH divergences $> 800\text{ ft}$.

### 4. Tactical Airspace Threat Assessment (Section 5.4)
- **Pairwise CPA/TCPA**: Simultaneous linear vector extrapolation for Closest Point of Approach distance and Time to CPA.
- **Separation Gating**: Real-time alerts for loss of standard separation ($< 5\text{ NM}$ horizontal, $< 1000\text{ ft}$ vertical).
- **Geofence Encroachment**: Detects penetrations into Ranchi Birsa Munda Airport (VERC) CTR and the Mesra Ground Station 5 km perimeter.

### 5. Eurocontrol ASTERIX CAT 021 Serializer (Section 5.6)
- Serializes every validated ADS-B target report into binary CAT 021 frames (SAC 0x42, SIC 0x07, WGS-84 coordinates scaled to $180^\circ / 2^{23}$, Flight Level in 25 ft increments, IA-5 6-bit packed callsigns).

### 6. Wideband Spectrum Monitoring & Jammer Detection (Section 5.5)
- Computes FFT power spectrum sweeps across 1090 MHz and 137 MHz.
- Tracks dynamic noise floor and triggers high-priority defense alarms upon detecting broadband noise jamming, continuous wave (CW) overrides, or frequency sweeps.

---

## Directory Layout

```
trinetra_phase1/
├── .venv/                      # Python 3.14 virtual environment
├── requirements.txt            # Locked dependencies
├── README.md                   # Systems engineering & operational guide
├── backend/
│   ├── config.py               # Ground station coordinates & defense thresholds
│   ├── main.py                 # FastAPI master service + WebSockets
│   ├── analytics/
│   │   ├── kinematics.py       # Section 5.1 state vector & spoofing detector
│   │   ├── threat_assessment.py# Section 5.4 CPA / separation & geofencing
│   │   └── rf_spectrum.py      # Section 5.5 FFT spectrum & jammer detector
│   ├── protocols/
│   │   └── asterix_cat021.py   # Section 5.6 Eurocontrol CAT 021 binary serializer
│   └── simulators/
│       ├── air_domain_sim.py   # Mode-S / readsb flight telemetry generator
│       └── space_domain_sim.py # LEO weather satellite orbit, Doppler & link budget
├── frontend/
│   ├── index.html              # Defense C2 dashboard HUD layout
│   ├── styles.css              # Military-grade tactical dark styling
│   └── tactical_c2.js          # Canvas radar scope & WebSocket streaming client
└── tests/
    ├── test_kinematics.py      # Rigid-body physics & spoofing unit tests
    ├── test_space_orbit.py     # SGP4 orbit, Doppler, and link budget tests
    └── test_asterix.py         # Eurocontrol ASTERIX CAT 021 encoding tests
```

---

## Quickstart

### 1. Launch the TRINETRA C2 Station
From the project root:
```powershell
.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

### 2. Access the Tactical Dashboard
Open your browser at:
**`http://127.0.0.1:8000`**

### 3. Run Automated Tests
```powershell
.venv\Scripts\python -m unittest discover tests
```

---

## Interactive Threat Simulation Controls

In the bottom toolbar of the C2 dashboard, you can click:
1. **`⚡ INJECT HACKRF SPOOF`**: Injects an unauthenticated target that executes an impossible $8g$ vertical climb and $50\text{ m/s}^2$ lateral acceleration, demonstrating real-time quarantine.
2. **`⚠️ INJECT QNH TAMPER`**: Injects a target with barometric vs GPS altitude divergence of $> 2000\text{ ft}$, triggering the atmospheric pressure gradient anomaly detector.
3. **`⚔️ INJECT AIRSPACE CONFLICT`**: Injects two converging flights on a collision course ($< 2\text{ NM}$ separation), triggering the CPA threat warning.
4. **`🛡️ INJECT MESRA PERIMETER INCURSION`**: Spawns an unauthorized target breaching the 5 km security perimeter of the Mesra ground station.
5. **`📡 INJECT RF JAMMER`**: Simulates high-power broadband noise jamming that elevates the noise floor by 30 dB and triggers the electronic warfare warning.
6. **`🔄 RESET / CLEAR ALL`**: Clears all active threat scenarios and restores clean operational monitoring.
7. **`🔌 TOGGLE HARDWARE MODE`**: Switches ingestion source between internal simulation and physical `/run/readsb/aircraft.json` RAM disk.
