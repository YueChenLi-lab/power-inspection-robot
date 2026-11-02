"""Bounded buffer with explicit backpressure and acknowledgement after write."""
from collections import deque
import threading


class BackpressureError(BufferError):pass


class Buffer:
    def __init__(self,capacity=1000):
        if capacity<1:raise ValueError('positive buffer capacity required')
        self.capacity=capacity;self._items=deque();self.lock=threading.RLock()

    def put(self,item):
        with self.lock:
            if len(self._items)>=self.capacity:raise BackpressureError('evidence buffer full; caller must retry or stop admission')
            self._items.append(item)

    def peek(self,limit):
        with self.lock:return list(self._items)[:limit]

    def acknowledge(self,items):
        with self.lock:
            if list(self._items)[:len(items)]!=items:raise RuntimeError('buffer head changed')
            for _ in items:self._items.popleft()

    def __len__(self):
        with self.lock:return len(self._items)
