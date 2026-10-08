"""
Module OCR Engine & Logic so khớp ký tự trên băng chuyền.
Hỗ trợ tiền xử lý ảnh và so khớp chuỗi ký tự tiêu chuẩn.
"""

import sys
import cv2
import numpy as np
import re
import difflib
import torch

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


class InspectionResult:
    def __init__(self, is_pass=False, detected_text="", target_text="", confidence=0.0, roi_image=None, details=""):
        self.is_pass = is_pass
        self.detected_text = detected_text
        self.target_text = target_text
        self.confidence = confidence
        self.roi_image = roi_image
        self.details = details

    def __repr__(self):
        status = "OK" if self.is_pass else "NG"
        return f"[{status}] Nhận diện: '{self.detected_text}' | Mục tiêu: '{self.target_text}' | Tỉ lệ: {self.confidence:.2f}"


class OcrInspector:
    def __init__(self, target_code="10A", confidence_threshold=0.75):
        self.target_code = self.normalize_text(target_code)
        self.confidence_threshold = confidence_threshold
        self.reader = None
        if EASYOCR_AVAILABLE:
            use_gpu = torch.cuda.is_available()
            print(f"[OCR] Khởi tạo EasyOCR (GPU: {use_gpu})...")
            self.reader = easyocr.Reader(['en'], gpu=use_gpu)
        
        # Bảng ánh xạ ký tự hay nhầm lẫn trong môi trường công nghiệp
        self.confusion_map = {
            'O': '0',
            'o': '0',
            'I': '1',
            'l': '1',
            '|': '1',
            'B': '8',
            'S': '5',
            'Z': '2'
        }

    @staticmethod
    def normalize_text(text: str) -> str:
        """Chuẩn hóa chuỗi: xóa khoảng trắng thừa, xóa ký tự đặc biệt, chuyển chữ hoa."""
        if not text:
            return ""
        # Giữ lại chữ cái và số
        cleaned = re.sub(r'[^A-Za-z0-9]', '', str(text))
        return cleaned.strip().upper()

    def crop_roi(self, frame: np.ndarray, roi_config: dict) -> np.ndarray:
        """Cắt vùng quan tâm (ROI) theo tỷ lệ phần trăm khung hình."""
        if frame is None:
            return None
        if not roi_config.get("enabled", True):
            return frame

        h, w = frame.shape[:2]
        ymin = int(roi_config.get("ymin", 0.0) * h)
        ymax = int(roi_config.get("ymax", 1.0) * h)
        xmin = int(roi_config.get("xmin", 0.0) * w)
        xmax = int(roi_config.get("xmax", 1.0) * w)

        # Giới hạn an toàn
        ymin, ymax = max(0, ymin), min(h, ymax)
        xmin, xmax = max(0, xmin), min(w, xmax)

        return frame[ymin:ymax, xmin:xmax]

    def preprocess_image(self, image: np.ndarray) -> np.ndarray:
        """
        Tiền xử lý ảnh phục vụ nhận diện ký tự:
        1. Chuyển Grayscale
        2. Cân bằng sáng CLAHE (tăng tương phản cho chữ khắc/in mờ)
        3. Khử nhiễu Gaussian
        4. Phân ngưỡng Otsu hoặc Adaptive
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        contrast_enhanced = clahe.apply(gray)

        # Khử nhiễu nhẹ
        blurred = cv2.GaussianBlur(contrast_enhanced, (3, 3), 0)

        # Nhị phân hóa Otsu
        _, binary = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        return binary

    def calculate_similarity(self, text_a: str, text_b: str) -> float:
        """Tính độ tương đồng giữa hai chuỗi theo Levenshtein SequenceMatcher."""
        if not text_a and not text_b:
            return 1.0
        if not text_a or not text_b:
            return 0.0
        
        # Thử trực tiếp
        score1 = difflib.SequenceMatcher(None, text_a, text_b).ratio()
        
        # Thử với ánh xạ ký tự nhầm lẫn (ví dụ O -> 0)
        mapped_a = "".join(self.confusion_map.get(c, c) for c in text_a)
        mapped_b = "".join(self.confusion_map.get(c, c) for c in text_b)
        score2 = difflib.SequenceMatcher(None, mapped_a, mapped_b).ratio()
        
        return max(score1, score2)

    def recognize(self, image: np.ndarray, apply_preprocessing=True) -> tuple[str, float]:
        """
        Nhận diện ký tự từ ảnh (hoặc vùng ROI).
        Trả về: (detected_text, confidence_score)
        """
        if image is None or self.reader is None:
            return "", 0.0

        target_img = self.preprocess_image(image) if apply_preprocessing else image
        
        try:
            # Nhận dạng bằng EasyOCR
            results = self.reader.readtext(target_img)
            if not results:
                # Nếu tiền xử lý không ra, thử lại với ảnh gốc
                if apply_preprocessing:
                    results = self.reader.readtext(image)

            if not results:
                return "", 0.0

            # Lấy tất cả text tìm được và confidence trung bình
            texts = []
            scores = []
            for (bbox, text, score) in results:
                cleaned = self.normalize_text(text)
                if cleaned:
                    texts.append(cleaned)
                    scores.append(score)

            combined_text = "".join(texts)
            avg_score = float(np.mean(scores)) if scores else 0.0
            return combined_text, avg_score

        except Exception as e:
            print(f"[LỖI OCR INFERENCE] {e}")
            return "", 0.0

    def inspect_frame(self, frame: np.ndarray, roi_config: dict = None) -> InspectionResult:
        """Quy trình toàn diện: Crop ROI -> Thu phóng tối ưu -> OCR -> Đánh giá OK/NG."""
        if roi_config is None:
            from config import DEFAULT_ROI
            roi_config = DEFAULT_ROI

        roi_img = self.crop_roi(frame, roi_config)
        if roi_img is None or roi_img.size == 0:
            return self.evaluate("", 0.0, None)

        # Tối ưu kích thước ROI để OCR xử lý nhanh trên CPU (< 100-200ms)
        h, w = roi_img.shape[:2]
        max_dim = 1200
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            proc_img = cv2.resize(roi_img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        else:
            proc_img = roi_img

        detected_text, score = self.recognize(proc_img)
        return self.evaluate(detected_text, score, roi_img)

    def evaluate(self, raw_detected_text: str, confidence_score: float, roi_img: np.ndarray = None) -> InspectionResult:
        """
        Đánh giá kết quả OCR với mã mục tiêu:
        - So khớp chính xác hoặc độ tương đồng >= ngưỡng
        - Trả về đối tượng InspectionResult (PASS/FAIL)
        """
        norm_detected = self.normalize_text(raw_detected_text)
        norm_target = self.target_code

        similarity = self.calculate_similarity(norm_detected, norm_target)
        final_confidence = min(1.0, (confidence_score + similarity) / 2.0) if confidence_score > 0 else similarity

        is_match = (norm_detected == norm_target) or (similarity >= self.confidence_threshold)
        
        # Đánh giá PASS chỉ khi trùng khớp hoặc tỉ lệ đủ cao
        is_pass = is_match and (final_confidence >= self.confidence_threshold)
        
        details = f"Mã đọc: '{norm_detected}' vs Mục tiêu: '{norm_target}' (Độ khớp: {similarity*100:.1f}%)"
        
        return InspectionResult(
            is_pass=is_pass,
            detected_text=norm_detected,
            target_text=norm_target,
            confidence=final_confidence,
            roi_image=roi_img,
            details=details
        )
