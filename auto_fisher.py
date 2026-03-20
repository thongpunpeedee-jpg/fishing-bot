import sys
import cv2
import numpy as np
import mss
import pydirectinput
import time
import keyboard
import random
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap

pydirectinput.PAUSE = 0 

class AutoDetectionWorker(QObject):
    update_preview = pyqtSignal(np.ndarray)

    def __init__(self, monitor_settings):
        super().__init__()
        self.running = False
        self.monitor = monitor_settings
        self.threshold = 0.60 
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

                if self.state == 0:
                    if keyboard.is_pressed('e'):
                        self.state = 1
                        self.last_time = current_time
                        time.sleep(0.2)

                elif self.state == 1:
                    if current_time - self.last_time >= self.wait_duration:
                        self.state = 2

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
                            if not any(abs(m['x'] - f['x']) < 30 for f in final):
                                final.append(m)
                        final.sort(key=lambda x: x['x'])
                        
                        time.sleep(random.uniform(0.1, 0.2)) 
                        for i, m in enumerate(final):
                            key = m['key'].lower()
                            pydirectinput.keyDown(key)
                            time.sleep(random.uniform(0.04, 0.06)) 
                            pydirectinput.keyUp(key)
                            if i < len(final) - 1:
                                time.sleep(random.uniform(0.1, 0.18))
                            else:
                                time.sleep(0.2) 
                    
                    self.state = 3
                    self.last_time = current_time

                elif self.state == 3:
                    if current_time - self.last_time >= 1.5:
                        pydirectinput.press('e')
                        self.state = 1
                        self.last_time = time.time()

                self.update_preview.emit(bgr)
                time.sleep(0.01)

    def stop(self): self.running = False

class DetectionDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎣 AUTO KUY - (Ready)")
        # ปรับความสูงหน้าต่างให้เล็กลงหน่อยเพื่อให้ดู "พอดีกรอบ" มากขึ้น
        self.setFixedSize(600, 140) 
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #000;")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setLayout(layout)
        
        # พิกัดการสแกนเดิมของคุณ
        self.monitor = {"top": 825, "left": 750, "width": 420, "height": 85}
        
        self.worker = AutoDetectionWorker(self.monitor)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.update_preview.connect(self.update_image)
        self.thread.start()

    def update_image(self, cv_img):
        h, w, ch = cv_img.shape
        
        # 🔥 ส่วนสำคัญ: Crop เน้นเฉพาะตัวอักษรเพื่อให้ซูมพอดีกรอบที่สุด
        # ตัดขอบบน-ล่างออกเพื่อให้เหลือแต่แถวตัวอักษร (ปรับค่า 0.10 ถึง 0.15 ตามความชอบ)
        crop_v = int(h * 0.10) 
        cropped = cv_img[crop_v:h-crop_v, :].copy() 
        
        new_h, new_w, _ = cropped.shape
        bytes_per_line = ch * new_w
        
        q_img = QImage(
            cropped.tobytes(), 
            new_w, 
            new_h, 
            bytes_per_line, 
            QImage.Format.Format_RGB888
        ).rgbSwapped()
        
        # 🔥 ใช้ KeepAspectRatio เพื่อให้ภาพไม่ยืด และขยายให้เต็มความกว้าง 600
        pixmap = QPixmap.fromImage(q_img).scaled(
            600, 140, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.label.setPixmap(pixmap)

    def closeEvent(self, event):
        self.worker.stop(); self.thread.quit(); self.thread.wait(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DetectionDisplay()
    window.show()
    sys.exit(app.exec())
