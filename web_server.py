"""
HỆ THỐNG KIỂM TRA OCR CAMERA BASLER GIGE - WEB HMI SERVER
Phát triển trên nền tảng FastAPI + OpenCV + EasyOCR
Hỗ trợ Live MJPEG Stream, Real-time WebSocket, Điều khiển Camera & Thống kê sản lượng.
"""

import os
import sys
import time
import json
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import cv2
import numpy as np

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import config
from camera_basler import BaslerGigECamera
from ocr_engine import OcrInspector, InspectionResult

@asynccontextmanager
async def lifespan(app: FastAPI):
    system_mgr.init_engines()
    yield

# --- Khởi tạo FastAPI App ---
app = FastAPI(title="Conveyor OCR Basler Vision HMI", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đường dẫn thư mục
BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
RECORDS_DIR = BASE_DIR / "records"

# Mount static files
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
app.mount("/records", StaticFiles(directory=str(RECORDS_DIR)), name="records")


# ==========================================================
# CLASS QUẢN LÝ TOÀN BỘ TRẠNG THÁI HỆ THỐNG (STATE MANAGER)
# ==========================================================
class VisionSystemManager:
    def __init__(self):
        self.lock = threading.Lock()
        
        # Thiết bị Camera & OCR
        self.camera: Optional[BaslerGigECamera] = None
        self.ocr_inspector: Optional[OcrInspector] = None
        
        # Trạng thái kết nối
        self.cam_connected = False
        self.cam_model = "Basler GigE acA3800-10gm"
        self.cam_serial = "23298384"
        self.cam_ip = config.CAMERA_IP
        
        # Cấu hình quang học & hoạt động
        self.auto_exposure = True
        self.exposure_time = float(config.CAMERA_EXPOSURE_TIME)
        self.gain = float(config.CAMERA_GAIN)
        self.focus_mode = False
        self.target_code = config.TARGET_CODE
        self.roi = dict(config.DEFAULT_ROI)
        
        # Tự động kiểm tra liên tục
        self.auto_inspect = False
        self.auto_interval = 2.0  # Giây giữa các lần auto
        self.last_auto_time = 0.0
        
        # Thống kê sản lượng
        self.stats = {
            "total": 0,
            "ok": 0,
            "ng": 0,
            "ng_rate": 0.0
        }
        
        # Khung hình & Hiệu năng
        self.latest_raw_frame: Optional[np.ndarray] = None
        self.latest_processed_frame: Optional[np.ndarray] = None
        self.fallback_frame: Optional[np.ndarray] = None
        self.fps = 0.0
        self.frame_count = 0
        self.fps_timer = time.time()
        
        # Kết quả kiểm tra gần nhất
        self.last_result: Optional[Dict[str, Any]] = None
        
        # Nhật ký hệ thống (tối đa 150 dòng)
        self.logs = []
        
        # Danh sách WebSocket clients
        self.ws_clients: list[WebSocket] = []
        
        # Luồng chạy ngầm
        self.running = True
        self.worker_thread = None
        
        self._load_fallback_sample()
        self.add_log("Hệ thống HMI Web khởi động thành công.", "info")

    def _load_fallback_sample(self):
        """Tải ảnh mẫu sẵn có để phòng trường hợp camera tạm ngắt kết nối."""
        candidates = [
            BASE_DIR / "records" / "TEST" / "test_snapshot.jpg",
            BASE_DIR / "records" / "OK" / "OK_20261007_133431_719_SEAT.jpg"
        ]
        for c in candidates:
            if c.exists():
                img = cv2.imread(str(c))
                if img is not None:
                    self.fallback_frame = img
                    break
        
        if self.fallback_frame is None:
            # Tạo frame đồ họa dự phòng
            h, w = 720, 1280
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            frame[:] = (20, 24, 33)
            cv2.putText(frame, "BASLER GIGE CAMERA STANDBY", (w//2 - 250, h//2 - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (80, 160, 240), 2)
            cv2.putText(frame, f"Connecting to {self.cam_ip}...", (w//2 - 180, h//2 + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (140, 150, 170), 1)
            self.fallback_frame = frame

    def add_log(self, text: str, level: str = "info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = {"time": timestamp, "text": text, "level": level}
        self.logs.append(entry)
        if len(self.logs) > 150:
            self.logs.pop(0)

    def init_engines(self):
        """Khởi tạo OCR và kết nối Camera Basler."""
        # Giới hạn số luồng PyTorch để tránh nghẽn CPU và rớt gói GigE
        try:
            import torch
            torch.set_num_threads(min(4, os.cpu_count() or 4))
        except Exception:
            pass

        self.add_log("Đang nạp mô hình OCR Engine...", "info")
        try:
            self.ocr_inspector = OcrInspector(
                target_code=self.target_code,
                confidence_threshold=config.CONFIDENCE_THRESHOLD
            )
            self.add_log("Mô hình OCR Engine đã sẵn sàng!", "success")
        except Exception as e:
            self.add_log(f"Lỗi khởi tạo OCR: {e}", "error")

        # Khởi chạy luồng camera và auto-inspect
        self.worker_thread = threading.Thread(target=self._camera_background_loop, daemon=True)
        self.worker_thread.start()

    def _connect_camera_safe(self) -> bool:
        """Thử kết nối Camera Basler với xử lý ngoại lệ an toàn."""
        try:
            self.camera = BaslerGigECamera(
                ip_address=self.cam_ip,
                exposure_time=self.exposure_time
            )
            self.camera.connect()
            self.cam_connected = True
            self.cam_model = self.camera.model_name
            self.cam_serial = self.camera.serial_number
            
            # Đồng bộ cấu hình ban đầu
            self.camera.set_auto_exposure(self.auto_exposure)
            if not self.auto_exposure:
                self.camera.set_exposure_time(self.exposure_time)
            self.camera.set_gain(self.gain)
            
            self.add_log(f"Camera Basler ONLINE: {self.cam_model} (S/N: {self.cam_serial})", "success")
            return True
        except Exception as e:
            self.cam_connected = False
            self.add_log(f"Chưa kết nối được camera ({self.cam_ip}): {e}", "warning")
            return False

    def _camera_background_loop(self):
        """Vòng lặp ngầm liên tục lấy khung hình từ Camera Basler."""
        last_conn_try = 0
        while self.running:
            now = time.time()
            
            # Kiểm tra & Tự động kết nối lại nếu mất tín hiệu
            if not self.cam_connected:
                if now - last_conn_try > 3.0:
                    last_conn_try = now
                    self._connect_camera_safe()
                if not self.cam_connected:
                    time.sleep(0.1)
                    continue

            # Thu nhận khung hình
            frame = None
            try:
                frame = self.camera.grab_frame(timeout_ms=3000)
            except Exception as e:
                self.cam_connected = False
                self.add_log(f"Mất tín hiệu camera: {e}", "error")
                time.sleep(1.0)
                continue

            if frame is not None:
                with self.lock:
                    self.latest_raw_frame = frame
                    self.frame_count += 1
                    
                    # Tính FPS
                    if now - self.fps_timer >= 1.0:
                        self.fps = round(self.frame_count / (now - self.fps_timer), 1)
                        self.frame_count = 0
                        self.fps_timer = now

                # Xử lý tự động kiểm tra liên tục nếu bật Auto Inspect
                if self.auto_inspect and (now - self.last_auto_time >= self.auto_interval):
                    self.last_auto_time = now
                    # Trigger bất đồng bộ để không kẹt vòng lặp lấy frame
                    threading.Thread(target=self.trigger_inspection, args=(frame.copy(),), daemon=True).start()

            time.sleep(0.015)  # Giới hạn ~30 FPS

    def get_display_frame(self) -> np.ndarray:
        """Tạo khung hình để stream ra Web, vẽ ROI hoặc phóng to 1:1 theo chế độ."""
        with self.lock:
            frame = self.latest_raw_frame.copy() if self.latest_raw_frame is not None else None
        
        if frame is None:
            # Dùng frame chờ sinh động
            frame = self.fallback_frame.copy() if self.fallback_frame is not None else np.zeros((600, 800, 3), dtype=np.uint8)
            # Thêm đồng hồ và trạng thái
            h, w = frame.shape[:2]
            status_txt = "CAMERA BASLER DANG KET NOI LAI..." if not self.cam_connected else "DANG DOI KHUNG HINH..."
            cv2.putText(frame, status_txt, (50, h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
            cv2.putText(frame, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), (50, 50),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
            return frame

        h, w = frame.shape[:2]
        ymin = max(0, min(h, int(self.roi.get("ymin", 0.25) * h)))
        ymax = max(0, min(h, int(self.roi.get("ymax", 0.75) * h)))
        xmin = max(0, min(w, int(self.roi.get("xmin", 0.25) * w)))
        xmax = max(0, min(w, int(self.roi.get("xmax", 0.75) * w)))

        if self.focus_mode:
            # CHẾ ĐỘ SOI NÉT 1:1: Cắt trực tiếp vùng ROI nguyên bản điểm ảnh
            crop_roi = frame[ymin:ymax, xmin:xmax]
            if crop_roi.size > 0:
                ch, cw = crop_roi.shape[:2]
                target_w = 960
                scale = target_w / max(1, cw)
                disp_w = max(10, int(cw * scale))
                disp_h = max(10, int(ch * scale))
                disp_frame = cv2.resize(crop_roi, (disp_w, disp_h), interpolation=cv2.INTER_NEAREST)
                
                # Header thông báo chế độ nét
                overlay = disp_frame.copy()
                cv2.rectangle(overlay, (0, 0), (disp_w, 50), (20, 24, 33), -1)
                cv2.addWeighted(overlay, 0.75, disp_frame, 0.25, 0, disp_frame)
                cv2.putText(disp_frame, "ZOOM 1:1 - XOAY NHOE / NET TREN ONG KINH CHO CHU THAT RO",
                            (15, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (74, 222, 128), 2)
                return disp_frame

        # CHẾ ĐỘ TOÀN CẢNH: Resize tối ưu băng thông và vẽ khung ROI công nghệ cao
        preview_w = 1280
        scale = preview_w / w
        preview_h = int(h * scale)
        disp_frame = cv2.resize(frame, (preview_w, preview_h), interpolation=cv2.INTER_AREA)

        # Tọa độ ROI trên ảnh thu nhỏ
        r_ymin = int(ymin * scale)
        r_ymax = int(ymax * scale)
        r_xmin = int(xmin * scale)
        r_xmax = int(xmax * scale)

        # Vẽ góc bounding box phong cách Cyberpunk / Industrial Vision
        box_color = (0, 230, 255)  # Cyan neon
        cv2.rectangle(disp_frame, (r_xmin, r_ymin), (r_xmax, r_ymax), box_color, 2)

        corner_len = min(25, (r_xmax - r_xmin) // 4, (r_ymax - r_ymin) // 4)
        thickness = 4
        # Góc trên-trái
        cv2.line(disp_frame, (r_xmin, r_ymin), (r_xmin + corner_len, r_ymin), box_color, thickness)
        cv2.line(disp_frame, (r_xmin, r_ymin), (r_xmin, r_ymin + corner_len), box_color, thickness)
        # Góc trên-phải
        cv2.line(disp_frame, (r_xmax, r_ymin), (r_xmax - corner_len, r_ymin), box_color, thickness)
        cv2.line(disp_frame, (r_xmax, r_ymin), (r_xmax, r_ymin + corner_len), box_color, thickness)
        # Góc dưới-trái
        cv2.line(disp_frame, (r_xmin, r_ymax), (r_xmin + corner_len, r_ymax), box_color, thickness)
        cv2.line(disp_frame, (r_xmin, r_ymax), (r_xmin, r_ymax - corner_len), box_color, thickness)
        # Góc dưới-phải
        cv2.line(disp_frame, (r_xmax, r_ymax), (r_xmax - corner_len, r_ymax), box_color, thickness)
        cv2.line(disp_frame, (r_xmax, r_ymax), (r_xmax, r_ymax - corner_len), box_color, thickness)

        # Nhãn thông số ROI
        label_text = f"ROI OCR [{self.target_code}]"
        cv2.putText(disp_frame, label_text, (r_xmin, max(25, r_ymin - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, box_color, 2)

        return disp_frame

    def trigger_inspection(self, frame: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """Kích hoạt kiểm tra OCR 1 khung hình."""
        if frame is None:
            with self.lock:
                frame = self.latest_raw_frame.copy() if self.latest_raw_frame is not None else None

        if frame is None and self.camera and self.camera.is_connected:
            frame = self.camera.grab_frame(timeout_ms=3000)

        if frame is None:
            if self.fallback_frame is not None:
                frame = self.fallback_frame.copy()
            else:
                raise ValueError("Không có khung hình nào từ camera.")

        start_time = time.time()
        
        # Cập nhật mã mục tiêu cho OCR Inspector
        if self.ocr_inspector:
            self.ocr_inspector.target_code = self.target_code
        else:
            self.ocr_inspector = OcrInspector(target_code=self.target_code)

        # Thực thi OCR
        result: InspectionResult = self.ocr_inspector.inspect_frame(frame, self.roi)
        latency_ms = round((time.time() - start_time) * 1000, 1)

        # Cập nhật thống kê
        with self.lock:
            self.stats["total"] += 1
            if result.is_pass:
                self.stats["ok"] += 1
            else:
                self.stats["ng"] += 1
            
            total = self.stats["total"]
            self.stats["ng_rate"] = round((self.stats["ng"] / total * 100), 1) if total > 0 else 0.0

        # Lưu ảnh vào đĩa
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        detected_clean = result.detected_text if result.detected_text else "EMPTY"
        category = "OK" if result.is_pass else "NG"
        save_dir = config.SAVE_DIR_OK if result.is_pass else config.SAVE_DIR_NG
        filename = f"{category}_{timestamp_str}_{detected_clean}.jpg"
        file_path = save_dir / filename

        # Lưu ảnh crop ROI nhỏ để xem nhanh trên web
        thumb_filename = f"thumb_{filename}"
        thumb_path = save_dir / thumb_filename

        try:
            cv2.imwrite(str(file_path), frame)
            if result.roi_image is not None and result.roi_image.size > 0:
                cv2.imwrite(str(thumb_path), result.roi_image)
            else:
                # Nếu không có roi_image thì resize frame
                cv2.imwrite(str(thumb_path), cv2.resize(frame, (320, 240)))
        except Exception as e:
            self.add_log(f"Lỗi khi lưu ảnh: {e}", "warning")

        res_payload = {
            "is_pass": result.is_pass,
            "detected_text": result.detected_text,
            "target_text": result.target_text,
            "confidence": round(float(result.confidence) * 100, 1),
            "latency_ms": latency_ms,
            "details": result.details,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "category": category,
            "image_url": f"/records/{category}/{filename}",
            "thumb_url": f"/records/{category}/{thumb_filename}",
            "stats": dict(self.stats)
        }

        self.last_result = res_payload

        # Ghi log
        status_tag = "ĐẠT (PASS)" if result.is_pass else "LỖI (FAIL)"
        log_level = "success" if result.is_pass else "error"
        self.add_log(f"[{status_tag}] Đọc: '{result.detected_text}' | Mục tiêu: '{result.target_text}' ({latency_ms}ms)", log_level)

        return res_payload

    def set_camera_exposure(self, exposure_us: float, auto: bool):
        self.exposure_time = exposure_us
        self.auto_exposure = auto
        if self.camera and self.camera.is_connected:
            self.camera.set_auto_exposure(auto)
            if not auto:
                self.camera.set_exposure_time(exposure_us)
        self.add_log(f"Đã cập nhật Camera Exposure: {exposure_us}µs (Auto: {auto})", "info")

    def set_camera_gain(self, gain_val: float):
        self.gain = gain_val
        if self.camera and self.camera.is_connected:
            self.camera.set_gain(gain_val)
        self.add_log(f"Đã cập nhật Gain: {gain_val}", "info")

    def set_target_code(self, new_code: str):
        clean_code = new_code.strip().upper()
        if clean_code:
            self.target_code = clean_code
            if self.ocr_inspector:
                self.ocr_inspector.target_code = clean_code
            self.add_log(f"Đã đổi Mã Tiêu Chuẩn sang: '{clean_code}'", "info")

    def set_roi(self, ymin: float, xmin: float, ymax: float, xmax: float):
        self.roi = {
            "enabled": True,
            "ymin": min(ymin, ymax - 0.05),
            "xmin": min(xmin, xmax - 0.05),
            "ymax": max(ymax, ymin + 0.05),
            "xmax": max(xmax, xmin + 0.05)
        }
        self.add_log(f"Đã cập nhật tọa độ ROI: Y[{self.roi['ymin']:.2f}-{self.roi['ymax']:.2f}], X[{self.roi['xmin']:.2f}-{self.roi['xmax']:.2f}]", "info")

    def reset_stats(self):
        with self.lock:
            self.stats = {"total": 0, "ok": 0, "ng": 0, "ng_rate": 0.0}
            self.last_result = None
        self.add_log("Đã đặt lại toàn bộ bộ đếm sản lượng về 0.", "info")

    def get_history(self, limit: int = 40) -> list[Dict[str, Any]]:
        """Lấy danh sách các sản phẩm đã chụp và kiểm tra gần đây."""
        records = []
        for cat in ["OK", "NG"]:
            cat_dir = RECORDS_DIR / cat
            if not cat_dir.exists():
                continue
            for f in cat_dir.glob("*.jpg"):
                if f.name.startswith("thumb_"):
                    continue
                stat = f.stat()
                # Parse filename format: OK_YYYYMMDD_HHMMSS_xxx_CODE.jpg
                parts = f.stem.split("_")
                detected = parts[-1] if len(parts) >= 4 else ""
                records.append({
                    "filename": f.name,
                    "category": cat,
                    "is_pass": (cat == "OK"),
                    "detected": detected,
                    "time": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime": stat.st_mtime,
                    "image_url": f"/records/{cat}/{f.name}",
                    "thumb_url": f"/records/{cat}/thumb_{f.name}" if (cat_dir / f"thumb_{f.name}").exists() else f"/records/{cat}/{f.name}"
                })
        records.sort(key=lambda x: x["mtime"], reverse=True)
        return records[:limit]


# Khởi tạo instance hệ thống
system_mgr = VisionSystemManager()


# ==========================================================
# ENDPOINTS GIAO DIỆN & TRUYỀN DÒNG VIDEO (MJPEG STREAM)
# ==========================================================
@app.get("/", response_class=FileResponse)
def index_page():
    return FileResponse(WEB_DIR / "index.html")


def mjpeg_stream_generator():
    """Tạo chuỗi MJPEG trực tiếp cho thẻ <img> trên trình duyệt."""
    while True:
        frame = system_mgr.get_display_frame()
        # Nén JPEG tốc độ cao
        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        time.sleep(0.035)  # ~28 FPS mượt mà và tiết kiệm băng thông


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        mjpeg_stream_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ==========================================================
# REST APIS ĐIỀU KHIỂN & CẤU HÌNH
# ==========================================================
@app.get("/api/status")
def get_status():
    return {
        "camera_connected": system_mgr.cam_connected,
        "camera_model": system_mgr.cam_model,
        "camera_serial": system_mgr.cam_serial,
        "camera_ip": system_mgr.cam_ip,
        "fps": system_mgr.fps,
        "focus_mode": system_mgr.focus_mode,
        "auto_inspect": system_mgr.auto_inspect,
        "auto_exposure": system_mgr.auto_exposure,
        "exposure_time": system_mgr.exposure_time,
        "gain": system_mgr.gain,
        "target_code": system_mgr.target_code,
        "roi": system_mgr.roi,
        "stats": system_mgr.stats,
        "last_result": system_mgr.last_result,
        "logs": system_mgr.logs[-30:]
    }


@app.post("/api/trigger")
def trigger_inspection_endpoint():
    try:
        res = system_mgr.trigger_inspection()
        return {"success": True, "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/focus_mode/toggle")
def toggle_focus_mode():
    system_mgr.focus_mode = not system_mgr.focus_mode
    mode_str = "BẬT SOI NÉT 1:1" if system_mgr.focus_mode else "TẮT SOI NÉT (VỀ TOÀN CẢNH)"
    system_mgr.add_log(f"Chế độ hiển thị: {mode_str}", "info")
    return {"success": True, "focus_mode": system_mgr.focus_mode}


@app.post("/api/auto_inspect/toggle")
def toggle_auto_inspect():
    system_mgr.auto_inspect = not system_mgr.auto_inspect
    mode_str = "BẬT TỰ ĐỘNG KIỂM TRA" if system_mgr.auto_inspect else "DỪNG TỰ ĐỘNG"
    system_mgr.add_log(f"Chế độ Auto Inspect: {mode_str}", "info")
    return {"success": True, "auto_inspect": system_mgr.auto_inspect}


@app.post("/api/settings/target")
async def update_target_code(payload: Dict[str, Any]):
    target = payload.get("target_code", "").strip().upper()
    if not target:
        raise HTTPException(status_code=400, detail="Mã tiêu chuẩn không được để trống")
    system_mgr.set_target_code(target)
    return {"success": True, "target_code": system_mgr.target_code}


@app.post("/api/settings/camera")
async def update_camera_settings(payload: Dict[str, Any]):
    if "exposure_time" in payload and "auto_exposure" in payload:
        system_mgr.set_camera_exposure(float(payload["exposure_time"]), bool(payload["auto_exposure"]))
    if "gain" in payload:
        system_mgr.set_camera_gain(float(payload["gain"]))
    return {"success": True}


@app.post("/api/settings/roi")
async def update_roi_settings(payload: Dict[str, Any]):
    ymin = float(payload.get("ymin", 0.25))
    xmin = float(payload.get("xmin", 0.25))
    ymax = float(payload.get("ymax", 0.75))
    xmax = float(payload.get("xmax", 0.75))
    system_mgr.set_roi(ymin, xmin, ymax, xmax)
    return {"success": True, "roi": system_mgr.roi}


@app.post("/api/stats/reset")
def reset_statistics():
    system_mgr.reset_stats()
    return {"success": True, "stats": system_mgr.stats}


@app.get("/api/history")
def get_history(limit: int = 50):
    return {"success": True, "history": system_mgr.get_history(limit)}


# ==========================================================
# WEBSOCKET REALTIME TELEMETRY
# ==========================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    system_mgr.ws_clients.append(websocket)
    try:
        while True:
            # Gửi gói nhịp tim và trạng thái mỗi 500ms
            telemetry = {
                "camera_connected": system_mgr.cam_connected,
                "fps": system_mgr.fps,
                "stats": system_mgr.stats,
                "focus_mode": system_mgr.focus_mode,
                "auto_inspect": system_mgr.auto_inspect,
                "last_result": system_mgr.last_result,
                "logs": system_mgr.logs[-15:]
            }
            await websocket.send_json(telemetry)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        if websocket in system_mgr.ws_clients:
            system_mgr.ws_clients.remove(websocket)
    except Exception:
        if websocket in system_mgr.ws_clients:
            system_mgr.ws_clients.remove(websocket)


def main():
    print("="*65)
    print(" KHỞI ĐỘNG HỆ THỐNG GIAO DIỆN WEB HMI - OCR BASLER GIGE ")
    print(" Truy cập tại trình duyệt: http://localhost:8000")
    print(" Hoặc từ máy khác trong mạng: http://[IP_MÁY_TÍNH]:8000")
    print("="*65)
    uvicorn.run("web_server:app", host="0.0.0.0", port=8000, reload=False, log_level="warning")


if __name__ == "__main__":
    main()
