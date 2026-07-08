export default function SerialMonitor({ lines }) {
  return (
    <section className="panel">
      <h2>Serial Monitor</h2>
      <pre className="serial-box">{(lines || []).join("\n") || "Serial monitor is empty."}</pre>
    </section>
  );
}
