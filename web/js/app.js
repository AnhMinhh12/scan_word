/**
 * CONVEYOR OCR INDUSTRIAL VISION SYSTEM - FRONTEND APPLICATION
 * Clean Light Theme, Horizontal Navigation Tabs & Zero-Scroll Single-Screen Layout.
 */

// --- Global Application State ---
const state = {
    connected: false,
    ws: null,
    cameraConnected: false,
    fps: 0,
    focusMode: false,
    autoInspect: false,
    targetCode: "10A",
    exposureTime: 25000,
    autoExposure: true,
    gain: 0,
    roi: { ymin: 0.25, xmin: 0.25, ymax: 0.75, xmax: 0.75 },
    stats: { total: 0, ok: 0, ng: 0, ng_rate: 0.0 },
    lastResult: null,
    recentReel: [],
    galleryFilter: "ALL",
    theme: "light"
};

// --- DOM References ---
const el = {
    // Header
    camStatusPill: document.getElementById("camStatusPill"),
    camStatusDot: document.getElementById("camStatusDot"),
    camStatusText: document.getElementById("camStatusText"),
    headerFps: document.getElementById("headerFps"),
    headerClock: document.getElementById("headerClock"),
    btnThemeToggle: document.getElementById("btnThemeToggle"),
    btnFullscreen: document.getElementById("btnFullscreenToggle"),

    // Nav Tabs
    navTabs: document.querySelectorAll(".nav-tab-item"),
    viewPanes: document.querySelectorAll(".hmi-view-pane"),

    // Monitor View
    btnFocusMode: document.getElementById("btnFocusMode"),
    btnFocusModeText: document.getElementById("btnFocusModeText"),
    viewModeBadge: document.getElementById("viewModeBadge"),
    btnGridToggle: document.getElementById("btnGridToggle"),
    gridOverlay: document.getElementById("gridOverlay"),
    streamImg: document.getElementById("streamImg"),

    // Result Banner
    resultBanner: document.getElementById("resultBanner"),
    bannerStatusBadge: document.getElementById("bannerStatusBadge"),
    bannerMsg: document.getElementById("bannerMsg"),
    bannerDetectedCode: document.getElementById("bannerDetectedCode"),
    bannerTargetCode: document.getElementById("bannerTargetCode"),
    bannerConfidence: document.getElementById("bannerConfidence"),
    bannerLatency: document.getElementById("bannerLatency"),

    // Trigger & Controls
    btnTriggerShot: document.getElementById("btnTriggerShot"),
    switchAutoInspect: document.getElementById("switchAutoInspect"),
    monitorTargetDisplay: document.getElementById("monitorTargetDisplay"),

    // KPIs
    kpiTotal: document.getElementById("kpiTotal"),
    kpiOk: document.getElementById("kpiOk"),
    kpiNg: document.getElementById("kpiNg"),
    kpiRate: document.getElementById("kpiRate"),
    rateBarFill: document.getElementById("rateBarFill"),
    btnResetStats: document.getElementById("btnResetStats"),

    // Reel
    recentReelStrip: document.getElementById("recentReelStrip"),
    reelCountText: document.getElementById("reelCountText"),

    // Settings View
    inputTargetCode: document.getElementById("inputTargetCode"),
    btnSaveTarget: document.getElementById("btnSaveTarget"),
    switchAutoExp: document.getElementById("switchAutoExp"),
    sliderExposure: document.getElementById("sliderExposure"),
    valExposure: document.getElementById("valExposure"),
    sliderGain: document.getElementById("sliderGain"),
    valGain: document.getElementById("valGain"),
    sliderYMin: document.getElementById("sliderYMin"),
    sliderYMax: document.getElementById("sliderYMax"),
    sliderXMin: document.getElementById("sliderXMin"),
    sliderXMax: document.getElementById("sliderXMax"),
    valYMin: document.getElementById("valYMin"),
    valYMax: document.getElementById("valYMax"),
    valXMin: document.getElementById("valXMin"),
    valXMax: document.getElementById("valXMax"),
    btnRoiDefault: document.getElementById("btnRoiPresetDefault"),
    btnRoiCenter: document.getElementById("btnRoiPresetCenter"),
    btnRoiFull: document.getElementById("btnRoiPresetFull"),

    // Gallery View
    galleryGrid: document.getElementById("galleryGrid"),
    btnRefreshGallery: document.getElementById("btnRefreshGallery"),

    // Logs View
    terminalLogBody: document.getElementById("terminalLogBody"),
    btnClearLogs: document.getElementById("btnClearLogs"),

    // Modal
    imageModal: document.getElementById("imageModal"),
    modalImgTitle: document.getElementById("modalImgTitle"),
    modalImgBadge: document.getElementById("modalImgBadge"),
    modalImgTag: document.getElementById("modalImgTag"),
    modalDetails: document.getElementById("modalDetails"),
    btnModalClose: document.getElementById("btnModalClose"),
    btnDownloadImg: document.getElementById("btnDownloadImg")
};

