import sys, time, random, subprocess, cv2, numpy as np, mss, pydirectinput, keyboard, requests
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLineEdit, QDialog, QFormLayout, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap

# --- SERVER SETTINGS ---
SERVER_URL = "https://rounded-unsurrendered-cherri.ngrok-free.dev/auth"
pydirectinput.PAUSE = 0

def get_hwid():
    try:
        cmd = 'wmic csproduct get uuid'
        output = subprocess.check_output(cmd, shell=True).decode().split('\n')
        return "".join(output[1].strip().split()).upper()
    except: return "UNKNOWN"

# --- ฟังก์ชันแก้แสงฟุ้ง (Gamma Correction) ---
def enhance_image(img):
    # ปรับ Gamma เพื่อลดความสว่างที่จ้าเกินไปและเพิ่มรายละเอียดขอบ
    gamma = 0.6 
    invGamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
    img = cv2.LUT(img, table)
    # เพิ่มความคมชัดด้วย Sharpening filter
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    img = cv2.filter2D(img, -1, kernel)
    return img

class KeyBox(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(55, 70)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #1a1a1a; color: #666; font-size: 22px; font-weight: bold; border-radius: 6px; border: 2px solid #333;")

    def glow(self, text):
        self.setText(text)
        self.setStyleSheet("background-color: #2b2b2b; color: #00ffff; font-size: 22px; font-weight: bold; border-radius: 6px; border: 2px solid #00ffff;")

    def press_effect(self):
        self.setStyleSheet("background-color: #00ffff; color: #000; font-size: 22px; font-weight: bold; border-radius: 6px; border: 2px solid #fff;")

    def clear(self):
        self.setText("")
        self.setStyleSheet("background-color: #1a1a1a; color: #666; font-size: 22px; font-weight: bold; border-radius: 6px; border: 2px solid #333;")

class TuningWindow(QWidget):
    settings_changed = pyqtSignal(dict)
    def __init__(self, current_monitor):
        super().__init__()
        self.setWindowTitle("Live Tuning - Admin Mode")
        self.setFixedWidth(280)
        self.setStyleSheet("background-color: #121212; color: #00ffff;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        layout = QFormLayout(self)
        self.top_in = QLineEdit(str(current_monitor['top']))
        self.left_in = QLineEdit(str(current_monitor['left']))
        self.width_in = QLineEdit(str(current_monitor['width']))
        self.height_in = QLineEdit(str(current_monitor['height']))
        for inp in [self.top_in, self.left_in, self.width_in, self.height_in]:
            inp.setStyleSheet("background: #1a1a1a; border: 1px solid #333; color: #00ffff; padding: 5px;")
        layout.addRow("Top:", self.top_in)
        layout.addRow("Left:", self.left_in)
        layout.addRow("Width:", self.width_in)
        layout.addRow("Height:", self.height_in)
        self.apply_btn = QPushButton("APPLY SETTINGS")
        self.apply_btn.setStyleSheet("background-color: #00ffff; color: black; font-weight: bold; padding: 10px;")
        self.apply_btn.clicked.connect(self.save)
        layout.addRow(self.apply_btn)
    def save(self):
        try:
            self.settings_changed.emit({"top": int(self.top_in.text()), "left": int(self.left_in.text()), "width": int(self.width_in.text()), "height": int(self.height_in.text())})
        except: pass

class Worker(QObject):
    update_preview = pyqtSignal(np.ndarray)
    update_ui_keys = pyqtSignal(list)
    press_index = pyqtSignal(int)
    update_status = pyqtSignal(str)

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.running = False
        self.threshold = 0.55 # ลดลงมาหน่อยเพื่อรองรับ Multi-scale
        self.templates = {}
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None: self.templates[k] = img
        self.state = 0 
        self.wait_duration = 11.0

    def update_monitor(self, m): self.monitor = m

    def run(self):
        self.running = True
        with mss.mss() as sct:
            while self.running:
                try:
                    sct_img = sct.grab(self.monitor)
                    frame = np.array(sct_img)
                    bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # ประมวลผลภาพให้ชัดขึ้น
                    processed = enhance_image(bgr)
                    now = time.time()

                    if self.state == 0:
                        self.update_status.emit("READY (PRESS 'E')")
                        if keyboard.is_pressed('e'):
                            self.state, self.last_time = 1, now
                            time.sleep(0.2)

                    elif self.state == 1:
                        remaining = max(0, int(self.wait_duration - (now - self.last_time)))
                        self.update_status.emit(f"FISHING... ({remaining}s)")
                        if now - self.last_time >= self.wait_duration: self.state = 2

                    elif self.state == 2:
                        self.update_status.emit("SCANNING...")
                        matches = []
                        # วนลูปสแกนหาปุ่ม
                        for k, temp in self.templates.items():
                            # ลองสแกน 3 ขนาด (90%, 100%, 110%) เผื่อภาพในเกมขยับขนาด
                            for scale in [0.9, 1.0, 1.1]:
                                w_t = int(temp.shape[1] * scale)
                                h_t = int(temp.shape[0] * scale)
                                resized_temp = cv2.resize(temp, (w_t, h_t))
                                
                                res = cv2.matchTemplate(processed, resized_temp, cv2.TM_CCOEFF_NORMED)
                                loc = np.where(res >= self.threshold)
                                for pt in zip(*loc[::-1]):
                                    matches.append({'x': pt[0], 'key': k, 'score': res[pt[1], pt[0]]})
                        
                        if matches:
                            final = []
                            matches.sort(key=lambda x: x['score'], reverse=True)
                            for m in matches:
                                if not any(abs(m['x'] - f['x']) < 25 for f in final): 
                                    final.append(m)
                            final.sort(key=lambda x: x['x'])
                            
                            self.update_ui_keys.emit([m['key'] for m in final])
                            time.sleep(0.1)
                            for i, m in enumerate(final):
                                self.press_index.emit(i)
                                pydirectinput.press(m['key'].lower())
                                time.sleep(random.uniform(0.08, 0.12))
                            
                            time.sleep(0.5)
                            self.update_ui_keys.emit([])
                            self.state, self.last_time = 3, now
                        elif now - self.last_time > self.wait_duration + 5: self.state = 3

                    elif self.state == 3:
                        if now - self.last_time >= 1.5:
                            pydirectinput.press('e')
                            self.state, self.last_time = 1, time.time()

                    self.update_preview.emit(processed) # โชว์ภาพที่บอทมองเห็นจริง
                except: pass
                time.sleep(0.01)

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto 0.1 ")
        self.setFixedWidth(380)
        self.setStyleSheet("background-color: #0d0d0d; color: white;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.main_layout = QVBoxLayout(self)
        self.status_label = QLabel("Waiting for Auth...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ffff; padding: 10px;")
        self.main_layout.addWidget(self.status_label)
        self.key_row = QHBoxLayout()
        self.boxes = [KeyBox() for _ in range(5)]
        for box in self.boxes: self.key_row.addWidget(box)
        self.main_layout.addLayout(self.key_row)
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(350, 95)
        self.preview_label.setStyleSheet("border: 2px solid #333; background: #000;")
        self.main_layout.addWidget(self.preview_label)
        self.admin_btn = QPushButton("ADMIN TUNING")
        self.admin_btn.setStyleSheet("color: #00ffff; background: #222; padding: 5px;")
        self.admin_btn.hide()
        self.admin_btn.clicked.connect(lambda: self.tune_win.show())
        self.main_layout.addWidget(self.admin_btn)
        self.monitor = {"top": 825, "left": 808, "width": 270, "height": 75}
        self.tune_win = TuningWindow(self.monitor)
        self.tune_win.settings_changed.connect(self.update_config)
        self.authenticate()

    def authenticate(self):
        hwid = get_hwid()
        key, ok = QInputDialog.getText(self, "License", f"HWID: {hwid}\nEnter Key:")
        if ok and key:
            if key.strip() == "Keerati":
                self.admin_btn.show()
                self.start_bot()
            else:
                try:
                    res = requests.post(SERVER_URL, json={"key": key.strip().upper(), "hwid": hwid}, timeout=5).json()
                    if res.get("status") == "ok": self.start_bot()
                    else: sys.exit()
                except: sys.exit()
        else: sys.exit()

    def update_config(self, new_m):
        self.monitor = new_m
        if hasattr(self, 'worker'): self.worker.update_monitor(new_m)

    def start_bot(self):
        self.worker = Worker(self.monitor)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.worker.update_preview.connect(self.update_image)
        self.worker.update_status.connect(self.status_label.setText)
        self.worker.update_ui_keys.connect(self.update_keys_ui)
        self.worker.press_index.connect(self.animate_press)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def update_image(self, cv_img):
        try:
            h, w, ch = cv_img.shape
            q_img = QImage(cv_img.tobytes(), w, h, ch*w, QImage.Format.Format_RGB888).rgbSwapped()
            self.preview_label.setPixmap(QPixmap.fromImage(q_img).scaled(350, 95, Qt.AspectRatioMode.IgnoreAspectRatio))
        except: pass

    def update_keys_ui(self, key_list):
        for box in self.boxes: box.clear()
        for i, key in enumerate(key_list):
            if i < 5: self.boxes[i].glow(key)

    def animate_press(self, index):
        if index < 5: self.boxes[index].press_effect()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())
