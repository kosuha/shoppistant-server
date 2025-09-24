"""
직접 공급자 SDK/HTTP를 통해 Gemini, OpenAI, Claude 모델을 호출하는 LLM 매니저.
LangChain 의존성을 제거하고 기존과 동일한 인터페이스(generate_with_meta)를 제공합니다.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional, Tuple, Type

import requests

try:  # optional dependency - guard import errors
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None  # type: ignore

try:  # optional dependency - guard import errors
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    anthropic = None  # type: ignore

from core.config import settings
from core.model_catalog import get_provider_mapping

logger = logging.getLogger(__name__)

ALLOWED_PROVIDERS = {"google", "openai", "anthropic"}


class LangChainLLMManager:
    """호환성을 위해 기존 클래스 이름을 유지한 직접 LLM 매니저."""

    _GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self) -> None:
        self._openai_client: Optional[OpenAI] = None  # type: ignore[assignment]
        self._anthropic_client: Optional["anthropic.Anthropic"] = None  # type: ignore[name-defined]

    # ------------------------------------------------------------------
    # 기본 기능
    # ------------------------------------------------------------------
    def is_supported(self, model_key: str) -> bool:
        return get_provider_mapping(model_key) is not None

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    async def generate_with_meta(
        self,
        model_key: str,
        system_prompt: str,
        user_input: str,
        temperature: float = 0.6,
        images: Optional[List[str]] = None,
        structured_schema: Optional[Type[Any]] = None,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """LLM 호출을 비동기 인터페이스로 제공."""

        mapping = get_provider_mapping(model_key)
        if not mapping:
            logger.error("지원되지 않는 모델 요청: %s", model_key)
            return None, {}

        provider, provider_model = mapping
        if provider not in ALLOWED_PROVIDERS:
            logger.error("허용되지 않은 공급자 요청: %s", provider)
            return None, {}

        try:
            return await asyncio.to_thread(
                self._generate_sync,
                provider,
                provider_model,
                system_prompt,
                user_input,
                float(temperature),
                images or [],
                structured_schema,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("LLM 호출 실패 (%s/%s): %s", provider, provider_model, exc)
            return None, {}

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------
    def _generate_sync(
        self,
        provider: str,
        provider_model: str,
        system_prompt: str,
        user_input: str,
        temperature: float,
        images: List[str],
        structured_schema: Optional[Type[Any]],
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        if provider == "google":
            return self._call_gemini(provider_model, system_prompt, user_input, temperature, images, structured_schema)
        if provider == "openai":
            return self._call_openai(provider_model, system_prompt, user_input, temperature, images, structured_schema)
        if provider == "anthropic":
            return self._call_anthropic(provider_model, system_prompt, user_input, temperature, images, structured_schema)

        raise ValueError(f"Unknown provider: {provider}")

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------
    def _call_gemini(
        self,
        model_name: str,
        system_prompt: str,
        user_input: str,
        temperature: float,
        images: List[str],
        structured_schema: Optional[Type[Any]],
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

        url = f"{self._GEMINI_ENDPOINT}/models/{model_name}:generateContent"
        params = {"key": api_key}

        parts: List[Dict[str, Any]] = [{"text": user_input}]
        for img in self._normalise_images(images):
            if img.get("mode") == "inline":
                parts.append({
                    "inline_data": {
                        "data": img["data"],
                        "mime_type": img.get("mime_type", "image/png"),
                    }
                })
            elif img.get("mode") == "url":
                parts.append({
                    "file_data": {
                        "file_uri": img["url"]
                    }
                })

        generation_config: Dict[str, Any] = {"temperature": temperature}
        schema_dict = self._schema_to_json_schema(structured_schema)
        if schema_dict:
            generation_config["response_mime_type"] = "application/json"
            generation_config["response_schema"] = schema_dict

        payload = {
            "system_instruction": {
                "role": "system",
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": parts
                }
            ],
            "generation_config": generation_config,
        }

        response = requests.post(url, params=params, json=payload, timeout=60)
        response.raise_for_status()
        data = response.json()

        text = self._extract_gemini_text(data)
        meta: Dict[str, Any] = {}
        usage = data.get("usageMetadata")
        if isinstance(usage, dict):
            meta["usage_metadata"] = usage
        meta["model"] = data.get("model", model_name)
        meta["raw_response"] = data  # 유지하여 추후 분석 가능

        return text, meta

    # ------------------------------------------------------------------
    # OpenAI
    # ------------------------------------------------------------------
    def _call_openai(
        self,
        model_name: str,
        system_prompt: str,
        user_input: str,
        temperature: float,
        images: List[str],
        structured_schema: Optional[Type[Any]],
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        client = self._get_openai_client()

        user_content: List[Dict[str, Any]] = [
            {"type": "text", "text": user_input}
        ]
        for img in self._normalise_images(images):
            if img.get("mode") == "inline":
                data_uri = f"data:{img.get('mime_type', 'image/png')};base64,{img['data']}"
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": data_uri}
                })
            elif img.get("mode") == "url":
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": img["url"]}
                })

        request_kwargs: Dict[str, Any] = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
        }

        response_format = self._build_json_schema_format(structured_schema)
        if response_format:
            request_kwargs["response_format"] = response_format

        completion = client.chat.completions.create(**request_kwargs)

        text: Optional[str] = None
        if completion.choices:
            message_content = completion.choices[0].message.content
            if isinstance(message_content, list):
                text_parts = [x.get("text") for x in message_content if isinstance(x, dict) and x.get("type") == "text"]
                text = "".join(filter(None, text_parts)) if text_parts else None
            else:
                text = message_content

        meta: Dict[str, Any] = {
            "id": getattr(completion, "id", None),
            "model": getattr(completion, "model", model_name),
        }

        usage = getattr(completion, "usage", None)
        if usage is not None:
            meta["usage"] = self._to_dict(usage)

        return text, meta

    # ------------------------------------------------------------------
    # Anthropic / Claude
    # ------------------------------------------------------------------
    def _call_anthropic(
        self,
        model_name: str,
        system_prompt: str,
        user_input: str,
        temperature: float,
        images: List[str],
        structured_schema: Optional[Type[Any]],
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        client = self._get_anthropic_client()

        content: List[Dict[str, Any]] = [
            {"type": "text", "text": user_input}
        ]
        for img in self._normalise_images(images):
            if img.get("mode") == "inline":
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.get("mime_type", "image/png"),
                        "data": img["data"],
                    }
                })
            elif img.get("mode") == "url":
                content.append({
                    "type": "image",
                    "source": {"type": "url", "url": img["url"]}
                })

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": content}
            ],
            "temperature": temperature,
            "max_output_tokens": getattr(settings, "CLAUDE_MAX_TOKENS", 8192) or 8192,
        }

        response_format = self._build_json_schema_format(structured_schema)
        if response_format:
            kwargs["response_format"] = response_format

        response = client.messages.create(**kwargs)

        text_parts: List[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text_parts.append(getattr(block, "text", ""))
        text = "".join(text_parts) if text_parts else None

        meta: Dict[str, Any] = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", model_name),
        }

        usage = getattr(response, "usage", None)
        if usage is not None:
            meta["usage"] = self._to_dict(usage)

        return text, meta

    # ------------------------------------------------------------------
    # 클라이언트 Lazy 생성
    # ------------------------------------------------------------------
    def _get_openai_client(self) -> OpenAI:  # type: ignore[override]
        if OpenAI is None:
            raise RuntimeError("openai 패키지가 설치되어 있지 않습니다. requirements를 확인하세요.")
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
        if self._openai_client is None:
            self._openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)  # type: ignore[call-arg]
        return self._openai_client

    def _get_anthropic_client(self) -> "anthropic.Anthropic":  # type: ignore[name-defined]
        if anthropic is None:
            raise RuntimeError("anthropic 패키지가 설치되어 있지 않습니다. requirements를 확인하세요.")
        if not settings.CLAUDE_API_KEY:
            raise RuntimeError("CLAUDE_API_KEY가 설정되지 않았습니다.")
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic(api_key=settings.CLAUDE_API_KEY)
        return self._anthropic_client

    # ------------------------------------------------------------------
    # 헬퍼 함수들
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_images(images: Optional[List[str]]) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        if not images:
            return result

        for item in images:
            if not item:
                continue
            item = item.strip()
            if not item:
                continue

            if item.startswith("data:"):
                header, _, data = item.partition(",")
                if not data:
                    continue
                mime_type = "image/png"
                if ";" in header:
                    mime_type = header.split(";", 1)[0].replace("data:", "") or mime_type
                elif header.startswith("data:"):
                    mime_type = header[5:] or mime_type
                result.append({"mode": "inline", "mime_type": mime_type, "data": data})
                continue

            # 순수 base64 문자열로 넘어오는 경우 (mime 추정 불가)
            if _is_base64(item):
                result.append({"mode": "inline", "mime_type": "image/png", "data": item})
                continue

            result.append({"mode": "url", "url": item})

        return result

    @staticmethod
    def _schema_to_json_schema(schema: Optional[Type[Any]]) -> Optional[Dict[str, Any]]:
        if schema is None:
            return None
        try:
            if hasattr(schema, "model_json_schema"):
                return schema.model_json_schema()  # type: ignore[attr-defined]
            if hasattr(schema, "schema"):
                return schema.schema()  # type: ignore[attr-defined]
        except Exception:
            logger.warning("JSON 스키마 변환 실패: %s", schema, exc_info=True)
        return None

    @staticmethod
    def _build_json_schema_format(schema: Optional[Type[Any]]) -> Optional[Dict[str, Any]]:
        schema_dict = LangChainLLMManager._schema_to_json_schema(schema)
        if not schema_dict:
            return None
        name = getattr(schema, "__name__", "response") if schema else "response"
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "schema": schema_dict,
                "strict": True,
            },
        }

    @staticmethod
    def _extract_gemini_text(data: Dict[str, Any]) -> Optional[str]:
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            return None
        for candidate in candidates:
            content = candidate.get("content") if isinstance(candidate, dict) else None
            parts = content.get("parts") if isinstance(content, dict) else None
            if not isinstance(parts, list):
                continue
            texts = []
            for part in parts:
                if isinstance(part, dict) and "text" in part:
                    texts.append(str(part["text"]))
            if texts:
                return "".join(texts)
        return None

    @staticmethod
    def _to_dict(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "model_dump"):
            try:
                dumped = value.model_dump()  # type: ignore[attr-defined]
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
        if hasattr(value, "dict"):
            try:
                dumped = value.dict()  # type: ignore[attr-defined]
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
        if hasattr(value, "__dict__"):
            try:
                dumped = dict(value.__dict__)
                if isinstance(dumped, dict):
                    return dumped
            except Exception:
                pass
        try:
            return json.loads(json.dumps(value))
        except Exception:
            return str(value)


def _is_base64(value: str) -> bool:
    try:
        # base64로 디코딩 후 다시 인코딩했을 때 동일한지 확인
        decoded = base64.b64decode(value, validate=True)
        return base64.b64encode(decoded).decode("utf-8").rstrip("=") == value.rstrip("=")
    except Exception:
        return False