// ==========================================================
// INITIALIZATION
// ==========================================================
document.addEventListener("DOMContentLoaded", () => {
    initTheme();
    initClock();
    fetchSystemStatus();
    initWebSocket();
    bindEvents();
    loadGalleryArchive();
});

function initTheme() {
    const savedTheme = localStorage.getItem("hmi_theme") || "light";
    setTheme(savedTheme);
}

function setTheme(theme) {
    state.theme = theme;
    localStorage.setItem("hmi_theme", theme);
    if (theme === "dark") {
        document.body.classList.remove("theme-light");
        document.body.classList.add("theme-dark");
    } else {
        document.body.classList.remove("theme-dark");
        document.body.classList.add("theme-light");
    }
}

function initClock() {
    setInterval(() => {
        const now = new Date();
        el.headerClock.textContent = now.toTimeString().split(" ")[0];
    }, 1000);
}

// ==========================================================
// WEBSOCKET TELEMETRY
// ==========================================================
function initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
        state.ws = new WebSocket(wsUrl);

        state.ws.onopen = () => {
            state.connected = true;
            appendLog({ time: getTimestamp(), text: "Kết nối WebSocket thành công (Realtime OK)", level: "success" });
        };

        state.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                applyTelemetry(data);
            } catch (err) {
                console.error("Lỗi parse WS:", err);
            }
        };

        state.ws.onclose = () => {
            state.connected = false;
            setTimeout(initWebSocket, 3000);
        };

        state.ws.onerror = () => {
            state.ws.close();
        };
    } catch (e) {
        console.warn("WebSocket fallback:", e);
        setInterval(fetchSystemStatus, 2000);
    }
}

function applyTelemetry(data) {
    updateCameraStatus(data.camera_connected, data.fps);

    if (data.stats) updateStatsUI(data.stats);

    if (data.focus_mode !== undefined && data.focus_mode !== state.focusMode) {
        state.focusMode = data.focus_mode;
        updateFocusModeUI(state.focusMode);
    }

    if (data.auto_inspect !== undefined && data.auto_inspect !== state.autoInspect) {
        state.autoInspect = data.auto_inspect;
        el.switchAutoInspect.checked = state.autoInspect;
    }

    if (data.last_result && JSON.stringify(data.last_result) !== JSON.stringify(state.lastResult)) {
        renderInspectionResult(data.last_result);
    }

    if (data.logs && Array.isArray(data.logs)) {
        renderTerminalLogs(data.logs);
    }
}

async function fetchSystemStatus() {
    try {
        const res = await fetch("/api/status");
        if (res.ok) {
            const data = await res.json();
            updateCameraStatus(data.camera_connected, data.fps);
            updateStatsUI(data.stats);

            state.targetCode = data.target_code;
            el.inputTargetCode.value = data.target_code;
            el.bannerTargetCode.textContent = data.target_code;
            el.monitorTargetDisplay.textContent = data.target_code;

            state.focusMode = data.focus_mode;
            updateFocusModeUI(state.focusMode);

            state.autoInspect = data.auto_inspect;
            el.switchAutoInspect.checked = state.autoInspect;

            state.autoExposure = data.auto_exposure;
            el.switchAutoExp.checked = state.autoExposure;

            state.exposureTime = data.exposure_time;
            el.sliderExposure.value = data.exposure_time;
            el.valExposure.textContent = `${Math.round(data.exposure_time)} µs`;

            state.gain = data.gain;
            el.sliderGain.value = data.gain;
            el.valGain.textContent = `${Math.round(data.gain)} dB`;

            if (data.roi) {
                state.roi = data.roi;
                el.sliderYMin.value = Math.round(data.roi.ymin * 100);
                el.sliderYMax.value = Math.round(data.roi.ymax * 100);
                el.sliderXMin.value = Math.round(data.roi.xmin * 100);
                el.sliderXMax.value = Math.round(data.roi.xmax * 100);
                updateRoiLabels();
            }

            if (data.last_result) renderInspectionResult(data.last_result);
            if (data.logs) renderTerminalLogs(data.logs);
        }
    } catch (e) {
        console.error("Lỗi fetch status:", e);
    }
}

