"""
Script kiểm tra kết nối Camera Basler tại IP chỉ định.
Chụp 1 ảnh thử nghiệm và lưu vào thư mục records/TEST/.
"""

import sys
import time
import cv2

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from camera_basler import BaslerGigECamera
import config

def test_connection():
    print(f"=== KIỂM TRA KẾT NỐI CAMERA BASLER ===")
    print(f"Địa chỉ IP mục tiêu: {config.CAMERA_IP}")
    
    cam = BaslerGigECamera(ip_address=config.CAMERA_IP, exposure_time=config.CAMERA_EXPOSURE_TIME)
    
    try:
        print("Đang khởi tạo kết nối...")
        cam.connect()
        
        print(f"[THÀNH CÔNG] Camera: {cam.model_name}")
        print(f"[THÀNH CÔNG] Serial: {cam.serial_number}")
        print("Đang chụp thử khung hình đầu tiên...")
        
        # Đợi camera ổn định 0.5s
        time.sleep(0.5)
        
        frame = cam.grab_frame(timeout_ms=5000)
        if frame is not None:
            h, w = frame.shape[:2]
            print(f"[THÀNH CÔNG] Đã nhận khung hình: Kích thước {w}x{h} px")
            
            output_path = config.SAVE_DIR_TEST / "test_snapshot.jpg"
            cv2.imwrite(str(output_path), frame)
            print(f"[THÀNH CÔNG] Đã lưu ảnh chụp thử vào: {output_path}")
        else:
            print("[THẤT BẠI] Không nhận được frame từ camera.")
            
    except Exception as e:
        print(f"[LỖI KẾT NỐI]: {e}")
        print("\nGỢI Ý KIỂM TRA:")
        print("1. Kiểm tra camera đã cắm nguồn và cắm cáp mạng vào PC chưa.")
        print("2. Chạy lệnh: ping 192.168.3.3 xem có thông không.")
        print("3. Đảm bảo phần mềm 'Pylon Viewer' không đang mở (vì Pylon Viewer sẽ khóa độc quyền camera).")
    finally:
        cam.disconnect()

if __name__ == "__main__":
    test_connection()
