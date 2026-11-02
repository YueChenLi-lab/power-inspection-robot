"""Composition root. Runtime contains no robot driver or model dependency."""
from .storage.database import Database
from .core.mission_manager import MissionManager
from .core.skill_registry import SkillRegistry
from .core.safety_supervisor import SafetySupervisor
from .core.scheduler import Scheduler
from .runtime.worker import Worker
from .runtime.recovery import Recovery
from .simulation.network_simulator import NetworkSimulator
from .skills.mock.alarm_query import AlarmQuerySkill
from .skills.mock.temperature_query import TemperatureQuerySkill
from .skills.mock.reinspection import ReinspectionSkill


class Application:
    def __init__(self,path,*,network=None,operator_token=None,registry=None,**database_options):
        self.db=Database(path,**database_options)
        self.registry=registry or SkillRegistry()
        if registry is None:
            for skill in (AlarmQuerySkill(),TemperatureQuerySkill(),ReinspectionSkill()):self.registry.register(skill)
        self.network=network or NetworkSimulator()
        self.manager=MissionManager(self.db,self.registry,SafetySupervisor(operator_token))
        self.scheduler=Scheduler(self.manager,self.network)
        self.worker=Worker(self.manager,self.scheduler)
        self.recovery=Recovery(self.manager)

    def close(self):self.db.close()
    def __enter__(self):return self
    def __exit__(self,*a):self.close()