// ==========================================================
// UI UPDATES
// ==========================================================
function updateCameraStatus(isOnline, fps) {
    state.cameraConnected = isOnline;
    if (isOnline) {
        el.camStatusDot.className = "status-dot online pulse";
        el.camStatusText.textContent = "CAM: ONLINE (acA3800-10gm)";
    } else {
        el.camStatusDot.className = "status-dot offline pulse";
        el.camStatusText.textContent = "CAM: ĐANG TÌM THIẾT BỊ...";
    }
    el.headerFps.textContent = (fps || 0.0).toFixed(1);
}

function updateStatsUI(stats) {
    state.stats = stats;
    el.kpiTotal.textContent = stats.total || 0;
    el.kpiOk.textContent = stats.ok || 0;
    el.kpiNg.textContent = stats.ng || 0;

    const rate = (stats.ng_rate || 0.0).toFixed(1);
    el.kpiRate.textContent = `${rate}%`;
    el.rateBarFill.style.width = `${Math.min(100, stats.ng_rate || 0)}%`;
}

function updateFocusModeUI(isFocus) {
    if (isFocus) {
        el.btnFocusMode.classList.add("active");
        el.btnFocusModeText.textContent = "TẮT NÉT 1:1";
        el.viewModeBadge.textContent = "SOI NÉT 1:1 ROI (VẶN LENS)";
        el.viewModeBadge.style.color = "var(--color-pass)";
    } else {
        el.btnFocusMode.classList.remove("active");
        el.btnFocusModeText.textContent = "SOI NÉT 1:1";
        el.viewModeBadge.textContent = "TOÀN CẢNH CẢM BIẾN";
        el.viewModeBadge.style.color = "var(--text-muted)";
    }
}

function renderInspectionResult(res) {
    if (!res) return;
    state.lastResult = res;

    if (res.is_pass) {
        el.resultBanner.className = "result-banner-strip banner-pass";
        el.bannerStatusBadge.textContent = "PASS (OK)";
        el.bannerMsg.textContent = `HỢP CHUẨN — MÃ: [ ${res.detected_text} ]`;
    } else {
        el.resultBanner.className = "result-banner-strip banner-fail";
        el.bannerStatusBadge.textContent = "FAIL (NG)";
        el.bannerMsg.textContent = `LỖI MÃ HOẶC MỜ — ĐỌC ĐƯỢC: [ ${res.detected_text || "TRỐNG"} ]`;
    }

    el.bannerDetectedCode.textContent = res.detected_text || "(Trống)";
    el.bannerTargetCode.textContent = res.target_text || state.targetCode;
    el.bannerConfidence.textContent = `${res.confidence || 0}%`;
    el.bannerLatency.textContent = `${res.latency_ms || 0} ms`;

    addToRecentReel(res);
}

function addToRecentReel(res) {
    state.recentReel.unshift(res);
    if (state.recentReel.length > 8) state.recentReel.pop();
    el.reelCountText.textContent = `${state.recentReel.length} ảnh`;

    el.recentReelStrip.innerHTML = "";
    state.recentReel.forEach(item => {
        const div = document.createElement("div");
        div.className = "reel-item";
        div.innerHTML = `
            <img src="${item.thumb_url || item.image_url}" alt="${item.detected_text}" loading="lazy" />
            <span class="reel-stamp ${item.is_pass ? 'ok' : 'ng'}">${item.is_pass ? 'OK' : 'NG'}</span>
        `;
        div.addEventListener("click", () => openImageModal(item));
        el.recentReelStrip.appendChild(div);
    });
}

function renderTerminalLogs(logs) {
    if (!logs || !Array.isArray(logs)) return;
    el.terminalLogBody.innerHTML = "";
    logs.forEach(log => appendLog(log, false));
    el.terminalLogBody.scrollTop = el.terminalLogBody.scrollHeight;
}

