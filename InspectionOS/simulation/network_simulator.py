"""Seeded local transport model; never opens a socket or grants hardware access."""
import random
import time


class NetworkSimulator:
    def __init__(self,*,seed=7,online=True,latency=0,loss=0,timeout=.1):
        if latency<0 or not 0<=loss<=1 or timeout<=0: raise ValueError('invalid network parameters')
        self.online,self.latency,self.loss,self.timeout=online,latency,loss,timeout
        self.random=random.Random(seed)
        self.records=[]

    def request(self,operation):
        start=time.perf_counter()
        error=None
        try:
            if not self.online: raise ConnectionError('simulated offline')
            time.sleep(min(self.latency,self.timeout))
            if self.latency>=self.timeout: raise ConnectionError('simulated timeout')
            if self.random.random()<self.loss: raise ConnectionError('simulated packet loss')
            return {'is_mock':True,'transport':'simulated','operation':operation}
        except ConnectionError as exc:
            error=str(exc);raise
        finally:
            self.records.append({'operation':operation,'duration':time.perf_counter()-start,'error':error,
                                 'timeout':error=='simulated timeout'})
