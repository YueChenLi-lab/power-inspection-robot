"""Text classification only. A proposal never carries execution authority."""
import re

# Deliberately conservative: even negated/quoted requests are never routed
# through corrected text. Knowledge questions containing these get abstained
# or handled by the original dispatcher in the offline router.
ACTION_PATTERN = re.compile(
    r"前进|前行|后退|后移|倒车|左转|右转|停车|急停|停止|移动|挪动|转动|旋转|转向|行驶|行走|"
    r"走到|去到|开到|驶向|导航|点动|使能|接管|跟随|跟着|追踪|跟踪|"
    r"抬头|低头|变焦|对焦|放大|缩小|拍照|抓拍|录像|"
    r"合闸|分闸|拉闸|送电|断电|打开|开启|关闭|关停|启动|重启|复位|加速|减速|"
    r"执行|开始巡检|运行巡检|"
    r"(?:往|向)(?:前|后|左|右)|(?:前往|返回)|"
    r"(?:去|到).{0,20}(?:变压器|主变|开关柜|巡检点)|开关.*(?:合上|断开)|"
    r"(?:move|drive|turn|stop|arm|disarm|shutdown|reboot)", re.IGNORECASE)


def action_markers(text):
    return list(dict.fromkeys(match.group(0) for match in ACTION_PATTERN.finditer(text)))


def operation_proposal(text, markers=None):
    return {
        "requested_text": text,
        "markers": action_markers(text) if markers is None else markers,
        "status": "proposal_only",
        "requires_human_authorization": True,
        "authorized": False,
        "executable": False,
        "chassis_commands_enabled": False,
        "hardware_commands_enabled": False,
    }
