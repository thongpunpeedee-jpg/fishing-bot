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

# --- หน้าต่าง Tuning แยก (สำหรับ Admin) ---
class TuningWindow(QWidget):
    settings_changed = pyqtSignal(dict)

    def __init__(self, current_monitor):
        super().__init__()
        self.setWindowTitle("Live Tuning - Admin Mode")
        self.setFixedWidth(280)
        self.setStyleSheet("background-color: #121212; color: #00ffff;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        
        layout = QFormLayout(self)
        input_style = "background: #1a1a1a; border: 1px solid #333; color: #00ffff; padding: 5px; font-weight: bold;"
        
        self.top_in = QLineEdit(str(current_monitor['top']))
        self.left_in = QLineEdit(str(current_monitor['left']))
        self.width_in = QLineEdit(str(current_monitor['width']))
        self.height_in = QLineEdit(str(current_monitor['height']))

        for inp in [self.top_in, self.left_in, self.width_in, self.height_in]:
            inp.setStyleSheet(input_style)

        layout.addRow("Top:", self.top_in)
        layout.addRow("Left:", self.left_in)
        layout.addRow("Width:", self.width_in)
        layout.addRow("Height:", self.height_in)

        self.apply_btn = QPushButton("APPLY SETTINGS")
        self.apply_btn.setStyleSheet("background-color: #00ffff; color: black; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.apply_btn.clicked.connect(self.save)
        layout.addRow(self.apply_btn)

    def save(self):
        try:
            new_val = {
                "top": int(self.top_in.text()),
                "left": int(self.left_in.text()),
                "width": int(self.width_in.text()),
                "height": int(self.height_in.text())
            }
            self.settings_changed.emit(new_val)
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
        self.threshold = 0.70 
        self.templates = {}
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None: self.templates[k] = img
        self.state = 0 
        self.wait_duration = 11.0

    def update_monitor(self, m):
        self.monitor = m

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
        self.setWindowTitle("Auto v3")
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
        self.preview_label.setStyleSheet("border: 2px solid #333; background: #000; border-radius: 8px; margin-top: 10px;")
        self.main_layout.addWidget(self.preview_label)

        # ปุ่ม Tuning (ซ่อนไว้ก่อน)
        self.admin_btn = QPushButton("OPEN LIVE TUNING (ADMIN)")
        self.admin_btn.setStyleSheet("background: #222; color: #555; border: 1px solid #333; padding: 5px; margin-top: 10px;")
        self.admin_btn.hide() 
        self.admin_btn.clicked.connect(self.show_tuning)
        self.main_layout.addWidget(self.admin_btn)

        self.monitor = {"top": 825, "left": 815, "width": 270, "height": 75}
        self.tune_win = TuningWindow(self.monitor)
        self.tune_win.settings_changed.connect(self.update_config)

        self.authenticate()

    def authenticate(self):
        hwid = get_hwid()
        key, ok = QInputDialog.getText(self, "License", f"HWID: {hwid}\nEnter Key:")
        if ok and key:
            raw_key = key.strip()
            
            # --- แอดมินเช็คพิเศษ ---
            if raw_key == "Keerati":
                self.admin_btn.show() # แสดงปุ่ม Tuning สำหรับแอดมินเท่านั้น
                self.start_bot()
                return

            # --- ระบบ Auth ปกติ ---
            try:
                res = requests.post(SERVER_URL, json={"key": raw_key.upper(), "hwid": hwid}, timeout=5).json()
                if res.get("status") == "ok":
                    self.start_bot()
                else:
                    QMessageBox.critical(self, "Error", "Invalid Key!")
                    sys.exit()
            except:
                QMessageBox.critical(self, "Error", "Connection Error!")
                sys.exit()
        else: sys.exit()

    def show_tuning(self):
        self.tune_win.show()

    def update_config(self, new_m):
        self.monitor = new_m
        if hasattr(self, 'worker'):
            self.worker.update_monitor(new_m)

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
