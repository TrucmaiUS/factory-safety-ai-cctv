export default function PersonStatusTable({ persons }) {
  const severityRank = { critical: 4, high: 3, warning: 2, normal: 1 };
  const rows = [...(persons || [])].sort((a, b) => {
    const severityDelta = (severityRank[b.severity] || 0) - (severityRank[a.severity] || 0);
    if (severityDelta !== 0) return severityDelta;
    const riskDelta = Number(b.risk || 0) - Number(a.risk || 0);
    if (riskDelta !== 0) return riskDelta;
    return Number(b.duration || 0) - Number(a.duration || 0);
  });
  return (
    <section className="panel person-status-panel">
      <h2>Person Status</h2>
      {rows.length === 0 ? (
        <p className="muted">No tracked persons yet.</p>
      ) : (
        <div className="compact-table-wrap">
          <table className="compact-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>PPE</th>
                <th>Zone</th>
                <th>Risk</th>
                <th>Severity</th>
                <th>Duration</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((person) => (
                <tr key={person.id}>
                  <td>#{person.id}</td>
                  <td>{person.ppe_state}</td>
                  <td>{person.zone_state}</td>
                  <td>{person.risk}</td>
                  <td><span className={`severity-tag severity-${person.severity}`}>{person.severity}</span></td>
                  <td>{person.duration}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
