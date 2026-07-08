import { useEffect, useMemo, useRef, useState } from "react";
import { api, WS_URL } from "./api/client";
import AlertPanel from "./components/AlertPanel.jsx";
import CameraSelector from "./components/CameraSelector.jsx";
import DevicePanel from "./components/DevicePanel.jsx";
import EventHistory from "./components/EventHistory.jsx";
import LiveMonitor from "./components/LiveMonitor.jsx";
import PersonStatusTable from "./components/PersonStatusTable.jsx";
import PlaybackPanel from "./components/PlaybackPanel.jsx";
import SerialMonitor from "./components/SerialMonitor.jsx";

const fallbackCameras = [
  { camera_id: "camera_1", name: "Camera 1", role: "Danger Zone + Helmet", status: "IDLE" },
  { camera_id: "camera_2", name: "Camera 2", role: "Danger Zone Only", status: "IDLE" },
  { camera_id: "camera_3", name: "Camera 3", role: "Helmet Compliance", status: "IDLE" }
];

const severityRank = {
  critical: 4,
  high: 3,
  warning: 2,
  normal: 1
};

function comparePersonRisk(a, b) {
  const severityDelta = (severityRank[b.severity] || 0) - (severityRank[a.severity] || 0);
  if (severityDelta !== 0) return severityDelta;
  const riskDelta = Number(b.risk || 0) - Number(a.risk || 0);
  if (riskDelta !== 0) return riskDelta;
  return Number(b.duration || 0) - Number(a.duration || 0);
}

function personToDecisionEvent(person, cameraId) {
  if (!person) return null;
  return {
    camera_id: person.camera_id || cameraId,
    track_id: person.id,
    risk_score: person.risk || 0,
    severity: person.severity || "normal",
    reasons: person.reasons || [],
    actions: person.actions || [],
    details: {
      ...(person.details || {}),
      event_state: person.status || "CURRENT",
      violation_type:
        person.details?.violation_type ||
        (person.details?.ppe_warning ? "ppe_warning" : null) ||
        (person.ppe_state === "no_helmet" ? "no_helmet" : person.zone_state === "IN_ZONE" ? "danger_zone" : "none"),
      violation_duration_seconds: person.duration || 0,
      ppe_state: person.ppe_state,
      zone_state: person.zone_state
    },
    zone_name: person.zone_state || "N/A",
    helmet_state: { ppe_state: person.ppe_state },
    is_fresh: true,
    age_seconds: 0
  };
}

function beep() {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const ctx = new AudioContext();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "square";
  osc.frequency.value = 820;
  gain.gain.value = 0.04;
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  setTimeout(() => {
    osc.stop();
    ctx.close();
  }, 180);
}