function appendLog(log, shouldScroll = true) {
    const row = document.createElement("div");
    row.className = "log-line";
    row.innerHTML = `
        <span class="log-time">[${log.time || getTimestamp()}]</span>
        <span class="log-text ${log.level || 'info'}">${escapeHtml(log.text)}</span>
    `;
    el.terminalLogBody.appendChild(row);
    if (shouldScroll) el.terminalLogBody.scrollTop = el.terminalLogBody.scrollHeight;
}

// ==========================================================
// EVENT BINDINGS
// ==========================================================
function bindEvents() {
    // 1. Chuyển đổi Tab Ngang
    el.navTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            const targetId = tab.dataset.target;
            el.navTabs.forEach(t => t.classList.remove("active"));
            el.viewPanes.forEach(p => p.classList.remove("active"));

            tab.classList.add("active");
            const targetPane = document.getElementById(targetId);
            if (targetPane) targetPane.classList.add("active");

            if (targetId === "viewGallery") loadGalleryArchive();
        });
    });

    // 2. Chuyển đổi Theme Sáng / Tối
    el.btnThemeToggle.addEventListener("click", () => {
        const nextTheme = state.theme === "light" ? "dark" : "light";
        setTheme(nextTheme);
    });

    // 3. Nút kích chụp
    el.btnTriggerShot.addEventListener("click", triggerSingleInspection);

    // Phím tắt: SPACE hoặc ENTER để kích chụp
    window.addEventListener("keydown", (e) => {
        const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : "";
        if (activeTag === "input" || activeTag === "textarea") return;

        if (e.code === "Space" || e.key === "Enter") {
            e.preventDefault();
            triggerSingleInspection();
        } else if (e.key.toLowerCase() === "f") {
            toggleFocusMode();
        }
    });

    // 4. Auto Inspect
    el.switchAutoInspect.addEventListener("change", async () => {
        try {
            const res = await fetch("/api/auto_inspect/toggle", { method: "POST" });
            const data = await res.json();
            state.autoInspect = data.auto_inspect;
            el.switchAutoInspect.checked = state.autoInspect;
        } catch (e) {
            console.error("Lỗi toggle auto:", e);
        }
    });

    // 5. Soi Nét 1:1
    el.btnFocusMode.addEventListener("click", toggleFocusMode);

    // 6. Lưới ngắm
    el.btnGridToggle.addEventListener("click", () => {
        el.gridOverlay.classList.toggle("visible");
        el.btnGridToggle.classList.toggle("active");
    });

    // 7. Toàn màn hình
    el.btnFullscreen.addEventListener("click", () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen().catch(() => {});
        } else {
            document.exitFullscreen().catch(() => {});
        }
    });

    // 8. Reset Thống kê
    el.btnResetStats.addEventListener("click", async () => {
        if (confirm("Đặt lại toàn bộ bộ đếm ca này về 0?")) {
            try {
                const res = await fetch("/api/stats/reset", { method: "POST" });
                const data = await res.json();
                if (data.success) {
                    updateStatsUI(data.stats);
                    el.resultBanner.className = "result-banner-strip banner-standby";
                    el.bannerStatusBadge.textContent = "RESET";
                    el.bannerMsg.textContent = "ĐÃ ĐẶT LẠI TOÀN BỘ BỘ ĐẾM SẢN LƯỢNG";
                }
            } catch (e) {
                console.error("Lỗi reset stats:", e);
            }
        }
    });

    // 9. Cài đặt Mã Tiêu Chuẩn
    el.btnSaveTarget.addEventListener("click", updateTargetCode);
    el.inputTargetCode.addEventListener("keydown", (e) => {
        if (e.key === "Enter") updateTargetCode();
    });

    document.querySelectorAll(".chips-row .chip-item").forEach(chip => {
        if (chip.dataset.code) {
            chip.addEventListener("click", () => {
                el.inputTargetCode.value = chip.dataset.code;
                updateTargetCode();
            });
        }
    });

    // 10. Điều khiển Camera (Auto Exposure & Sliders)
    el.switchAutoExp.addEventListener("change", () => {
        state.autoExposure = el.switchAutoExp.checked;
        sendCameraSettings();
    });

    el.sliderExposure.addEventListener("input", () => {
        state.exposureTime = parseFloat(el.sliderExposure.value);
        el.valExposure.textContent = `${Math.round(state.exposureTime)} µs`;
        if (state.autoExposure) {
            state.autoExposure = false;
            el.switchAutoExp.checked = false;
        }
        debounceSendCameraSettings();
    });

    document.querySelectorAll(".quick-exp-chips .chip-mini").forEach(btn => {
        btn.addEventListener("click", () => {
            const exp = parseFloat(btn.dataset.exp);
            state.exposureTime = exp;
            el.sliderExposure.value = exp;
            el.valExposure.textContent = `${Math.round(exp)} µs`;
            if (state.autoExposure) {
                state.autoExposure = false;
                el.switchAutoExp.checked = false;
            }
            sendCameraSettings();
        });
    });

    el.sliderGain.addEventListener("input", () => {
        state.gain = parseFloat(el.sliderGain.value);
        el.valGain.textContent = `${Math.round(state.gain)} dB`;
        debounceSendCameraSettings();
    });

    // 11. ROI Sliders
    [el.sliderYMin, el.sliderYMax, el.sliderXMin, el.sliderXMax].forEach(s => {
        s.addEventListener("input", () => {
            updateRoiLabels();
            debounceSendRoiSettings();
        });
    });

    el.btnRoiDefault.addEventListener("click", () => setRoiPreset(0.25, 0.25, 0.75, 0.75));
    el.btnRoiCenter.addEventListener("click", () => setRoiPreset(0.35, 0.35, 0.65, 0.65));
    el.btnRoiFull.addEventListener("click", () => setRoiPreset(0.05, 0.05, 0.95, 0.95));

    // 12. Gallery Filter & Refresh
    document.querySelectorAll(".filter-group .filter-chip").forEach(btn => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".filter-group .filter-chip").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            state.galleryFilter = btn.dataset.filter;
            filterGallery();
        });
    });

    el.btnRefreshGallery.addEventListener("click", loadGalleryArchive);

    // 13. Clear Logs
    el.btnClearLogs.addEventListener("click", () => {
        el.terminalLogBody.innerHTML = "";
    });

    // 14. Modal Close
    el.btnModalClose.addEventListener("click", () => el.imageModal.classList.remove("open"));
    el.imageModal.addEventListener("click", (e) => {
        if (e.target === el.imageModal) el.imageModal.classList.remove("open");
    });
}

