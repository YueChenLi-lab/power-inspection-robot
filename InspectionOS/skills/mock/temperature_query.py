from .validation import MockQueryContract
from InspectionOS.skills.contracts import SkillSpec, INPUT, OUTPUT
from .data import TEMPERATURES, select, output


class TemperatureQuerySkill(MockQueryContract):
    record_kind='temperature'
    spec = SkillSpec('mock.temperature_query','Mock测温与历史比较','固定模拟红外记录，非实测',INPUT,OUTPUT,recovery_safe=True)
    def execute(self,payload):
        rows=sorted(select(TEMPERATURES,payload),key=lambda r:r['timestamp'])
        summary=f'Mock 测温记录 {len(rows)} 条'
        if payload.get('compare'):
            from .validation import device_set
            for device in sorted(device_set(payload)):
                local=[r for r in rows if r['device_id']==device]
                summary += (f'；{device} 最近两次差值 {local[-1]["temperature_c"]-local[-2]["temperature_c"]:.1f} 摄氏度，仅模拟比较' if len(local)>=2 else f'；{device} 不足两条，无法比较')
        return output(payload,rows,summary)
