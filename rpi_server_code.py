import cv2
import numpy as np
import threading
import time
import json
import serial  
from flask import Flask, request, jsonify
from flask_cors import CORS

# =========================
# Config
# =========================
CFG_PATH = "yolov3-tiny.cfg"
WEIGHTS_PATH = "yolov3-tiny.weights"
NAMES_PATH = "coco.names"
CAMERA_INDEX = 0 

SERIAL_PORT = "/dev/serial0"  # ACM0 for USB, serial0: rx-tx pins
BAUD_RATE = 9600

CONF_THRESHOLD = 0.5
NMS_THRESHOLD = 0.4

# =========================
# Initialization and Global State
# =========================
state_lock = threading.Lock()
serial_lock = threading.Lock()

state = {
    "temp": 0.0,
    "humidity": 0.0,
    "presence": False,
    "fan": False,
    "light": False,
    "mode": "auto",        
    "target_temp": 23.0    
}

ser = None

# =========================
# All YOLO
# =========================
with open(NAMES_PATH, "r") as f:
    classes = [line.strip() for line in f.readlines()]

try:
    PERSON_CLASS_ID = classes.index("person")
except ValueError:
    raise RuntimeError("'person' class not found in coco.names")

net = cv2.dnn.readNetFromDarknet(CFG_PATH, WEIGHTS_PATH)
net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)

layer_names = net.getLayerNames()
output_layers = [layer_names[i - 1] for i in net.getUnconnectedOutLayers().flatten()]

# =========================
# Serial Functions
# =========================
def init_serial():
    global ser
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1.0)
        ser.flushInput()
        print(f"[SERIAL] Connected on {SERIAL_PORT}")
    except Exception as e:
        print(f"[SERIAL] Connection Error: {e}")
        ser = None

def send_command(cmd):
    """ Sends command to Arduino ('FAN:1') """
    with serial_lock:
        if ser and ser.is_open:
            try:
                full_cmd = f"{cmd}\n"
                ser.write(full_cmd.encode('utf-8'))
                print(f"[SERIAL] Sent: {cmd}")
            except Exception as e:
                print(f"[SERIAL] Write Failed: {e}")

def serial_manager_loop():
    """ Reads JSON from Arduino and updates State """
    if ser is None: init_serial()

    while True:
        if ser and ser.is_open:
            try:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            data = json.loads(line)
                            with state_lock:
                                if "temp" in data: state["temp"] = float(data["temp"])
                                if "humidity" in data: state["humidity"] = float(data["humidity"])
                                
                                # Syncing LED/Fan state if changed by IR Remote
                                if "led" in data:
                                    state["light"] = (str(data["led"]).lower() == "true")
                                if "fan" in data:
                                    state["fan"] = (str(data["fan"]).lower() == "true")
                        except ValueError:
                            pass
            except Exception as e:
                print(f"[SERIAL] Error: {e}")
                time.sleep(1)
        else:
            time.sleep(2)
            init_serial()

# =========================
# Auto mode Loop
# =========================
def auto_logic_loop():
    while True:
        with state_lock:
            curr_mode = state["mode"]
            occupied = state["presence"]
            curr_light = state["light"]
            curr_fan = state["fan"]
            curr_temp = state["temp"]
            target_t = state["target_temp"]
            
            # --- AUTO LOGIC ---
            if curr_mode == "auto":
                # 1. Light logic (opencv)
                should_light_be_on = occupied
                if should_light_be_on != curr_light:
                    state["light"] = should_light_be_on
                    cmd = "LED:1" if should_light_be_on else "LED:0"
                    threading.Thread(target=send_command, args=(cmd,)).start()
                    print(f"[AUTO] Motion {'Detected' if occupied else 'Ended'} -> Light {cmd}")

                # 2. Fan Logic (temp)
                # Turn ON if temp is above target
                if curr_temp > target_t and not curr_fan:
                    state["fan"] = True
                    threading.Thread(target=send_command, args=("FAN:1",)).start()
                    print(f"[AUTO] Temp ({curr_temp}) > Target ({target_t}) -> Fan ON")
                
                # Turn off if temp drops below (Target - 1.0) 
                # -1.0 to prevent the fan from alternating on/off quick when right on temp
                elif curr_temp < (target_t - 1.0) and curr_fan:
                    state["fan"] = False
                    threading.Thread(target=send_command, args=("FAN:0",)).start()
                    print(f"[AUTO] Temp ({curr_temp}) < Target ({target_t}) -> Fan OFF")

        time.sleep(1.0)

