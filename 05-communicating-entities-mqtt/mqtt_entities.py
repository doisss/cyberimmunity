import paho.mqtt.client as mqtt
import json
import threading
import time
import logging
import sys

# ---------------------- Настройка логирования ----------------------
logger = logging.getLogger("MQTTSystem")
logger.setLevel(logging.INFO)

# Очищаем старые обработчики, если они были
if logger.hasHandlers():
    logger.handlers.clear()

# Лог в файл
file_handler = logging.FileHandler("system.log", encoding="utf-8", mode='a')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
file_handler.setFormatter(file_formatter)
logger.addHandler(file_handler)

# Лог в консоль
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# ---------------------- Политика безопасности ----------------------
class SecurityPolicy:
    mode = 0
    lock = threading.Lock()

    @classmethod
    def can_send(cls, sender, receiver):
        with cls.lock:
            if cls.mode == 1 and sender == "A":
                logger.warning(f"Policy blocked message from {sender} to {receiver} (mode {cls.mode})")
                return False
            return True

    @classmethod
    def set_mode(cls, new_mode):
        with cls.lock:
            cls.mode = new_mode

# ---------------------- Визуальный индикатор режима ----------------------
def display_mode():
    while True:
        sys.stdout.write(f"\rCurrent security mode: {SecurityPolicy.mode}  ")
        sys.stdout.flush()
        time.sleep(1)

threading.Thread(target=display_mode, daemon=True).start()

# ---------------------- Базовый класс сущности ----------------------
class BaseEntity:
    def __init__(self, name):
        self.name = name
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.connect("localhost", 1883, 60)
        self.client.loop_start()
        logger.info(f"{self.name} connected to MQTT broker")

    def on_connect(self, client, userdata, flags, rc):
        logger.info(f"{self.name} connected with result code {rc}")

    def send_message(self, receiver, message):
        if not SecurityPolicy.can_send(self.name, receiver):
            return
        topic = f"{self.name}/{receiver}"
        payload = json.dumps(message)
        self.client.publish(topic, payload)
        logger.info(f"{self.name} -> {receiver}: {message}")

    def on_message(self, client, userdata, msg):
        raise NotImplementedError

# ---------------------- Сущности ----------------------
class EntityA(BaseEntity):
    def __init__(self):
        super().__init__("A")
        self.client.subscribe("B/A")
        self.client.subscribe("C/A")
        threading.Thread(target=self.start_sending, daemon=True).start()

    def start_sending(self):
        while True:
            self.send_message("B", {"text": "Hello from A"})
            time.sleep(5)

    def on_message(self, client, userdata, msg):
        try:
            message = json.loads(msg.payload.decode())
            logger.info(f"A received message: {message}")
        except Exception as e:
            logger.error(f"A failed to decode message: {e}")

class EntityB(BaseEntity):
    def __init__(self):
        super().__init__("B")
        self.client.subscribe("A/B")

    def on_message(self, client, userdata, msg):
        try:
            message = json.loads(msg.payload.decode())
            logger.info(f"B received message: {message}")
            self.send_message("A", {"reply": "Message received"})
        except Exception as e:
            logger.error(f"B failed to decode message: {e}")

class EntityC(BaseEntity):
    def __init__(self):
        super().__init__("C")
        self.client.subscribe("A/C")

    def on_message(self, client, userdata, msg):
        try:
            message = json.loads(msg.payload.decode())
            logger.info(f"C received message: {message}")
            if message.get("operation") == "change_mode":
                new_mode = int(message.get("mode", SecurityPolicy.mode))
                if new_mode in [0, 1]:
                    SecurityPolicy.set_mode(new_mode)
                    logger.info(f"Security mode changed to {new_mode}")
                else:
                    logger.error(f"Invalid mode: {new_mode}")
        except Exception as e:
            logger.error(f"C failed to decode message: {e}")

# ---------------------- Основная программа ----------------------
if __name__ == "__main__":
    A = EntityA()
    B = EntityB()
    C = EntityC()

    logger.info("System started. Press CTRL+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("System stopped by user.")
