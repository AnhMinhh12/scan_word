"""
Module quản lý kết nối và thu nhận hình ảnh từ Camera công nghiệp Basler GigE.
Hỗ trợ tìm và kết nối trực tiếp theo địa chỉ IP.
"""

import sys
import cv2
import numpy as np

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import config
try:
    from pypylon import pylon
    PYPYLON_AVAILABLE = True
except ImportError:
    PYPYLON_AVAILABLE = False


class BaslerGigECamera:
    def __init__(self, ip_address="192.168.3.3", exposure_time=2000.0):
        self.ip_address = ip_address
        self.exposure_time = exposure_time
        self.camera = None
        self.converter = None
        self.is_connected = False
        self.model_name = "Unknown"
        self.serial_number = "Unknown"

    def connect(self):
        """Khởi tạo kết nối tới camera Basler theo địa chỉ IP."""
        if not PYPYLON_AVAILABLE:
            raise RuntimeError("Thư viện 'pypylon' chưa được cài đặt. Chạy: pip install pypylon")

        tl_factory = pylon.TlFactory.GetInstance()

        # Cách 1: Tìm thiết bị khớp đúng địa chỉ IP trong danh sách mạng
        devices = tl_factory.EnumerateDevices()
        target_device_info = None

        for dev in devices:
            dev_ip = dev.GetIpAddress() if hasattr(dev, "GetIpAddress") else dev.GetPropertyOrDefault("IpAddress", "")
            if dev_ip == self.ip_address:
                target_device_info = dev
                break

        # Cách 2: Nếu không duyệt thấy bằng EnumerateDevices, thử tạo DeviceInfo gán IP trực tiếp
        if target_device_info is None:
            info = pylon.DeviceInfo()
            info.SetIpAddress(self.ip_address)
            target_device_info = info

        try:
            device = tl_factory.CreateDevice(target_device_info)
            self.camera = pylon.InstantCamera(device)
            self.camera.Open()

            # Lấy thông tin thiết bị
            dev_info = self.camera.GetDeviceInfo()
            self.model_name = dev_info.GetModelName()
            self.serial_number = dev_info.GetSerialNumber()
            self.is_connected = True

            # 1. Tắt TriggerMode để camera truyền frame liên tục (free-run), không đợi kích xung ngoài
            try:
                if hasattr(self.camera, "TriggerMode"):
                    self.camera.TriggerMode.SetValue("Off")
            except Exception as e:
                print(f"[CẢNH BÁO] Không thể chỉnh TriggerMode: {e}")

            # 2. Cấu hình Packet Size GigE phù hợp card mạng (1500 bytes tránh drop packet trên card Realtek)
            try:
                if hasattr(self.camera, "GevSCPSPacketSize"):
                    pkt_size = getattr(config, "PACKET_SIZE", 1500)
                    self.camera.GevSCPSPacketSize.SetValue(int(pkt_size))
                    print(f"[BASLER] Đã thiết lập Packet Size: {pkt_size} bytes")
            except Exception as e:
                print(f"[CẢNH BÁO] Không thể cấu hình Packet Size: {e}")

            # 3. Cấu hình Inter-Packet Delay (SCPD) để tránh tràn bộ đệm card mạng
            try:
                if hasattr(self.camera, "GevSCPD"):
                    scpd = getattr(config, "GEV_SCPD", 100)
                    self.camera.GevSCPD.SetValue(int(scpd))
                    print(f"[BASLER] Đã thiết lập GevSCPD: {scpd} ticks")
            except Exception:
                pass

            # 4. Tăng bộ đệm khung hình
            try:
                self.camera.MaxNumBuffer = 15
            except Exception:
                pass

            # Khởi tạo bộ chuyển đổi định dạng ảnh sang BGR8 của OpenCV
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_BGR8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

            # Cấu hình Exposure Time ban đầu
            self.set_exposure_time(self.exposure_time)

            # Bắt đầu chế độ lấy ảnh
            self.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

            print(f"[BASLER] Đã kết nối thành công: Model={self.model_name}, S/N={self.serial_number}, IP={self.ip_address}")
            return True

        except Exception as e:
            self.is_connected = False
            self.camera = None
            raise ConnectionError(f"Không thể mở camera Basler tại IP {self.ip_address}: {e}")

    def set_exposure_time(self, exposure_us):
        """Cài đặt thời gian phơi sáng (micro-giây / µs)."""
        if self.camera and self.camera.IsOpen():
            try:
                # Tắt Auto Exposure trước nếu đang bật để nhận giá trị manual
                if hasattr(self.camera, "ExposureAuto") and self.camera.ExposureAuto.GetValue() != "Off":
                    self.camera.ExposureAuto.SetValue("Off")

                # Camera Basler ace 1 dùng ExposureTimeAbs, ace 2 dùng ExposureTime
                if hasattr(self.camera, "ExposureTimeAbs"):
                    self.camera.ExposureTimeAbs.SetValue(float(exposure_us))
                elif hasattr(self.camera, "ExposureTime"):
                    self.camera.ExposureTime.SetValue(float(exposure_us))
                elif hasattr(self.camera, "ExposureTimeRaw"):
                    self.camera.ExposureTimeRaw.SetValue(int(exposure_us))
                self.exposure_time = exposure_us
            except Exception as e:
                print(f"[CẢNH BÁO] Không thể chỉnh Exposure: {e}")

    def set_auto_exposure(self, enable=True):
        """Bật hoặc tắt chế độ Tự Động Phơi Sáng (Continuous Auto Exposure)."""
        if self.camera and self.camera.IsOpen():
            try:
                if hasattr(self.camera, "ExposureAuto"):
                    mode = "Continuous" if enable else "Off"
                    self.camera.ExposureAuto.SetValue(mode)
                    print(f"[BASLER] ExposureAuto: {mode}")
            except Exception as e:
                print(f"[CẢNH BÁO] Không thể đổi ExposureAuto: {e}")

    def set_gain(self, gain_val):
        """Cài đặt Gain khuếch đại tín hiệu sáng (tự động kẹp trong dải Min - Max hợp lệ)."""
        if self.camera and self.camera.IsOpen():
            try:
                if hasattr(self.camera, "GainRaw"):
                    min_v = self.camera.GainRaw.GetMin()
                    max_v = self.camera.GainRaw.GetMax()
                    val = int(max(min_v, min(max_v, int(gain_val))))
                    self.camera.GainRaw.SetValue(val)
                elif hasattr(self.camera, "Gain"):
                    min_v = self.camera.Gain.GetMin()
                    max_v = self.camera.Gain.GetMax()
                    val = float(max(min_v, min(max_v, float(gain_val))))
                    self.camera.Gain.SetValue(val)
            except Exception as e:
                print(f"[CẢNH BÁO] Không thể chỉnh Gain: {e}")

    def grab_frame(self, timeout_ms=5000):
        """
        Chụp một khung hình từ camera.
        Trả về: frame dạng numpy.ndarray (BGR) hoặc None nếu lỗi.
        """
        if not self.is_connected or not self.camera or not self.camera.IsGrabbing():
            return None

        try:
            grab_result = self.camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)
            if grab_result.GrabSucceeded():
                image = self.converter.Convert(grab_result)
                frame = image.GetArray()
                grab_result.Release()
                return frame
            grab_result.Release()
            return None
        except Exception as e:
            err_msg = str(e)
            if "TimeoutException" in err_msg:
                print(f"[LỖI GRAB] Hết thời gian chờ nhận ảnh (Timeout {timeout_ms}ms). Gói tin có thể bị chặn bởi MTU hoặc Trigger.")
            else:
                print(f"[LỖI GRAB] {e}")
            return None

    def disconnect(self):
        """Dừng thu nhận ảnh và giải phóng camera."""
        if self.camera:
            try:
                if self.camera.IsGrabbing():
                    self.camera.StopGrabbing()
                if self.camera.IsOpen():
                    self.camera.Close()
            except Exception as e:
                print(f"[LỖI ĐÓNG CAM] {e}")
            finally:
                self.camera = None
                self.is_connected = False
                print("[BASLER] Đã ngắt kết nối an toàn.")
