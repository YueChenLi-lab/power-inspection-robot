"""v2/v3 comparison without changing ASR, existing rules, or control dispatch."""
from datetime import datetime
import time
from inspection_brain.domain_v2.service import ElectricalBrainV2
from inspection_brain.service import SHANGHAI
from . import ENGINE_VERSION
from .config import ProviderConfig
from .evidence import build_evidence, provider_input
from .providers import make_provider, RulesFallbackProvider, ProviderError
from .safety import SafetyGuard
from .validator import SemanticValidator


class SemanticEngine:
    def __init__(self, brain=None, provider=None, config=None):
        self.brain = brain or ElectricalBrainV2()
        self.config = config or ProviderConfig()
        self.provider = provider or make_provider(self.config)
        self.validator, self.guard = SemanticValidator(), SafetyGuard()

    def status(self):
        return {"engine_version": ENGINE_VERSION, "provider": self.provider.status(),
                "configuration": self.config.public(), "configuration_sha256": self.config.sha256,
                "hardware_commands_enabled": False, "default_mode": "v2_rules"}

    def analyze(self, text, *, mode="v2_rules", now=None, apply_homophones=False, dialogue_context=None):
        if mode not in ("v2_rules", "v3_llm", "auto_fallback"):
            raise ValueError("语义模式须为v2_rules、v3_llm或auto_fallback")
        start = time.perf_counter()
        now = now or datetime.now(SHANGHAI)
        v2 = self.brain.ask(text, now=now, apply_homophones=apply_homophones)
        evidence = build_evidence(text, v2, now)
        request = provider_input(text, v2, evidence, dialogue_context or [])
        result = {"engine_version": ENGINE_VERSION, "mode": mode, "original_request": text,
                  "v2": v2, "v3": None, "validation": None, "model_candidate": None,
                  "provider": self.provider.status(), "llm_inference_seconds": None,
                  "fallback_used": False, "fallback_success": False, "error": None,
                  "configuration_sha256": self.config.sha256, "authorized": False,
                  "executable": False, "hardware_commands_enabled": False,
                  "lexicon_version": self.brain.normalizer.version, "lexicon_sha256": self.brain.normalizer.sha256,
                  "reference_time": now.astimezone(SHANGHAI).isoformat()}
        if mode == "v2_rules":
            result["status"] = "v2_only"
            result["structured_task_draft"] = self.guard.seal(evidence, self.validator.validate(evidence, evidence), "rules_v2")["structured_task_draft"]
        else:
            try:
                if isinstance(self.provider, RulesFallbackProvider):
                    raise ProviderError("未连接LLM；配置为RulesFallbackProvider")
                generated = self.provider.generate(request)
                candidate = generated.candidate
                validation = self.validator.validate(candidate, evidence)
                result.update(validation=validation, model_candidate=candidate,
                              llm_inference_seconds=generated.inference_seconds,
                              provider={**self.provider.status(), "model": generated.model,
                                        "model_version": generated.model_version, "is_real_llm": generated.is_real_llm})
                safe = self.guard.seal(candidate, validation, generated.origin)
                result.update(v3=safe, status="validated_candidate" if validation["valid"] else "validation_rejected",
                              structured_task_draft=safe["structured_task_draft"])
                if not validation["valid"]:
                    result["error"] = "模型候选校验失败：" + "; ".join(validation["errors"][:12])
            except ProviderError as exc:
                result.update(status="provider_unavailable", error=str(exc), structured_task_draft=None)
            except Exception:
                # Keep the v2 result usable even when a plugin violates its contract.
                result.update(status="provider_error", error="Provider异常，未采用模型候选；可回退v2", structured_task_draft=None)
            if result["status"] != "validated_candidate" and mode == "auto_fallback":
                generated = RulesFallbackProvider().generate(request)
                validation = self.validator.validate(generated.candidate, evidence)
                fallback = self.guard.seal(generated.candidate, validation, "rules_v2")
                result.update(fallback_used=True, fallback_success=validation["valid"], fallback=fallback,
                              structured_task_draft=fallback["structured_task_draft"])
        result["total_seconds"] = time.perf_counter()-start
        return result
