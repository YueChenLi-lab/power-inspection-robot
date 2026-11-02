"""Editable lexicon with exact aliases and opt-in read-only corrections."""
from dataclasses import dataclass
import json
from pathlib import Path
import re

from .safety import action_markers


@dataclass(frozen=True)
class Term:
    id: str
    standard_name: str
    category: str
    equipment_category: str | None
    aliases: tuple[str, ...]
    homophones: tuple[str, ...]
    parent_id: str | None = None
    device_ids: tuple[str, ...] = ()


class Lexicon:
    def __init__(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("terms"), list):
            raise ValueError("术语词库格式无效")
        self.terms = []
        ids, surface_owner = set(), {}
        for row in data["terms"]:
            term = Term(row["id"], row["standard_name"], row["category"],
                        row.get("equipment_category"), tuple(row.get("aliases", [])),
                        tuple(row.get("homophones", [])), row.get("parent_id"),
                        tuple(row.get("device_ids", [])))
            if not term.id or term.id in ids or not term.standard_name:
                raise ValueError("术语ID/标准名无效或重复")
            if term.category not in {"equipment", "metric", "defect", "business"}:
                raise ValueError("未知术语类别")
            ids.add(term.id)
            for surface in (term.standard_name, *term.aliases):
                if not isinstance(surface, str) or not surface.strip():
                    raise ValueError("空术语/别名")
                key = surface.casefold()
                if key in surface_owner and surface_owner[key] != term.id:
                    raise ValueError("不同术语不能共享别名: " + surface)
                surface_owner[key] = term.id
            if any(not isinstance(word, str) or not word.strip() for word in term.homophones):
                raise ValueError("无效同音候选")
            self.terms.append(term)
        self.by_id = {t.id: t for t in self.terms}
        if any(t.parent_id and t.parent_id not in ids for t in self.terms):
            raise ValueError("术语父类别不存在")
        for term in self.terms:
            seen = {term.id}
            while term.parent_id:
                if term.parent_id in seen:
                    raise ValueError("术语父类别形成环")
                seen.add(term.parent_id)
                term = self.by_id[term.parent_id]

    @staticmethod
    def occurrences(text, surface):
        # ASCII aliases such as CT/PT must be whole tokens, never part of ACT.
        if surface.isascii() and surface.isalnum():
            pattern = r"(?<![A-Za-z0-9_])" + re.escape(surface) + r"(?![A-Za-z0-9_])"
        else:
            pattern = re.escape(surface)
        return re.finditer(pattern, text, re.IGNORECASE)

    def matches(self, text):
        candidates = []
        uncertain_windows = [(m.start(), m.end()) for term in self.terms
                             for word in term.homophones for m in self.occurrences(text, word)]
        for term in self.terms:
            for surface in (term.standard_name, *term.aliases):
                for match in self.occurrences(text, surface):
                    # A known whole-term transcription candidate must not be
                    # misread as an independent metric substring (电流互赶器
                    # is unresolved equipment, not a confirmed 电流 mention).
                    if not any(a <= match.start() and b >= match.end() and
                               b-a > match.end()-match.start() for a, b in uncertain_windows):
                        candidates.append((match.start(), match.end(), term, match.group(0)))
        chosen = []
        for item in sorted(candidates, key=lambda x: (-(x[1]-x[0]), x[0], x[2].id)):
            if not any(item[0] < prev[1] and item[1] > prev[0] for prev in chosen):
                chosen.append(item)
        return sorted(chosen, key=lambda x: x[0])


class TextNormalizer:
    def __init__(self, lexicon):
        self.lexicon = lexicon

    def normalize(self, text, *, apply_homophones=False):
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("请输入1～2000字的文本")
        protected = bool(action_markers(text))
        readonly_question = bool(re.search(r"什么|区别|哪些|多少|有没有|是否|查询|资料|解释|介绍", text))
        # Never fix numbers, measurements or identifiers; only whitelist words.
        matches = self.lexicon.matches(text)
        replacements = []
        candidates = []
        for start, end, term, surface in matches:
            if not protected and surface != term.standard_name:
                replacements.append((start, end, term.standard_name, "exact_alias", term.id))
        homophones = {}
        for term in self.lexicon.terms:
            for word in term.homophones:
                homophones.setdefault(word.casefold(), []).append(term)
        for word, terms in homophones.items():
            for match in self.lexicon.occurrences(text, word):
                if any(match.start() < end and match.end() > start for start, end, _, _ in matches):
                    continue
                unique = len(terms) == 1
                allowed = apply_homophones and readonly_question and not protected and unique
                candidates.append({"surface": match.group(0), "span": [match.start(), match.end()],
                                   "standard_names": [t.standard_name for t in terms],
                                   "term_ids": [t.id for t in terms], "applied": bool(allowed),
                                   "reason": "readonly_whitelist" if allowed else
                                   "protected_operation" if protected else "ambiguous" if not unique else "suggestion_only"})
                if allowed:
                    replacements.append((match.start(), match.end(), terms[0].standard_name,
                                         "readonly_homophone", terms[0].id))
        # Ambiguous/overlapping correction windows stay suggestions.
        accepted = []
        for item in sorted(replacements, key=lambda x: x[0]):
            if not any(item[0] < prev[1] and item[1] > prev[0] for prev in accepted):
                accepted.append(item)
        normalized = text
        for start, end, replacement, _, _ in reversed(accepted):
            normalized = normalized[:start] + replacement + normalized[end:]
        changes = [{"original": text[a:b], "replacement": value, "span": [a, b],
                    "kind": kind, "term_id": term_id} for a, b, value, kind, term_id in accepted]
        for candidate in candidates:
            candidate["applied"] = any(change["kind"] == "readonly_homophone" and
                                       change["span"] == candidate["span"] for change in changes)
        recognized = [{"term_id": term.id, "standard_name": term.standard_name,
                       "category": term.category, "equipment_category": term.equipment_category,
                       "span": [start, end], "surface": surface}
                      for start, end, term, surface in self.lexicon.matches(normalized)]
        return {"raw_text": text, "normalized_text": normalized, "changes": changes,
                "homophone_candidates": candidates, "recognized_terms": recognized,
                "operation_text_protected": protected, "authorization_granted": False}