// ==========================================================
// ACTIONS & API
// ==========================================================
async function triggerSingleInspection() {
    el.btnTriggerShot.disabled = true;
    el.btnTriggerShot.style.opacity = "0.7";

    try {
        const res = await fetch("/api/trigger", { method: "POST" });
        const json = await res.json();
        if (json.success && json.data) {
            renderInspectionResult(json.data);
            updateStatsUI(json.data.stats);
        }
    } catch (e) {
        appendLog({ time: getTimestamp(), text: `Lỗi kích chụp: ${e.message}`, level: "error" });
    } finally {
        setTimeout(() => {
            el.btnTriggerShot.disabled = false;
            el.btnTriggerShot.style.opacity = "1";
        }, 150);
    }
}

async function toggleFocusMode() {
    try {
        const res = await fetch("/api/focus_mode/toggle", { method: "POST" });
        const data = await res.json();
        state.focusMode = data.focus_mode;
        updateFocusModeUI(state.focusMode);
    } catch (e) {
        console.error("Lỗi focus mode:", e);
    }
}

async function updateTargetCode() {
    const val = el.inputTargetCode.value.trim().toUpperCase();
    if (!val) return;

    try {
        const res = await fetch("/api/settings/target", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_code: val })
        });
        const data = await res.json();
        if (data.success) {
            state.targetCode = data.target_code;
            el.bannerTargetCode.textContent = data.target_code;
            el.monitorTargetDisplay.textContent = data.target_code;
            appendLog({ time: getTimestamp(), text: `Mã tiêu chuẩn đã lưu: '${data.target_code}'`, level: "success" });
        }
    } catch (e) {
        console.error("Lỗi lưu mã:", e);
    }
}

let camDebounceTimer = null;
function debounceSendCameraSettings() {
    clearTimeout(camDebounceTimer);
    camDebounceTimer = setTimeout(sendCameraSettings, 200);
}

