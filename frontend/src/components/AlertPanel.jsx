export default function AlertPanel({ event }) {
  if (!event) {
    return (
      <section className="panel">
        <h2>Current Alert / Decision Trace</h2>
        <p className="muted">No active alert.</p>
      </section>
    );
  }

  const title = event.is_fresh ? "Current Decision" : "Last Event";
  const details = event.details || {};
  return (
    <section className={`panel alert-panel severity-${event.severity}`}>
      <div className="panel-title">
        <h2>{title}</h2>
        <span>{event.age_seconds ?? "?"}s old</span>
      </div>
      <div className="risk-line">
        <strong>{event.risk_score}/100</strong>
        <span>{String(event.severity).toUpperCase()}</span>
      </div>
      <dl className="trace">
        <dt>Camera</dt>
        <dd>{event.camera_id ?? "N/A"}</dd>
        <dt>Person ID</dt>
        <dd>{event.track_id ?? "N/A"}</dd>
        <dt>Event State</dt>
        <dd>{details.event_state ?? "N/A"}</dd>
        <dt>Violation</dt>
        <dd>{details.violation_type ?? "N/A"}</dd>
        <dt>Duration</dt>
        <dd>{details.violation_duration_seconds ?? 0}s</dd>
        <dt>Reasons</dt>
        <dd>{(event.reasons || []).join(", ") || "none"}</dd>
        <dt>Actions</dt>
        <dd>{(event.actions || []).join(", ") || "none"}</dd>
        <dt>Zone</dt>
        <dd>{event.zone_name ?? "N/A"}</dd>
        <dt>Helmet State</dt>
        <dd>{event.helmet_state ? JSON.stringify(event.helmet_state) : "N/A"}</dd>
      </dl>
    </section>
  );
}
