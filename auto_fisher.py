import sys, time, random, subprocess, cv2, numpy as np, mss, pydirectinput, keyboard, requests
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLineEdit, QFormLayout, QInputDialog)
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

class Worker(QObject):
    update_preview = pyqtSignal(np.ndarray, bool)
    update_ui_keys = pyqtSignal(list)
    press_index = pyqtSignal(int)
    update_status = pyqtSignal(str)

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.running = False
        self.threshold = 0.62
        self.is_morning_mode = True # เริ่มต้นโหมดเช้า (ขาวดำ)
        self.templates_binary = {}
        self.templates_gray = {}
        self.load_templates()
        self.state = 0 
        self.wait_duration = 11.0
        self.last_time = time.time()

    def load_templates(self):
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png", cv2.IMREAD_GRAYSCALE)
            if img is not None:
                self.templates_gray[k] = img
                _, binary = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                self.templates_binary[k] = binary

    def run(self):
        self.running = True
        with mss.mss() as sct:
            while self.running:
                try:
                    # สลับโหมดด้วยปุ่ม L
                    if keyboard.is_pressed('l'):
                        self.is_morning_mode = not self.is_morning_mode
                        mode_name = "MORNING (B&W)" if self.is_morning_mode else "NIGHT (COLOR)"
                        self.update_status.emit(f"MODE: {mode_name}")
                        time.sleep(0.3)

                    sct_img = sct.grab(self.monitor)
                    frame = np.array(sct_img)
                    bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
                    
                    if self.is_morning_mode:
                        _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                        current_templates = self.templates_binary
                        preview_img = processed
                        is_color_preview = False
                    else:
                        processed = gray
                        current_templates = self.templates_gray
                        preview_img = bgr
                        is_color_preview = True

                    now = time.time()
                    # Logic การตกปลา (State Machine)
                    if self.state == 0:
                        if keyboard.is_pressed('e'): self.state, self.last_time = 1, now
                    elif self.state == 1:
                        if now - self.last_time >= self.wait_duration: self.state = 2
                    elif self.state == 2:
                        all_matches = []
                        for k, temp in current_templates.items():
                            res = cv2.matchTemplate(processed, temp, cv2.TM_CCOEFF_NORMED)
                            loc = np.where(res >= self.threshold)
                            for pt in zip(*loc[::-1]):
                                all_matches.append({'x': pt[0], 'key': k, 'score': res[pt[1], pt[0]]})
                        
                        if all_matches:
                            all_matches.sort(key=lambda x: x['score'], reverse=True)
                            filtered = []
                            for m in all_matches:
                                if not any(abs(m['x'] - f['x']) < 25 for f in filtered):
                                    filtered.append(m)
                            filtered.sort(key=lambda x: x['x'])
                            
                            if filtered:
                                self.update_ui_keys.emit([m['key'] for m in filtered])
                                time.sleep(0.1)
                                for i, m in enumerate(filtered):
                                    self.press_index.emit(i)
                                    pydirectinput.press(m['key'].lower())
                                    time.sleep(random.uniform(0.08, 0.12))
                                self.state, self.last_time = 3, now
                        elif now - self.last_time > self.wait_duration + 5: self.state = 3
                    elif self.state == 3:
                        if now - self.last_time >= 1.5:
                            pydirectinput.press('e')
                            self.state, self.last_time = 1, time.time()
                            self.update_ui_keys.emit([])

                    self.update_preview.emit(preview_img, is_color_preview)
                except: pass
                time.sleep(0.01)

    def update_monitor(self, m): self.monitor = m

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto 0.2")
        self.setFixedWidth(380)
        self.setStyleSheet("background-color: #0d0d0d; color: white;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.main_layout = QVBoxLayout(self)
        
        self.status_label = QLabel("Waiting for Auth...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 16px; color: #00ffff; padding: 5px;")
        self.main_layout.addWidget(self.status_label)
        
        self.key_row = QHBoxLayout()
        self.boxes = [KeyBox() for _ in range(5)]
        for box in self.boxes: self.key_row.addWidget(box)
        self.main_layout.addLayout(self.key_row)
        
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(350, 95)
        self.preview_label.setStyleSheet("border: 2px solid #333;")
        self.main_layout.addWidget(self.preview_label)
        
        self.admin_btn = QPushButton("ADMIN TUNING")
        self.admin_btn.hide()
        self.admin_btn.clicked.connect(lambda: self.tune_win.show())
        self.main_layout.addWidget(self.admin_btn)

        self.monitor = {"top": 820, "left": 808, "width": 270, "height": 85}
        self.tune_win = TuningWindow(self.monitor)
        self.tune_win.settings_changed.connect(self.update_config)
        
        # รันระบบ Login
        self.authenticate()

    def authenticate(self):
        hwid = get_hwid()
        key, ok = QInputDialog.getText(self, "License", f"HWID: {hwid}\nEnter Key:")
        if ok and key.strip() == "Keerati":
            self.admin_btn.show()
            self.start_bot()
            self.status_label.setText("MODE: MORNING (Press L)")
        elif ok:
            try:
                res = requests.post(SERVER_URL, json={"key": key.strip().upper(), "hwid": hwid}, timeout=5).json()
                if res.get("status") == "ok": 
                    self.start_bot()
                    self.status_label.setText("MODE: MORNING (Press L)")
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

    def update_image(self, cv_img, is_color):
        try:
            if is_color:
                h, w, ch = cv_img.shape
                q_img = QImage(cv_img.tobytes(), w, h, ch*w, QImage.Format.Format_RGB888).rgbSwapped()
            else:
                h, w = cv_img.shape
                q_img = QImage(cv_img.tobytes(), w, h, w, QImage.Format.Format_Grayscale8)
            self.preview_label.setPixmap(QPixmap.fromImage(q_img).scaled(350, 95))
        except: pass

    def update_keys_ui(self, key_list):
        for box in self.boxes: box.clear()
        for i, key in enumerate(key_list):
            if i < 5: self.boxes[i].glow(key)
    def animate_press(self, index):
        if index < 5: self.boxes[index].press_effect()

class TuningWindow(QWidget):
    settings_changed = pyqtSignal(dict)
    def __init__(self, current_monitor):
        super().__init__()
        self.setWindowTitle("Admin Tuning")
        layout = QFormLayout(self)
        self.top_in = QLineEdit(str(current_monitor['top']))
        self.left_in = QLineEdit(str(current_monitor['left']))
        layout.addRow("Top:", self.top_in)
        layout.addRow("Left:", self.left_in)
        self.apply_btn = QPushButton("APPLY")
        self.apply_btn.clicked.connect(lambda: self.settings_changed.emit({"top": int(self.top_in.text()), "left": int(self.left_in.text()), "width": 270, "height": 85}))
        layout.addRow(self.apply_btn)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())