async function sendCameraSettings() {
    try {
        await fetch("/api/settings/camera", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                exposure_time: state.exposureTime,
                auto_exposure: state.autoExposure,
                gain: state.gain
            })
        });
    } catch (e) {
        console.error("Lỗi camera settings:", e);
    }
}

function updateRoiLabels() {
    el.valYMin.textContent = `${el.sliderYMin.value}%`;
    el.valYMax.textContent = `${el.sliderYMax.value}%`;
    el.valXMin.textContent = `${el.sliderXMin.value}%`;
    el.valXMax.textContent = `${el.sliderXMax.value}%`;
}

function setRoiPreset(ymin, xmin, ymax, xmax) {
    el.sliderYMin.value = Math.round(ymin * 100);
    el.sliderXMin.value = Math.round(xmin * 100);
    el.sliderYMax.value = Math.round(ymax * 100);
    el.sliderXMax.value = Math.round(xmax * 100);
    updateRoiLabels();
    sendRoiSettings();
}

let roiDebounceTimer = null;
function debounceSendRoiSettings() {
    clearTimeout(roiDebounceTimer);
    roiDebounceTimer = setTimeout(sendRoiSettings, 200);
}

async function sendRoiSettings() {
    const ymin = parseFloat(el.sliderYMin.value) / 100.0;
    const ymax = parseFloat(el.sliderYMax.value) / 100.0;
    const xmin = parseFloat(el.sliderXMin.value) / 100.0;
    const xmax = parseFloat(el.sliderXMax.value) / 100.0;

    try {
        const res = await fetch("/api/settings/roi", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ymin, xmin, ymax, xmax })
        });
        const data = await res.json();
        if (data.success) state.roi = data.roi;
    } catch (e) {
        console.error("Lỗi gửi ROI:", e);
    }
}

// ==========================================================
// GALLERY & MODAL
// ==========================================================
let allGalleryItems = [];

async function loadGalleryArchive() {
    try {
        const res = await fetch("/api/history?limit=50");
        const json = await res.json();
        if (json.success && Array.isArray(json.history)) {
            allGalleryItems = json.history;
            filterGallery();
        }
    } catch (e) {
        console.error("Lỗi tải archive:", e);
    }
}

function filterGallery() {
    const filter = state.galleryFilter;
    const items = allGalleryItems.filter(item => {
        if (filter === "ALL") return true;
        return item.category === filter;
    });

    el.galleryGrid.innerHTML = "";
    if (items.length === 0) {
        el.galleryGrid.innerHTML = `<div style="grid-column: 1/-1; padding: 24px; color: var(--text-muted); font-style: italic;">Không tìm thấy ảnh nào.</div>`;
        return;
    }

    items.forEach(item => {
        const card = document.createElement("div");
        card.className = "gallery-card";
        card.innerHTML = `
            <div class="gallery-thumb-wrap">
                <img src="${item.thumb_url || item.image_url}" alt="${item.filename}" loading="lazy" />
            </div>
            <div class="gallery-info">
                <div class="gallery-top-row">
                    <span class="gallery-badge ${item.is_pass ? 'ok' : 'ng'}">${item.category}</span>
                    <span class="gallery-code">${item.detected || '--'}</span>
                </div>
                <span class="gallery-time">${item.time}</span>
            </div>
        `;
        card.addEventListener("click", () => openImageModal(item));
        el.galleryGrid.appendChild(card);
    });
}

function openImageModal(item) {
    el.modalImgTitle.textContent = item.filename || "Chi Tiết Kiểm Tra";
    el.modalImgBadge.textContent = item.category || (item.is_pass ? "OK" : "NG");
    el.modalImgBadge.className = `modal-badge ${item.is_pass ? 'ok' : 'ng'}`;
    el.modalImgTag.src = item.image_url;
    el.btnDownloadImg.href = item.image_url;

    el.modalDetails.innerHTML = `
        <div>Thời gian: <strong>${item.time || item.timestamp || '--'}</strong></div>
        <div>Mã nhận dạng: <strong>${item.detected || item.detected_text || '--'}</strong></div>
        ${item.confidence ? `<div>Độ tin cậy: <strong>${item.confidence}%</strong></div>` : ''}
    `;

    el.imageModal.classList.add("open");
}

function getTimestamp() {
    return new Date().toTimeString().split(" ")[0];
}

function escapeHtml(str) {
    if (!str) return "";
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
