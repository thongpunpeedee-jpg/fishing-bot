import sys
import cv2
import numpy as np
import mss
import pydirectinput
import time
import keyboard
import random  # 🔥 เพิ่มการสุ่มเพื่อความเนียน
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
        self.threshold = 0.65  
        self.templates = {}

        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None:
                self.templates[k] = img

        self.state = 0
        self.last_time = 0
        self.wait_duration = 10.0
        self.last_result = None
        self.same_count = 0
        self.use_brightness = True

    def enhance(self, img):
        alpha = 1.3
        beta = 30
        return cv2.convertScaleAbs(img, alpha=alpha, beta=beta)

    def run(self):
        self.running = True
        with mss.mss() as sct:
            while self.running:
                if keyboard.is_pressed('f1'):
                    self.use_brightness = not self.use_brightness
                    time.sleep(0.3)

                sct_img = sct.grab(self.monitor)
                frame = np.array(sct_img)
                bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                if self.use_brightness:
                    bgr = self.enhance(bgr)

                current_time = time.time()

                if self.state == 0:
                    if keyboard.is_pressed('e'):
                        self.state = 1
                        self.last_time = current_time
                        time.sleep(0.05)

                elif self.state == 1:
                    if current_time - self.last_time >= self.wait_duration:
                        self.state = 2

                elif self.state == 2:
                    all_results = []
                    # แคปภาพ 6 ครั้งเพื่อความแม่นยำ
                    for _ in range(6):  
                        sct_img = sct.grab(self.monitor)
                        # ... (ส่วนประมวลผลเหมือนเดิม)
                        frame = np.array(sct_img)
                        temp_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        if self.use_brightness: temp_bgr = self.enhance(temp_bgr)
                        
                        raw_matches = []
                        for key_name, temp_img in self.templates.items():
                            res = cv2.matchTemplate(temp_bgr, temp_img, cv2.TM_CCOEFF_NORMED)
                            loc = np.where(res >= self.threshold)
                            for pt in zip(*loc[::-1]):
                                raw_matches.append({'x': pt[0], 'key': key_name, 'score': res[pt[1], pt[0]]})

                        if raw_matches:
                            raw_matches.sort(key=lambda x: x['score'], reverse=True)
                            final = []
                            for m in raw_matches:
                                if not any(abs(m['x'] - f['x']) < 35 for f in final):
                                    final.append(m)
                            final.sort(key=lambda x: x['x'])
                            all_results.append(tuple(m['key'] for m in final))
                        time.sleep(0.005)

                    if all_results:
                        most_common = Counter(all_results).most_common(1)[0][0]

                        if most_common == self.last_result:
                            self.same_count += 1
                        else:
                            self.same_count = 1
                            self.last_result = most_common

                        # --- ส่วนที่ปรับปรุง: การรอและจังหวะกดปุ่ม ---
                        if self.same_count >= 1:
                            # 1. รอหลังจากแคปเสร็จ (0.15 - 0.3 วินาที) ไม่ให้กดทันทีจนเกินไป
                            time.sleep(random.uniform(0.15, 0.3))

                            for key in most_common:
                                pydirectinput.press(key.lower())
                                # 2. ความเร็วระหว่างการกดแต่ละปุ่ม (0.08 - 0.15 วินาที)
                                # ไม่ช้าจนคอมโบหลุด แต่ไม่เร็วเหมือนบอทกด
                                time.sleep(random.uniform(0.08, 0.15))

                            self.same_count = 0
                            self.last_result = None
                            self.state = 3
                            self.last_time = current_time

                elif self.state == 3:
                    # รอหลังจากกดจบชุด ก่อนจะกด 'e' ต่อ
                    if current_time - self.last_time >= 1.1:
                        pydirectinput.press('e')
                        self.state = 1
                        self.last_time = time.time()

                self.update_preview.emit(bgr)
                time.sleep(0.001)

    def stop(self): 
        self.running = False

# --- ส่วน Class DetectionDisplay (เหมือนเดิม) ---
class DetectionDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🎣AUTO🎣")
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
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DetectionDisplay()
    window.show()
    sys.exit(app.exec())
