import logging
from typing import AsyncIterator, Optional
from openai import AsyncOpenAI
from app.core.config import settings
from app.core.key_manager import key_manager

logger = logging.getLogger(__name__)

MODEL_CONFIGS = [
    # ── OpenAI ──
    {
        "key": "gpt-4o-mini",
        "name": "GPT-4o Mini",
        "provider": "openai",
        "base_url_env": "OPENAI_BASE_URL",
        "key_env": "OPENAI_API_KEY",
    },
    {
        "key": "gpt-4o",
        "name": "GPT-4o",
        "provider": "openai",
        "base_url_env": "OPENAI_BASE_URL",
        "key_env": "OPENAI_API_KEY",
    },
    # ── DeepSeek ──
    {
        "key": "deepseek-chat",
        "name": "DeepSeek V3",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
    },
    {
        "key": "deepseek-v4-flash",
        "name": "DeepSeek V4 Flash",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "model_id": "deepseek-chat",
    },
    # ── 智谱 GLM ──
    {
        "key": "glm-4-flash",
        "name": "GLM-4 Flash",
        "provider": "zhipu",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_env": "GLM_API_KEY",
    },
    {
        "key": "glm-5.2",
        "name": "GLM-5.2",
        "provider": "zhipu",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "key_env": "GLM_API_KEY",
    },
    # ── 通义千问 Qwen (DashScope) ──
    {
        "key": "qwen3.5-397b-a17b",
        "name": "Qwen3.5-397B-A17B",
        "provider": "qwen",
        "base_url_env": "QWEN_BASE_URL",
        "key_env": "QWEN_API_KEY",
    },
    {
        "key": "qwen3.5-27b",
        "name": "Qwen3.5-27B",
        "provider": "qwen",
        "base_url_env": "QWEN_BASE_URL",
        "key_env": "QWEN_API_KEY",
    },
]


class LLMService:
    def __init__(self):
        self._clients: dict = {}
        self._model_configs = MODEL_CONFIGS

    def _get_config(self, model_key: str) -> dict:
        for cfg in self._model_configs:
            if cfg["key"] == model_key:
                return cfg
        raise ValueError(f"Unknown model: {model_key}")

    def _get_model_id(self, model_key: str) -> str:
        """Return the actual API model ID (may differ from display key)."""
        cfg = self._get_config(model_key)
        return cfg.get("model_id", cfg["key"])

    def _get_api_key(self, model_key: str) -> str:
        cfg = self._get_config(model_key)
        key_env = cfg["key_env"]
        api_key = key_manager.get(key_env)
        if not api_key:
            # Try env var as fallback
            api_key = getattr(settings, key_env, None) or ""
        if not api_key:
            raise ValueError(
                f"API key not configured for {model_key}. "
                f"Please set the {key_env} in Settings page or environment variable."
            )
        return api_key

    def _get_base_url(self, model_key: str) -> str:
        cfg = self._get_config(model_key)
        base_url = cfg.get("base_url")
        if base_url:
            return base_url
        base_url_env = cfg.get("base_url_env")
        if base_url_env:
            return getattr(settings, base_url_env, "https://api.openai.com/v1") or "https://api.openai.com/v1"
        return "https://api.openai.com/v1"

    def get_client(self, model_key: str) -> AsyncOpenAI:
        if model_key not in self._clients:
            api_key = self._get_api_key(model_key)
            base_url = self._get_base_url(model_key)
            self._clients[model_key] = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=60.0,      # fail fast instead of hanging for minutes
                max_retries=3,     # built-in exponential backoff on transient errors
            )
        return self._clients[model_key]

    def _has_key(self, model_key: str) -> bool:
        """Check if API key is configured for the given model."""
        try:
            cfg = self._get_config(model_key)
            key_env = cfg["key_env"]
            return key_manager.has(key_env) or bool(getattr(settings, key_env, None) or "")
        except ValueError:
            return False

    def has_any_key(self) -> bool:
        """Return True if at least one configured model has an API key.

        Used to decide whether the app runs in real mode or Demo mode
        (so a fresh clone with no keys still produces usable results).
        """
        return any(self._has_key(cfg["key"]) for cfg in self._model_configs)

    async def chat_complete(
        self,
        model_key: str,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> str:
        if not self._has_key(model_key):
            return self._demo_response(model_key, messages, system_prompt)

        client = self.get_client(model_key)
        model_id = self._get_model_id(model_key)
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM error for {model_key}: {e}")
            raise

    async def chat_stream(
        self,
        model_key: str,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 8192,
    ) -> AsyncIterator[str]:
        if not self._has_key(model_key):
            demo = self._demo_response(model_key, messages, system_prompt)
            yield demo
            return

        client = self.get_client(model_key)
        model_id = self._get_model_id(model_key)
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        try:
            stream = await client.chat.completions.create(
                model=model_id,
                messages=full_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"LLM stream error for {model_key}: {e}")
            raise

    def get_available_models(self) -> list[dict]:
        models = []
        for cfg in self._model_configs:
            has_key = key_manager.has(cfg["key_env"]) or bool(getattr(settings, cfg["key_env"], None) or "")
            models.append({
                "key": cfg["key"],
                "name": cfg["name"],
                "provider": cfg["provider"],
                "available": has_key,
                "key_env": cfg["key_env"],
            })
        return models

    def _demo_response(self, model_key: str, messages: list[dict], system_prompt: Optional[str] = None) -> str:
        """Reply shown before the user connects a model provider.

        ResearchPal is a bring-your-own-key product: a model is only reachable
        once the user supplies a key in Settings. This copy must stay in product
        language — it must never leak env-var names or make the deployment look
        half-configured, since that is exactly what a viewer would notice first.
        """
        cfg = self._get_config(model_key)
        return (
            f"还没有连接 {cfg['name']}。\n\n"
            f"ResearchPal 采用「自带密钥」模式：请到**设置**页面填入你的 API Key，"
            f"保存后立即生效，无需重启。目前支持 OpenAI / DeepSeek / 智谱 GLM / 通义千问。\n\n"
            f"密钥只保存在服务端，仅用于你发起的请求。\n\n"
            f"连接成功后，我可以帮你：\n\n"
            f"1. 总结上传的文献，回答附带可点击的页码级引用\n"
            f"2. 基于知识图谱回答跨文献的关联问题\n"
            f"3. 用深度研究模式自动拆解子问题，生成带参考文献的综述\n"
        )


llm_service = LLMService()
