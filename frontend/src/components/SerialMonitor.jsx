export default function SerialMonitor({ lines }) {
  const hasLines = (lines || []).length > 0;
  return (
    <details className="panel serial-panel" open={hasLines}>
      <summary>Serial Monitor {hasLines ? `(${lines.length})` : "(empty)"}</summary>
      <pre className="serial-box">{(lines || []).join("\n") || "Serial monitor is empty."}</pre>
    </details>
  );
}
