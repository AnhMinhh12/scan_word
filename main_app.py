"""
ỨNG DỤNG HMI KIỂM TRA MÃ KÝ TỰ SẢN PHẨM TRÊN BĂNG CHUYỀN (OCR INSPECTION)
Camera: Basler GigE (acA3800-10gm) - IP: 192.168.3.3
Tích hợp Auto Exposure, chỉnh Gain/Exposure trực tiếp và chế độ Focus Zoom 1:1.
"""

import sys
import os
import time
import threading
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import cv2
from PIL import Image, ImageTk
import numpy as np

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

import config
from camera_basler import BaslerGigECamera
from ocr_engine import OcrInspector, InspectionResult


class ConveyorOcrApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HỆ THỐNG KIỂM TRA OCR CAMERA BASLER - [IP: 192.168.3.3]")
        self.root.geometry("1366x850")
        self.root.minsize(1080, 720)
        self.root.configure(bg="#1E1E2E")  # Dark modern theme

        # Biến trạng thái hệ thống
        self.is_running = False
        self.camera = None
        self.ocr_inspector = None
        self.capture_thread = None
        self.focus_mode = False  # Chế độ soi nét 1:1 vùng chữ

        # Thống kê sản lượng
        self.total_count = 0
        self.ok_count = 0
        self.ng_count = 0

        # Cấu hình ROI (tỷ lệ 0.0 - 1.0)
        self.roi = dict(config.DEFAULT_ROI)

        self._init_ui()
        self._init_engine_async()

    def _init_ui(self):
        # Header Bar
        header = tk.Frame(self.root, bg="#11111B", height=60)
        header.pack(fill=tk.X, side=tk.TOP)

        title_lbl = tk.Label(
            header,
            text="HỆ THỐNG KIỂM TRA MÃ KÝ TỰ BĂNG CHUYỀN (CONVEYOR OCR)",
            font=("Segoe UI", 16, "bold"),
            fg="#CDD6F4",
            bg="#11111B"
        )
        title_lbl.pack(side=tk.LEFT, padx=20, pady=12)

        self.lbl_cam_status = tk.Label(
            header,
            text="CAMERA: ĐANG KẾT NỐI...",
            font=("Segoe UI", 11, "bold"),
            fg="#F9E2AF",
            bg="#11111B"
        )
        self.lbl_cam_status.pack(side=tk.RIGHT, padx=20, pady=12)

        # Main Layout (Left: Live Feed, Right: Control & Stats)
        main_body = tk.Frame(self.root, bg="#1E1E2E")
        main_body.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)

        # --- CỘT TRÁI: CAMERA VIEW ---
        left_panel = tk.Frame(main_body, bg="#181825", bd=2, relief=tk.GROOVE)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Thanh công cụ camera nhanh trên màn hình ảnh
        cam_toolbar = tk.Frame(left_panel, bg="#181825")
        cam_toolbar.pack(fill=tk.X, padx=8, pady=(8, 0))

        self.btn_focus_mode = tk.Button(
            cam_toolbar,
            text="🔍 BẬT SOI NÉT (ZOOM 1:1 ROI)",
            font=("Segoe UI", 10, "bold"),
            bg="#313244",
            fg="#89B4FA",
            command=self.toggle_focus_mode
        )
        self.btn_focus_mode.pack(side=tk.LEFT, padx=4)

        self.lbl_mode_desc = tk.Label(
            cam_toolbar,
            text="[Chế độ: Toàn cảnh cảm biến]",
            font=("Segoe UI", 9, "italic"),
            fg="#A6ADC8",
            bg="#181825"
        )
        self.lbl_mode_desc.pack(side=tk.LEFT, padx=10)

        # Khung hiển thị Video
        self.video_canvas = tk.Label(left_panel, bg="#000000", text="Đang tải luồng camera...")
        self.video_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Banner trạng thái kết quả (PASS / FAIL)
        self.result_banner = tk.Label(
            left_panel,
            text="CHƯA CÓ KẾT QUẢ",
            font=("Segoe UI", 22, "bold"),
            bg="#313244",
            fg="#CDD6F4",
            height=2
        )
        self.result_banner.pack(fill=tk.X, padx=8, pady=(0, 8))

        # --- CỘT PHẢI: CONTROL PANEL & STATS ---
        right_panel = tk.Frame(main_body, bg="#181825", width=420)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        right_panel.pack_propagate(False)

        # 1. CÀI ĐẶT ĐỘ SÁNG & ĐỘ NÉT CAMERA
        cam_group = tk.LabelFrame(
            right_panel,
            text=" 1. Điều Chỉnh Độ Sáng & Nét (Camera) ",
            font=("Segoe UI", 11, "bold"),
            fg="#89B4FA",
            bg="#181825",
            bd=1,
            relief=tk.SOLID
        )
        cam_group.pack(fill=tk.X, padx=12, pady=6)

        # Checkbox Auto Exposure
        self.var_auto_exp = tk.BooleanVar(value=True)
        chk_auto = tk.Checkbutton(
            cam_group,
            text="Tự động cân sáng liên tục (Auto Exposure)",
            variable=self.var_auto_exp,
            font=("Segoe UI", 10, "bold"),
            fg="#A6E3A1",
            bg="#181825",
            selectcolor="#313244",
            activebackground="#181825",
            activeforeground="#A6E3A1",
            command=self.on_auto_exp_toggle
        )
        chk_auto.pack(anchor="w", padx=8, pady=4)

        # Slider Phơi Sáng (Exposure)
        exp_frame = tk.Frame(cam_group, bg="#181825")
        exp_frame.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(exp_frame, text="Phơi sáng (µs):", font=("Segoe UI", 9), fg="#CDD6F4", bg="#181825").pack(side=tk.LEFT)
        self.lbl_exp_val = tk.Label(exp_frame, text="25000", font=("Segoe UI", 9, "bold"), fg="#89B4FA", bg="#181825")
        self.lbl_exp_val.pack(side=tk.RIGHT)

        self.slider_exp = ttk.Scale(cam_group, from_=1000, to=80000, value=25000, command=self.on_exposure_slide)
        self.slider_exp.pack(fill=tk.X, padx=8, pady=(0, 6))

        # Slider Khuếch đại sáng (Gain)
        gain_frame = tk.Frame(cam_group, bg="#181825")
        gain_frame.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(gain_frame, text="Độ lợi sáng (Gain):", font=("Segoe UI", 9), fg="#CDD6F4", bg="#181825").pack(side=tk.LEFT)
        self.lbl_gain_val = tk.Label(gain_frame, text="0", font=("Segoe UI", 9, "bold"), fg="#FAB387", bg="#181825")
        self.lbl_gain_val.pack(side=tk.RIGHT)

        self.slider_gain = ttk.Scale(cam_group, from_=0, to=300, value=0, command=self.on_gain_slide)
        self.slider_gain.pack(fill=tk.X, padx=8, pady=(0, 6))

        # 2. CÀI ĐẶT CA SẢN XUẤT
        setup_group = tk.LabelFrame(
            right_panel,
            text=" 2. Cài Đặt Ca Sản Xuất ",
            font=("Segoe UI", 11, "bold"),
            fg="#A6E3A1",
            bg="#181825",
            bd=1,
            relief=tk.SOLID
        )
        setup_group.pack(fill=tk.X, padx=12, pady=6)

        tk.Label(setup_group, text="Mã Tiêu Chuẩn:", font=("Segoe UI", 10), fg="#CDD6F4", bg="#181825").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.entry_target = tk.Entry(setup_group, font=("Segoe UI", 13, "bold"), justify="center", bg="#313244", fg="#A6E3A1", insertbackground="white")
        self.entry_target.insert(0, config.TARGET_CODE)
        self.entry_target.grid(row=0, column=1, padx=8, pady=6, sticky="ew")

        # 3. NÚT ĐIỀU KHIỂN CHÍNH
        btn_group = tk.Frame(right_panel, bg="#181825")
        btn_group.pack(fill=tk.X, padx=12, pady=6)

        self.btn_single_trigger = tk.Button(
            btn_group,
            text="⚡ CHỤP & KIỂM TRA THỬ (1 ẢNH)",
            font=("Segoe UI", 11, "bold"),
            bg="#89B4FA",
            fg="#11111B",
            activebackground="#B4BEFE",
            command=self.trigger_single_shot,
            height=2
        )
        self.btn_single_trigger.pack(fill=tk.X, pady=4)

        # 4. THỐNG KÊ SẢN LƯỢNG
        stats_group = tk.LabelFrame(
            right_panel,
            text=" 3. Thống Kê Sản Lượng ",
            font=("Segoe UI", 11, "bold"),
            fg="#FAB387",
            bg="#181825",
            bd=1,
            relief=tk.SOLID
        )
        stats_group.pack(fill=tk.X, padx=12, pady=6)

        self.lbl_total = self._create_stat_row(stats_group, "TỔNG SỐ ĐÃ TEST:", "0", "#CDD6F4", 0)
        self.lbl_ok = self._create_stat_row(stats_group, "SỐ LƯỢNG OK (PASS):", "0", "#A6E3A1", 1)
        self.lbl_ng = self._create_stat_row(stats_group, "SỐ LƯỢNG NG (FAIL):", "0", "#F38BA8", 2)
        self.lbl_rate = self._create_stat_row(stats_group, "TỶ LỆ LỖI (NG RATE):", "0.0%", "#F9E2AF", 3)

        btn_reset = tk.Button(stats_group, text="Reset Bộ Đếm", font=("Segoe UI", 9), bg="#45475A", fg="#CDD6F4", command=self.reset_counters)
        btn_reset.grid(row=4, column=0, columnspan=2, pady=6, padx=8, sticky="ew")

        # 5. NHẬT KÝ CHI TIẾT
        log_group = tk.LabelFrame(
            right_panel,
            text=" 4. Nhật Ký Nhận Diện ",
            font=("Segoe UI", 11, "bold"),
            fg="#CBA6F7",
            bg="#181825",
            bd=1,
            relief=tk.SOLID
        )
        log_group.pack(fill=tk.BOTH, expand=True, padx=12, pady=(6, 10))

        self.log_text = tk.Text(log_group, bg="#11111B", fg="#CDD6F4", font=("Consolas", 9), state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

    def _create_stat_row(self, parent, label_text, default_val, fg_color, row_idx):
        tk.Label(parent, text=label_text, font=("Segoe UI", 9, "bold"), fg="#A6ADC8", bg="#181825").grid(row=row_idx, column=0, sticky="w", padx=8, pady=3)
        val_lbl = tk.Label(parent, text=default_val, font=("Segoe UI", 12, "bold"), fg=fg_color, bg="#181825")
        val_lbl.grid(row=row_idx, column=1, sticky="e", padx=8, pady=3)
        return val_lbl

    def log(self, message):
        """Ghi thông báo vào khung nhật ký và hiển thị trên terminal."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"
        print(f"[{timestamp}] {message}", flush=True)

        def _update():
            try:
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, formatted)
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
            except Exception:
                pass

        self.root.after(0, _update)

    def toggle_focus_mode(self):
        """Chuyển đổi giữa xem toàn cảnh và phóng to 1:1 vùng ROI để vặn nét."""
        self.focus_mode = not self.focus_mode
        if self.focus_mode:
            self.btn_focus_mode.config(text="🔎 TẮT SOI NÉT (VỀ TOÀN CẢNH)", bg="#A6E3A1", fg="#11111B")
            self.lbl_mode_desc.config(text="[ĐANG SOI NÉT: Phóng to 1:1 vùng chữ để vặn lens]", fg="#A6E3A1")
            self.log("[CHẾ ĐỘ NÉT] Đang phóng to 1:1 vùng ROI. Bạn hãy xoay vòng nét trên ống kính cho đến khi chữ thật rõ!")
        else:
            self.btn_focus_mode.config(text="🔍 BẬT SOI NÉT (ZOOM 1:1 ROI)", bg="#313244", fg="#89B4FA")
            self.lbl_mode_desc.config(text="[Chế độ: Toàn cảnh cảm biến]", fg="#A6ADC8")

    def on_auto_exp_toggle(self):
        """Bật/tắt Auto Exposure."""
        is_auto = self.var_auto_exp.get()
        if self.camera:
            self.camera.set_auto_exposure(is_auto)
            if is_auto:
                self.log("[CAMERA] Đã BẬT Auto Exposure. Camera đang tự cân sáng.")
            else:
                self.log("[CAMERA] Đã TẮT Auto Exposure. Bạn có thể kéo thanh trượt phơi sáng.")

    def on_exposure_slide(self, val):
        """Điều chỉnh thời gian phơi sáng bằng slider."""
        exp_us = int(float(val))
        self.lbl_exp_val.config(text=str(exp_us))
        if self.camera:
            # Tự động bỏ tick Auto khi kéo tay
            if self.var_auto_exp.get():
                self.var_auto_exp.set(False)
            self.camera.set_exposure_time(exp_us)

    def on_gain_slide(self, val):
        """Điều chỉnh Gain bằng slider."""
        gain_val = int(float(val))
        self.lbl_gain_val.config(text=str(gain_val))
        if self.camera:
            self.camera.set_gain(gain_val)

    def _init_engine_async(self):
        """Khởi tạo camera và OCR trong luồng nền để không treo GUI."""
        def worker():
            self.log("Đang khởi tạo OCR Engine...")
            self.ocr_inspector = OcrInspector(target_code=config.TARGET_CODE)
            self.log("[OK] OCR Engine đã sẵn sàng!")

            self.log(f"Đang kết nối Camera Basler IP: {config.CAMERA_IP}...")
            try:
                self.camera = BaslerGigECamera(ip_address=config.CAMERA_IP, exposure_time=config.CAMERA_EXPOSURE_TIME)
                self.camera.connect()
                
                # Bật Auto Exposure ngay khi khởi động để ảnh sáng rõ tức thì
                self.camera.set_auto_exposure(True)

                self.lbl_cam_status.config(text=f"CAM: ONLINE ({self.camera.model_name})", fg="#A6E3A1")
                self.log(f"[OK] Đã kết nối camera: {self.camera.model_name} (S/N: {self.camera.serial_number})")
                self.log("[OK] Đã kích hoạt Auto Exposure tự động cân sáng!")
                
                # Bắt đầu luồng hiển thị Live View
                self.is_running = True
                self.capture_thread = threading.Thread(target=self._camera_loop, daemon=True)
                self.capture_thread.start()
            except Exception as e:
                self.lbl_cam_status.config(text="CAM: LỖI KẾT NỐI", fg="#F38BA8")
                self.log(f"[LỖI] Không thể mở camera: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def _camera_loop(self):
        """Vòng lặp thu nhận hình ảnh liên tục từ camera."""
        while True:
            if not self.camera or not self.camera.is_connected:
                time.sleep(0.1)
                continue

            frame = self.camera.grab_frame(timeout_ms=1000)
            if frame is not None:
                self._update_display(frame)
            time.sleep(0.03)  # ~30 FPS preview

    def _update_display(self, frame):
        """Hiển thị khung hình và hỗ trợ chế độ soi nét 1:1."""
        try:
            h, w = frame.shape[:2]

            ymin, xmin = int(self.roi["ymin"] * h), int(self.roi["xmin"] * w)
            ymax, xmax = int(self.roi["ymax"] * h), int(self.roi["xmax"] * w)

            canvas_w = self.video_canvas.winfo_width() or 800
            canvas_h = self.video_canvas.winfo_height() or 550

            if self.focus_mode:
                # CHẾ ĐỘ SOI NÉT: Cắt nguyên vẹn độ phân giải 1:1 vùng chữ
                crop_roi = frame[ymin:ymax, xmin:xmax]
                ch, cw = crop_roi.shape[:2]
                scale = min(canvas_w / cw, canvas_h / ch)
                disp_w, disp_h = max(10, int(cw * scale)), max(10, int(ch * scale))
                resized = cv2.resize(crop_roi, (disp_w, disp_h), interpolation=cv2.INTER_NEAREST)
                cv2.putText(resized, "ZOOM 1:1 - XOAY NHOE/NET TREN ONG KINH", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            else:
                # CHẾ ĐỘ TOÀN CẢNH: Vẽ khung ROI định vị
                disp_frame = frame.copy()
                cv2.rectangle(disp_frame, (xmin, ymin), (xmax, ymax), (0, 255, 255), 4)
                cv2.putText(disp_frame, "VUNG OCR (ROI)", (xmin, max(40, ymin - 15)),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)

                scale = min(canvas_w / w, canvas_h / h)
                disp_w, disp_h = max(10, int(w * scale)), max(10, int(h * scale))
                resized = cv2.resize(disp_frame, (disp_w, disp_h), interpolation=cv2.INTER_AREA)

            rgb_frame = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)
            img_tk = ImageTk.PhotoImage(image=img)

            self.video_canvas.img_tk = img_tk
            self.video_canvas.config(image=img_tk, text="")
        except Exception:
            pass

    def trigger_single_shot(self):
        """Kích hoạt chụp và kiểm tra 1 sản phẩm."""
        if not self.camera or not self.camera.is_connected:
            messagebox.showwarning("Cảnh báo", "Camera chưa được kết nối!")
            return

        def process():
            self.log(">> Đang kích chụp & phân tích...")
            target = self.entry_target.get().strip().upper()
            if self.ocr_inspector:
                self.ocr_inspector.target_code = target

            frame = self.camera.grab_frame(timeout_ms=3000)
            if frame is None:
                self.log("[LỖI] Không lấy được frame.")
                return

            result = self.ocr_inspector.inspect_frame(frame, self.roi)
            self._handle_inspection_result(result, frame)

        threading.Thread(target=process, daemon=True).start()

    def _handle_inspection_result(self, result: InspectionResult, full_frame: np.ndarray):
        """Xử lý kết quả kiểm tra: Cập nhật UI, lưu ảnh, cập nhật bộ đếm."""
        self.total_count += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]

        if result.is_pass:
            self.ok_count += 1
            status_text = f"PASS (OK) - Mã: '{result.detected_text}'"
            banner_bg = "#A6E3A1"
            banner_fg = "#11111B"
            save_path = config.SAVE_DIR_OK / f"OK_{timestamp}_{result.detected_text}.jpg"
        else:
            self.ng_count += 1
            status_text = f"FAIL (NG) - Đọc được: '{result.detected_text}' [Mục tiêu: {result.target_text}]"
            banner_bg = "#F38BA8"
            banner_fg = "#11111B"
            save_path = config.SAVE_DIR_NG / f"NG_{timestamp}_{result.detected_text}.jpg"

        try:
            cv2.imwrite(str(save_path), full_frame)
        except Exception as e:
            print(f"Lỗi lưu ảnh: {e}")

        def update_ui():
            self.result_banner.config(text=status_text, bg=banner_bg, fg=banner_fg)
            self.lbl_total.config(text=str(self.total_count))
            self.lbl_ok.config(text=str(self.ok_count))
            self.lbl_ng.config(text=str(self.ng_count))
            ng_rate = (self.ng_count / self.total_count * 100) if self.total_count > 0 else 0.0
            self.lbl_rate.config(text=f"{ng_rate:.1f}%")
            self.log(f"Kết quả: {result.details} -> Lưu: {save_path.name}")

        self.root.after(0, update_ui)

    def reset_counters(self):
        """Đặt lại toàn bộ bộ đếm sản lượng."""
        self.total_count = 0
        self.ok_count = 0
        self.ng_count = 0
        self.lbl_total.config(text="0")
        self.lbl_ok.config(text="0")
        self.lbl_ng.config(text="0")
        self.lbl_rate.config(text="0.0%")
        self.result_banner.config(text="ĐÃ RESET BỘ ĐẾM", bg="#313244", fg="#CDD6F4")
        self.log("Đã reset toàn bộ thống kê sản lượng.")


def main():
    root = tk.Tk()
    app = ConveyorOcrApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
