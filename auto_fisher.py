import sys
import cv2
import numpy as np
import mss
import pydirectinput
import time
import keyboard
import random
from collections import Counter
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
                        # เรียงตามคะแนนความเหมือนก่อน
                        raw_matches.sort(key=lambda x: x['score'], reverse=True)
                        for m in raw_matches:
                            # ปรับระยะห่างเป็น 25 เพื่อไม่ให้ทับซ้อนกันมากเกินไป
                            if not any(abs(m['x'] - f['x']) < 25 for f in final):
                                final.append(m)
                        
                        # เรียงจากซ้ายไปขวาตามตำแหน่ง X
                        final.sort(key=lambda x: x['x'])
                        
                        # หน่วงก่อนเริ่มกดนิดนึง
                        time.sleep(random.uniform(0.1, 0.15)) 
                        
                        for i, m in enumerate(final):
                            key = m['key'].lower()
                            # ป้องกันปุ่มค้างด้วยการใช้ press แทนในบางจังหวะ 
                            # หรือใช้ keyDown/Up แบบคุมเวลาให้ชัวร์
                            pydirectinput.keyDown(key)
                            time.sleep(random.uniform(0.05, 0.07)) 
                            pydirectinput.keyUp(key)
                            
                            if i < len(final) - 1:
                                time.sleep(random.uniform(0.12, 0.18))
                        
                        # หลังจากกดครบทุกตัว ให้รอเซิร์ฟเวอร์ตอบสนอง
                        time.sleep(0.3)
                        self.state = 3
                        self.last_time = time.time()
                    
                    # ถ้าสแกนไม่เจออะไรเลยใน State 2 ให้รอแป๊บนึงแล้วสแกนใหม่ (ป้องกันบอทค้าง)
                    else:
                        time.sleep(0.1)

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
        self.setWindowTitle("🎣AUTO kuy")
        self.setFixedSize(600, 190)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #000;")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        self.setLayout(layout)
        
        # ปรับขอบเขตการมองเห็นให้กว้างขึ้นนิดหน่อย เผื่อตัว A มันอยู่ริม
        self.monitor = {"top": 825, "left": 750, "width": 450, "height": 85}
        
        self.worker = AutoDetectionWorker(self.monitor)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.update_preview.connect(self.update_image)
        self.thread.start()

    def update_image(self, cv_img):
        h, w, ch = cv_img.shape
        # ยืดภาพให้เต็มกรอบแบบที่ต้องการ
        crop_h = int(h * 0.20) # ลดการ crop ลงนิดนึงเพื่อให้เห็นขอบชัดขึ้น
        crop_w = int(w * 0.02)
        cropped = cv_img[crop_h:h-crop_h, crop_w:w-crop_w].copy() 
        
        new_h, new_w, _ = cropped.shape
        bytes_per_line = ch * new_w
        
        q_img = QImage(
            cropped.tobytes(), 
            new_w, 
            new_h, 
            bytes_per_line, 
            QImage.Format.Format_RGB888
        ).rgbSwapped()
        
        pixmap = QPixmap.fromImage(q_img).scaled(
            610, 190, 
            Qt.AspectRatioMode.IgnoreAspectRatio, 
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
