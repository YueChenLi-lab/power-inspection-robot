"""Ollama native structured output. Reuses the original semantic safety contract.

last_response is bounded, local diagnostic data (possibly private input); never
includes headers. It is not automatically copied to the voice lab or logs.
"""
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler
from .providers import NoRedirect, ProviderError, ProviderResult, strict_json
from .schema import SCHEMA


class OllamaProvider:
    def __init__(self, config):
        self.config = config
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.last_response = None
        self.timings = {}

    def status(self):
        return {"provider": "ollama", "available": self.config.enabled and bool(self.config.model),
                "is_real_llm": True, "model": self.config.model,
                "model_version": self.config.model_version, "label": "Ollama配置；可达性与效果需实测"}

    def generate(self, request):
        self.last_response, self.timings = None, {}
        if not self.status()["available"]:
            raise ProviderError("Ollama未启用；没有发出请求")
        payload = {"model": self.config.model, "stream": False, "format": SCHEMA,
                   "options": {"temperature": self.config.temperature, "num_predict": self.config.max_output_tokens},
                   "messages": [{"role": "system", "content": "只输出给定Schema的JSON。保留evidence的原文、设备、时间、否定和约束；reasoning_source为llm_candidate。不得添加动作、现场结论或执行权限。"},
                                {"role": "user", "content": json.dumps(request, ensure_ascii=False)}]}
        req = Request(self.config.endpoint(), json.dumps(payload, ensure_ascii=False).encode(),
                      {"Content-Type": "application/json"}, method="POST")
        if self.config.api_key:
            req.add_header("Authorization", "Bearer " + self.config.api_key)
        start = time.perf_counter()
        parse = None
        try:
            with self.opener.open(req, timeout=self.config.timeout_seconds) as response:
                raw = response.read(self.config.max_response_bytes + 1)
            self.timings["provider_seconds"] = time.perf_counter() - start
            if len(raw) > self.config.max_response_bytes:
                raise ProviderError("Ollama响应超过长度限制")
            self.last_response = raw.decode("utf-8")
            parse = time.perf_counter()
            body = strict_json(raw)
            if not isinstance(body, dict):
                raise ProviderError("Ollama消息封装必须为JSON对象")
            if body.get("done") is not True or body.get("done_reason", "stop") != "stop":
                raise ProviderError("Ollama响应未完整结束")
            message = body["message"]
            if not isinstance(message, dict):
                raise ProviderError("Ollama message必须为对象")
            if message.get("tool_calls"):
                raise ProviderError("拒绝模型工具调用")
            candidate = strict_json(message["content"])
            if not isinstance(candidate, dict):
                raise ProviderError("模型JSON必须为对象")
            self.timings["json_parse_seconds"] = time.perf_counter() - parse
            return ProviderResult(candidate, body.get("model", self.config.model), self.config.model_version,
                                  time.perf_counter()-start, True, "llm_candidate")
        except HTTPError as exc:
            raise ProviderError(f"Ollama HTTP错误:{exc.code}") from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError("Ollama连接失败或超时") from None
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ProviderError("Ollama返回非法JSON或消息结构") from None
        finally:
            self.timings.setdefault("provider_seconds", time.perf_counter()-start)
            if parse is not None:
                self.timings.setdefault("json_parse_seconds", time.perf_counter()-parse)
