from .validation import MockQueryContract
from InspectionOS.skills.contracts import SkillSpec, INPUT, OUTPUT
from .data import ALARMS, TEMPERATURES, select, output


class ReinspectionSkill(MockQueryContract):
    record_kind='mixed'
    spec = SkillSpec('mock.reinspection','Mock复检建议','组合模拟告警和测温，仅供演示',INPUT,OUTPUT,recovery_safe=True)
    def execute(self,payload):
        rows=select(ALARMS,payload)+select(TEMPERATURES,payload)
        return output(payload,rows,'Mock 建议：人工复核模拟告警与测温记录；无现场诊断、导航或动作')
