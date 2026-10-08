import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent

# --- CẤU HÌNH CAMERA BASLER ---
CAMERA_IP = "192.168.3.3"
CAMERA_EXPOSURE_TIME = 25000.0  # Thời gian phơi sáng mặc định (25ms), đủ sáng cho ánh sáng phòng
CAMERA_GAIN = 0.0              # Gain (dB)
PACKET_SIZE = 9000             # Kích thước gói GigE (Jumbo Frame) hoặc 1500 nếu card mạng chuẩn

# --- CẤU HÌNH OCR & INSPECTION ---
TARGET_CODE = "10A"            # Mã ký tự tiêu chuẩn ca sản xuất
CONFIDENCE_THRESHOLD = 0.75    # Ngưỡng độ tin cậy chấp nhận

# --- CẤU HÌNH VÙNG QUAN TÂM (ROI - Region of Interest) ---
# Tỷ lệ phần trăm [ymin, xmin, ymax, xmax] so với toàn khung hình (0.0 đến 1.0)
# Hoặc để None nếu muốn quét toàn bộ ảnh
DEFAULT_ROI = {
    "enabled": True,
    "ymin": 0.25,
    "xmin": 0.25,
    "ymax": 0.75,
    "xmax": 0.75
}

# --- CẤU HÌNH LƯU TRỮ ---
SAVE_DIR_OK = BASE_DIR / "records" / "OK"
SAVE_DIR_NG = BASE_DIR / "records" / "NG"
SAVE_DIR_TEST = BASE_DIR / "records" / "TEST"

for d in [SAVE_DIR_OK, SAVE_DIR_NG, SAVE_DIR_TEST]:
    d.mkdir(parents=True, exist_ok=True)
