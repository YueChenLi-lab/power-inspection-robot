"""Killable subprocess execution. Trusted local skills only, not a code sandbox."""
import multiprocessing
import time


class ExecutionError(RuntimeError): pass
class ExecutionTimeout(ExecutionError): pass
class ExecutionCancelled(ExecutionError): pass


def _call(pipe, skill, payload):
    try:
        result=skill.execute(payload)
        pipe.send(('ok',result))
    except Exception as exc:
        pipe.send(('error',type(exc).__name__+': '+str(exc)))
    finally:
        pipe.close()


class Executor:
    def __init__(self,registry): self.registry=registry

    def execute(self,mission,cancelled=lambda:False):
        skill=self.registry.get(mission['skill_id'])
        self.registry.validate_input(mission['skill_id'],mission['payload'])
        ctx=multiprocessing.get_context('fork')
        parent,child=ctx.Pipe(duplex=False)
        process=ctx.Process(target=_call,args=(child,skill,mission['payload']),daemon=True)
        started=time.monotonic()
        process.start();child.close()
        try:
            while not parent.poll(.01):
                if cancelled(): raise ExecutionCancelled('mission cancelled')
                if time.monotonic()-started>=skill.spec.timeout: raise ExecutionTimeout('skill deadline exceeded')
                if not process.is_alive(): raise ExecutionError('skill process exited without result')
            try: status,result=parent.recv()
            except EOFError: raise ExecutionError('skill process pipe closed') from None
            if status!='ok': raise ExecutionError(result)
            if cancelled(): raise ExecutionCancelled('mission cancelled')
            self.registry.validate_output(mission['skill_id'],result)
            return result
        finally:
            if process.is_alive(): process.terminate()
            process.join(timeout=1)
            if process.is_alive(): process.kill();process.join()
            parent.close();process.close()
