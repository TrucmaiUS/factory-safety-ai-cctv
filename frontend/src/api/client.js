import axios from "axios";

export const API_BASE = "http://127.0.0.1:8000";
export const WS_URL = "ws://127.0.0.1:8000/ws/live";

export const api = axios.create({
  baseURL: API_BASE,
  timeout: 10000
});

export function frameUrl(cameraId, token = Date.now()) {
  return `${API_BASE}/api/cameras/${cameraId}/frame?ts=${token}`;
}

export function mjpegUrl(cameraId) {
  return `${API_BASE}/api/cameras/${cameraId}/mjpeg`;
}

export function videoUrl(cameraId) {
  return `${API_BASE}/api/cameras/${cameraId}/video`;
}
