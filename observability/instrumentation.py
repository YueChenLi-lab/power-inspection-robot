"""Optional wrappers; existing voice lab and v2 paths remain unchanged."""
from contextlib import contextmanager
import time


class Recorder:
    def __init__(self):self.records=[]
    @contextmanager
    def span(self,stage,context):
        start=time.perf_counter();error=None
        try:yield
        except Exception as exc:error=type(exc).__name__;raise
        finally:self.records.append({**context.fields(),'stage':stage,'seconds':time.perf_counter()-start,'error':error})
