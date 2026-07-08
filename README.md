# Factory Safety AI CCTV

Hệ thống demo giám sát an toàn công trường bằng AI/CV. Pipeline chính:

```text
Video/CCTV
-> YOLO person + PPE detection
-> person tracking
-> temporal smoothing
-> risk scoring / rule engine
-> stable alert + IoT device simulator
-> FastAPI backend + React realtime dashboard
```

Hệ thống hiện hỗ trợ 3 camera:

- `camera_1`: danger zone + helmet/PPE check
- `camera_2`: danger zone only
- `camera_3`: helmet/PPE compliance

## Cấu Trúc Thư Mục

```text
factory-safety-ai-cctv/
├── backend/                    # FastAPI backend cho dashboard realtime
│   ├── api/                    # REST endpoints: cameras, events, devices, logs
│   ├── schemas/                # Pydantic/API schemas nếu cần mở rộng contract
│   ├── services/               # Process manager, output reader, websocket payload
│   └── main.py                 # FastAPI app, startup/reset/shutdown cleanup
│
├── frontend/                   # React + Vite dashboard
│   ├── src/api/                # Axios/API URL helpers
│   ├── src/components/         # Live monitor, alert panel, status table, history, device UI
│   ├── src/styles/             # CSS layout/dashboard styling
│   └── package.json            # Frontend scripts/dependencies
│
├── src/                        # Core AI/CV pipeline
│   ├── configs/                # Tất cả config vận hành/risk/camera/zone
│   ├── demo/                   # CLI E2E runner: python -m src.demo.run_cctv_demo
│   ├── perception/             # Detection types, person detector, PPE detector
│   ├── safety/                 # Zone check, tracking, smoothing, risk scoring, history logger
│   ├── iot/                    # ESP32/relay simulator, command schema, serial-style logs
│   ├── device/                 # Legacy/simple relay simulator wrapper
│   ├── visualization/          # OpenCV overlay trên frame/video
│   ├── data/                   # Dataset helper scripts, không dùng trong realtime dashboard
│   └── utils/                  # Shared utilities, ví dụ atomic file write/read helpers
│
├── model/                      # Model weights
│   ├── person/yolov8s.pt       # YOLOv8s COCO, dùng class person
│   └── ppe/yolo8s_ppe_best.pt  # PPE model: person/helmet/head
│
├── video_source/               # Input videos theo camera
│   ├── camera_1/cam1.mp4
│   ├── camera_2/cam2.mp4
│   └── camera_3/cam3.mp4
│
├── outputs/                    # Runtime/generated files, có thể reset/xóa khi cần
│   ├── live/                   # latest frame/event/person status cho dashboard
│   ├── demo_videos/            # annotated output mp4
│   ├── alert_snapshots/        # ảnh chụp khi có alert/event
│   ├── worker_logs/            # log process camera worker
│   ├── alert_history.jsonl     # event history
│   ├── device_status.json      # trạng thái relay/buzzer/light simulator
│   └── serial_monitor.log      # serial-style log
│
├── scripts/                    # Dev/smoke utilities, không chạy trong dashboard
├── notebooks/                  # Notebook thí nghiệm, không dùng trong realtime pipeline
├── dataset/, data/             # Dataset/raw/experiment assets nếu có
├── docs/                       # Tài liệu phụ nếu có
├── requirements.txt            # Python dependencies
└── README.md
```

## File Config Quan Trọng

Các thông số nên sửa trong `src/configs/`, hạn chế hardcode trong code.

| Muốn chỉnh | File |
|---|---|
| Video source, camera role, camera nào dùng PPE/zone | `src/configs/video_sources.yaml` |
| Danger zone polygon | `src/configs/camera_zones.yaml` |
| Risk score, severity threshold, dwell time 2s/3s, actions | `src/configs/risk_rules.yaml` |
| Runtime pipeline: inference FPS/skip, confidence, smoothing, loop video, live frame width | `src/configs/runtime_settings.yaml` |
| Policy cho confidence/uncertainty | `src/configs/uncertainty_policy.yaml` |

### Chỉnh Risk/Dwell Time

Vào:

```text
src/configs/risk_rules.yaml
```

Ví dụ đổi thời gian để Camera 2 từ 80 lên 100:

