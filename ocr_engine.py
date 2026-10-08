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

import warnings
warnings.filterwarnings("ignore", category=UserWarning)

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
        """Chuẩn hóa chuỗi: giữ lại chữ cái, số, dấu chấm (.), gạch nối (-), gạch chéo (/), gạch dưới (_) và khoảng trắng."""
        if not text:
            return ""
        # Giữ lại ký tự chữ, số, dấu chấm (.), gạch nối (-), gạch dưới (_), gạch chéo (/), hai chấm (:) và khoảng trắng
        cleaned = re.sub(r'[^A-Za-z0-9.\-_/: ]', '', str(text))
        cleaned = re.sub(r'\s+', ' ', cleaned).strip().upper()
        return cleaned

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
        Cân bằng tương phản nhẹ bằng CLAHE trên Grayscale (không nhị phân hóa gắt
        để bảo toàn viền nét của dấu chấm . và ký tự nhỏ).
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(gray)

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

    def recognize(self, image: np.ndarray) -> tuple[str, float, list[tuple[str, float]]]:
        """
        Nhận diện ký tự từ ảnh (hoặc vùng ROI).
        Trả về: (combined_text, best_confidence, candidate_items)
        """
        if image is None or self.reader is None:
            return "", 0.0, []

        try:
            # Ưu tiên nhận diện trực tiếp trên ảnh gốc để không mất dấu chấm hoặc chi tiết viền
            results = self.reader.readtext(image)
            if not results:
                # Nếu không đọc được, thử tiếp với ảnh cân bằng tương phản CLAHE
                enhanced = self.preprocess_image(image)
                results = self.reader.readtext(enhanced)

            if not results:
                return "", 0.0, []

            candidate_items = []
            texts = []
            scores = []
            for (bbox, text, score) in results:
                cleaned = self.normalize_text(text)
                if cleaned:
                    texts.append(cleaned)
                    sc = float(score)
                    scores.append(sc)
                    candidate_items.append((cleaned, sc))

            combined_text = " ".join(texts)
            max_score = max(scores) if scores else 0.0
            return combined_text, max_score, candidate_items

        except Exception as e:
            print(f"[LỖI OCR INFERENCE] {e}")
            return "", 0.0, []

    def inspect_frame(self, frame: np.ndarray, roi_config: dict = None) -> InspectionResult:
        """Quy trình toàn diện: Crop ROI -> Thu phóng tối ưu (~1s CPU) -> OCR -> Đánh giá OK/NG."""
        if roi_config is None:
            from config import DEFAULT_ROI
            roi_config = DEFAULT_ROI

        roi_img = self.crop_roi(frame, roi_config)
        if roi_img is None or roi_img.size == 0:
            return self.evaluate("", 0.0, [], None)

        # Tối ưu kích thước ROI để OCR xử lý nhanh trên CPU (~1-1.5s) và nhận diện sắc nét nhất
        h, w = roi_img.shape[:2]
        target_w = 760
        if w > target_w:
            scale = target_w / w
            proc_img = cv2.resize(roi_img, (target_w, int(h * scale)), interpolation=cv2.INTER_AREA)
        elif w < 300:
            scale = 400 / max(1, w)
            proc_img = cv2.resize(roi_img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        else:
            proc_img = roi_img

        combined_text, score, candidate_items = self.recognize(proc_img)
        return self.evaluate(combined_text, score, candidate_items, roi_img)

    def evaluate(self, combined_text: str, confidence_score: float, candidate_items: list = None, roi_img: np.ndarray = None) -> InspectionResult:
        """
        Đánh giá kết quả OCR với mã mục tiêu:
        - Tiêu chí: Chỉ cần chuỗi nhận dạng chứa đủ ký tự cần tìm (substring / containment) là ĐẠT (OK).
        - Ví dụ: Cần tìm '2.5' mà sản phẩm là '2.5 GBE' -> ĐẠT (OK)!
        - Tự động bỏ qua khác biệt dấu cách: '2.5' khớp '2.5GBE'.
        - Hỗ trợ fuzzy matching nếu ký tự gần đúng (độ tương đồng >= confidence_threshold).
        """
        norm_detected = self.normalize_text(combined_text)
        norm_target = self.normalize_text(self.target_code)

        if not norm_target:
            return InspectionResult(is_pass=False, detected_text=norm_detected, target_text="", confidence=0.0, roi_image=roi_img, details="Mã mục tiêu trống")

        target_no_space = norm_target.replace(" ", "")
        detected_no_space = norm_detected.replace(" ", "")

        candidates = [(norm_detected, confidence_score)]
        if candidate_items:
            for c_txt, c_sc in candidate_items:
                candidates.append((self.normalize_text(c_txt), c_sc))

        # 1. Kiểm tra chứa chuỗi mục tiêu (Substring / Containment Match)
        matched_candidate = None
        match_score = confidence_score
        for c_txt, c_sc in candidates:
            c_no_space = c_txt.replace(" ", "")
            if (norm_target in c_txt) or (target_no_space and target_no_space in c_no_space):
                matched_candidate = c_txt
                match_score = max(match_score, c_sc)
                break

        if matched_candidate is not None:
            # Tìm thấy ký tự mục tiêu nằm trong chuỗi đọc được!
            final_conf = max(match_score, 0.85)  # Gán độ tin cậy chuẩn xác vì đã chứa đúng cụm từ
            details = f"Tìm thấy '{norm_target}' trong '{matched_candidate}' (Khớp đạt chuẩn)"
            return InspectionResult(
                is_pass=True,
                detected_text=norm_detected,
                target_text=norm_target,
                confidence=final_conf,
                roi_image=roi_img,
                details=details
            )

        # 2. So khớp mờ (Fuzzy Similarity) nếu không chứa trọn vẹn
        similarity = self.calculate_similarity(detected_no_space, target_no_space)
        is_pass = (similarity >= self.confidence_threshold)
        final_conf = similarity if confidence_score <= 0 else min(1.0, (confidence_score + similarity) / 2.0)
        status_txt = "Khớp mờ đạt" if is_pass else "Không khớp"
        details = f"{status_txt}: '{norm_detected}' vs Mục tiêu '{norm_target}' (Độ tương đồng: {similarity*100:.1f}%)"

        return InspectionResult(
            is_pass=is_pass,
            detected_text=norm_detected,
            target_text=norm_target,
            confidence=final_conf,
            roi_image=roi_img,
            details=details
        )
