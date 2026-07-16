import paho.mqtt.client as mqtt
import time
import ujson as json
from threading import Event
import numpy as np
import sqlite3
import os

# ======== SECURITY POLICIES ========
SECURITY_POLICIES = {
    "camera": ["modyl_polycheniya_dannyh"],
    "modyl_polycheniya_dannyh": ["modyl_neyroseti"],
    "modyl_neyroseti": ["modyl_upakovki_dannyh", "sd"],
    "modyl_upakovki_dannyh": ["csu"],
    "gnss": ["nav"],
    "ins": ["nav"],
    "csu": ["nav", "sd", "database"],  # CSU может писать в БД
    "nav": ["csu", "sd"],
    "sd": [],
    "database": []  # никто не может писать в БД кроме CSU
}

# ======== TELEMETRY & OUTLIER DETECTION ========
telemetry_window = {"gnss": [], "ins": []}
WINDOW_SIZE = 5

def find_outliers_iqr(data) -> list:
    if len(data) == 0:
        return []
    q1 = np.percentile(data, 25)
    q3 = np.percentile(data, 75)
    iqr = q3 - q1
    k = 1.5
    if len(data) < 20:
        k = 2.0
    elif len(data) > 100:
        k = 1.3
    lower = q1 - k * iqr
    upper = q3 + k * iqr
    return [x for x in data if x < lower or x > upper]

def find_outliers_robust(data, new_val, sensor):
    if len(data) == 0:
        return False
    median = float(np.median(data))
    std = float(np.std(data)) if len(data) > 1 else 0.0
    thresholds = {"gnss": 50.0, "ins": 20.0}
    abs_thresh = thresholds.get(sensor, 100.0)
    if std > 0 and abs(new_val - median) > 3 * std:
        return True
    if abs(new_val - median) > abs_thresh:
        return True
    iqr_out = find_outliers_iqr(data)
    return new_val in iqr_out

def telemetry_check(sensor, value):
    window = telemetry_window[sensor]
    window.append(value)
    if len(window) > WINDOW_SIZE:
        window.pop(0)
    iqr_out = find_outliers_iqr(window)
    robust_flag = find_outliers_robust(window, value, sensor)
    if iqr_out or robust_flag:
        outs = iqr_out if iqr_out else [value]
        print(f"[{sensor}] WARNING: outliers detected: {outs}")
    else:
        print(f"[{sensor}] OK window: {window}")

# ======== POLICY CHECK ========
def check_policies(message) -> bool:
    sender = message.get('sender')
    dest = message.get('destination')
    allowed = SECURITY_POLICIES.get(sender, [])
    return dest in allowed