```yaml
dwell_time:
  danger_zone_seconds: 2.0
  no_helmet_seconds: 2.0
```

Chỉnh severity:

```yaml
severity_thresholds:
  normal: [0, 24]
  warning: [25, 49]
  high: [50, 79]
  critical: [80, 100]
```

Chỉnh trọng số theo camera:

```yaml
camera_rules:
  camera_2:
    weights:
      inside_danger_zone: 80
      stay_time_over_threshold: 20
```

### Chỉnh Runtime/Realtime

Vào:

```text
src/configs/runtime_settings.yaml
```

Các key hay chỉnh:

```yaml
pipeline:
  inference_every: 2          # chạy YOLO mỗi N frame
  live_frame_width: 960       # resize latest frame cho dashboard
  person_conf: 0.35
  ppe_conf: 0.25
  smoothing_window: 12
  no_helmet_confirm_frames: 6
  risk_alpha: 0.85
  alert_duration_sec: 1.5

dashboard_worker:
  max_frames: 0               # 0 = chạy tới khi bấm Stop
  loop_video: true            # hết video thì quay lại đầu
  save_video: true
  realtime_logs: true
```

Sau khi đổi config, restart camera hoặc restart backend để process mới load lại config.

## Cách Chạy

### Chuẩn Bị Model Và Video Demo

Do file model và video có dung lượng lớn, repo không commit trực tiếp các file `.pt` và `.mp4`.

Cần đặt file theo cấu trúc:

