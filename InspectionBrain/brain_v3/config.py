"""Text-only provider configuration. Secrets never enter diagnostics or records."""
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "rules"
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434/v1"
    model: str = ""
    model_version: str = "unspecified"
    api_key: str = field(default="", repr=False, compare=False)
    temperature: float = 0.0
    timeout_seconds: float = 15.0
    max_output_tokens: int = 4096
    max_response_bytes: int = 256 * 1024
    allow_external_text: bool = False

    def __post_init__(self):
        if self.provider not in ("rules", "mock", "openai_compatible"):
            raise ValueError("provider须为rules、mock或openai_compatible")
        if type(self.enabled) is not bool or type(self.allow_external_text) is not bool:
            raise ValueError("模型开关须为布尔值")
        if not isinstance(self.model, str) or len(self.model) > 200 or not isinstance(self.api_key, str):
            raise ValueError("模型配置格式错误")
        if type(self.temperature) not in (int, float) or not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2:
            raise ValueError("temperature须在0～2")
        if type(self.timeout_seconds) not in (int, float) or not math.isfinite(self.timeout_seconds) or not 0.1 <= self.timeout_seconds <= 60 or type(self.max_output_tokens) is not int or not 128 <= self.max_output_tokens <= 8192:
            raise ValueError("超时须在0.1～60秒，最大输出128～8192 token")
        if type(self.max_response_bytes) is not int or not 1024 <= self.max_response_bytes <= 1024 * 1024:
            raise ValueError("响应限制须在1 KiB～1 MiB")
        self.endpoint()

    def endpoint(self):
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url须为不含凭据、查询或片段的HTTP服务地址")
        local = parsed.hostname.lower() in ("localhost", "127.0.0.1", "::1")
        if not local and (not self.allow_external_text or parsed.scheme != "https"):
            raise ValueError("非loopback文本服务须使用HTTPS并显式allow_external_text=true；默认禁止外发")
        try:
            parsed.port
        except ValueError as exc:
            raise ValueError("端口无效") from exc
        return self.base_url.rstrip("/") + "/chat/completions"

    def public(self):
        # Do not expose credential-bearing headers or any private prompt.
        return {k: getattr(self, k) for k in (
            "provider", "enabled", "base_url", "model", "model_version", "temperature",
            "timeout_seconds", "max_output_tokens", "max_response_bytes", "allow_external_text")}

    @property
    def sha256(self):
        return hashlib.sha256(json.dumps(self.public(), sort_keys=True).encode()).hexdigest()

    @classmethod
    def from_environment(cls):
        def flag(name):
            raw = os.environ.get(name, "false").lower()
            if raw not in ("true", "false", "1", "0"):
                raise ValueError(name + "须为true/false")
            return raw in ("true", "1")
        return cls(provider=os.environ.get("BRAIN_V3_PROVIDER", "rules"),
                   enabled=flag("BRAIN_V3_ENABLE_LLM"),
                   base_url=os.environ.get("BRAIN_V3_BASE_URL", "http://127.0.0.1:11434/v1"),
                   model=os.environ.get("BRAIN_V3_MODEL", ""),
                   model_version=os.environ.get("BRAIN_V3_MODEL_VERSION", "unspecified"),
                   api_key=os.environ.get("BRAIN_V3_API_KEY", ""),
                   temperature=float(os.environ.get("BRAIN_V3_TEMPERATURE", "0")),
                   timeout_seconds=float(os.environ.get("BRAIN_V3_TIMEOUT", "15")),
                   max_output_tokens=int(os.environ.get("BRAIN_V3_MAX_TOKENS", "4096")),
                   allow_external_text=flag("BRAIN_V3_ALLOW_EXTERNAL_TEXT"))


def voice_lab_configuration():
    """A bad optional LLM configuration must not prevent the existing v2 lab."""
    try:
        return ProviderConfig.from_environment(), None
    except (ValueError, TypeError, OverflowError):
        # Avoid echoing environment values (even a misassigned secret).
        return ProviderConfig(), "v3 Provider配置无效；已保留v2规则且未调用网络。请检查BRAIN_V3_*参数。"