# =========================
# YOLO Loop 
# =========================
def yolo_loop():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    
    # Attempt to set buffer size to 1
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1) 
    
    if not cap.isOpened():
        print("[YOLO] Could not open camera")
        return

    while True:
        # --- OPTIMIZATION 1: CLEAR BUFFER ---
        # Grab a frame. If the camera has a queue, this reads the 'next' one.
        # We want to discard the backlog to get the latest one.
        # This quick loop flushes the buffer.
        for _ in range(5): 
            cap.grab()
            
        ret, frame = cap.read()
        if not ret:
            print("[YOLO] Failed to read frame")
            time.sleep(1)
            continue

        height, width = frame.shape[:2]


        # (416, 416) to (320, 320). 
        # fewer pixels to calculate, speeding up FPS 
        blob = cv2.dnn.blobFromImage(
            frame, 1 / 255.0, (320, 320), swapRB=True, crop=False
        )
        
        net.setInput(blob)
        outs = net.forward(output_layers)

        boxes = []
        confidences = []

        for out in outs:
            for detection in out:
                scores = detection[5:]
                class_id = np.argmax(scores)
                confidence = scores[class_id]

                if class_id == PERSON_CLASS_ID and confidence > CONF_THRESHOLD:
                    center_x = int(detection[0] * width)
                    center_y = int(detection[1] * height)
                    w = int(detection[2] * width)
                    h = int(detection[3] * height)

                    x = int(center_x - w / 2)
                    y = int(center_y - h / 2)

                    boxes.append([x, y, w, h])
                    confidences.append(float(confidence))

        indices = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, NMS_THRESHOLD)
        people_present = len(indices) > 0

        with state_lock:
            state["presence"] = people_present

        # Reduced sleep time since the processing is already the bottleneck
        time.sleep(0.01)

    cap.release()

# =========================
# Flask API
# =========================
app = Flask(__name__)
CORS(app)

@app.route("/status", methods=["GET"])
def get_status():
    with state_lock: return jsonify(state)

@app.route("/fan", methods=["POST"])
def set_fan():
    body = request.get_json(force=True, silent=True) or {}
    val = str(body.get("state", "")).lower()
    if val not in ("on", "off"): return jsonify({"error": "invalid"}), 400
    
    with state_lock: state["fan"] = (val == "on")
    # Send 1 or 0
    send_command(f"FAN:{'1' if val == 'on' else '0'}")
    return jsonify({"ok": True})

@app.route("/light", methods=["POST"])
def set_light():
    body = request.get_json(force=True, silent=True) or {}
    val = str(body.get("state", "")).lower()
    if val not in ("on", "off"): return jsonify({"error": "invalid"}), 400
    
    with state_lock: state["light"] = (val == "on")
    send_command(f"LED:{'1' if val == 'on' else '0'}")
    return jsonify({"ok": True})

@app.route("/mode", methods=["POST"])
def set_mode():
    body = request.get_json(force=True, silent=True) or {}
    m = str(body.get("mode", "")).lower()
    if m in ("auto", "manual"):
        with state_lock: state["mode"] = m
        return jsonify({"ok": True})
    return jsonify({"error": "invalid mode"}), 400

@app.route("/config", methods=["POST"])
def set_config():
    body = request.get_json(force=True, silent=True) or {}
    if "target_temp" in body:
        with state_lock: state["target_temp"] = float(body["target_temp"])
        return jsonify({"ok": True})
    return jsonify({"error": "missing target_temp"}), 400

if __name__ == "__main__":
    threading.Thread(target=serial_manager_loop, daemon=True).start()
    threading.Thread(target=yolo_loop, daemon=True).start()
    threading.Thread(target=auto_logic_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