```text
model/
├── person/yolov8s.pt
└── ppe/yolo8s_ppe_best.pt

video_source/
├── camera_1/cam1.mp4
├── camera_2/cam2.mp4
└── camera_3/cam3.mp4

### 1. Cài Python dependencies

```powershell
cd D:\DAI_HOC\PHONG_VAN\factory-safety-ai-cctv
pip install -r requirements.txt
```

### 2. Chạy Backend

```powershell
uvicorn backend.main:app --reload
```

Backend mặc định chạy ở:

```text
http://127.0.0.1:8000
```

Khi backend startup/reset, runtime state trong `outputs/live`, device status, serial log, history sẽ được clear.

### 3. Chạy Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend mặc định chạy ở:

```text
http://127.0.0.1:5173
```

Trên dashboard:

1. Chọn camera trong dropdown.
2. Backend tự stop camera cũ và activate camera mới.
3. Bấm `Stop` để dừng camera.
4. Bấm `Reset Realtime State` để clear runtime data/log/history.

## Chạy E2E Demo Bằng CLI

Chạy Camera 2:

```powershell
python -m src.demo.run_cctv_demo --camera camera_2 --max-frames 300 --save-video
```

Chạy cả 3 camera tuần tự:

```powershell
python -m src.demo.run_cctv_demo --all --max-frames 300 --save-video
```

Chạy loop video như dashboard:

```powershell
python -m src.demo.run_cctv_demo --camera camera_2 --loop-video --save-video --realtime-logs
```

Output chính:

- `outputs/demo_videos/camera_1_output.mp4`
- `outputs/demo_videos/camera_2_output.mp4`
- `outputs/demo_videos/camera_3_output.mp4`
- `outputs/alert_history.jsonl`
- `outputs/alert_snapshots/*.jpg`
- `outputs/worker_logs/*_worker.log`

## Smoke/Dev Scripts

`scripts/` là thư mục tiện ích, không được dashboard gọi trực tiếp.

```text
scripts/smoke_test_detectors.py   # test person/PPE detector trên video sample
scripts/smoke_test_zones.py       # preview danger zone polygon
scripts/extract_zone_frames.py    # trích frame để chỉnh polygon
```

## Realtime Architecture

Backend dashboard dùng mô hình:

```text
React UI
  ├── MJPEG stream: /api/cameras/{camera_id}/mjpeg
  └── WebSocket metadata: /ws/live

FastAPI backend
  ├── process_manager start/stop camera worker
  ├── output_reader đọc latest frame/event/person status
  └── websocket_manager gửi dashboard payload mỗi giây

Camera worker
  ├── đọc video
  ├── YOLO detection
  ├── tracking + temporal smoothing
  ├── risk scoring/rule engine
  ├── ghi latest jpg/json bằng atomic IO
  └── ghi history/snapshot/device command nếu có event
```

Video vẫn dùng MJPEG vì đơn giản, dễ debug, phù hợp CPU demo. WebSocket chỉ dùng cho metadata realtime.

## Các Quyết Định Thiết Kế Chính

- YOLO được dùng như tầng nhận thức hình ảnh (perception layer), không phải là nơi ra quyết định cuối cùng.
- Risk scoring và rule engine được tách khỏi logic detection để hệ thống dễ kiểm soát, dễ giải thích và dễ mở rộng theo yêu cầu an toàn thực tế.
- MJPEG được dùng cho video stream vì đơn giản, dễ debug và phù hợp với demo chạy CPU.
- WebSocket chỉ được dùng cho metadata realtime như decision trace, trạng thái từng người, alert, trạng thái thiết bị và serial-style logs.
- Person tracking và temporal smoothing được dùng để giảm hiện tượng prediction bị nhấp nháy theo từng frame.
- Hệ thống cũng theo dõi các trạng thái warning để dashboard có thể hiển thị rủi ro sớm trước khi chuyển thành vi phạm nghiêm trọng.
- Event logging được xử lý theo trạng thái ổn định và cooldown, không ghi log liên tục theo từng frame.

## Model Và Class Mapping

Person detector:

```text
model/person/yolov8s.pt
COCO class 0 = person
```

PPE detector:

```text
model/ppe/yolo8s_ppe_best.pt
0 = person
1 = helmet
2 = head
```

Lưu ý:

- Không dùng class `person` từ PPE model để check danger zone.
- `head` được hiểu là exposed head / possible no helmet.
- Hiện model chưa được train để phân biệt kỹ `safety_helmet` với `normal_hat`.

## Hạn Chế Hiện Tại

- Demo hiện tại chạy realtime trên CPU nên FPS có thể chưa thật sự mượt, tùy cấu hình máy.
- Kết quả AI theo từng frame vẫn có thể dao động trong các tình huống khó như motion blur, che khuất, người ở xa hoặc góc quay không thuận lợi.
- PPE model hiện tại dùng class `helmet` và `head`, nhưng chưa được train riêng để phân biệt rõ `safety_helmet` với `normal_hat`.
- Dashboard hiện tập trung vào một camera active tại một thời điểm để đảm bảo demo ổn định và dễ quan sát.
- Hệ thống hiện là MVP prototype, chưa phải bản production-ready.

## Hướng Phát Triển Tiếp Theo

- Mở rộng dataset và class để phân biệt rõ `safety_helmet`, `normal_hat` và `bare_head`.
- Export model sang ONNX/TensorRT hoặc chạy inference trên GPU để cải thiện FPS realtime.
- Cải thiện xử lý multi-camera concurrent nếu cần chạy nhiều camera cùng lúc.
- Có thể dùng WebRTC nếu cần video streaming latency thấp hơn trong môi trường gần production.
- Cải thiện tracking trong các cảnh đông người, bị che khuất hoặc người di chuyển giao nhau.
- Bổ sung thêm rule/risk config theo yêu cầu thực tế của ban an toàn nhà máy.

## Debug Nhanh

Nếu camera tự về `IDLE`, kiểm tra worker log:

```powershell
Get-Content outputs\worker_logs\camera_1_worker.log -Tail 80
Get-Content outputs\worker_logs\camera_2_worker.log -Tail 80
Get-Content outputs\worker_logs\camera_3_worker.log -Tail 80
```

Nếu dashboard còn alert/frame cũ, reset runtime:

```powershell
curl -X POST "http://127.0.0.1:8000/api/system/reset-realtime-state?clear_history=true"
```

Nếu muốn chỉnh zone:

1. Dùng `scripts/extract_zone_frames.py` hoặc `scripts/smoke_test_zones.py`.
2. Sửa polygon trong `src/configs/camera_zones.yaml`.
3. Restart camera.

## Ghi Chú Bảo Trì

- Config risk nằm ở `risk_rules.yaml`.
- Config runtime nằm ở `runtime_settings.yaml`.
- Config camera/source/capability nằm ở `video_sources.yaml`.
- Không nên sửa trực tiếp magic number trong code nếu có thể đưa vào config.
- `outputs/` là runtime generated data, không nên coi là source of truth.
- `notebooks/` và `scripts/` phục vụ thí nghiệm/debug, không thuộc realtime production path.


