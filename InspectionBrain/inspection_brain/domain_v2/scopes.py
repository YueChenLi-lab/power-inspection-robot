"""Conservative local negation/condition scope. Never generates authorization."""
import re
from ..safety import ACTION_PATTERN


def action_scopes(text):
    matches = list(ACTION_PATTERN.finditer(text))
    matches += list(re.finditer(r"倒闸操作|道闸操作|操作", text))
    rows = []
    for match in sorted(matches, key=lambda m: m.start()):
        boundary = max([m.end() for m in re.finditer(r"[，。；,;！!?？]|但是|但|同时|最终", text[:match.start()])] or [0])
        left = text[boundary:match.start()]
        right = text[match.end():match.end()+18]
        clause = text[boundary:match.end()+18]
        if re.search(r"不要|不能|不得|不允许|禁止|不执行|不移动|不操作|不启动|未经授权|不(?:再)?$", left[-36:]):
            polarity, reason = "prohibited", "局部否定/未经授权约束，不能解释为肯定命令"
        elif re.search(r"如果|若|只有|除非|取得授权后|经授权后", left):
            polarity, reason = "conditional", "条件尚未满足；无执行授权"
        elif re.search(r"原理|含义|是什么|怎么理解", clause) or re.match(r"状态|位置|记录|次数|原理|规程", right) or (match.group(0) == "合闸" and left.endswith("分")):
            polarity, reason = "mention", "知识/状态提及，不是执行指令"
        else:
            polarity, reason = "proposal", "可能的操作请求，仅生成不可执行提案"
        rows.append({"action": match.group(0), "source_span": [match.start(), match.end()],
                     "scope_text": clause, "polarity": polarity, "reason": reason,
                     "authorized": False, "executable": False})
    return rows
