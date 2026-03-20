import sys, time, random, subprocess, cv2, numpy as np, mss, pydirectinput, keyboard, requests
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLineEdit, QDialog, QFormLayout, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap

# ตั้งค่า Server (ต้องรัน node server.js ไว้ด้วย)
SERVER_URL = SERVER_URL = "https://rounded-unsurrendered-cherri.ngrok-free.dev/auth"
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
        self.setFixedSize(60, 75)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #2b2b2b; color: white; font-size: 20px; border-radius: 8px; border: 3px solid #00ffff;")

    def glow(self, text):
        self.setText(text)
        self.setStyleSheet("background-color: #2b2b2b; color: #00ffff; font-size: 20px; border-radius: 8px; border: 3px solid #00ffff;")

    def press_effect(self):
        self.setStyleSheet("background-color: #444; color: white; font-size: 20px; border-radius: 8px; border: 3px solid #00ffff;")

    def clear(self):
        self.setText("")
        self.setStyleSheet("background-color: #2b2b2b; color: white; font-size: 20px; border-radius: 8px; border: 3px solid #00ffff;")

class Worker(QObject):
    update_preview = pyqtSignal(np.ndarray)
    update_ui_keys = pyqtSignal(list)
    press_index = pyqtSignal(int)
    update_status = pyqtSignal(str)

    def __init__(self, monitor):
        super().__init__()
        self.monitor = monitor
        self.running = False
        self.threshold = 0.65 # ค่าจาก message.txt
        self.templates = {}
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None: self.templates[k] = img
        self.state = 0 
        self.wait_duration = 10.0 # เวลารอตามที่ขอ

    def update_monitor(self, new_config):
        self.monitor = new_config

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
                                if not any(abs(m['x'] - f['x']) < 30 for f in final): final.append(m)
                            final.sort(key=lambda x: x['x'])
                            
                            self.update_ui_keys.emit([m['key'] for m in final])
                            time.sleep(0.1)
                            for i, m in enumerate(final):
                                self.press_index.emit(i)
                                pydirectinput.press(m['key'].lower())
                                time.sleep(random.uniform(0.06, 0.12)) # สุ่มเวลาจาก message.txt
                            self.state, self.last_time = 3, now

                    elif self.state == 3:
                        if now - self.last_time >= 1.5:
                            pydirectinput.press('e')
                            self.state, self.last_time = 1, time.time()

                    self.update_preview.emit(bgr)
                except: pass
                time.sleep(0.005)

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Auto Fisher Pro (UI Fix)")
        self.setFixedSize(380, 320)
        self.setStyleSheet("background-color: #111; color: white;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        
        layout = QVBoxLayout(self)
        self.status_label = QLabel("Initializing...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #00ffff; margin-bottom: 10px;")
        layout.addWidget(self.status_label)

        # Key Boxes (เหมือนในรูป)
        self.key_row = QHBoxLayout()
        self.boxes = [KeyBox() for _ in range(5)]
        for box in self.boxes: self.key_row.addWidget(box)
        layout.addLayout(self.key_row)

        # Preview (เหมือนในรูป)
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(350, 100)
        self.preview_label.setStyleSheet("border: 2px solid #333; background: #000; border-radius: 4px;")
        layout.addWidget(self.preview_label)

        self.monitor = {"top": 820, "left": 790, "width": 280, "height": 85}
        
        # ตรวจสอบสิทธิ์
        hwid = get_hwid()
        key, ok = QInputDialog.getText(self, "License", f"HWID: {hwid}\nEnter Key:")
        if ok:
            try:
                res = requests.post(SERVER_URL, json={"key": key.strip().upper(), "hwid": hwid}, timeout=5).json()
                if res.get("status") == "ok":
                    self.start_bot()
                else:
                    QMessageBox.critical(self, "Error", "Invalid Key or already used!")
                    sys.exit()
            except:
                QMessageBox.critical(self, "Error", "Cannot connect to Server!")
                sys.exit()
        else: sys.exit()

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
        h, w, ch = cv_img.shape
        q_img = QImage(cv_img.tobytes(), w, h, ch*w, QImage.Format.Format_RGB888).rgbSwapped()
        self.preview_label.setPixmap(QPixmap.fromImage(q_img).scaled(350, 100, Qt.AspectRatioMode.KeepAspectRatio))

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
