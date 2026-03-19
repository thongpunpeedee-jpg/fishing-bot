import sys
import cv2
import numpy as np
import mss
import pydirectinput
import time
import keyboard
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap

# ตั้งค่าให้ pydirectinput ส่งคำสั่งทันทีโดยไม่รอ (Default คือ 0.1 ซึ่งช้ามาก)
pydirectinput.PAUSE = 0 

class AutoDetectionWorker(QObject):
    update_preview = pyqtSignal(np.ndarray)

    def __init__(self, monitor_settings):
        super().__init__()
        self.running = False
        self.monitor = monitor_settings
        self.threshold = 0.55 
        self.templates = {}
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None:
                self.templates[k] = img

        self.state = 0
        self.last_time = 0
        self.wait_duration = 11.0 

    def run(self):
        self.running = True
        with mss.mss() as sct:
            while self.running:
                sct_img = sct.grab(self.monitor)
                frame = np.array(sct_img)
                bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                current_time = time.time()

                # State 0: รอเริ่มครั้งแรกด้วยการกด E
                if self.state == 0:
                    if keyboard.is_pressed('e'):
                        self.state = 1
                        self.last_time = current_time
                        time.sleep(0.05) # ปรับลดจาก 0.2 เหลือ 0.05

                # State 1: นับถอยหลัง 11 วิ
                elif self.state == 1:
                    if current_time - self.last_time >= self.wait_duration:
                        self.state = 2

                # State 2: Snapshot & Press (ปรับให้รวดเร็วที่สุด)
                elif self.state == 2:
                    raw_matches = []
                    for key_name, temp_img in self.templates.items():
                        res = cv2.matchTemplate(bgr, temp_img, cv2.TM_CCOEFF_NORMED)
                        loc = np.where(res >= self.threshold)
                        for pt in zip(*loc[::-1]):
                            raw_matches.append({'x': pt[0], 'key': key_name, 'score': res[pt[1], pt[0]]})

                    if raw_matches:
                        final = []
                        raw_matches.sort(key=lambda x: x['score'], reverse=True)
                        for m in raw_matches:
                            if not any(abs(m['x'] - f['x']) < 25 for f in final):
                                final.append(m)
                        final.sort(key=lambda x: x['x'])
                        
                        for m in final:
                            pydirectinput.press(m['key'].lower())
                            # ปรับจาก 0.05 เหลือ 0.001 (เกือบจะทันที)
                            time.sleep(0.050) 
                    
                    self.state = 3
                    self.last_time = current_time

                # State 3: กด E อัตโนมัติเพื่อเริ่มรอบใหม่
                elif self.state == 3:
                    # ปรับจาก 1.5 วิ เหลือ 1.1 วิ (เร่งจังหวะจบแอนิเมชัน)
                    if current_time - self.last_time >= 1.1:
                        pydirectinput.press('e')
                        self.state = 1
                        self.last_time = time.time()

                # ส่งภาพสดไปที่ Preview
                self.update_preview.emit(bgr)
                # ปรับลด sleep หลักจาก 0.01 เหลือ 0.001 เพื่อเพิ่มรอบการสแกนต่อวินาที
                time.sleep(0.001)

    def stop(self): self.running = False

class DetectionDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎣 FAST AUTO LOOP")
        self.setFixedSize(600, 150)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #000;")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        layout.addWidget(self.label)
        self.setLayout(layout)
        
        self.monitor = {"top": 825, "left": 750, "width": 420, "height": 85}
        
        self.worker = AutoDetectionWorker(self.monitor)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.update_preview.connect(self.update_image)
        self.thread.start()

    def update_image(self, cv_img):
        h, w, ch = cv_img.shape
        q_img = QImage(cv_img.data, w, h, ch * w, QImage.Format.Format_RGB888).rgbSwapped()
        self.label.setPixmap(QPixmap.fromImage(q_img).scaled(600, 150, Qt.AspectRatioMode.KeepAspectRatio))

    def closeEvent(self, event):
        self.worker.stop(); self.thread.quit(); self.thread.wait(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DetectionDisplay()
    window.show()
    sys.exit(app.exec())
