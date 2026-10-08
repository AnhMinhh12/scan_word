import os
from pathlib import Path

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent

# --- CẤU HÌNH CAMERA BASLER ---
CAMERA_IP = "192.168.3.3"
CAMERA_EXPOSURE_TIME = 25000.0  # Thời gian phơi sáng mặc định (25ms), đủ sáng cho ánh sáng phòng
CAMERA_GAIN = 51.0             # Gain mặc định (cho acA3800-10gm Min là 51)
PACKET_SIZE = 1500             # Kích thước gói GigE (1500 chuẩn MTU Ethernet Realtek để không drop packet)
GEV_SCPD = 100                 # Độ trễ giữa các gói GigE (100 ticks giúp tăng FPS lên gấp đôi ~8FPS mà không nghẽn)

# --- CẤU HÌNH OCR & INSPECTION ---
TARGET_CODE = "2.5"            # Mã ký tự tiêu chuẩn ca sản xuất (ví dụ 2.5, 2.5 GbE, 10A)
CONFIDENCE_THRESHOLD = 0.60    # Ngưỡng độ tin cậy chấp nhận

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
