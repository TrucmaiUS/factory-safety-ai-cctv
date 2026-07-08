import { useMemo, useState } from "react";

export default function EventHistory({ events, cameras }) {
  const [cameraFilter, setCameraFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const filtered = useMemo(() => {
    return (events || []).filter((event) => {
      return (cameraFilter === "all" || event.camera_id === cameraFilter)
        && (severityFilter === "all" || event.severity === severityFilter);
    });
  }, [events, cameraFilter, severityFilter]);

  return (
    <section className="panel history-panel">
      <div className="panel-title">
        <h2>Event History</h2>
        <div className="filters">
          <select value={cameraFilter} onChange={(e) => setCameraFilter(e.target.value)}>
            <option value="all">All cameras</option>
            {cameras.map((camera) => <option key={camera.camera_id} value={camera.camera_id}>{camera.name}</option>)}
          </select>
          <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
            <option value="all">All severities</option>
            <option value="warning">warning</option>
            <option value="high">high</option>
            <option value="critical">critical</option>
          </select>
        </div>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Camera</th>
              <th>Risk</th>
              <th>Severity</th>
              <th>Reasons</th>
              <th>Actions</th>
              <th>Track</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((event, index) => (
              <tr key={`${event.timestamp}-${index}`}>
                <td>{event.timestamp ? new Date(event.timestamp).toLocaleString() : "N/A"}</td>
                <td>{event.camera_id}</td>
                <td>{event.risk_score}</td>
                <td><span className={`severity-tag severity-${event.severity}`}>{event.severity}</span></td>
                <td>{(event.reasons || []).join(", ")}</td>
                <td>{(event.actions || []).join(", ")}</td>
                <td>{event.track_id ?? "N/A"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
