const cameraLabels = {
  camera_1: "Camera 1 - Danger zone + PPE",
  camera_2: "Camera 2 - Danger zone",
  camera_3: "Camera 3 - Helmet compliance"
};

const severityCopy = {
  normal: {
    title: "Normal monitoring",
    tone: "No immediate safety action required."
  },
  warning: {
    title: "Early warning",
    tone: "The system found a risk signal and is watching it closely."
  },
  high: {
    title: "High risk",
    tone: "A safety rule is active and local warning devices may be engaged."
  },
  critical: {
    title: "Critical safety alert",
    tone: "Immediate attention is recommended."
  }
};

const violationLabels = {
  danger_zone: "Person inside restricted zone",
  no_helmet: "Helmet compliance issue",
  ppe_warning: "PPE visibility warning",
  none: "No active violation",
  CURRENT: "Current monitoring state",
  WARNING_STARTED: "Warning started",
  WARNING_ONGOING: "Warning ongoing",
  CRITICAL_STARTED: "Critical alert started",
  CRITICAL_ONGOING: "Critical alert ongoing",
  RESOLVED: "Resolved"
};

const ppeLabels = {
  helmet: "Helmet detected",
  no_helmet: "No safety helmet confirmed",
  unknown: "PPE state uncertain",
  none: "No PPE signal"
};

const zoneLabels = {
  IN_ZONE: "Inside restricted zone",
  OUTSIDE: "Outside restricted zone",
  "N/A": "Zone not used"
};

const reasonLabels = {
  person_detected: "Person detected in the camera view",
  inside_danger_zone: "Person is inside the configured danger zone",
  no_helmet: "Safety helmet is not confirmed",
  combined_danger_no_helmet: "Danger zone and helmet issue happen together",
  multiple_no_helmet_persons: "Multiple people may be missing safety helmets",
  uncertain_detection: "Detection confidence is uncertain, so the score is adjusted",
  head_visible_ppe_warning: "Head is visible and PPE needs attention",
  WARNING_STARTED: "Warning has just started",
  WARNING_ONGOING: "Warning is still active",
  CRITICAL_STARTED: "Critical alert has just started",
  CRITICAL_ONGOING: "Critical alert is still active",
  RESOLVED: "The previous warning has been resolved"
};

const actionLabels = {
  save_history: "Saved event history",
  ui_warning: "Shown on dashboard",
  relay_on: "Relay activated",
  buzzer_on: "Buzzer activated",
  warning_light_on: "Warning light activated"
};

function prettifyToken(value) {
  if (value === null || value === undefined || value === "") return "N/A";
  return String(value)
    .replace(/^stayed_in_zone_over_(.+)s$/, "Stayed in danger zone over $1 seconds")
    .replace(/^no_helmet_over_(.+)s$/, "No helmet confirmed over $1 seconds")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function mapItems(items, dictionary) {
  return [...new Set(items || [])].map((item) => dictionary[item] || prettifyToken(item));
}

function actionSummary(actions = []) {
  const actionSet = new Set(actions);
  if (actionSet.has("warning_light_on")) return "Dashboard + relay + buzzer + warning light";
  if (actionSet.has("relay_on") || actionSet.has("buzzer_on")) return "Dashboard + relay + buzzer";
  if (actionSet.has("ui_warning") || actionSet.has("save_history")) return "Dashboard warning + event snapshot";
  return "Monitoring only";
}

function scenarioFor(event, details) {
  const violation = details.violation_type || details.event_state || "none";
  if (violationLabels[violation]) return violationLabels[violation];
  if ((event.reasons || []).includes("combined_danger_no_helmet")) {
    return "Person in danger zone without confirmed safety helmet";
  }
  return prettifyToken(violation);
}

function statusText(event) {
  if (event.is_fresh) return "Live decision";
  if (event.age_seconds !== undefined && event.age_seconds !== null) {
    return `Last event, ${event.age_seconds}s old`;
  }
  return "Last event";
}

export default function AlertPanel({ event }) {
  if (!event) {
    return (
      <section className="panel alert-panel">
        <div className="panel-title">
          <h2>Safety Decision</h2>
          <span className="decision-badge">Idle</span>
        </div>
        <p className="muted">No active safety decision yet.</p>
      </section>
    );
  }

  const details = event.details || {};
  const severity = event.severity || "normal";
  const severityInfo = severityCopy[severity] || severityCopy.normal;
  const reasons = mapItems(event.reasons, reasonLabels);
  const actions = mapItems(event.actions, actionLabels);
  const ppeState = details.ppe_state || details.stable_ppe || event.helmet_state?.ppe_state || "unknown";
  const zoneState =
    details.zone_state ||
    (details.stable_inside_zone === true ? "IN_ZONE" : details.stable_inside_zone === false ? "OUTSIDE" : null) ||
    event.zone_name ||
    "N/A";
  const duration = Number(details.violation_duration_seconds || 0);

  return (
    <section className={`panel alert-panel severity-${severity}`}>
      <div className="panel-title">
        <h2>Safety Decision</h2>
        <span className="decision-badge">{statusText(event)}</span>
      </div>

      <div className="decision-hero">
        <div>
          <span className="decision-kicker">{scenarioFor(event, details)}</span>
          <strong>{severityInfo.title}</strong>
          <p>{severityInfo.tone}</p>
        </div>
        <div className="risk-meter" aria-label={`Risk score ${event.risk_score || 0} out of 100`}>
          <strong>{event.risk_score ?? 0}</strong>
          <span>Risk score</span>
        </div>
      </div>

      <div className="decision-summary-grid">
        <div>
          <span>Camera</span>
          <strong>{cameraLabels[event.camera_id] || prettifyToken(event.camera_id)}</strong>
        </div>
        <div>
          <span>Person</span>
          <strong>{event.track_id !== null && event.track_id !== undefined ? `#${event.track_id}` : "Not tracked"}</strong>
        </div>
        <div>
          <span>PPE</span>
          <strong>{ppeLabels[ppeState] || prettifyToken(ppeState)}</strong>
        </div>
        <div>
          <span>Zone</span>
          <strong>{zoneLabels[zoneState] || prettifyToken(zoneState)}</strong>
        </div>
        <div>
          <span>Duration</span>
          <strong>{duration > 0 ? `${duration.toFixed(1)}s` : "Just detected"}</strong>
        </div>
        <div>
          <span>System response</span>
          <strong>{actionSummary(event.actions)}</strong>
        </div>
      </div>

      <div className="decision-section">
        <h3>Why this decision?</h3>
        {reasons.length ? (
          <ul className="decision-list">
            {reasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        ) : (
          <p className="muted">No risk signal is active.</p>
        )}
      </div>

      <div className="decision-section">
        <h3>Actions taken</h3>
        {actions.length ? (
          <ul className="action-chips">
            {actions.map((action) => <li key={action}>{action}</li>)}
          </ul>
        ) : (
          <p className="muted">No alert action has been triggered.</p>
        )}
      </div>
    </section>
  );
}
