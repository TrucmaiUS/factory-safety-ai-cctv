import { videoUrl } from "../api/client";

export default function PlaybackPanel({ cameraId }) {
  return (
    <details className="panel playback-panel">
      <summary>Processed Video Playback</summary>
      <video src={videoUrl(cameraId)} controls preload="metadata" />
    </details>
  );
}
