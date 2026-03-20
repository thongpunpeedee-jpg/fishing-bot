import sys
import cv2
import numpy as np
import mss
import pydirectinput
import time
import keyboard
import random
import subprocess

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLineEdit, QDialog, QFormLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QImage, QPixmap

# --- [ นำค่าที่ก๊อปได้จากปุ่ม COPY HWID มาวางที่นี่ ] ---
AUTHORIZED_HWID = "69870546-78D9-BD81-B324-08BFB8BA48FF  \R" 
# --------------------------------------------------

def get_hwid():
    try:
        # ดึง UUID และทำความสะอาดข้อมูล (ตัดช่องว่าง, ปรับเป็นตัวพิมพ์ใหญ่)
        cmd = 'wmic csproduct get uuid'
        uuid = str(subprocess.check_output(cmd, shell=True))
        clean_uuid = uuid.split('\\r\\n')[1].strip().upper()
        return clean_uuid
    except:
        return "UNKNOWN"

pydirectinput.PAUSE = 0 

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

class SettingsDialog(QDialog):
    def __init__(self, current_monitor, callback):
        super().__init__()
        self.setWindowTitle("Live Tuning - Authorized")
        self.setFixedWidth(280)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.callback = callback
        
        layout = QFormLayout(self)
        self.inputs = {}
        for key, val in current_monitor.items():
            self.inputs[key] = QLineEdit(str(val))
            self.inputs[key].setStyleSheet("background: #222; color: #00ffff; border: 1px solid #444; padding: 5px;")
            layout.addRow(f"<b>{key.capitalize()}:</b>", self.inputs[key])
            
        self.apply_btn = QPushButton("APPLY SETTINGS")
        self.apply_btn.setStyleSheet("background-color: #00ffff; color: #111; font-weight: bold; height: 35px; border-radius: 5px;")
        self.apply_btn.clicked.connect(self.apply_settings)
        layout.addRow(self.apply_btn)
        
        self.info = QLabel("เปลี่ยนเลขแล้วกด Apply ได้เลย ภาพจะเปลี่ยนทันที")
        self.info.setStyleSheet("color: #888; font-size: 9px;")
        layout.addRow(self.info)

    def apply_settings(self):
        try:
            new_vals = {k: int(v.text()) for k, v in self.inputs.items()}
            self.callback(new_vals)
        except: pass

class AutoDetectionWorker(QObject):
    update_preview = pyqtSignal(np.ndarray)
    update_ui_keys = pyqtSignal(list)
    press_index = pyqtSignal(int)

    def __init__(self, monitor_settings):
        super().__init__()
        self.running = False
        self.monitor = monitor_settings
        self.threshold = 0.65 
        self.templates = {}
        for k in ['A', 'W', 'S', 'D']:
            img = cv2.imread(f"{k}.png")
            if img is not None: self.templates[k] = img

        self.state = 0
        self.last_time = 0
        self.wait_duration = 11.0 

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
                    
                    current_time = time.time()
                    if self.state == 0:
                        if keyboard.is_pressed('e'):
                            self.state = 1
                            self.last_time = current_time
                            time.sleep(0.2)
                    elif self.state == 1:
                        if current_time - self.last_time >= self.wait_duration: self.state = 2
                    elif self.state == 2:
                        matches = []
                        for key_name, temp_img in self.templates.items():
                            res = cv2.matchTemplate(bgr, temp_img, cv2.TM_CCOEFF_NORMED)
                            loc = np.where(res >= self.threshold)
                            for pt in zip(*loc[::-1]):
                                matches.append({'x': pt[0], 'key': key_name, 'score': res[pt[1], pt[0]]})
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
                                time.sleep(random.uniform(0.06, 0.12)) 
                            self.state = 3
                            self.last_time = current_time
                    elif self.state == 3:
                        if current_time - self.last_time >= 1.5:
                            pydirectinput.press('e')
                            self.state = 1
                            self.last_time = time.time()
                    self.update_preview.emit(bgr)
                except: pass
                time.sleep(0.005) 

    def stop(self): self.running = False

