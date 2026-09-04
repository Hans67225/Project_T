/**
 * Project TRINETRA Phase 1 - Master Tactical C2 Interface Logic
 * Tactical Radio Intelligence Network for Electromagnetic Tracking Reconnaissance & Analysis
 * Ground Station: Mesra, Ranchi, Jharkhand (23.4123°N, 85.4399°E)
 * Integrated with Leaflet.js Interactive Tactical Base Map
 */

(function() {
  'use strict';

  // Station Coordinates
  const STATION_LAT = 23.4123;
  const STATION_LON = 85.4399;
  const KM_PER_NM = 1.852;
  const METERS_PER_NM = 1852.0;

  // State
  let telemetryData = null;
  let selectedAircraftHex = null;
  let isHardwareMode = false;
  const aircraftMarkers = {}; // hex -> L.marker

  // DOM Elements
  const canvasSpec1090 = document.getElementById('canvas-spec-1090');
  const ctxSpec1090 = canvasSpec1090.getContext('2d');
  const canvasSpec137 = document.getElementById('canvas-spec-137');
  const ctxSpec137 = canvasSpec137 ? canvasSpec137.getContext('2d') : null;

  const targetDrawer = document.getElementById('target-drawer');
  const btnCloseDrawer = document.getElementById('btn-close-drawer');
  const btnModeToggle = document.getElementById('btn-mode-toggle');
  const txtMode = document.getElementById('txt-mode');

  // Stats Elements
  const statAirTracks = document.getElementById('stat-air-tracks');
  const statQuarantined = document.getElementById('stat-quarantined');
  const statConflicts = document.getElementById('stat-conflicts');

  // Space Elements
  // Weather Satellite & Meteorological Elements
  const satActiveName = document.getElementById('sat-active-name');
  const satActiveFreq = document.getElementById('sat-active-freq');
  const satIngestBadge = document.getElementById('sat-ingest-badge');
  const satLineSync = document.getElementById('sat-line-sync');
  const satSnrVal = document.getElementById('sat-snr-val');
  const satPowerVal = document.getElementById('sat-power-val');

  const metStormBadge = document.getElementById('met-storm-badge');
  const metCloudTemp = document.getElementById('met-cloud-temp');
  const metSurfaceTemp = document.getElementById('met-surface-temp');
  const metMoisture = document.getElementById('met-moisture');
  const metCloudCover = document.getElementById('met-cloud-cover');
  const metCh1Albedo = document.getElementById('met-ch1-albedo');
  const metCh2Ndvi = document.getElementById('met-ch2-ndvi');
  const metCh4Temp = document.getElementById('met-ch4-temp');
  const jammerBadge = document.getElementById('jammer-badge');
  const specFloorInfo = document.getElementById('spec-floor-info');

  // Clocks
  function updateClocks() {
    const now = new Date();
    document.getElementById('clock-utc').innerText = now.toISOString().substring(11, 19) + 'Z';
    const istOffset = 5.5 * 60 * 60 * 1000;
    const istTime = new Date(now.getTime() + istOffset);
    document.getElementById('clock-ist').innerText = istTime.toISOString().substring(11, 19) + '+05:30';
  }
  setInterval(updateClocks, 1000);
  updateClocks();

  // =========================================================================
  // Leaflet Interactive Map Initialization
  // =========================================================================
  const map = L.map('map', {
    center: [STATION_LAT, STATION_LON],
    zoom: 7,
    zoomControl: false,
    attributionControl: false
  });

  // Official OpenStreetMap tile layer (reliable and universal)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  // Invalidate map size immediately to ensure full viewport fill
  setTimeout(() => map.invalidateSize(), 150);
  window.addEventListener('resize', () => map.invalidateSize());

  // Tactical Range Rings Layer (50, 100, 150, 200, 250 NM)
  const rangeRingsGroup = L.layerGroup().addTo(map);
  const rings = [50, 100, 150, 200, 250];

  rings.forEach(nm => {
    const radiusMeters = nm * METERS_PER_NM;
    L.circle([STATION_LAT, STATION_LON], {
      radius: radiusMeters,
      color: nm % 100 === 0 ? '#00f0ff' : '#334155',
      weight: 1,
      dashArray: '4, 6',
      fill: false,
      opacity: nm % 100 === 0 ? 0.45 : 0.25
    }).addTo(rangeRingsGroup);

    // Range Marker on northern edge of ring
    const latOffset = nm / 60.0;
    const marker = L.marker([STATION_LAT + latOffset, STATION_LON], {
      icon: L.divIcon({
        className: 'range-label-icon',
        html: `<span style="color: rgba(0, 240, 255, 0.6); font-size: 9px; font-family: 'JetBrains Mono'; font-weight: 700;">${nm} NM</span>`,
        iconSize: [40, 12],
        iconAnchor: [20, 6]
      })
    }).addTo(rangeRingsGroup);
  });

  // Ground Station Marker
  const stationIcon = L.divIcon({
    className: 'station-marker-icon',
    html: `
      <div style="display: flex; flex-direction: column; align-items: center;">
        <div class="station-pulse-pin"></div>
        <span class="station-label" style="margin-top: 4px;">GS MESRA (ASDA-01)</span>
      </div>
    `,
    iconSize: [120, 30],
    iconAnchor: [60, 5]
  });
  L.marker([STATION_LAT, STATION_LON], { icon: stationIcon }).addTo(map);

  // Mesra 5 km Security Buffer
  L.circle([STATION_LAT, STATION_LON], {
    radius: 5000,
    color: '#00f0ff',
    weight: 1.5,
    dashArray: '4, 4',
    fillColor: '#00f0ff',
    fillOpacity: 0.05
  }).addTo(map);

  // Ranchi Birsa Munda Airport (VERC) CTR Restricted Airspace
  const vercBounds = [
    [23.36, 85.27],
    [23.36, 85.38],
    [23.28, 85.38],
    [23.28, 85.27]
  ];
  L.polygon(vercBounds, {
    color: '#ffaa00',
    weight: 1.5,
    dashArray: '6, 3',
    fillColor: '#ffaa00',
    fillOpacity: 0.08
  }).addTo(map).bindTooltip('RANCHI VERC CTR RESTRICTED AIRSPACE', {
    permanent: false,
    className: 'tactical-tooltip'
  });

  // Zoom and Pan Controls
  document.getElementById('btn-zoom-in').addEventListener('click', () => map.zoomIn());
  document.getElementById('btn-zoom-out').addEventListener('click', () => map.zoomOut());
  document.getElementById('btn-reset-view').addEventListener('click', () => {
    map.setView([STATION_LAT, STATION_LON], 7);
  });

  // =========================================================================
  // Aircraft Marker Factory & Management
  // =========================================================================
  function createPlaneIcon(flight, hex, altBaro, speed, trackDeg, isQuarantined, isConflict, isSelected) {
    let colorHex = '#00ff88'; // Emerald green
    let colorClass = 'civil';
    if (isConflict) { colorHex = '#ffaa00'; colorClass = 'conflict'; }
    if (isQuarantined) { colorHex = '#ff2255'; colorClass = 'spoof'; }

    const fl = Math.round((altBaro || 0) / 100);
    const spd = Math.round(speed || 0);

    const html = `
      <div class="plane-marker-container" style="${isSelected ? 'filter: drop-shadow(0 0 10px #00f0ff);' : ''}">
        <svg class="plane-svg-icon ${colorClass}" width="28" height="28" style="transform: rotate(${trackDeg || 0}deg);" viewBox="0 0 24 24">
          <!-- Sleek Commercial Airliner Silhouette -->
          <path d="M12 2c-.5 0-.9.4-.9.9L10 9l-7 3.5v2l7-1.5v4.5l-2.5 1.8v1.2l3.5-1 3.5 1v-1.2L12 18.5V13l7 1.5v-2L12 9l-1-6.1c0-.5-.4-.9-.9-.9z" fill="${colorHex}" stroke="#000000" stroke-width="0.8"/>
        </svg>
        <div class="plane-datablock ${colorClass}">
          <strong>${flight}</strong> [FL${fl}] ${spd}kt
        </div>
      </div>
    `;

    return L.divIcon({
      className: 'custom-plane-divicon',
      html: html,
      iconSize: [100, 50],
      iconAnchor: [50, 14]
    });
  }

  function updateAircraftMapLayer(aircraftList) {
    const activeHexes = new Set();

    aircraftList.forEach(ac => {
      const lat = ac.lat;
      const lon = ac.lon;
      const hex = ac.hex;
      if (lat === undefined || lon === undefined || !hex) return;

      activeHexes.add(hex);
      const isQuarantined = ac.kinematics && ac.kinematics.is_spoofed;
      const isConflict = checkAircraftInConflict(hex);
      const isSelected = (selectedAircraftHex === hex);

      const icon = createPlaneIcon(
        ac.flight || 'UNKNOWN',
        hex,
        ac.alt_baro,
        ac.speed,
        ac.track,
        isQuarantined,
        isConflict,
        isSelected
      );

      if (aircraftMarkers[hex]) {
        // Move existing marker smoothly
        aircraftMarkers[hex].setLatLng([lat, lon]);
        aircraftMarkers[hex].setIcon(icon);
      } else {
        // Create new marker
        const marker = L.marker([lat, lon], { icon: icon }).addTo(map);
        marker.on('click', () => {
          selectAircraft(hex);
        });
        aircraftMarkers[hex] = marker;
      }
    });

    // Clean up markers that left radar coverage
    Object.keys(aircraftMarkers).forEach(hex => {
      if (!activeHexes.has(hex)) {
        map.removeLayer(aircraftMarkers[hex]);
        delete aircraftMarkers[hex];
      }
    });
  }

  function checkAircraftInConflict(hex) {
    if (!telemetryData || !telemetryData.alerts || !telemetryData.alerts.airspace_conflicts) return false;
    return telemetryData.alerts.airspace_conflicts.some(c => c.ac1_hex === hex || c.ac2_hex === hex);
  }

  function selectAircraft(hex) {
    selectedAircraftHex = hex;
    if (telemetryData && telemetryData.air_domain && telemetryData.air_domain.aircraft) {
      const found = telemetryData.air_domain.aircraft.find(a => a.hex === hex);
      if (found) {
        populateTargetDrawer(found);
        targetDrawer.classList.add('active');
        // Refresh icons to show selection highlight
        updateAircraftMapLayer(telemetryData.air_domain.aircraft);
      }
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

  btnCloseDrawer.addEventListener('click', () => {
    targetDrawer.classList.remove('active');
    selectedAircraftHex = null;
    if (telemetryData && telemetryData.air_domain) {
      updateAircraftMapLayer(telemetryData.air_domain.aircraft || []);
    }
  });

  // =========================================================================
  // RF Power Spectrum Visualizer
  // =========================================================================
  function drawSpectrum(canvasEl, ctxEl, sweepData, color) {
    if (!canvasEl || !ctxEl || !sweepData || !sweepData.power_dbm) return;
    const w = canvasEl.width;
    const h = canvasEl.height;
    ctxEl.clearRect(0, 0, w, h);

    const powers = sweepData.power_dbm;
    const minPower = -135;
    const maxPower = -40;

    // Grid lines
    ctxEl.strokeStyle = '#1a2234';
    ctxEl.lineWidth = 1;
    for (let y = 0; y < h; y += 18) {
      ctxEl.beginPath();
      ctxEl.moveTo(0, y);
      ctxEl.lineTo(w, y);
      ctxEl.stroke();
    }

    // Thermal Noise Floor Line (-119 dBm)
    const floorY = h - ((-119 - minPower) / (maxPower - minPower)) * h;
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

  // =========================================================================
  // Telemetry Updates Handler
  // =========================================================================
  function updateTelemetry(data) {
    telemetryData = data;

    // Header & Mode
    isHardwareMode = (data.mode === 'HARDWARE');
    txtMode.innerText = isHardwareMode ? 'MODE: HARDWARE (/run/readsb)' : 'MODE: SIMULATION';
    btnModeToggle.className = isHardwareMode ? 'btn-mode mode-hw' : 'btn-mode mode-sim';

    // Air Stats & Leaflet Map Layer
    if (data.air_domain) {
      statAirTracks.innerText = data.air_domain.total_tracks || 0;
      statQuarantined.innerText = data.air_domain.quarantined_count || 0;
      statConflicts.innerText = data.air_domain.threat_summary ? data.air_domain.threat_summary.conflicts_count : 0;

      updateAircraftMapLayer(data.air_domain.aircraft || []);

      if (selectedAircraftHex) {
        const found = (data.air_domain.aircraft || []).find(a => a.hex === selectedAircraftHex);
        if (found) populateTargetDrawer(found);
      }
    }

    // Weather Satellite & Meteorological Telemetry
    if (data.space_domain && satActiveName) {
      const sp = data.space_domain;
      const dl = sp.downlink || {};
      const met = sp.meteorological_telemetry || {};
      const ch = sp.sensor_channels || {};

      // Downlink Health
      satActiveName.innerText = `${sp.satellite_id} (${sp.sensor_payload || 'AVHRR'})`;
      satActiveFreq.innerText = `${dl.frequency_mhz?.toFixed(4) || '137.1000'} MHz ${dl.modulation || 'APT'}`;
      if (satIngestBadge) satIngestBadge.innerText = dl.carrier_state || 'CARRIER LOCKED';
      if (satLineSync) satLineSync.innerText = dl.line_sync_state || '2080 px/line (100% SYNC)';
      if (satSnrVal) satSnrVal.innerText = `${dl.snr_db || 19.4} dB`;
      if (satPowerVal) satPowerVal.innerText = `${dl.received_power_dbm || -99.6} dBm / ${dl.noise_floor_dbm || -119} dBm`;

      // Real-time Meteorological Readouts
      if (metCloudTemp) metCloudTemp.innerText = `${met.cloud_top_temperature_c > 0 ? '+' : ''}${met.cloud_top_temperature_c?.toFixed(1)}°C`;
      if (metSurfaceTemp) metSurfaceTemp.innerText = `+${met.surface_skin_temperature_c?.toFixed(1)}°C`;
      if (metMoisture) metMoisture.innerText = `${met.precipitable_water_moisture_mm?.toFixed(1)} mm`;
      if (metCloudCover) metCloudCover.innerText = `${met.regional_cloud_cover_pct?.toFixed(1)}%`;

      if (metStormBadge) {
        metStormBadge.innerText = (met.convective_status || 'NOMINAL').replace(/_/g, ' ');
        if (met.alert_level === 'WARNING') {
          metStormBadge.className = 'met-badge alert-warning';
        } else if (met.alert_level === 'ADVISORY') {
          metStormBadge.className = 'met-badge alert-advisory';
        } else {
          metStormBadge.className = 'met-badge alert-nominal';
        }
      }

      // Radiometer Spectral Channels
      if (metCh1Albedo && ch.ch1_visible) metCh1Albedo.innerText = `Albedo: ${ch.ch1_visible.measured_albedo_pct}%`;
      if (metCh2Ndvi && ch.ch2_near_ir) metCh2Ndvi.innerText = `NDVI: ${ch.ch2_near_ir.ndvi_index}`;
      if (metCh4Temp && ch.ch4_thermal_ir) metCh4Temp.innerText = `Brightness: ${ch.ch4_thermal_ir.brightness_temp_c}°C`;
    }

    // RF Spectrum & Jammer Status (Section 5.5)
    if (data.rf_spectrum) {
      const spec1090 = data.rf_spectrum.adsb_1090 || data.rf_spectrum;
      const isJammer = data.alerts && data.alerts.rf_jammer_alert;
      const jammerType = data.alerts ? data.alerts.jammer_details : 'SPECTRUM_NOMINAL';

      jammerBadge.className = isJammer ? 'jammer-status-badge jammed' : 'jammer-status-badge nominal';
      jammerBadge.innerText = isJammer ? `⚠️ EW DETECTED: ${jammerType}` : 'SPECTRUM NOMINAL';
      specFloorInfo.innerText = isJammer 
        ? `ALERT: Intentional Electromagnetic Interference Active!`
        : `NOISE FLOOR: -119.0 dBm | NO ACTIVE ELECTRONIC ATTACK`;

      drawSpectrum(canvasSpec1090, ctxSpec1090, spec1090, 'rgb(0, 240, 255)');
      if (ctxSpec137 && data.rf_spectrum.vhf_space_137) {
        drawSpectrum(canvasSpec137, ctxSpec137, data.rf_spectrum.vhf_space_137, 'rgb(168, 85, 247)');
      }
    }
  }

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

  // Modal Image Handling (if modal present)
  const imageModal = document.getElementById('image-modal');
  const btnViewImage = document.getElementById('btn-view-image');
  const btnCloseModal = document.getElementById('btn-close-modal');

  if (btnViewImage && imageModal) {
    btnViewImage.addEventListener('click', () => imageModal.classList.add('active'));
  }
  if (btnCloseModal && imageModal) {
    btnCloseModal.addEventListener('click', () => imageModal.classList.remove('active'));
    imageModal.addEventListener('click', e => {
      if (e.target === imageModal) imageModal.classList.remove('active');
    });
  }

  // WebSocket Connection
  function connectWebSocket() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${proto}//${window.location.host}/ws/telemetry`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('Tactical C2 WebSocket stream connected with Leaflet Map.');
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

  // Start WebSocket
  connectWebSocket();

})();
