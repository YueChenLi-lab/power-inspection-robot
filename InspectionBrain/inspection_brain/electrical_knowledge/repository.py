from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class EvidenceChunk:
    id: str
    document_id: str
    title: str
    revision: str
    source: dict
    text: str
    content_sha256: str
    required_terms: tuple
    intents: tuple
    keywords: tuple

    def citation(self):
        return {"chunk_id": self.id, "document_id": self.document_id, "title": self.title,
                "revision": self.revision, "source": self.source,
                "content_sha256": self.content_sha256, "excerpt": self.text}


class Retriever(Protocol):
    def search(self, analysis: dict, limit: int = 3) -> list[EvidenceChunk]: ...


class LLMProvider(Protocol):
    """Replaceable answer interface. Phase 1 only accepts exact evidence text.

    No credentials, tools or device handles are passed to a provider. A future
    generative provider needs a separate grounded-claim validation contract.
    """
    def compose(self, question: str, evidence: list[EvidenceChunk]) -> dict: ...


class DocumentRepository:
    def __init__(self, folder, lexicon):
        self.documents = {}
        self.chunks = []
        self.term_index = {}
        self.lexicon = lexicon
        for path in sorted(Path(folder).glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            self._validate(data)
            if data["id"] in self.documents:
                raise ValueError("重复文档ID")
            self.documents[data["id"]] = data
            chunk_ids = set()
            for chunk in data["chunks"]:
                if chunk["id"] in chunk_ids:
                    raise ValueError("重复片段ID")
                chunk_ids.add(chunk["id"])
                item = EvidenceChunk(data["id"]+"#"+chunk["id"], data["id"], data["title"],
                                     data["revision"], dict(data["source"]), chunk["text"],
                                     hashlib.sha256(chunk["text"].encode()).hexdigest(),
                                     tuple(chunk["required_terms"]), tuple(chunk["intents"]),
                                     tuple(chunk["keywords"]))
                self.chunks.append(item)
                for term in item.required_terms:
                    self.term_index.setdefault(term, []).append(item.id)

    def _validate(self, data):
        if data.get("schema_version") != 1 or not all(isinstance(data.get(k), str) and data[k].strip()
                                                      for k in ("id", "title", "revision")):
            raise ValueError("文档ID、标题和版本必填")
        source = data.get("source", {})
        if not all(isinstance(source.get(k), str) and source[k].strip() for k in ("kind", "label", "uri")) or type(source.get("is_example")) is not bool:
            raise ValueError("文档来源和示例标记必填")
        if source["uri"].startswith("example://") and not source["is_example"]:
            raise ValueError("示例来源不能伪装成真实来源")
        if not isinstance(data.get("chunks"), list) or not data["chunks"]:
            raise ValueError("文档需要可检索片段")
        for chunk in data["chunks"]:
            if not all(isinstance(chunk.get(k), str) and chunk[k].strip() for k in ("id", "text")):
                raise ValueError("片段ID和正文必填")
            for field in ("required_terms", "intents", "keywords"):
                if not isinstance(chunk.get(field), list) or not chunk[field] or not all(isinstance(v, str) and v for v in chunk[field]):
                    raise ValueError("片段索引字段不能为空: " + field)
            if any(term not in self.lexicon.by_id for term in chunk["required_terms"]):
                raise ValueError("文档引用未知术语")

    def search(self, analysis, limit=3):
        query = analysis["normalization"]["normalized_text"]
        terms = {t["term_id"] for t in analysis["normalization"]["recognized_terms"]}
        expanded = set(terms)
        for term_id in terms:
            term = self.lexicon.by_id[term_id]
            visited = set()
            while term.parent_id and term.parent_id not in visited:
                visited.add(term.parent_id)
                expanded.add(term.parent_id)
                term = self.lexicon.by_id[term.parent_id]
        ranked = []
        for item in self.chunks:
            if analysis["intent"] not in item.intents or not set(item.required_terms) <= expanded:
                continue
            keyword_hits = sum(word in query for word in item.keywords)
            if not keyword_hits:
                continue
            ranked.append((len(item.required_terms)*10+keyword_hits, item))
        return [item for _, item in sorted(ranked, key=lambda row: (-row[0], row[1].id))[:limit]]

    def metadata(self):
        return [{"id": d["id"], "title": d["title"], "revision": d["revision"],
                 "source": d["source"], "device_terms": d.get("device_terms", [])}
                for d in self.documents.values()]


class ExtractiveProvider:
    def compose(self, question, evidence):
        return {"passages": [{"chunk_id": chunk.id, "text": chunk.text} for chunk in evidence]}


def undetermined(message, missing=None):
    return {"status": "undetermined", "answer": message, "citations": [],
            "missing_evidence": missing or [], "is_example": False,
            "site_conclusion": None}


class KnowledgeQA:
    def __init__(self, retriever: Retriever, provider: LLMProvider | None = None):
        self.retriever = retriever
        self.provider = provider or ExtractiveProvider()

    def answer(self, analysis):
        evidence = self.retriever.search(analysis)
        if not evidence:
            return undetermined("没有匹配的有效知识证据，不能据此下结论。", ["适用知识文档"])
        result = self.provider.compose(analysis["normalization"]["raw_text"], evidence)
        allowed = {chunk.id: chunk for chunk in evidence}
        passages = result.get("passages") if isinstance(result, dict) else None
        # Fail closed: citation IDs alone do not prove generated prose grounded.
        if not isinstance(passages, list) or not passages or any(
            not isinstance(p, dict) or p.get("chunk_id") not in allowed or
            p.get("text") != allowed[p["chunk_id"]].text for p in passages
        ):
            return undetermined("回答未通过来源一致性校验，已拒绝输出专业结论。", ["可核对的原文证据"])
        used = list(dict.fromkeys(p["chunk_id"] for p in passages))
        return {"status": "knowledge_answer", "answer": "\n\n".join(p["text"] for p in passages),
                "citations": [allowed[cid].citation() for cid in used],
                "is_example": any(allowed[cid].source["is_example"] for cid in used),
                "missing_evidence": [], "site_conclusion": None,
                "notice": "当前来源为离线示例，不能替代行业规范、设备说明书或现场规程。"}
