import { frameUrl } from "../api/client";

export default function CameraCard({ camera, liveCamera }) {
  const event = liveCamera?.latest_event;
  const freshAlert = event?.is_fresh && ["high", "critical"].includes(event?.severity);
  const status = freshAlert ? "ALERT" : liveCamera?.status || camera.status || "IDLE";
  const risk = event?.risk_score ?? 0;
  const severity = event?.severity || "normal";

  return (
    <article className={`camera-card ${status.toLowerCase()} severity-${severity}`}>
      <div className="card-head">
        <div>
          <h3>{camera.name}</h3>
          <p>{camera.role}</p>
        </div>
        <span className="status-pill">{status}</span>
      </div>
      <div className="mini-grid">
        <span>Risk</span><strong>{risk}/100</strong>
        <span>Severity</span><strong>{severity.toUpperCase()}</strong>
        <span>Updated</span><strong>{event?.timestamp ? new Date(event.timestamp).toLocaleTimeString() : "N/A"}</strong>
      </div>
      <img
        src={frameUrl(camera.camera_id)}
        alt={`${camera.name} latest preview`}
        onError={(event) => { event.currentTarget.style.display = "none"; }}
      />
    </article>
  );
}