export default function App() {
  const [cameras, setCameras] = useState(fallbackCameras);
  const [selectedCamera, setSelectedCamera] = useState("");
  const [live, setLive] = useState({ cameras: {}, device_status: {}, serial_tail: [] });
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [activatingCamera, setActivatingCamera] = useState("");
  const [backendOnline, setBackendOnline] = useState(false);
  const [muted, setMuted] = useState(false);
  const [refreshToken, setRefreshToken] = useState(Date.now());
  const lastCriticalRef = useRef(null);
  const selectedCameraRef = useRef(selectedCamera);
  const mutedRef = useRef(muted);

  useEffect(() => {
    selectedCameraRef.current = selectedCamera;
  }, [selectedCamera]);

  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  async function loadInitial() {
    try {
      const [cameraRes, eventRes, deviceRes, logRes] = await Promise.all([
        api.get("/api/cameras"),
        api.get("/api/events/recent?limit=100"),
        api.get("/api/devices/status"),
        api.get("/api/logs/serial?tail=100")
      ]);
      setCameras(cameraRes.data);
      setEvents(eventRes.data);
      const cameraMap = Object.fromEntries(
        cameraRes.data.map((camera) => [
          camera.camera_id,
          {
            status: camera.status,
            pid: camera.pid,
            latest_event: camera.latest_event,
            latest_frame_url: camera.latest_frame_url
          }
        ])
      );
      setLive((prev) => ({
        ...prev,
        cameras: cameraMap,
        device_status: deviceRes.data,
        serial_tail: logRes.data.lines || []
      }));
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }

  useEffect(() => {
    loadInitial();
    let closedByComponent = false;
    const socket = new WebSocket(WS_URL);
    socket.onopen = () => setBackendOnline(true);
    socket.onmessage = (message) => {
      const payload = JSON.parse(message.data);
      if (payload.type !== "dashboard_update") return;
      setLive(payload);
      setRefreshToken(Date.now());
      const selectedEvent = payload.cameras?.[selectedCameraRef.current]?.latest_event;
      if (!mutedRef.current && selectedEvent?.is_fresh && selectedEvent?.severity === "critical") {
        const eventKey = selectedEvent.timestamp;
        if (eventKey && eventKey !== lastCriticalRef.current) {
          lastCriticalRef.current = eventKey;
          beep();
        }
      }
    };
    socket.onerror = () => setBackendOnline(false);
    socket.onclose = () => {
      if (!closedByComponent) setBackendOnline(false);
    };
    const historyTimer = setInterval(async () => {
      try {
        const res = await api.get("/api/events/recent?limit=100");
        setEvents(res.data);
      } catch {
        setBackendOnline(false);
      }
    }, 3000);
    return () => {
      closedByComponent = true;
      socket.close();
      clearInterval(historyTimer);
    };
  }, []);

  async function cameraAction(action, cameraId = selectedCamera) {
    if (!cameraId) return;
    setBusy(true);
    try {
      const res = await api.post(`/api/cameras/${cameraId}/${action}`);
      setLive((prev) => ({
        ...prev,
        cameras: {
          ...(prev.cameras || {}),
          [cameraId]: {
            ...(prev.cameras?.[cameraId] || {}),
            status: res.data.status,
            pid: res.data.pid,
            latest_event: res.data.latest_event
          }
        }
      }));
      await loadInitial();
    } finally {
      setBusy(false);
    }
  }

  async function activateCamera(cameraId) {
    if (!cameraId) return;
    setSelectedCamera(cameraId);
    selectedCameraRef.current = cameraId;
    setActivatingCamera(cameraId);
    setBusy(true);
    try {
      const res = await api.post(`/api/cameras/${cameraId}/activate`);
      setCameras((prev) => prev.map((camera) => ({
        ...camera,
        status: camera.camera_id === cameraId ? res.data.status : "IDLE",
        pid: camera.camera_id === cameraId ? res.data.pid : null
      })));
      setLive((prev) => {
        const nextCameras = Object.fromEntries(
          Object.entries(prev.cameras || {}).map(([id, camera]) => [
            id,
            {
              ...camera,
              status: id === cameraId ? res.data.status : "IDLE",
              pid: id === cameraId ? res.data.pid : null,
              latest_event: id === cameraId ? res.data.latest_event : null,
              person_status: id === cameraId ? camera.person_status : { camera_id: id, persons: [] }
            }
          ])
        );
        nextCameras[cameraId] = {
          ...(nextCameras[cameraId] || {}),
          status: res.data.status,
          pid: res.data.pid,
          latest_event: res.data.latest_event
        };
        return { ...prev, cameras: nextCameras };
      });
      await loadInitial();
    } finally {
      setActivatingCamera("");
      setBusy(false);
    }
  }

  async function resetRealtimeState() {
    setBusy(true);
    try {
      await api.post("/api/system/reset-realtime-state?clear_history=true");
      setEvents([]);
      setLive({ cameras: {}, device_status: {}, serial_tail: [] });
      await loadInitial();
    } finally {
      setBusy(false);
    }
  }

  const selectedCameraInfo = useMemo(
    () => cameras.find((camera) => camera.camera_id === selectedCamera) || {
      camera_id: "",
      name: "No Camera Selected",
      role: "Select a camera to activate monitoring",
      status: "IDLE"
    },
    [cameras, selectedCamera]
  );
  const selectedLive = live.cameras?.[selectedCamera] || {};
  const selectedEvent = selectedLive.latest_event;
  const selectedPersons = [...(selectedLive.person_status?.persons || [])].sort(comparePersonRisk);
  const highestRiskPerson = selectedPersons[0] || null;
  const currentDecision = highestRiskPerson ? personToDecisionEvent(highestRiskPerson, selectedCamera) : selectedEvent;
  const selectedIsActive = selectedLive.status === "ACTIVE";
  const selectedIsStarting = activatingCamera === selectedCamera;
  const activeAlerts = Object.values(live.cameras || {}).filter((camera) => {
    const event = camera.latest_event;
    return event?.is_fresh && ["high", "critical"].includes(event?.severity);
  }).length;
  const criticalEvents = events.filter((event) => event.severity === "critical").length;
  const deviceOnCount = Object.values(live.device_status || {}).reduce((count, state) => {
    return count + ["relay", "buzzer", "warning_light"].filter((key) => state?.[key] === "ON").length;
  }, 0);

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <h1>Factory Safety AI Monitoring Dashboard</h1>
          <p>AI Safety Risk Scoring & IoT Device Simulation</p>
        </div>
        <div className={backendOnline ? "backend online" : "backend offline"}>
          Backend {backendOnline ? "ONLINE" : "OFFLINE"}
        </div>
      </header>

      <section className="metrics">
        <div><span>Total Events</span><strong>{events.length}</strong></div>
        <div><span>Active Alerts</span><strong>{activeAlerts}</strong></div>
        <div><span>Critical Events</span><strong>{criticalEvents}</strong></div>
        <div><span>Device ON Count</span><strong>{deviceOnCount}</strong></div>
        <div><span>Selected Camera</span><strong>{selectedCameraInfo.name}</strong></div>
      </section>

      <CameraSelector
        cameras={cameras}
        selectedCamera={selectedCamera}
        onSelect={activateCamera}
        onStop={() => cameraAction("stop")}
        onRestart={() => cameraAction("restart")}
        busy={busy}
      />

      <section className="main-grid">
        <div className="left-stack">
          <LiveMonitor
            cameraId={selectedCamera}
            cameraName={selectedCameraInfo.name}
            refreshToken={refreshToken}
            isActive={selectedIsActive}
            isStarting={selectedIsStarting}
          />
          {selectedCamera ? <PlaybackPanel cameraId={selectedCamera} /> : null}
        </div>
        <div className="right-stack">
          <AlertPanel event={currentDecision} />
          <PersonStatusTable persons={selectedPersons} />
          <DevicePanel deviceStatus={live.device_status} />
          <SerialMonitor lines={live.serial_tail} />
        </div>
      </section>

      <section className="system-actions">
        <label>
          <input type="checkbox" checked={muted} onChange={(e) => setMuted(e.target.checked)} />
          Mute critical alert sound
        </label>
        <button onClick={resetRealtimeState} disabled={busy}>Reset Realtime State</button>
      </section>

      <EventHistory events={events} cameras={cameras} />
    </main>
  );
}
