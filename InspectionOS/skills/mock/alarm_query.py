from InspectionOS.skills.contracts import SkillSpec, INPUT, OUTPUT
from .data import ALARMS, select, output


class AlarmQuerySkill:
    spec = SkillSpec('mock.alarm_query','Mock告警查询','读取固定模拟告警，非真实台账',INPUT,OUTPUT)
    def execute(self,payload):
        rows=select(ALARMS,payload)
        return output(payload,rows,f'Mock 告警记录 {len(rows)} 条；不判断现场状态')
