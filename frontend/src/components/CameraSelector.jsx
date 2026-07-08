export default function CameraSelector({ cameras, selectedCamera, onSelect, onStop, onRestart, busy }) {
  return (
    <section className="toolbar">
      <div className="camera-select">
        <label htmlFor="active-camera">Active Camera</label>
        <select
          id="active-camera"
          value={selectedCamera}
          onChange={(event) => onSelect(event.target.value)}
          disabled={busy}
        >
          <option value="">Select camera to activate</option>
          {cameras.map((camera) => (
            <option key={camera.camera_id} value={camera.camera_id}>
              {camera.name} - {camera.role}
            </option>
          ))}
        </select>
      </div>
      <div className="actions">
        <button onClick={onStop} disabled={busy}>Stop</button>
        <button onClick={onRestart} disabled={busy}>Restart</button>
      </div>
    </section>
  );
}