class DetectionDisplay(QWidget):
    def __init__(self):
        super().__init__()
        self.current_hwid = get_hwid()
        self.setWindowTitle("🎣AUTO🎣- (Ready)")
        self.setFixedSize(380, 270) # เพิ่มพื้นที่ด้านล่าง
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("background-color: #111; color: white;")
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(15, 10, 15, 5) 
        
        self.key_row = QHBoxLayout()
        self.boxes = [KeyBox() for _ in range(5)]
        for box in self.boxes: self.key_row.addWidget(box)
        main_layout.addLayout(self.key_row)

        self.preview_label = QLabel("Loading...")
        self.preview_label.setFixedSize(350, 80)
        self.preview_label.setStyleSheet("border: 2px solid #333; background: #000;")
        main_layout.addWidget(self.preview_label)

        footer = QVBoxLayout()
        
        id_layout = QHBoxLayout()
        self.id_label = QLabel(f"ID: {self.current_hwid[:15]}...")
        self.id_label.setStyleSheet("color: #555; font-size: 10px;")
        self.copy_btn = QPushButton("COPY ID")
        self.copy_btn.setFixedSize(60, 20)
        self.copy_btn.setStyleSheet("background: #333; font-size: 9px; border-radius: 3px;")
        self.copy_btn.clicked.connect(self.copy_id)
        id_layout.addWidget(self.id_label)
        id_layout.addWidget(self.copy_btn)
        footer.addLayout(id_layout)

        self.admin_btn = QPushButton("⚙️ OPEN SETTINGS")
        # เช็คสิทธิ์
        if self.current_hwid == AUTHORIZED_HWID.upper().strip():
            self.admin_btn.setStyleSheet("background: #008080; color: #fff; font-weight: bold; height: 30px; border-radius: 5px;")
            self.admin_btn.setEnabled(True)
        else:
            self.admin_btn.setStyleSheet("background: #222; color: #444; height: 30px; border-radius: 5px;")
            self.admin_btn.setText("🔒 LOCKED (UNAUTHORIZED)")
            self.admin_btn.setEnabled(False)
        
        self.admin_btn.clicked.connect(self.show_settings)
        footer.addWidget(self.admin_btn)
        main_layout.addLayout(footer)
        
        self.setLayout(main_layout)
        self.monitor = {"top": 820, "left": 790, "width": 280, "height": 85}
        
        self.worker = AutoDetectionWorker(self.monitor)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.update_preview.connect(self.update_image)
        self.worker.update_ui_keys.connect(self.update_keys_ui)
        self.worker.press_index.connect(self.animate_press)
        self.thread.start()
        self.settings_win = None

    def copy_id(self):
        QApplication.clipboard().setText(self.current_hwid)
        self.copy_btn.setText("COPIED!")

    def show_settings(self):
        if not self.settings_win:
            self.settings_win = SettingsDialog(self.monitor, self.apply_new_config)
        self.settings_win.show()

    def apply_new_config(self, new_vals):
        self.monitor = new_vals
        self.worker.update_monitor(new_vals)

    def update_keys_ui(self, key_list):
        for box in self.boxes: box.clear()
        for i, key in enumerate(key_list):
            if i < len(self.boxes): self.boxes[i].glow(key)

    def animate_press(self, index):
        if index < len(self.boxes): self.boxes[index].press_effect()

    def update_image(self, cv_img):
        try:
            h, w, ch = cv_img.shape
            crop_v, crop_h = int(h * 0.20), int(w * 0.05)
            cropped = cv_img[crop_v:h-crop_v, crop_h:w-crop_h].copy() 
            new_h, new_w = cropped.shape[:2]
            q_img = QImage(cropped.tobytes(), new_w, new_h, ch*new_w, QImage.Format.Format_RGB888).rgbSwapped()
            self.preview_label.setPixmap(QPixmap.fromImage(q_img).scaled(350, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        except: pass

    def closeEvent(self, event):
        if self.settings_win: self.settings_win.close()
        self.worker.stop(); self.thread.quit(); self.thread.wait(); event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DetectionDisplay()
    window.show()
    sys.exit(app.exec())
