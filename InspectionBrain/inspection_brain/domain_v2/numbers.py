"""Exact decimal arithmetic and format conversion. No missing decimal inference."""
from decimal import Decimal, InvalidOperation
import re

CHINESE = "零〇一二三四五六七八九十百千万两"
NUMBER = rf"(?:[+-]?\d+(?:\.\d+)?|[负{CHINESE}]+?(?:点[零〇一二三四五六七八九]+)?)"
UNITS = {"℃":"℃","摄氏度":"℃","度":"℃","kV":"kV","千伏":"kV","V":"V","伏":"V",
         "A":"A","安培":"A","安":"A","MPa":"MPa","兆帕":"MPa","%":"%","％":"%"}


def parse_number(value):
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?",value):
        if re.fullmatch(r"[+-]?0\d+",value):
            return None
        return str(Decimal(value))
    negative=value.startswith("负")
    value=value.removeprefix("负")
    integer, _, fractional=value.partition("点")
    digits={c:i for i,c in enumerate("零一二三四五六七八九")};digits.update({"〇":0,"两":2})
    if not integer:
        return None
    if all(c in digits for c in integer):
        result="".join(str(digits[c]) for c in integer)
    else:
        if re.search(r"[一二三四五六七八九两]{2}|[一二三四五六七八九两]零$",integer):return None
        last_weight=10000
        total=section=current=0
        for c in integer:
            if c in digits: current=digits[c]
            elif c in "十百千":
                weight={"十":10,"百":100,"千":1000}[c]
                if weight>=last_weight:return None
                section+=(current or 1)*weight;current=0;last_weight=weight
            elif c=="万":total+=(section+current)*10000;section=current=0;last_weight=10000
            else:return None
        result=str(total+section+current)
    if fractional:
        if not all(c in digits for c in fractional):return None
        result+="."+"".join(str(digits[c]) for c in fractional)
    return ("-" if negative else "")+result


def extract_numeric_slots(text):
    rows=[]
    pattern=re.compile(rf"(?<![A-Za-z0-9.])(?P<number>{NUMBER})\s*(?P<unit>摄氏度|℃|千伏|kV|MPa|兆帕|赵帕|百分比|伏|V|安培|A|安|%|％|度)(?![A-Za-z])",re.IGNORECASE)
    for match in pattern.finditer(text):
        number,unit=match.group("number"),match.group("unit")
        # 6伏化流 is a chemical confusion, not verified 6V equipment voltage.
        chemical = unit in ("伏","V") and text[match.end():match.end()+2] == "化流"
        value=parse_number(number)
        canonical=UNITS.get(unit)  # SI prefix case matters: mPa is not MPa.
        uncertainties=["仅为文本格式解析；需原音频、仪表及采样时间核验，不能形成现场异常结论"]
        prefix=text[max(0,match.start()-40):match.start()]
        labels=list(re.finditer(r"绕组温度|绕阻温度|油温|负载率|气体压力|压力|温差|接头温度|电压|零序电流|电流|温度",prefix))
        subject=labels[-1].group() if labels else None
        phase_matches=list(re.finditer(r"([ABCabc])相",prefix))
        number_matches=list(re.finditer(rf"([{CHINESE}\d]+)号",prefix))
        device_context=number_matches[-1].group(1) if number_matches else None
        if device_context and not device_context.isdecimal():device_context=parse_number(device_context)
        if chemical:canonical=None;value=None;uncertainties.append("疑似化学术语转写，不能当作电压")
        if unit=="赵帕":canonical=None;uncertainties.append("单位未知，候选兆帕需人工确认；数值小数点不推测")
        if canonical is None:uncertainties.append("单位未确认；SI单位大小写不自动合并")
        if value is None:uncertainties.append("前导零或数字格式歧义，禁止猜测小数点")
        if re.fullmatch(r"\d{3,}",number):uncertainties.append("连续多位测量数字需核对小数点与单位；保留原值，不按阈值猜测")
        rows.append({"kind":"measurement","raw_value":number,"raw_unit":unit,"raw_text":match.group(),
                     "normalized_value":value,"normalized_unit":canonical,"source_span":[match.start(),match.end()],
                     "subject":subject,
                     "phase_context":phase_matches[-1].group(1).upper() if phase_matches else None,"device_number_context":device_context,
                     "uncertainty":uncertainties,"verification_status":"ambiguous" if value is None or canonical is None else "format_only_not_verified"})
    for match in re.finditer(rf"百分之(?P<number>[零〇一二三四五六七八九十百两\d]+(?:点[零〇一二三四五六七八九]+)?)",text):
        prefix=text[max(0,match.start()-25):match.start()]
        rows.append({"kind":"measurement","raw_value":match.group("number"),"raw_unit":"百分之","raw_text":match.group(),
                     "normalized_value":parse_number(match.group("number")),"normalized_unit":"%","source_span":[match.start(),match.end()],
                     "subject":"负载率" if "负载率" in prefix else None,
                     "uncertainty":["格式转换不是现场测量核验"],"verification_status":"format_only_not_verified"})
    for match in re.finditer(rf"(?<![{CHINESE}\d])(?P<number>[{CHINESE}\d]+)号",text):
        raw=match.group("number")
        value=raw if raw.isdecimal() else parse_number(raw)
        rows.append({"kind":"device_number","raw_value":raw,"raw_unit":"号","raw_text":match.group(),
                     "normalized_value":value,"normalized_unit":"号","source_span":[match.start(),match.end()],
                     "uncertainty":["文本序号未与真实台账核对；前导零保留"],"verification_status":"identity_unverified"})
    for match in re.finditer(r"(?<![A-Za-z])([ABCabc])\s*(相|箱)",text):
        rows.append({"kind":"phase","raw_value":match.group(1),"raw_unit":match.group(2),"raw_text":match.group(),
                     "normalized_value":match.group(1).upper() if match.group(2)=="相" else None,"normalized_unit":"相" if match.group(2)=="相" else None,
                     "source_span":[match.start(),match.end()],"uncertainty":["相别需核对原音频与接线标识"],
                     "verification_status":"ambiguous" if match.group(2)=="箱" else "identity_unverified"})
    return sorted(rows,key=lambda r:r["source_span"])


def equivalent_value(slot):
    if slot["normalized_value"] is None or slot["normalized_unit"] is None:return None
    if slot["kind"] != "measurement":return (slot["kind"],slot["normalized_unit"],slot["normalized_value"])
    value=Decimal(slot["normalized_value"])
    unit=slot["normalized_unit"]
    if unit=="kV":value*=1000;unit="V"
    return (slot["kind"],slot.get("subject"),slot.get("phase_context"),unit,str(value.normalize()))
