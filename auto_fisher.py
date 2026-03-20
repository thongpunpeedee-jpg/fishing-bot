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
    update_preview = pyqtSignal(np.ndarray)
    update_ui_keys = pyqtSignal(list)
    press_index = pyqtSignal(int)
    update_status = pyqtSignal(str)

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.running = False
        self.threshold = 0.55 
        self.templates = {}
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None: self.templates[k] = img
        self.state = 0 
        self.wait_duration = 11.0

    def update_monitor(self, new_monitor):
        self.monitor = new_monitor

    def run(self):
        self.running = True
        with mss.mss() as sct:
            while self.running:
                try:
                    sct_img = sct.grab(self.monitor)
                    frame = np.array(sct_img)
                    bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
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
                        for k, temp in self.templates.items():
                            res = cv2.matchTemplate(bgr, temp, cv2.TM_CCOEFF_NORMED)
                            loc = np.where(res >= self.threshold)
                            for pt in zip(*loc[::-1]):
                                matches.append({'x': pt[0], 'key': k, 'score': res[pt[1], pt[0]]})
                        if matches:
                            final = []
                            matches.sort(key=lambda x: x['score'], reverse=True)
                            for m in matches:
                                if not any(abs(m['x'] - f['x']) < 20 for f in final): 
                                    final.append(m)
                            final.sort(key=lambda x: x['x'])
                            self.update_ui_keys.emit([m['key'] for m in final])
                            time.sleep(0.1)
                            for i, m in enumerate(final):
                                self.press_index.emit(i)
                                pydirectinput.press(m['key'].lower())
                                time.sleep(random.uniform(0.06, 0.11))
                            self.state, self.last_time = 3, now
                    elif self.state == 3:
                        if now - self.last_time >= 1.5:
                            pydirectinput.press('e')
                            self.state, self.last_time = 1, time.time()

                    self.update_preview.emit(bgr)
                except: pass
                time.sleep(0.01)

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Fisher Pro")
        self.setFixedWidth(380)
        self.setStyleSheet("background-color: #0d0d0d; color: white;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        
        main_layout = QVBoxLayout(self)

        # --- Status & Keys Section ---
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ffff; padding: 5px;")
        main_layout.addWidget(self.status_label)

        self.key_row = QHBoxLayout()
        self.boxes = [KeyBox() for _ in range(5)]
        for box in self.boxes: self.key_row.addWidget(box)
        main_layout.addLayout(self.key_row)

        self.preview_label = QLabel()
        self.preview_label.setFixedSize(350, 90) 
        self.preview_label.setStyleSheet("border: 2px solid #333; background: #000; border-radius: 8px;")
        main_layout.addWidget(self.preview_label)

        # --- TUNING SECTION (Integrated from your image) ---
        tune_container = QWidget()
        tune_layout = QFormLayout(tune_container)
        tune_layout.setContentsMargins(20, 10, 20, 10)
        tune_layout.setSpacing(10)

        # สไตล์สำหรับ Input ตามรูป
        input_style = """
            QLineEdit {
                background-color: #1a1a1a; 
                border: 1px solid #333; 
                color: #00ffff; 
                font-size: 16px; 
                font-weight: bold; 
                padding: 4px;
            }
        """
        label_style = "color: #00ffff; font-size: 16px; font-weight: bold;"

        self.top_in = QLineEdit("820")
        self.left_in = QLineEdit("790")
        self.width_in = QLineEdit("270")
        self.height_in = QLineEdit("75")

        for inp in [self.top_in, self.left_in, self.width_in, self.height_in]:
            inp.setStyleSheet(input_style)

        # สร้าง Label และตั้งสไตล์
        l1, l2, l3, l4 = QLabel("Top:"), QLabel("Left:"), QLabel("Width:"), QLabel("Height:")
        for lab in [l1, l2, l3, l4]: lab.setStyleSheet(label_style)

        tune_layout.addRow(l1, self.top_in)
        tune_layout.addRow(l2, self.left_in)
        tune_layout.addRow(l3, self.width_in)
        tune_layout.addRow(l4, self.height_in)

        self.apply_btn = QPushButton("APPLY SETTINGS")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #00ffff; 
                color: black; 
                font-weight: bold; 
                font-size: 14px; 
                padding: 10px; 
                border-radius: 5px;
                margin-top: 5px;
            }
            QPushButton:pressed { background-color: #00cccc; }
        """)
        self.apply_btn.clicked.connect(self.apply_settings)
        tune_layout.addRow(self.apply_btn)

        main_layout.addWidget(tune_container)

        # Initial Monitor
        self.monitor = {"top": 820, "left": 790, "width": 270, "height": 75}
        
        # Authentication & Start
        self.authenticate()

    def authenticate(self):
        hwid = get_hwid()
        key, ok = QInputDialog.getText(self, "License", f"HWID: {hwid}\nEnter Key:")
        if ok and key:
            try:
                res = requests.post(SERVER_URL, json={"key": key.strip().upper(), "hwid": hwid}, timeout=5).json()
                if res.get("status") == "ok":
                    self.start_bot()
                else:
                    QMessageBox.critical(self, "Error", "Invalid Key!")
                    sys.exit()
            except:
                # เพื่อการทดสอบ: หากไม่มี server ให้คอมเมนต์ 2 บรรทัดข้างล่าง แล้วเปิด self.start_bot() แทน
                QMessageBox.critical(self, "Error", "Connection Error!")
                sys.exit()
        else: sys.exit()

    def apply_settings(self):
        try:
            self.monitor = {
                "top": int(self.top_in.text()),
                "left": int(self.left_in.text()),
                "width": int(self.width_in.text()),
                "height": int(self.height_in.text())
            }
            if hasattr(self, 'worker'):
                self.worker.update_monitor(self.monitor)
            self.status_label.setText("SETTINGS APPLIED!")
            time.sleep(0.5)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "กรุณาใส่เฉพาะตัวเลขครับ")

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
            pixmap = QPixmap.fromImage(q_img)
            self.preview_label.setPixmap(pixmap.scaled(self.preview_label.width(), self.preview_label.height(), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except: pass

    def update_keys_ui(self, key_list):
        for box in self.boxes: box.clear()
        for i, key in enumerate(key_list):
            if i < len(self.boxes): self.boxes[i].glow(key)

    def animate_press(self, index):
        if index < len(self.boxes): self.boxes[index].press_effect()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec())
