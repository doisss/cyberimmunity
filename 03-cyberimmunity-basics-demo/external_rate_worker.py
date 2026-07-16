import logging
import sys
from multiprocessing import Queue, Process
from multiprocessing.queues import Empty
from time import sleep
from dataclasses import dataclass
import requests


# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),              # вывод в консоль
        logging.FileHandler("system.log", encoding="utf-8")  # вывод в файл
    ]
)


print = logging.info

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
# Security Monitor (FLASK)
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
        print(f'[monitor] obrabativaem sobytie {event}')
        authorized = False
        if not isinstance(event, Event):
            return False

        # ---------------------------
        # Security policies
        # ---------------------------
        if event.source == "WorkerA" and event.destination == "WorkerB" and event.operation == "say":
            authorized = True
        if event.source == "WorkerC" and event.destination == "WorkerA" and event.operation == "say":
            authorized = True

        if authorized:
            print("[monitor] politika bezopasnosti: dostup razreshen")
        else:
            print("[monitor] sobytie ne razresheno politikami bezopasnosti")

        return authorized

    def _proceed(self, event):
        try:
            dst_q: Queue = self._entity_queues[event.destination]
            dst_q.put(event)
            print(f'[monitor] otpravlyaem zapros {event}')
        except Exception as e:
            print(f"[monitor] oshibka vypolnenie zaprosa {e}")

    def run(self):
        print(f'[monitor] start')
        while not self._force_quit:
            event = None
            try:
                event = self._events_q.get_nowait()
                if self._check_policies(event):
                    self._proceed(event)
            except Empty:
                sleep(0.5)
            except Exception as e:
                print(f"[monitor] oshibka obrabotki {e}, {event}")
            self._check_control_q()
        print(f'[monitor] zavershenie raboti')

    def stop(self):
        self._control_q.put(ControlEvent(operation='stop'))

    def _check_control_q(self):
        try:
            request: ControlEvent = self._control_q.get_nowait()
            if isinstance(request, ControlEvent) and request.operation == 'stop':
                self._force_quit = True
        except Empty:
            pass

# ---------------------------
# Worker A
# ---------------------------
class WorkerA(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()
        self.threshold = 100

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[WorkerA] start')
        event = Event(source="WorkerA", destination="WorkerB", operation="say", parameters="hello")
        print(f'[WorkerA] otpravlyaem: {event.parameters}')
        self.monitor_queue.put(event)

        attempts = 10
        while attempts > 0:
            try:
                event_in: Event = self._own_queue.get_nowait()
                if event_in.source == "WorkerC":
                    rate = float(event_in.parameters)
                    print(f'[WorkerA] poluchil kurs ot WorkerC: {rate}')
                    if rate > self.threshold:
                        alert = Event(source="WorkerA", destination="WorkerB", operation="say",
                                      parameters=f"alert: kurs={rate}!")
                        print(f'[WorkerA] otsluzhivaem alert WorkerB: {alert.parameters}')
                        self.monitor_queue.put(alert)
                    break
            except Empty:
                sleep(0.5)
                attempts -= 1

        attempts = 5
        while attempts > 0:
            try:
                reply: Event = self._own_queue.get_nowait()
                if reply.source == "WorkerB":
                    print(f'[WorkerA] poluchil otvet ot WorkerB: {reply.parameters}')
                    break
            except Empty:
                sleep(0.5)
                attempts -= 1

        print(f'[WorkerA] zavershenie raboti')

# ---------------------------
# Worker B
# ---------------------------
class WorkerB(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[WorkerB] start')
        attempts = 10
        while attempts > 0:
            try:
                event: Event = self._own_queue.get_nowait()
                print(f'[WorkerB] poluchil soobshenie: {event.source} -> {event.parameters}')
                if event.source == "WorkerA":
                    reply = Event(source="WorkerB", destination="WorkerA", operation="say", parameters="done")
                    print(f'[WorkerB] otpravlyaem otvet: {reply.parameters}')
                    self.monitor_queue.put(reply)
                break
            except Empty:
                sleep(0.5)
                attempts -= 1
        print(f'[WorkerB] zavershenie raboti')

# ---------------------------
# Worker C
# ---------------------------
class WorkerC(Process):
    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[WorkerC] start')
        for _ in range(2):
            try:
                r = requests.get("https://www.cbr-xml-daily.ru/latest.js")
                data = r.json()
                usd_rate = data["rates"]["USD"]
                event = Event(source="WorkerC", destination="WorkerA", operation="say", parameters=str(usd_rate))
                print(f'[WorkerC] otpravlyaem kurs USD={usd_rate} WorkerA')
                self.monitor_queue.put(event)
            except Exception as e:
                print(f'[WorkerC] oshibka zaprosa: {e}')
            sleep(5)
        print(f'[WorkerC] zavershenie raboti')

# ---------------------------
# System startup
# ---------------------------
if __name__ == "__main__":
    monitor_events_queue = Queue()
    monitor = Monitor(monitor_events_queue)
    worker_a = WorkerA(monitor_events_queue)
    worker_b = WorkerB(monitor_events_queue)
    worker_c = WorkerC(monitor_events_queue)

    monitor.add_entity_queue(worker_a.__class__.__name__, worker_a.entity_queue())
    monitor.add_entity_queue(worker_b.__class__.__name__, worker_b.entity_queue())
    monitor.add_entity_queue(worker_c.__class__.__name__, worker_c.entity_queue())

    monitor.start()
    worker_a.start()
    worker_b.start()
    worker_c.start()

    sleep(15)

    monitor.stop()
    worker_a.join()
    worker_b.join()
    worker_c.join()
    monitor.join()
