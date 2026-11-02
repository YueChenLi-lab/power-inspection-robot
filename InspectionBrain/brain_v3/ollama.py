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
        self.diagnostics = {}
        self.last_candidate = None

    def status(self):
        return {"provider": "ollama", "available": self.config.enabled and bool(self.config.model),
                "is_real_llm": True, "model": self.config.model,
                "model_version": self.config.model_version, "label": "Ollama配置；可达性与效果需实测"}

    def generate(self, request):
        self.last_response, self.timings = None, {}
        self.last_candidate = None
        self.diagnostics = {'json_parse_success':None,'failure_kind':None}
        if not self.status()["available"]:
            self.diagnostics["failure_kind"] = "disabled"
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
                self.diagnostics["failure_kind"] = "incomplete_response"
                raise ProviderError("Ollama响应未完整结束")
            message = body["message"]
            if not isinstance(message, dict):
                raise ProviderError("Ollama message必须为对象")
            if message.get("tool_calls"):
                raise ProviderError("拒绝模型工具调用")
            candidate = strict_json(message["content"])
            self.last_candidate = candidate
            self.diagnostics["json_parse_success"] = True
            if not isinstance(candidate, dict):
                raise ProviderError("模型JSON必须为对象")
            self.timings["json_parse_seconds"] = time.perf_counter() - parse
            return ProviderResult(candidate, body.get("model", self.config.model), self.config.model_version,
                                  time.perf_counter()-start, True, "llm_candidate")
        except HTTPError as exc:
            self.diagnostics["failure_kind"] = "http_error"
            raise ProviderError(f"Ollama HTTP错误:{exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            timeout = isinstance(exc,TimeoutError) or isinstance(getattr(exc,'reason',None),TimeoutError)
            self.diagnostics["failure_kind"] = "timeout" if timeout else "transport_failure"
            raise ProviderError("Ollama请求超时" if timeout else "Ollama连接失败") from None
        except ValueError:
            self.diagnostics.update(json_parse_success=False,failure_kind='json_parse_failure')
            raise ProviderError("Ollama返回非法JSON") from None
        except (KeyError, TypeError):
            self.diagnostics['failure_kind']='response_contract_failure'
            raise ProviderError("Ollama返回非法消息结构") from None
        except ProviderError:
            if self.diagnostics['failure_kind'] is None:
                self.diagnostics['failure_kind']='response_contract_failure'
            raise
        finally:
            self.timings.setdefault("provider_seconds", time.perf_counter()-start)
            if parse is not None:
                self.timings.setdefault("json_parse_seconds", time.perf_counter()-parse)
