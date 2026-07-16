from multiprocessing import Queue, Process
from multiprocessing.queues import Empty
from time import sleep
from dataclasses import dataclass


@dataclass
class Event:
    source: str       # otpravitel
    destination: str  # poluchatel
    operation: str    # deistvie
    parameters: str   # parametri



# Security Monitor (FLASK)
@dataclass
class ControlEvent:
    operation: str


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

        authorized = True  # default deny

        if not isinstance(event, Event):
            return False

        
        # Security policies
        # 1) Proverka: razreshen tolko hello
        if event.source == "WorkerA" \
                and event.destination == "WorkerB" \
                and event.operation == "say" \
                and event.parameters == "hello":
            authorized = True
            print("[monitor] politika bezopasnosti: dostup razreshen")

        if authorized is False:
            print("[monitor] sobytie ne razresheno politikami bezopasnosti")

        return authorized

    def _proceed(self, event):
        print(f'[monitor] otpravlyaem zapros {event}')
        try:
            dst_q: Queue = self._entity_queues[event.destination]
            dst_q.put(event)
        except Exception as e:
            print(f"[monitor] oshibka vypolnenie zaprosa {e}")

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
                sleep(0.5)
            except Exception as e:
                print(f"[monitor] oshibka obrabotki {e}, {event}")
            self._check_control_q()
        print(f'[monitor] zavershenie raboti')

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



# Entity A
class WorkerA(Process):

    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[{self.__class__.__name__}] start')

        # Izmeni parametri zdes dlya proverki
        # Primer 1: parameters="hello" --> soobshenie proydyot
        # Primer 2: parameters="privet" --> soobshenie zablokiruyetsya
        event = Event(source=self.__class__.__name__,
                      destination='WorkerB',
                      operation='say',
                      parameters='privet')

        print(f'[{self.__class__.__name__}] otpravlyaem testoviy zapros: {event.parameters}')
        self.monitor_queue.put(event)
        print(f'[{self.__class__.__name__}] zavershenie raboti')



# Entity B
class WorkerB(Process):

    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[{self.__class__.__name__}] start')
        attempts = 5
        while attempts > 0:
            try:
                event: Event = self._own_queue.get_nowait()
                if event.operation == "say":
                    print(f"[{self.__class__.__name__}] {event.source} skazal: {event.parameters}")
                    break
            except Empty:
                sleep(0.2)
                attempts -= 1
        print(f'[{self.__class__.__name__}] zavershenie raboti')



# System startup
if __name__ == "__main__":
    monitor_events_queue = Queue()
    monitor = Monitor(monitor_events_queue)
    worker_a = WorkerA(monitor_events_queue)
    worker_b = WorkerB(monitor_events_queue)

    monitor.add_entity_queue(worker_a.__class__.__name__, worker_a.entity_queue())
    monitor.add_entity_queue(worker_b.__class__.__name__, worker_b.entity_queue())

    monitor.start()
    worker_a.start()
    worker_b.start()

    sleep(2)

    monitor.stop()
    worker_a.join()
    worker_b.join()
    monitor.join()