# ======== DATABASE HANDLER ========
class DatabaseHandler:
    def __init__(self, db_file="system_data.db"):
        self.db_file = db_file
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            sender TEXT,
            destination TEXT,
            data TEXT
        )
        """)
        conn.commit()
        conn.close()

    def insert_record(self, sender, destination, data):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("INSERT INTO logs (timestamp, sender, destination, data) VALUES (?, ?, ?, ?)",
                  (time.time(), sender, destination, data))
        conn.commit()
        conn.close()

    def show_last_entries(self, limit=5):
        conn = sqlite3.connect(self.db_file)
        c = conn.cursor()
        c.execute("SELECT timestamp, sender, destination, data FROM logs ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        print("\n[database] последние записи в журнале:")
        for r in rows:
            print(f"  {r[0]:.2f} | {r[1]} → {r[2]} : {r[3]}")

# ======== MQTT SERVICE CLASS ========
class MQTT_service:
    def __init__(self, name, broker_host='localhost', broker_port=1883):
        self.name = name
        self.client = mqtt.Client(client_id=name)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.stop_event = Event()
        if self.name == "database":
            self.db = DatabaseHandler()

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"[{self.name}] connected to broker OK")
        else:
            print(f"[{self.name}] connection error code {rc}")

    def on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            sender = payload.get("sender")
            data = payload.get("data")
            destination = payload.get("destination")

            if destination == self.name:
                print(f"[{self.name}] got message from [{sender}] via [{msg.topic}]: {data}")
                self.process_message(payload)
        except Exception as e:
            print(f"[{self.name}] message error: {e}")

    def process_message(self, message):
        sender = message["sender"]
        data = message["data"]

        # === Логика БД ===
        if self.name == "database":
            self.db.insert_record(sender, self.name, data)
            print(f"[database] запись сохранена: {sender} → {data}")
            self.db.show_last_entries()
            return

        # === Навигация и телеметрия ===
        if self.name == "nav":
            if "Accel" in data:
                try:
                    value = float(data.split(":")[1].strip().split()[0])
                    telemetry_check("ins", value)
                except Exception:
                    pass
            elif "Coords" in data:
                try:
                    coords = data.split(":")[1].strip()[1:-1].split(",")
                    lat = float(coords[0])
                    telemetry_check("gnss", lat)
                except Exception:
                    pass

        # === Общая логика обмена ===
        if self.name == "modyl_polycheniya_dannyh":
            time.sleep(2)
            self.send_message("sokol/network", f"Analiz dannyh kamery ({data})", "modyl_neyroseti")

        elif self.name == "modyl_neyroseti":
            time.sleep(2)
            self.send_message("sokol/network", f"Rezultat AI analiza ({data})", "modyl_upakovki_dannyh")
            self.send_message("sokol/network", f"Status modyl_neyroseti: OK", "sd")

        elif self.name == "modyl_upakovki_dannyh":
            time.sleep(2)
            self.send_message("sokol/network", f"Otzhet o dannyh: [{data}]", "csu")

        elif self.name == "csu":
            time.sleep(2)
            self.send_message("sokol/network", f"Komanda upravleniya OK", "nav")
            self.send_message("sokol/network", f"Otzhet CSU: proverka sistem", "sd")
            # Запись в БД
            self.send_message("sokol/network", f"Log zapis: {data}", "database")

        elif self.name == "nav":
            time.sleep(2)
            self.send_message("sokol/network", f"Vypolnyayu komandu", "csu")
            self.send_message("sokol/network", f"Status navigacii: stabilen", "sd")

        elif self.name == "gnss":
            self.send_message("sokol/network", "Coords: (60.17, 24.94)", "nav")

        elif self.name == "ins":
            self.send_message("sokol/network", "Accel: 9.81 m/s2", "nav")

        elif self.name == "sd":
            print(f"[sd] diagnostika prinjala otzhet: {data}")

    def send_message(self, topic, data, destination):
        message = {
            "sender": self.name,
            "destination": destination,
            "data": data,
            "timestamp": time.time()
        }
        if check_policies(message):
            self.client.publish(topic, json.dumps(message))
            print(f"[{self.name}] → [{destination}] : {data}")
        else:
            print(f"[{self.name}] BLOCKED: cannot send to [{destination}] (policy violation)")

    def start(self, topics):
        self.client.connect(self.broker_host, self.broker_port, 60)
        for t in topics:
            self.client.subscribe(t)
            print(f"[{self.name}] subscribed to {t}")
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

# ======== MAIN SYSTEM ========
def run_sokol_system():
    topic = "sokol/network"
    camera = MQTT_service("camera")
    d1 = MQTT_service("modyl_polycheniya_dannyh")
    d2 = MQTT_service("modyl_neyroseti")
    d3 = MQTT_service("modyl_upakovki_dannyh")
    csu = MQTT_service("csu")
    nav = MQTT_service("nav")
    sd = MQTT_service("sd")
    gnss = MQTT_service("gnss")
    ins = MQTT_service("ins")
    database = MQTT_service("database")

    services = [camera, d1, d2, d3, csu, nav, sd, gnss, ins, database]
    for s in services:
        s.start([topic])

    time.sleep(2)
    print("\n--- SYSTEM START ---\n")

    camera.send_message(topic, "Image_1", "modyl_polycheniya_dannyh")

    time.sleep(2)
    gnss.send_message(topic, "Coords: (60.17, 24.94)", "nav")
    time.sleep(0.5)
    gnss.send_message(topic, "Coords: (300.0, 24.94)", "nav")
    time.sleep(0.5)
    ins.send_message(topic, "Accel: 9.81 m/s2", "nav")
    time.sleep(0.2)
    ins.send_message(topic, "Accel: 50.0 m/s2", "nav")
    time.sleep(0.2)
    ins.send_message(topic, "Accel: 9.9 m/s2", "nav")
    time.sleep(0.2)
    ins.send_message(topic, "Accel: 10.0 m/s2", "nav")

    time.sleep(4)
    csu.send_message(topic, "Ping all modules", "sd")

    time.sleep(2)
    camera.send_message(topic, "Try to contact CSU", "csu")

    print("\n--- SYSTEM STOPPING --- (waiting for all modules to finish processing)\n")
    time.sleep(3)
    for s in services:
        s.stop()
    print("\n--- SYSTEM STOP ---\nSystem finished.")

# ======== RUN ========
if __name__ == "__main__":
    run_sokol_system()

