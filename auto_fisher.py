import sys, time, random, subprocess
import cv2, numpy as np, mss, pydirectinput, keyboard, requests
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QInputDialog, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap

SERVER_URL = "http://127.0.0.1:5000/auth"

pydirectinput.PAUSE = 0
pydirectinput.FAILSAFE = False

# ---------------- HWID ----------------
def get_hwid():
    try:
        # ดึง UUID และจัดการให้เป็นมาตรฐาน (ไม่มีช่องว่าง, ตัวพิมพ์ใหญ่)
        cmd = 'wmic csproduct get uuid'
        output = subprocess.check_output(cmd, shell=True).decode().split('\n')
        raw_uuid = output[1].strip()
        return "".join(raw_uuid.split()).upper()
    except:
        return "UNKNOWN"

def check_key(key, hwid):
    try:
        # ล้างช่องว่างของ key ก่อนส่ง
        clean_key = "".join(key.split()).upper()
        res = requests.post(SERVER_URL, json={"key": clean_key, "hwid": hwid}, timeout=5)
        return res.json().get("status") == "ok"
    except Exception as e:
        print(f"Connection Error: {e}")
        return False

# ---------------- Worker ----------------
class Worker(QObject):
    update_preview = pyqtSignal(np.ndarray)
    update_ui_keys = pyqtSignal(list)
    press_index = pyqtSignal(int)

    def __init__(self, monitor, templates):
        super().__init__()
        self.monitor = monitor
        self.templates = templates
        self.running = False
        self.state = 0 # 0: Wait E, 1: Fishing, 2: Scanning, 3: Reset
        self.last_time = 0
        self.wait_duration = 10.0 # เวลารอปลากินเบ็ด

    def run(self):
        self.running = True
        with mss.mss() as sct:
            while self.running:
                img = np.array(sct.grab(self.monitor))
                bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                now = time.time()

                if self.state == 0:
                    if keyboard.is_pressed('e'):
                        self.state = 1
                        self.last_time = now
                        time.sleep(0.2)
                
                elif self.state == 1:
                    if now - self.last_time >= self.wait_duration:
                        self.state = 2
                        self.detected_keys = []
                
                elif self.state == 2:
                    matches = []
                    for key, temp in self.templates.items():
                        res = cv2.matchTemplate(bgr, temp, cv2.TM_CCOEFF_NORMED)
                        loc = np.where(res >= 0.65)
                        for pt in zip(*loc[::-1]):
                            matches.append({'key': key, 'x': pt[0]})
                    
                    if matches:
                        # กรองปุ่มที่ซ้ำกันในตำแหน่งใกล้เคียง
                        unique_matches = []
                        matches.sort(key=lambda x: x['x'])
                        for m in matches:
                            if not any(abs(m['x'] - u['x']) < 20 for u in unique_matches):
                                unique_matches.append(m)
                        
                        self.update_ui_keys.emit([m['key'] for m in unique_matches])
                        for i, m in enumerate(unique_matches):
                            self.press_index.emit(i)
                            pydirectinput.press(m['key'].lower())
                            time.sleep(random.uniform(0.07, 0.12))
                        
                        self.state = 3
                        self.last_time = now
                
                elif self.state == 3:
                    if now - self.last_time >= 1.5:
                        pydirectinput.press('e')
                        self.state = 1
                        self.last_time = time.time()

                self.update_preview.emit(bgr)
                time.sleep(0.01)

    def stop(self):
        self.running = False

# ---------------- UI ----------------
class KeyBox(QLabel):
    def __init__(self):
        super().__init__()
        self.setFixedSize(60, 75)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color:#2b2b2b;color:white;font-size:20px;border-radius:8px;border:3px solid #00ffff")

    def glow(self, text):
        self.setText(text)
        self.setStyleSheet("background-color:#2b2b2b;color:#00ffff;font-size:20px;border-radius:8px;border:3px solid #00ffff")

    def press_effect(self):
        self.setStyleSheet("background-color:#444;color:white;font-size:20px;border-radius:8px;border:3px solid #00ffff")

    def clear(self):
        self.setText("")
        self.setStyleSheet("background-color:#2b2b2b;color:white;font-size:20px;border-radius:8px;border:3px solid #00ffff")

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎣 Auto Fisher Pro")
        self.setFixedSize(380, 280)
        self.setStyleSheet("background:#111;color:white;")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        
        layout = QVBoxLayout()
        self.label = QLabel("Authenticating...")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

        self.preview = QLabel()
        self.preview.setFixedSize(350, 100)
        self.preview.setStyleSheet("background:#000;border:2px solid #333;")
        layout.addWidget(self.preview)

        self.boxes = [KeyBox() for _ in range(5)]
        h_layout = QHBoxLayout()
        for box in self.boxes: h_layout.addWidget(box)
        layout.addLayout(h_layout)
        self.setLayout(layout)

        # การตรวจสอบสิทธิ์
        hwid = get_hwid()
        key, ok = QInputDialog.getText(self, "License Key", f"Your HWID: {hwid}\nEnter Key:")
        
        if ok and check_key(key, hwid):
            self.label.setText("✅ Status: Authorized")
            self.start_bot()
        else:
            QMessageBox.critical(self, "Error", "Invalid Key or Key already used!")
            sys.exit()

    def start_bot(self):
        self.monitor = {"top": 820, "left": 790, "width": 280, "height": 85}
        self.templates = {}
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None: self.templates[k] = img
        
        if not self.templates:
            QMessageBox.warning(self, "Warning", "Template images (A,W,S,D.png) not found!")

        self.worker = Worker(self.monitor, self.templates)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.update_preview.connect(self.update_image)
        self.worker.update_ui_keys.connect(self.update_keys)
        self.worker.press_index.connect(self.animate_press)
        self.thread.start()

    def update_image(self, img):
        h, w, ch = img.shape
        qimg = QImage(img.tobytes(), w, h, ch*w, QImage.Format.Format_RGB888).rgbSwapped()
        self.preview.setPixmap(QPixmap.fromImage(qimg).scaled(350, 100, Qt.AspectRatioMode.KeepAspectRatio))

    def update_keys(self, key_list):
        for box in self.boxes: box.clear()
        for i, key in enumerate(key_list):
            if i < len(self.boxes): self.boxes[i].glow(key)

    def animate_press(self, index):
        if index < len(self.boxes): self.boxes[index].press_effect()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = App()
    w.show()
    sys.exit(app.exec())
