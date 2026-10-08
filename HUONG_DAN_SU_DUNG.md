# HƯỚNG DẪN VẬN HÀNH HỆ THỐNG OCR CAMERA BASLER GIGE

Hệ thống thị giác máy tính nhận diện và kiểm tra mã ký tự trên băng chuyền sản xuất.
Đã tích hợp và xác thực trực tiếp với camera thật:
* **Hãng:** Basler GigE
* **Model:** acA3800-10gm (Độ phân giải: 3840 x 2748 px)
* **Serial Number:** 23298384
* **Địa chỉ IP:** 192.168.3.3

---

## 1. Cấu Trúc Mã Nguồn Dự Án

* `web_server.py`: **Máy chủ Web HMI chính** (FastAPI, Uvicorn, MJPEG Live Stream, REST API & WebSocket Realtime).
* `web/`: Thư mục giao diện Web hiện đại (HTML5, Vanilla CSS Glassmorphic Cyber Dark, JavaScript ES6).
* `start_web.bat`: File nhấp đúp để khởi chạy nhanh giao diện Web HMI.
* `config.py`: Tệp cấu hình hệ thống (IP camera, thời gian phơi sáng Exposure, mã mục tiêu mặc định `10A`, tỷ lệ ROI, thư mục lưu ảnh).
* `camera_basler.py`: Module điều khiển camera Basler qua thư viện chính hãng `pypylon`.
* `ocr_engine.py`: Lõi thuật toán tiền xử lý ảnh (CLAHE, Otsu, Gaussian), nhận dạng OCR và bộ so khớp ký tự thông minh.
* `main_app.py`: Giao diện cửa sổ Desktop truyền thống cũ (Tkinter).

---

## 2. Cách Khởi Chạy Giao Diện Web (Khuyên dùng)

### Cách 1: Khởi chạy nhanh bằng file Batch
Nhấp đúp chuột vào file:
👉 **`start_web.bat`**

### Cách 2: Khởi chạy bằng lệnh PowerShell
```powershell
python web_server.py
```
Sau đó mở trình duyệt web (Chrome, Edge, Firefox, Cốc Cốc) và truy cập:
* Trên máy tính gắn camera: **`http://localhost:8000`**
* Hoặc từ điện thoại, máy tính bảng, màn hình HMI khác trong mạng LAN: **`http://[IP_MAY_TINH]:8000`**

---

## 3. Tính Năng Vượt Trội Của Giao Diện Web HMI

1. **Live Stream Camera Siêu Mượt:** Xem video trực tiếp 25–30 FPS ngay trên trình duyệt mà không cần cài đặt phần mềm phụ trợ.
2. **Kích Chụp Linh Hoạt:**
   * Bấm nút **"⚡ CHỤP & KIỂM TRA (1 ẢNH)"** trên màn hình.
   * Hoặc nhấn phím tắt **[SPACE]** hoặc **[ENTER]** trên bàn phím.
3. **Chế Độ Tự Động (Auto Inspect):** Bật công tắc gạt *"Tự Động Quét Liên Tục"* để hệ thống tự động kiểm tra định kỳ chu kỳ 2.0s trên băng chuyền.
4. **Chế Độ Soi Nét 1:1 (Lens Focus Mode):** Bấm nút **"🔍 SOI NÉT 1:1"** (phím tắt **[F]**) để phóng to nguyên bản điểm ảnh vùng chữ, hỗ trợ kỹ thuật viên vặn vòng nét ống kính chính xác tuyệt đối.
5. **Điều Khiển Phần Cứng Trực Tiếp:**
   * Bật/tắt Auto Exposure cân sáng tức thì.
   * Kéo thanh trượt thời gian phơi sáng (1,000 µs - 80,000 µs) hoặc chọn nhanh `5ms`, `15ms`, `25ms`, `40ms`.
   * Tăng giảm Gain trực tiếp.
6. **Vùng Nhận Diện ROI Trực Quan:** Kéo 4 thanh trượt Y-Min, Y-Max, X-Min, X-Max để căn chỉnh khung đọc ký tự theo mọi kích thước sản phẩm.
7. **Thư Viện Ảnh Lưu Trữ (OK / NG Archive):** Xem lại toàn bộ ảnh lịch sử phân loại, lọc ảnh Đạt/Lỗi, nhấp vào để phóng to toàn màn hình và tải ảnh gốc độ phân giải cao về máy.
