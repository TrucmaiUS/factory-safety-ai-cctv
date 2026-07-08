export default function DevicePanel({ deviceStatus }) {
  const rows = Object.entries(deviceStatus || {});
  return (
    <section className="panel">
      <h2>IoT Device Simulator</h2>
      <div className="device-list">
        {rows.length === 0 && <p className="muted">No device state yet.</p>}
        {rows.map(([cameraId, state]) => (
          <div className="device-row compact-device-row" key={cameraId}>
            <strong>{state.device_id}</strong>
            <small>{cameraId}</small>
            <span className={state.relay === "ON" ? "indicator on" : "indicator"}>Relay {state.relay}</span>
            <span className={state.buzzer === "ON" ? "indicator on" : "indicator"}>Buzzer {state.buzzer}</span>
            <span className={state.warning_light === "ON" ? "indicator on" : "indicator"}>Light {state.warning_light}</span>
          </div>
        ))}
      </div>
    </section>
  );
}
