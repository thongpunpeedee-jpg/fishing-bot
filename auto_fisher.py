import sys
import cv2
import numpy as np
import mss
import pydirectinput
import time
import keyboard
import random

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap

pydirectinput.PAUSE = 0 

class KeyBox(QLabel):
    def __init__(self):
        super().__init__("")
        self.setFixedSize(75, 95) 
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(self.default_style())

    def default_style(self):
        return "background-color: #2b2b2b; color: white; font-size: 26px; border-radius: 10px; border: 3px solid #00ffff;"

    def glow(self, text):
        self.setText(text)
        self.setStyleSheet("background-color: #2b2b2b; color: #00ffff; font-size: 26px; border-radius: 10px; border: 3px solid #00ffff;")

    def press_effect(self):
        self.setStyleSheet("background-color: #444; color: white; font-size: 26px; border-radius: 10px; border: 3px solid #00ffff;")

    def clear(self):
        self.setText("")
        self.setStyleSheet(self.default_style())

class AutoDetectionWorker(QObject):
    update_preview = pyqtSignal(np.ndarray)
    update_ui_keys = pyqtSignal(list)
    press_index = pyqtSignal(int)

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
                        t_h, t_w = temp_img.shape[:2]
                        f_h, f_w = bgr.shape[:2]
                        target_bgr = bgr
                        if f_h < t_h or f_w < t_w:
                            target_bgr = cv2.resize(bgr, (max(f_w, t_w), max(f_h, t_h)))

                        res = cv2.matchTemplate(target_bgr, temp_img, cv2.TM_CCOEFF_NORMED)
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
                        
                        self.update_ui_keys.emit([m['key'] for m in final])
                        
                        time.sleep(0.1) 
                        for i, m in enumerate(final):
                            self.press_index.emit(i) 
                            key = m['key'].lower()
                            pydirectinput.press(key) 
                            time.sleep(random.uniform(0.08, 0.15))
                    
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
        self.setWindowTitle("🎣AUTO🎣- (Ready) ")
        self.setFixedSize(500, 260) 
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #111;")
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        self.key_row = QHBoxLayout()
        self.boxes = []
        for _ in range(5):
            box = KeyBox()
            self.boxes.append(box)
            self.key_row.addWidget(box)
        main_layout.addLayout(self.key_row)

        self.preview_label = QLabel("Waiting for 'E'...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("border: 2px solid #333; background: #000;")
        self.preview_label.setFixedSize(480, 130)
        main_layout.addWidget(self.preview_label)
        
        self.setLayout(main_layout)
        
        self.monitor = {"top": 825, "left": 750, "width": 420, "height": 85}
        
        self.worker = AutoDetectionWorker(self.monitor)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        
        self.worker.update_preview.connect(self.update_image)
        self.worker.update_ui_keys.connect(self.update_keys_ui)
        self.worker.press_index.connect(self.animate_press)
        
        self.thread.start()

    def update_keys_ui(self, key_list):
        for box in self.boxes: box.clear()
        for i, key in enumerate(key_list):
            if i < len(self.boxes):
                self.boxes[i].glow(key)

    def animate_press(self, index):
        if index < len(self.boxes):
            self.boxes[index].press_effect()

    def update_image(self, cv_img):
        h, w, ch = cv_img.shape
        
        crop_v = int(h * 0.15) 
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
        
        pixmap = QPixmap.fromImage(q_img).scaled(
            480, 130, 
            Qt.AspectRatioMode.KeepAspectRatio, 
            Qt.TransformationMode.SmoothTransformation
        )
        self.preview_label.setPixmap(pixmap)

    def closeEvent(self, event):
        self.worker.stop(); self.thread.quit(); self.thread.wait(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DetectionDisplay()
    window.show()
    sys.exit(app.exec())
