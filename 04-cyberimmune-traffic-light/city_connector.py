from multiprocessing import Queue, Process
from multiprocessing.queues import Empty
from time import sleep
from dataclasses import dataclass
import json

# ---------------------------
# Message format
# ---------------------------
@dataclass
class Event:
    source: str
    destination: str
    operation: str
    parameters: str


@dataclass
class ControlEvent:
    operation: str


# ---------------------------
# Allowed configurations
# ---------------------------
traffic_lights_allowed_configurations = [
    {"direction_1": "red", "direction_2": "green"},
    {"direction_1": "red", "direction_2": "red"},
    {"direction_1": "red", "direction_2": "yellow"},
    {"direction_1": "yellow", "direction_2": "yellow"},
    {"direction_1": "off", "direction_2": "off"},
    {"direction_1": "green", "direction_2": "red"},
    {"direction_1": "green", "direction_2": "yellow"},
    {"direction_1": "yellow_blinking", "direction_2": "yellow_blinking"}  # blinking yellow
]


# ---------------------------
# Monitor
# ---------------------------
class Monitor(Process):
    def __init__(self, events_q: Queue):
        super().__init__()
        self._events_q = events_q
        self._control_q = Queue()
        self._entity_queues = {}
        self._force_quit = False

    def add_entity_queue(self, entity_id: str, queue: Queue):
        print(f"[monitor] registriruem sushnost {entity_id}")
        self._entity_queues[entity_id] = queue

    def _check_policies(self, event):
        print(f'[monitor] obrabatyvaem sobytie {event}')
        authorized = False  # default deny

        if not isinstance(event, Event):
            return False

        # Allow only correct configs
        if event.operation == "set_mode":
            try:
                mode = json.loads(event.parameters)
                if mode in traffic_lights_allowed_configurations:
                    authorized = True
                    print("[monitor] politika bezopasnosti: dostup razreshen")
            except Exception:
                pass

        # Allow diagnostic and city commands
        if event.operation in ["diagnostic", "city_command"]:
            authorized = True

        if authorized is False:
            print("[monitor] sobytie ne razresheno politikami bezopasnosti")

        return authorized

    def _proceed(self, event):
        print(f'[monitor] peresylaem sobytie {event}')
        try:
            dst_q: Queue = self._entity_queues[event.destination]
            dst_q.put(event)
        except Exception as e:
            print(f"[monitor] oshibka peresylki sobytiya {e}")

    def run(self):
        print(f'[monitor] start')
        while self._force_quit is False:
            event = None
            try:
                event = self._events_q.get_nowait()
                authorized = self._check_policies(event)
                if authorized:
                    self._proceed(event)
            except Empty:
                sleep(0.2)
            except Exception as e:
                print(f"[monitor] oshibka obrabotki {e}, {event}")
            self._check_control_q()
        print(f'[monitor] stop')

    def stop(self):
        request = ControlEvent(operation='stop')
        self._control_q.put(request)

    def _check_control_q(self):
        try:
            request: ControlEvent = self._control_q.get_nowait()
            if isinstance(request, ControlEvent) and request.operation == 'stop':
                self._force_quit = True
        except Empty:
            pass


# ---------------------------
# ControlSystem
# ---------------------------
class ControlSystem(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()
        self.green_duration = 3  # sec for green light

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[ControlSystem] start')

        modes = [
            {"direction_1": "green", "direction_2": "red"},
            {"direction_1": "yellow", "direction_2": "yellow"},
            {"direction_1": "red", "direction_2": "green"},
        ]

        current_idx = 0
        while True:
            mode = modes[current_idx]
            event = Event(source=self.__class__.__name__,
                          destination='LightsGPIO',
                          operation='set_mode',
                          parameters=json.dumps(mode))

            print(f'[ControlSystem] otpravlyaem rezhim: {mode}')
            self.monitor_queue.put(event)

            # also send diagnostic info
            diag = Event(source=self.__class__.__name__,
                         destination='CitySystemConnector',
                         operation='diagnostic',
                         parameters=json.dumps({"status": "ok", "mode": mode}))
            self.monitor_queue.put(diag)

            # wait with check for city commands
            for _ in range(self.green_duration * 5):
                try:
                    event_in: Event = self._own_queue.get_nowait()
                    if event_in.operation == "city_command":
                        cmd = json.loads(event_in.parameters)
                        if "green_duration" in cmd:
                            self.green_duration = cmd["green_duration"]
                            print(f"[ControlSystem] poluchena komanda iz goroda: izmenit green_duration na {self.green_duration}")
                        if "set_mode" in cmd:
                            mode = cmd["set_mode"]
                            print(f"[ControlSystem] poluchena komanda iz goroda: perehod v rezhim {mode}")
                            self.monitor_queue.put(Event(source=self.__class__.__name__,
                                                         destination='LightsGPIO',
                                                         operation='set_mode',
                                                         parameters=json.dumps(mode)))
                except Empty:
                    sleep(0.2)

            current_idx = (current_idx + 1) % len(modes)


# ---------------------------
# LightsGPIO
# ---------------------------
class LightsGPIO(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[LightsGPIO] start')
        while True:
            try:
                event: Event = self._own_queue.get_nowait()
                if event.operation == "set_mode":
                    mode = json.loads(event.parameters)
                    print(f"[LightsGPIO] noviy rezhim svetofora: {mode}")
            except Empty:
                sleep(0.2)


# ---------------------------
# CitySystemConnector
# ---------------------------
class CitySystemConnector(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[CitySystemConnector] start')

        # send command after some time
        sleep(5)
        cmd = {"green_duration": 1}
        event = Event(source=self.__class__.__name__,
                      destination="ControlSystem",
                      operation="city_command",
                      parameters=json.dumps(cmd))
        print(f"[CitySystemConnector] otpravlyaem komandu: {cmd}")
        self.monitor_queue.put(event)

        # listen to diagnostics
        while True:
            try:
                event: Event = self._own_queue.get_nowait()
                if event.operation == "diagnostic":
                    data = json.loads(event.parameters)
                    print(f"[CitySystemConnector] diagnostika: svetofor = {data}")
            except Empty:
                sleep(0.2)


# ---------------------------
# Startup
# ---------------------------
if __name__ == "__main__":
    monitor_events_queue = Queue()
    monitor = Monitor(monitor_events_queue)
    control_system = ControlSystem(monitor_events_queue)
    lights_gpio = LightsGPIO(monitor_events_queue)
    city_connector = CitySystemConnector(monitor_events_queue)

    monitor.add_entity_queue(control_system.__class__.__name__, control_system.entity_queue())
    monitor.add_entity_queue(lights_gpio.__class__.__name__, lights_gpio.entity_queue())
    monitor.add_entity_queue(city_connector.__class__.__name__, city_connector.entity_queue())

    monitor.start()
    control_system.start()
    lights_gpio.start()
    city_connector.start()

    try:
        sleep(20)
    finally:
        monitor.stop()
        control_system.terminate()
        lights_gpio.terminate()
        city_connector.terminate()
        monitor.join()
        control_system.join()
        lights_gpio.join()
        city_connector.join()
