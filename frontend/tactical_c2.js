/**
 * Project TRINETRA Phase 1 - Master Tactical C2 Interface Logic
 * Tactical Radio Intelligence Network for Electromagnetic Tracking Reconnaissance & Analysis
 * Ground Station: Mesra, Ranchi, Jharkhand (23.4123°N, 85.4399°E)
 */

(function() {
  'use strict';

  // Station Coordinates
  const STATION_LAT = 23.4123;
  const STATION_LON = 85.4399;
  const NM_PER_DEG_LAT = 60.0;
  const KM_PER_NM = 1.852;

  // State
  let telemetryData = null;
  let selectedAircraftHex = null;
  let isHardwareMode = false;

  // Radar Viewport State
  let radarScale = 1.8; // Pixels per Nautical Mile
  let radarCenterLat = STATION_LAT;
  let radarCenterLon = STATION_LON;
  let sweepAngle = 0; // Radians for radar sweep animation
  const aircraftTrails = {}; // hex -> [{lat, lon, time}]

  // DOM Elements
  const canvas = document.getElementById('radar-canvas');
  const ctx = canvas.getContext('2d');
  const radarContainer = document.getElementById('radar-container');

  const canvasSpec1090 = document.getElementById('canvas-spec-1090');
  const ctxSpec1090 = canvasSpec1090.getContext('2d');
  const canvasSpec137 = document.getElementById('canvas-spec-137');
  const ctxSpec137 = canvasSpec137.getContext('2d');

  const targetDrawer = document.getElementById('target-drawer');
  const btnCloseDrawer = document.getElementById('btn-close-drawer');
  const btnModeToggle = document.getElementById('btn-mode-toggle');
  const txtMode = document.getElementById('txt-mode');

  // Stats Elements
  const statAirTracks = document.getElementById('stat-air-tracks');
  const statQuarantined = document.getElementById('stat-quarantined');
  const statConflicts = document.getElementById('stat-conflicts');

  // Space Elements
  const satActiveName = document.getElementById('sat-active-name');
  const satActiveFreq = document.getElementById('sat-active-freq');
  const satSubPos = document.getElementById('sat-sub-pos');
  const satAzEl = document.getElementById('sat-az-el');
  const satSlantRange = document.getElementById('sat-slant-range');
  const satDopplerVal = document.getElementById('sat-doppler-val');
  const satRxFreq = document.getElementById('sat-rx-freq');
  const satRigctlStep = document.getElementById('sat-rigctl-step');
  const satFreqMarker = document.getElementById('sat-freq-marker');
  const satSnrBadge = document.getElementById('sat-snr-badge');
  const lbLfs = document.getElementById('lb-lfs');
  const lbPr = document.getElementById('lb-pr');
  const jammerBadge = document.getElementById('jammer-badge');
  const specFloorInfo = document.getElementById('spec-floor-info');

  // Clocks
  function updateClocks() {
    const now = new Date();
    document.getElementById('clock-utc').innerText = now.toISOString().substring(11, 19) + 'Z';
    // Indian Standard Time (UTC+05:30)
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + istOffset);
    document.getElementById('clock-ist').innerText = istTime.toISOString().substring(11, 19) + '+05:30';
  }
  setInterval(updateClocks, 1000);
  updateClocks();

  // Resize Canvas to fit container
  function resizeCanvas() {
    const rect = radarContainer.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;
  }
  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();

  // Coordinate transforms: Geodetic -> Radar Screen Pixels
  function geoToRadar(lat, lon) {
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    
    const dLat = lat - radarCenterLat;
    const dLon = lon - radarCenterLon;
    
    // Convert to Nautical Miles
    const dLatNm = dLat * NM_PER_DEG_LAT;
    const dLonNm = dLon * NM_PER_DEG_LAT * Math.cos((STATION_LAT * Math.PI) / 180.0);
    
    // Screen coords: x = East (positive right), y = North (negative up)
    const screenX = cx + dLonNm * radarScale;
    const screenY = cy - dLatNm * radarScale;
    return { x: screenX, y: screenY };
  }

  function radarToGeo(x, y) {
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;
    
    const dLonNm = (x - cx) / radarScale;
    const dLatNm = (cy - y) / radarScale;
    
    const dLat = dLatNm / NM_PER_DEG_LAT;
    const dLon = dLonNm / (NM_PER_DEG_LAT * Math.cos((STATION_LAT * Math.PI) / 180.0));
    return { lat: radarCenterLat + dLat, lon: radarCenterLon + dLon };
  }

  // Draw Air Domain Radar Scope
  function drawRadar() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const cx = canvas.width / 2;
    const cy = canvas.height / 2;

    // 1. Concentric Range Rings (50, 100, 150, 200, 250 NM)
    const rings = [50, 100, 150, 200, 250];
    ctx.lineWidth = 1;
    ctx.font = '10px "JetBrains Mono"';

    rings.forEach(rangeNm => {
      const radiusPx = rangeNm * radarScale;
      ctx.strokeStyle = rangeNm % 100 === 0 ? 'rgba(0, 240, 255, 0.25)' : 'rgba(30, 41, 59, 0.7)';
      ctx.beginPath();
      ctx.arc(cx, cy, radiusPx, 0, Math.PI * 2);
      ctx.stroke();

      // Range Label
      ctx.fillStyle = 'rgba(0, 240, 255, 0.5)';
      ctx.fillText(`${rangeNm} NM`, cx + 4, cy - radiusPx + 12);
    });

    // 2. Azimuth Radial Spokes (every 30 degrees)
    for (let deg = 0; deg < 360; deg += 30) {
      const rad = (deg - 90) * (Math.PI / 180);
      const maxR = 250 * radarScale;
      const x2 = cx + Math.cos(rad) * maxR;
      const y2 = cy + Math.sin(rad) * maxR;

      ctx.strokeStyle = deg % 90 === 0 ? 'rgba(0, 240, 255, 0.2)' : 'rgba(30, 41, 59, 0.4)';
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(x2, y2);
      ctx.stroke();

      // Heading Text on edge
      const labelX = cx + Math.cos(rad) * (maxR - 15);
      const labelY = cy + Math.sin(rad) * (maxR - 15);
      ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
      ctx.fillText(`${String(deg).padStart(3, '0')}°`, labelX - 10, labelY + 4);
    }

    // 3. Mesra Ground Station Security Perimeter (5 km buffer)
    const mesra5kmNm = 5.0 / KM_PER_NM;
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.8)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.arc(cx, cy, mesra5kmNm * radarScale, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Station Symbol
    ctx.fillStyle = '#00f0ff';
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = 'bold 9px "JetBrains Mono"';
    ctx.fillText('GS MESRA (ASDA-01)', cx + 8, cy + 12);

    // 4. Ranchi Birsa Munda Airport VERC CTR Restricted Airspace Boundary
    const vercBounds = [
      { lat: 23.36, lon: 85.27 },
      { lat: 23.36, lon: 85.38 },
      { lat: 23.28, lon: 85.38 },
      { lat: 23.28, lon: 85.27 }
    ];
    ctx.strokeStyle = 'rgba(255, 170, 0, 0.8)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([6, 3]);
    ctx.beginPath();
    vercBounds.forEach((pt, i) => {
      const scr = geoToRadar(pt.lat, pt.lon);
      if (i === 0) ctx.moveTo(scr.x, scr.y);
      else ctx.lineTo(scr.x, scr.y);
    });
    ctx.closePath();
    ctx.stroke();
    ctx.setLineDash([]);
    const vercLabelPt = geoToRadar(23.36, 85.27);
    ctx.fillStyle = 'rgba(255, 170, 0, 0.9)';
    ctx.fillText('RANCHI VERC CTR', vercLabelPt.x + 4, vercLabelPt.y - 4);

    // 5. Rotating Radar Sweep Beam with Phosphor Fade
    sweepAngle = (sweepAngle + 0.02) % (Math.PI * 2);
    const sweepRadius = 250 * radarScale;
    const gradient = ctx.createRadialGradient(cx, cy, 10, cx, cy, sweepRadius);
    gradient.addColorStop(0, 'rgba(0, 240, 255, 0.25)');
    gradient.addColorStop(1, 'rgba(0, 240, 255, 0.0)');

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, sweepRadius, sweepAngle - 0.25, sweepAngle);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Leading edge beam
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.8)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(sweepAngle) * sweepRadius, cy + Math.sin(sweepAngle) * sweepRadius);
    ctx.stroke();
    ctx.restore();

    // 6. Draw Aircraft Tracks
    if (telemetryData && telemetryData.air_domain && telemetryData.air_domain.aircraft) {
      const aircraftList = telemetryData.air_domain.aircraft;

      aircraftList.forEach(ac => {
        const lat = ac.lat;
        const lon = ac.lon;
        if (lat === undefined || lon === undefined) return;

        const scr = geoToRadar(lat, lon);
        const hex = ac.hex;
        const flight = ac.flight || 'UNKNOWN';
        const altBaro = ac.alt_baro || 0;
        const speed = ac.speed || 0;
        const trackDeg = ac.track || 0;
        const squawk = ac.squawk || '----';

        const isQuarantined = ac.kinematics && ac.kinematics.is_spoofed;
        const isConflict = checkAircraftInConflict(hex);
        const isSelected = selectedAircraftHex === hex;

        // Record history trail
        if (!aircraftTrails[hex]) aircraftTrails[hex] = [];
        aircraftTrails[hex].push({ x: scr.x, y: scr.y, time: Date.now() });
        if (aircraftTrails[hex].length > 10) aircraftTrails[hex].shift();

        // Draw Trail dots
        ctx.fillStyle = isQuarantined ? 'rgba(255, 34, 85, 0.4)' : 'rgba(0, 255, 136, 0.3)';
        aircraftTrails[hex].forEach((trailPt, idx) => {
          const sz = (idx / 10) * 3;
          ctx.beginPath();
          ctx.arc(trailPt.x, trailPt.y, sz, 0, Math.PI * 2);
          ctx.fill();
        });

        // Determine Color Scheme
        let trackColor = '#00ff88'; // Emerald green normal civil
        if (isConflict) trackColor = '#ffaa00'; // Amber alert
        if (isQuarantined) trackColor = '#ff2255'; // Threat Red

        // Quarantined Pulsing Ring
        if (isQuarantined) {
          ctx.strokeStyle = 'rgba(255, 34, 85, 0.8)';
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          const pulseR = 12 + Math.sin(Date.now() / 150) * 4;
          ctx.arc(scr.x, scr.y, pulseR, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Selection Ring
        if (isSelected) {
          ctx.strokeStyle = '#00f0ff';
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(scr.x, scr.y, 16, 0, Math.PI * 2);
          ctx.stroke();
        }

        // Target Symbol (Directional Chevron)
        ctx.save();
        ctx.translate(scr.x, scr.y);
        ctx.rotate((trackDeg * Math.PI) / 180.0);

        ctx.strokeStyle = trackColor;
        ctx.fillStyle = trackColor;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, -9);
        ctx.lineTo(6, 6);
        ctx.lineTo(0, 2);
        ctx.lineTo(-6, 6);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Velocity Leader Line (30 second extrapolation)
        const leaderLen = (speed / 10) * radarScale * 0.15;
        ctx.beginPath();
        ctx.moveTo(0, -9);
        ctx.lineTo(0, -9 - leaderLen);
        ctx.stroke();
        ctx.restore();

        // Tactical Datablock Tag
        ctx.font = '10px "JetBrains Mono"';
        ctx.fillStyle = trackColor;
        const tagX = scr.x + 12;
        const tagY = scr.y - 12;

        ctx.fillText(`${flight} [${hex}]`, tagX, tagY);
        ctx.fillStyle = '#94a3b8';
        ctx.fillText(`FL${Math.round(altBaro / 100)} ${Math.round(speed)}kt SQ${squawk}`, tagX, tagY + 12);

        if (isQuarantined) {
          ctx.fillStyle = '#ff2255';
          ctx.fillText(`[QUARANTINED SPOOF]`, tagX, tagY + 24);
        } else if (isConflict) {
          ctx.fillStyle = '#ffaa00';
          ctx.fillText(`[SEPARATION ALERT]`, tagX, tagY + 24);
        }
      });
    }

    requestAnimationFrame(drawRadar);
  }

  function checkAircraftInConflict(hex) {
    if (!telemetryData || !telemetryData.alerts || !telemetryData.alerts.airspace_conflicts) return false;
    return telemetryData.alerts.airspace_conflicts.some(c => c.ac1_hex === hex || c.ac2_hex === hex);
  }

  // Draw RF Power Spectrum Canvas
  function drawSpectrum(canvasEl, ctxEl, sweepData, color) {
    if (!sweepData || !sweepData.power_dbm) return;
    const w = canvasEl.width;
    const h = canvasEl.height;
    ctxEl.clearRect(0, 0, w, h);

    const powers = sweepData.power_dbm;
    const minPower = -135;
    const maxPower = -40;

    // Background grid
    ctxEl.strokeStyle = '#1a2234';
    ctxEl.lineWidth = 1;
    for (let y = 0; y < h; y += 18) {
      ctxEl.beginPath();
      ctxEl.moveTo(0, y);
      ctxEl.lineTo(w, y);
      ctxEl.stroke();
    }

    // Thermal Noise Floor Line (-119 dBm)
    const floorY = h - (( -119 - minPower) / (maxPower - minPower)) * h;
    ctxEl.strokeStyle = 'rgba(100, 116, 139, 0.7)';
    ctxEl.setLineDash([4, 4]);
    ctxEl.beginPath();
    ctxEl.moveTo(0, floorY);
    ctxEl.lineTo(w, floorY);
    ctxEl.stroke();
    ctxEl.setLineDash([]);

    // FFT Curve
    ctxEl.beginPath();
    powers.forEach((p, i) => {
      const x = (i / (powers.length - 1)) * w;
      const y = h - ((p - minPower) / (maxPower - minPower)) * h;
      if (i === 0) ctxEl.moveTo(x, y);
      else ctxEl.lineTo(x, y);
    });

    ctxEl.strokeStyle = color;
    ctxEl.lineWidth = 1.5;
    ctxEl.stroke();

    // Fill under curve
    ctxEl.lineTo(w, h);
    ctxEl.lineTo(0, h);
    ctxEl.closePath();
    ctxEl.fillStyle = color.replace(')', ', 0.15)').replace('rgb', 'rgba');
    ctxEl.fill();
  }

  // Update Telemetry Displays
  function updateTelemetry(data) {
    telemetryData = data;

    // Header & Mode
    isHardwareMode = (data.mode === 'HARDWARE');
    txtMode.innerText = isHardwareMode ? 'MODE: HARDWARE (/run/readsb)' : 'MODE: SIMULATION';
    btnModeToggle.className = isHardwareMode ? 'btn-mode mode-hw' : 'btn-mode mode-sim';

    // Air Stats
    if (data.air_domain) {
      statAirTracks.innerText = data.air_domain.total_tracks || 0;
      statQuarantined.innerText = data.air_domain.quarantined_count || 0;
      statConflicts.innerText = data.air_domain.threat_summary ? data.air_domain.threat_summary.conflicts_count : 0;

      // Update Target Drawer if open
      if (selectedAircraftHex) {
        const found = data.air_domain.aircraft.find(a => a.hex === selectedAircraftHex);
        if (found) populateTargetDrawer(found);
      }
    }

    // Space Domain Interceptor
    if (data.space_domain) {
      const sp = data.space_domain;
      satActiveName.innerText = `${sp.active_satellite} (NORAD ${sp.norad_id})`;
      satActiveFreq.innerText = `${sp.kinematics.nominal_freq_mhz.toFixed(4)} MHz ${sp.mode}`;
      satSubPos.innerText = `${sp.subsatellite_lat.toFixed(2)}°N, ${sp.subsatellite_lon.toFixed(2)}°E`;
      satAzEl.innerText = `${sp.kinematics.azimuth_deg}° / ${sp.kinematics.elevation_deg}°`;
      satSlantRange.innerText = `${sp.kinematics.slant_range_km} km`;

      // Doppler
      const dKhz = sp.kinematics.doppler_shift_hz / 1000.0;
      satDopplerVal.innerText = `Δf: ${dKhz > 0 ? '+' : ''}${dKhz.toFixed(2)} kHz`;
      satRxFreq.innerText = `${sp.kinematics.rx_corrected_freq_mhz.toFixed(6)} MHz`;
      satRigctlStep.innerText = `${sp.kinematics.rigctl_step_khz.toFixed(2)} kHz`;

      // Doppler S-Curve marker position (-4.5 to +4.5 kHz range)
      const markerPct = Math.max(5, Math.min(95, 50 + (dKhz / 4.5) * 45));
      satFreqMarker.style.left = `${markerPct}%`;

      // Link Budget (Section 4.2)
      lbLfs.innerText = `${sp.kinematics.free_space_loss_db} dB`;
      lbPr.innerText = `${sp.kinematics.received_power_dbm} dBm`;
      satSnrBadge.innerText = `SNR: ${sp.kinematics.snr_db} dB`;
    }

    // RF Spectrum & Jammer Status (Section 5.5)
    if (data.rf_spectrum) {
      const isJammer = data.alerts && data.alerts.rf_jammer_alert;
      const jammerType = data.alerts ? data.alerts.jammer_details : 'SPECTRUM_NOMINAL';

      jammerBadge.className = isJammer ? 'jammer-status-badge jammed' : 'jammer-status-badge nominal';
      jammerBadge.innerText = isJammer ? `⚠️ EW DETECTED: ${jammerType}` : 'SPECTRUM NOMINAL';
      specFloorInfo.innerText = isJammer 
        ? `ALERT: Intentional Electromagnetic Interference Active!`
        : `NOISE FLOOR: -119.0 dBm | NO ACTIVE ELECTRONIC ATTACK`;

      drawSpectrum(canvasSpec1090, ctxSpec1090, data.rf_spectrum.adsb_1090, 'rgb(0, 240, 255)');
      drawSpectrum(canvasSpec137, ctxSpec137, data.rf_spectrum.vhf_space_137, 'rgb(168, 85, 247)');
    }
  }

  // Populate Target Drawer
  function populateTargetDrawer(ac) {
    document.getElementById('det-hex').innerText = `HEX: ${ac.hex}`;
    document.getElementById('det-callsign').innerText = `CALLSIGN: ${ac.flight || 'UNKNOWN'}`;

    const kine = ac.kinematics || {};
    const statusBadge = document.getElementById('det-status-badge');
    if (kine.is_spoofed) {
      statusBadge.className = 'target-badge spoof';
      statusBadge.innerText = `QUARANTINED SPOOF [${(kine.anomalies || []).join(', ')}]`;
    } else {
      statusBadge.className = 'target-badge';
      statusBadge.innerText = 'STATUS: VALID COOPERATIVE';
    }

    document.getElementById('det-pos').innerText = `${ac.lat?.toFixed(4)}°N, ${ac.lon?.toFixed(4)}°E (X:${kine.enu_x_km}km, Y:${kine.enu_y_km}km)`;
    document.getElementById('det-alt').innerText = `${ac.alt_baro} ft / ${ac.alt_geom} ft`;
    document.getElementById('det-qnh').innerText = `${kine.alt_divergence_ft || 0} ft`;
    document.getElementById('det-spd').innerText = `${ac.speed} kts / ${ac.track}°`;
    document.getElementById('det-accel').innerText = `${kine.accel_total_ms2 || 0} m/s² (Lat: ${kine.accel_lateral_ms2 || 0} m/s²)`;
    document.getElementById('det-jerk').innerText = `${kine.jerk_ms3 || 0} m/s³`;
    document.getElementById('det-vert').innerText = `${ac.vert_rate} fpm (${kine.accel_vertical_ms2 || 0} m/s²)`;

    // ASTERIX CAT 021
    if (ac.asterix_cat021) {
      const ast = ac.asterix_cat021;
      document.getElementById('det-asterix-sac').innerText = `${ast.breakdown.sac_sic} (India / Mesra)`;
      document.getElementById('det-asterix-addr').innerText = ast.breakdown.icao_hex;
      document.getElementById('det-asterix-fl').innerText = `FL${ast.breakdown.flight_level}`;
      document.getElementById('det-asterix-len').innerText = `${ast.breakdown.length_bytes} bytes`;
      document.getElementById('det-asterix-hex').innerText = formatHexStream(ast.hex_stream);
    }
  }

  function formatHexStream(hex) {
    if (!hex) return 'NO ASTERIX DATA';
    return hex.match(/.{1,2}/g).join(' ');
  }

  // Click on Radar Canvas to select Aircraft
  canvas.addEventListener('click', e => {
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    if (!telemetryData || !telemetryData.air_domain || !telemetryData.air_domain.aircraft) return;

    let closest = null;
    let minD = 25; // 25 px radius

    telemetryData.air_domain.aircraft.forEach(ac => {
      if (ac.lat === undefined || ac.lon === undefined) return;
      const scr = geoToRadar(ac.lat, ac.lon);
      const d = Math.hypot(clickX - scr.x, clickY - scr.y);
      if (d < minD) {
        minD = d;
        closest = ac;
      }
    });

    if (closest) {
      selectedAircraftHex = closest.hex;
      populateTargetDrawer(closest);
      targetDrawer.classList.add('active');
    }
  });

  btnCloseDrawer.addEventListener('click', () => {
    targetDrawer.classList.remove('active');
    selectedAircraftHex = null;
  });

  // Radar Zoom & Pan Controls
  document.getElementById('btn-zoom-in').addEventListener('click', () => {
    radarScale = Math.min(6.0, radarScale * 1.3);
  });
  document.getElementById('btn-zoom-out').addEventListener('click', () => {
    radarScale = Math.max(0.6, radarScale / 1.3);
  });
  document.getElementById('btn-reset-view').addEventListener('click', () => {
    radarScale = 1.8;
    radarCenterLat = STATION_LAT;
    radarCenterLon = STATION_LON;
  });

  // Modal Image Handling
  const imageModal = document.getElementById('image-modal');
  document.getElementById('btn-view-image').addEventListener('click', () => {
    imageModal.classList.add('active');
  });
  document.getElementById('btn-close-modal').addEventListener('click', () => {
    imageModal.classList.remove('active');
  });
  imageModal.addEventListener('click', e => {
    if (e.target === imageModal) imageModal.classList.remove('active');
  });

  // Scenario Injection API Calls
  async function triggerScenario(name) {
    try {
      const res = await fetch('/api/scenario/inject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario: name })
      });
      const result = await res.json();
      console.log('Scenario Triggered:', result);
    } catch (err) {
      console.error('Failed to trigger scenario:', err);
    }
  }

  document.getElementById('btn-inject-hackrf').addEventListener('click', () => triggerScenario('HACKRF_SPOOF'));
  document.getElementById('btn-inject-qnh').addEventListener('click', () => triggerScenario('QNH_TAMPER'));
  document.getElementById('btn-inject-conflict').addEventListener('click', () => triggerScenario('SEPARATION_CONFLICT'));
  document.getElementById('btn-inject-incursion').addEventListener('click', () => triggerScenario('GEOFENCE_INCURSION'));
  document.getElementById('btn-inject-jammer').addEventListener('click', () => triggerScenario('JAMMER_BROADBAND'));
  document.getElementById('btn-clear-threats').addEventListener('click', () => triggerScenario('CLEAR'));

  // Toggle Mode (Simulation vs Hardware)
  btnModeToggle.addEventListener('click', async () => {
    const nextMode = isHardwareMode ? 'SIMULATION' : 'HARDWARE';
    try {
      const res = await fetch('/api/config/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: nextMode })
      });
      const result = await res.json();
      isHardwareMode = (result.current_mode === 'HARDWARE');
      txtMode.innerText = isHardwareMode ? 'MODE: HARDWARE (/run/readsb)' : 'MODE: SIMULATION';
      btnModeToggle.className = isHardwareMode ? 'btn-mode mode-hw' : 'btn-mode mode-sim';
    } catch (err) {
      console.error('Failed to switch mode:', err);
    }
  });

  // WebSocket Connection with Polling Fallback
  function connectWebSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${window.location.host}/ws/telemetry`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('Tactical C2 WebSocket stream connected.');
    };

    ws.onmessage = evt => {
      try {
        const data = JSON.parse(evt.data);
        updateTelemetry(data);
      } catch (e) {
        console.error('JSON parsing error on telemetry message:', e);
      }
    };

    ws.onclose = () => {
      console.warn('WebSocket stream closed. Reconnecting in 2 seconds...');
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = err => {
      console.error('WebSocket error:', err);
      ws.close();
    };
  }

  // Fallback Polling (in case WebSocket is blocked)
  async function pollFallback() {
    try {
      const airRes = await fetch('/api/air/aircraft');
      const airData = await airRes.json();
      const spaceRes = await fetch('/api/space/telemetry');
      const spaceData = await spaceRes.json();
      const specRes = await fetch('/api/rf/spectrum');
      const specData = await specRes.json();

      updateTelemetry({
        air_domain: airData,
        space_domain: spaceData,
        rf_spectrum: specData,
        alerts: {
          quarantined_spoofs: [],
          airspace_conflicts: airData.threat_summary ? airData.threat_summary.conflicts : [],
          rf_jammer_alert: specData.adsb_1090.jammer_detected,
          jammer_details: specData.adsb_1090.jammer_classification
        }
      });
    } catch (e) {
      // Offline/connecting
    }
  }

  // Start Loops
  connectWebSocket();
  drawRadar();

})();
