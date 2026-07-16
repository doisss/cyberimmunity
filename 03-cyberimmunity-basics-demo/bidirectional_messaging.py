from multiprocessing import Queue, Process
from multiprocessing.queues import Empty
from time import sleep
from dataclasses import dataclass

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
        print(f'[monitor] obrabativaem sobytie {event}')

        authorized = False  # default deny

        if not isinstance(event, Event):
            return False

        # ---------------------------
        # Security policies
        # ---------------------------

        # Разрешаем только say с hello или done
        if event.operation == "say" and event.parameters in ["hello", "done"]:
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
                sleep(0.2)
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


# ---------------------------
# Worker A
# ---------------------------
class WorkerA(Process):

    def __init__(self, monitor_queue: Queue):
        super().__init__()
        self.monitor_queue = monitor_queue
        self._own_queue = Queue()

    def entity_queue(self):
        return self._own_queue

    def run(self):
        print(f'[{self.__class__.__name__}] start')

        # Шлем первое сообщение WorkerB
        event = Event(source=self.__class__.__name__,
                      destination='WorkerB',
                      operation='say',
                      parameters='hello')

        print(f'[{self.__class__.__name__}] otpravlyaem: {event.parameters}')
        self.monitor_queue.put(event)

        # Ждем ответ
        attempts = 5
        while attempts > 0:
            try:
                reply: Event = self._own_queue.get_nowait()
                if reply.operation == "say" and reply.parameters == "done":
                    print(f"[{self.__class__.__name__}] poluchil otvet: {reply.parameters}")
                    break
            except Empty:
                sleep(0.2)
                attempts -= 1

        print(f'[{self.__class__.__name__}] zavershenie raboti')


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
        print(f'[{self.__class__.__name__}] start')
        attempts = 5
        while attempts > 0:
            try:
                event: Event = self._own_queue.get_nowait()
                if event.operation == "say" and event.parameters == "hello":
                    print(f"[{self.__class__.__name__}] {event.source} skazal: {event.parameters}")
                    # Отвечаем обратно
                    reply = Event(source=self.__class__.__name__,
                                  destination=event.source,
                                  operation="say",
                                  parameters="done")
                    print(f"[{self.__class__.__name__}] otpravlyaem otvet: done")
                    self.monitor_queue.put(reply)
                    break
            except Empty:
                sleep(0.2)
                attempts -= 1
        print(f'[{self.__class__.__name__}] zavershenie raboti')


# ---------------------------
# System startup
# ---------------------------
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

    sleep(3)

    monitor.stop()
    worker_a.join()
    worker_b.join()
    monitor.join()
