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
# Allowed configurations (basic svetofor + arrows)
# ---------------------------
traffic_lights_allowed_configurations = [
    {"direction_1": "red", "direction_2": "green"},
    {"direction_1": "red", "direction_2": "red"},
    {"direction_1": "red", "direction_2": "yellow"},
    {"direction_1": "yellow", "direction_2": "yellow"},
    {"direction_1": "off", "direction_2": "off"},
    {"direction_1": "green", "direction_2": "red"},
    {"direction_1": "green", "direction_2": "yellow"},
    {"direction_1": "yellow_blinking", "direction_2": "yellow_blinking"},  # migauchiy zheltyy
    # novye arrow configi
    {"direction_1": "green_left", "direction_2": "red"},
    {"direction_1": "green_right", "direction_2": "red"},
    {"direction_1": "red", "direction_2": "green_left"},
    {"direction_1": "red", "direction_2": "green_right"}
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

        if event.operation == "set_mode":
            try:
                mode = json.loads(event.parameters)
                if mode in traffic_lights_allowed_configurations:
                    authorized = True
                    print("[monitor] politika bezopasnosti: dostup razreshen")
            except Exception:
                pass

        if event.operation == "status_report":
            # ot SelfDiagnostics i LightsGPIO razreshaem
            authorized = True
            print("[monitor] prinimaem otchet o sostoyanii")

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
# ControlSystem (bessrochnaya rabota)
# ---------------------------
class ControlSystem(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[ControlSystem] start')
        configs = [
            {"direction_1": "red", "direction_2": "green"},
            {"direction_1": "green_left", "direction_2": "red"},
            {"direction_1": "red", "direction_2": "green_right"}
        ]
        i = 0
        while True:
            mode = configs[i % len(configs)]
            event = Event(source=self.__class__.__name__,
                          destination='LightsGPIO',
                          operation='set_mode',
                          parameters=json.dumps(mode))
            print(f'[ControlSystem] otpravlyaem: {mode}')
            self.monitor_queue.put(event)
            i += 1
            sleep(3)


# ---------------------------
# LightsGPIO (otpravlyaet status)
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
        tekushiy_mode = None
        while True:
            try:
                event: Event = self._own_queue.get_nowait()
                if event.operation == "set_mode":
                    mode = json.loads(event.parameters)
                    tekushiy_mode = mode
                    print(f"[LightsGPIO] noviy rezhim svetofora: {mode}")
                    # otpravlyaem report v monitor
                    report = Event(source='LightsGPIO',
                                   destination='SelfDiagnostics',
                                   operation='status_report',
                                   parameters=json.dumps({"mode": mode}))
                    self.monitor_queue.put(report)
            except Empty:
                sleep(0.5)


# ---------------------------
# SelfDiagnostics (poluchaet statusy)
# ---------------------------
class SelfDiagnostics(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[SelfDiagnostics] start')
        while True:
            try:
                event: Event = self._own_queue.get_nowait()
                if event.operation == "status_report":
                    data = json.loads(event.parameters)
                    print(f"[SelfDiagnostics] poluchen report: {data}")
            except Empty:
                sleep(1)


# ---------------------------
# Startup
# ---------------------------
if __name__ == "__main__":
    monitor_events_queue = Queue()
    monitor = Monitor(monitor_events_queue)
    control_system = ControlSystem(monitor_events_queue)
    lights_gpio = LightsGPIO(monitor_events_queue)
    self_diag = SelfDiagnostics(monitor_events_queue)

    monitor.add_entity_queue(control_system.__class__.__name__, control_system.entity_queue())
    monitor.add_entity_queue(lights_gpio.__class__.__name__, lights_gpio.entity_queue())
    monitor.add_entity_queue(self_diag.__class__.__name__, self_diag.entity_queue())

    monitor.start()
    control_system.start()
    lights_gpio.start()
    self_diag.start()

    try:
        sleep(20)
    except KeyboardInterrupt:
        pass

    monitor.stop()
    control_system.terminate()
    lights_gpio.terminate()
    self_diag.terminate()
    control_system.join()
    lights_gpio.join()
    self_diag.join()
    monitor.join()