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

# ตั้งค่า pydirectinput ให้ไม่มีความหน่วงแฝง
pydirectinput.PAUSE = 0.0 

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
                # แปลง Template เป็น Gray ตั้งแต่แรกเพื่อลดภาระใน Loop
                self.templates[k] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        self.state = 0
        self.last_time = 0
        self.wait_duration = 11.0 

    def run(self):
        self.running = True
        with mss.mss() as sct:
            while self.running:
                # 1. ใช้ Grab และแปลงเป็น Gray ทันทีเพื่อความเร็ว
                sct_img = sct.grab(self.monitor)
                frame = np.array(sct_img)
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
                
                current_time = time.time()

                if self.state == 0:
                    if keyboard.is_pressed('e'):
                        self.state = 1
                        self.last_time = current_time
                        time.sleep(0.1) # ลดเวลาหลับลง

                elif self.state == 1:
                    if current_time - self.last_time >= self.wait_duration:
                        self.state = 2

                elif self.state == 2:
                    raw_matches = []
                    # 2. ทำ Template Matching บน Gray scale (เร็วกว่า BGR มาก)
                    for key_name, temp_gray in self.templates.items():
                        res = cv2.matchTemplate(gray_frame, temp_gray, cv2.TM_CCOEFF_NORMED)
                        loc = np.where(res >= self.threshold)
                        
                        for pt in zip(*loc[::-1]):
                            raw_matches.append({
                                'x': pt[0], 
                                'key': key_name, 
                                'score': res[pt[1], pt[0]]
                            })

                    if raw_matches:
                        final = []
                        # คัดเลือกจุดที่ดีที่สุด
                        raw_matches.sort(key=lambda x: x['score'], reverse=True)
                        for m in raw_matches:
                            if not any(abs(m['x'] - f['x']) < 20 for f in final): # ลดระยะ Check ลง
                                final.append(m)
                        
                        final.sort(key=lambda x: x['x'])
                        
                        # 3. กดปุ่มแบบสายฟ้าแลบ
                        for m in final:
                            pydirectinput.press(m['key'].lower())
                            # ลบ time.sleep(0.05) ออก หรือใช้ค่าน้อยมากๆ
                        
                        self.state = 3
                        self.last_time = current_time

                elif self.state == 3:
                    # ปรับลดเวลาเตรียมตัวก่อนกด E รอบใหม่ (ถ้าเกมรับไหว)
                    if current_time - self.last_time >= 1.2: 
                        pydirectinput.press('e')
                        self.state = 1
                        self.last_time = time.time()

                # ส่งภาพไป Preview (ถ้าคอมกระตุก ให้ใส่เงื่อนไขส่งทุกๆ 2-3 เฟรมแทน)
                self.update_preview.emit(cv2.cvtColor(gray_frame, cv2.COLOR_GRAY2BGR))
                # ลบ time.sleep(0.01) ออกเพื่อให้ Loop รันไวที่สุดตามพลัง CPU

    def stop(self): self.running = False

# ... (ส่วน DetectionDisplay และ Main เหมือนเดิม)
