from InspectionOS.skills.contracts import SkillSpec, INPUT, OUTPUT
from .data import TEMPERATURES, select, output


class TemperatureQuerySkill:
    spec = SkillSpec('mock.temperature_query','Mock测温与历史比较','固定模拟红外记录，非实测',INPUT,OUTPUT)
    def execute(self,payload):
        rows=sorted(select(TEMPERATURES,payload),key=lambda r:r['timestamp'])
        summary=f'Mock 测温记录 {len(rows)} 条'
        if payload.get('compare'):
            summary += (f'；最近两次差值 {rows[-1]["temperature_c"]-rows[-2]["temperature_c"]:.1f} 摄氏度，仅模拟比较' if len(rows)>=2 else '；不足两条，无法比较')
        return output(payload,rows,summary)
