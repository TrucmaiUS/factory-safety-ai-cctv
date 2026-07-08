import { useEffect, useState } from "react";
import { frameUrl, mjpegUrl } from "../api/client";

export default function LiveMonitor({ cameraId, cameraName, refreshToken, isActive }) {
  const [mjpegError, setMjpegError] = useState(false);
  const [displaySrc, setDisplaySrc] = useState("");
  const [fallbackReady, setFallbackReady] = useState(false);

  useEffect(() => {
    setMjpegError(false);
    setDisplaySrc("");
    setFallbackReady(false);
  }, [cameraId]);

  useEffect(() => {
    if (!cameraId || !mjpegError) return;

    const nextSrc = frameUrl(cameraId, refreshToken);
    const image = new Image();
    image.onload = () => {
      setDisplaySrc(nextSrc);
      setFallbackReady(true);
    };
    image.onerror = () => {
      setFallbackReady(Boolean(displaySrc));
    };
    image.src = nextSrc;
  }, [cameraId, refreshToken, mjpegError, displaySrc]);

  let body;
  if (!cameraId) {
    body = <div className="placeholder idle-badge">Choose a camera to activate monitoring.</div>;
  } else if (!isActive) {
    body = <div className="placeholder idle-badge">Camera is idle. Select a camera to start MJPEG monitoring.</div>;
  } else if (!mjpegError) {
    body = (
      <img
        src={mjpegUrl(cameraId)}
        alt={`${cameraName} live annotated stream`}
        className="live-stream-img"
        onError={() => setMjpegError(true)}
      />
    );
  } else if (fallbackReady && displaySrc) {
    body = (
      <img
        src={displaySrc}
        alt={`${cameraName} live annotated fallback frame`}
        className="live-stream-img"
      />
    );
  } else {
    body = <div className="placeholder idle-badge">Live stream is starting. Waiting for the first frame.</div>;
  }

  return (
    <section className="panel live-panel">
      <div className="panel-title">
        <h2>Active Camera Monitor</h2>
        <span>{cameraName} | {isActive ? "ACTIVE" : "IDLE"}</span>
      </div>
      <div className="live-monitor">{body}</div>
    </section>
  );
}
