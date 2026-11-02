import hashlib
import json
from pathlib import Path
import re
from .scopes import action_scopes


def candidate_id(kind, span, replacement):
    return hashlib.sha256(f"{kind}:{span}:{replacement}".encode()).hexdigest()[:16]


class DomainNormalizer:
    def __init__(self, lexicon, path):
        self.path = Path(path).resolve()
        self.lexicon = lexicon
        data = json.loads(Path(path).read_text())
        self.version = data["lexicon_version"]
        self.sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        self.metadata = {row["id"]: row for row in data["terms"]}
        for row in data["terms"]:
            for confusion, override in row.get("confusion_overrides", {}).items():
                if confusion not in row["confusion_candidates"] or override.get("replacement", row["standard_name"]) not in [row["standard_name"], *row["aliases"]]:
                    raise ValueError("混淆候选的展示替换必须属于同一术语的标准名或别名")

    def normalize(self, text, *, apply_homophones=False):
        if not isinstance(text, str) or not text.strip() or len(text)>2000:
            raise ValueError("请输入1～2000字的文本")
        scopes = action_scopes(text)
        protected = any(row["polarity"] in ("proposal", "conditional") for row in scopes)
        exact = self.lexicon.matches(text)
        changes, candidates, replacements = [], [], []
        for start, end, term, surface in exact:
            if not protected and surface != term.standard_name:
                replacements.append((start, end, term.standard_name, "exact_alias", term.id))
        windows = []
        for term in self.lexicon.terms:
            metadata = self.metadata[term.id]
            for confusion in metadata["confusion_candidates"]:
                for match in self.lexicon.occurrences(text, confusion):
                    if any(match.start()<b and match.end()>a for a,b,_,_ in exact):
                        continue
                    windows.append((match.start(), match.end(), term, metadata))
        selected = []
        for window in sorted(windows, key=lambda w: (-(w[1]-w[0]), w[0])):
            if not any(window[0]<w[1] and window[1]>w[0] for w in selected):
                selected.append(window)
        for start,end,term,metadata in selected:
            surface = text[start:end]
            override = metadata.get("confusion_overrides", {}).get(surface, {})
            replacement = override.get("replacement", term.standard_name)
            context = text[max(0,start-80):start]+text[end:end+80]
            hits = [word for word in override.get("context_keywords", metadata["context_keywords"]) if word in context]
            exclusions = [word for word in override.get("excluded_context_keywords", []) if word in context]
            permitted = (not protected and bool(hits) and not exclusions and metadata["correction_policy"] != "candidate_only")
            applied = bool(apply_homophones and permitted)
            reason = "protected_operation" if protected else "high_risk_candidate_only" if metadata["risk_level"] == "high" else "context_conflict" if exclusions else "context_missing" if not hits else "context_whitelist" if applied else "switch_disabled"
            span = [start,end]
            candidates.append({"id":candidate_id("term",span,replacement), "surface":surface,
                               "span":span,"source_span":span,"standard_names":[term.standard_name],"replacement":replacement,
                               "term_ids":[term.id],"applied":applied,"reason":reason,"context_hits":hits,"context_exclusions":exclusions,
                               "risk_level":metadata["risk_level"],"confidence_level":"rule_context" if hits else "uncertain",
                               "display_confirmation_allowed":not protected and not exclusions and (bool(hits) or not override.get("require_context_for_confirmation", False)),
                               "authorization_granted":False})
            if applied:
                replacements.append((start,end,replacement,"context_homophone",term.id))
        accepted = []
        for row in sorted(replacements):
            if not any(row[0]<old[1] and row[1]>old[0] for old in accepted):
                accepted.append(row)
        normalized=text
        for a,b,replacement,kind,term_id in reversed(accepted):
            normalized=normalized[:a]+replacement+normalized[b:]
        for a,b,replacement,kind,term_id in accepted:
            changes.append({"original":text[a:b],"replacement":replacement,"span":[a,b],"source_span":[a,b],
                            "kind":kind,"term_id":term_id,"reason":"显式别名" if kind=="exact_alias" else "只读上下文白名单且纠错开关启用",
                            "confidence_level":"deterministic_alias" if kind=="exact_alias" else "rule_context","stage":"raw_transcript"})
        return {"raw_text":text,"normalized_text":normalized,"raw_transcript":text,"term_normalized_text":normalized,
                "changes":changes,"homophone_candidates":candidates,"correction_candidates":candidates,
                "recognized_terms":[{"term_id":term.id,"standard_name":term.standard_name,"category":term.category,
                                      "equipment_category":term.equipment_category,"span":[a,b],"surface":surface}
                                     for a,b,term,surface in self.lexicon.matches(normalized)],
                "operation_text_protected":protected,"authorization_granted":False,"lexicon_version":self.version,"lexicon_sha256":self.sha256}
