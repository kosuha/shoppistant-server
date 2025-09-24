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

try:  # optional dependency - guard import errors
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None  # type: ignore

try:  # optional dependency - guard import errors
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    anthropic = None  # type: ignore

try:  # optional dependency - guard import errors
    from google import genai  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    genai = None  # type: ignore

from core.config import settings
from core.model_catalog import get_provider_mapping

logger = logging.getLogger(__name__)

ALLOWED_PROVIDERS = {"google", "openai", "anthropic"}


class LangChainLLMManager:
    """호환성을 위해 기존 클래스 이름을 유지한 직접 LLM 매니저."""

    def __init__(self) -> None:
        self._openai_client: Optional[OpenAI] = None  # type: ignore[assignment]
        self._anthropic_client: Optional["anthropic.Anthropic"] = None  # type: ignore[name-defined]
        self._gemini_client: Optional["genai.Client"] = None  # type: ignore[name-defined]

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
        client = self._get_gemini_client()

        parts: List[Dict[str, Any]] = []
        combined_texts: List[str] = []
        if system_prompt.strip():
            combined_texts.append(system_prompt)
        if user_input.strip():
            combined_texts.append(user_input)
        if combined_texts:
            parts.append({"text": "\n\n".join(combined_texts)})

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

        contents = [{"role": "user", "parts": parts}] if parts else [user_input or system_prompt]

        config: Dict[str, Any] = {
            "temperature": temperature,
        }

        if structured_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = structured_schema

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        text: Optional[str] = getattr(response, "text", None)
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            payload = self._to_dict(parsed)
            if isinstance(payload, (dict, list)):
                text = json.dumps(payload, ensure_ascii=False)
            elif payload is not None:
                text = str(payload)

        meta: Dict[str, Any] = {
            "model": model_name,
        }

        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            meta["usage_metadata"] = self._to_dict(usage)

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

        return self._call_openai_responses(
            client,
            model_name,
            system_prompt,
            user_input,
            temperature,
            images,
            structured_schema,
        )

    def _call_openai_responses(
        self,
        client: "OpenAI",  # type: ignore[name-defined]
        model_name: str,
        system_prompt: str,
        user_input: str,
        temperature: float,
        images: List[str],
        structured_schema: Optional[Type[Any]],
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        system_message = {
            "role": "system",
            "content": [
                {"type": "input_text", "text": system_prompt},
            ],
        }

        user_content: List[Dict[str, Any]] = [
            {"type": "input_text", "text": user_input},
        ]
        for img in self._normalise_images(images):
            data_uri = self._to_data_uri(img)
            if not data_uri:
                continue
            user_content.append({
                "type": "input_image",
                "image_url": {"url": data_uri},
            })

        messages = [system_message, {"role": "user", "content": user_content}]

        request_kwargs: Dict[str, Any] = {
            "model": model_name,
            "input": messages,
        }

        text_payload: Optional[Dict[str, Any]] = None
        if self._openai_uses_reasoning_controls(model_name):
            effort = self._map_reasoning_effort(model_name, temperature)
            request_kwargs["reasoning"] = {"effort": effort}
            verbosity = self._map_verbosity(temperature)
            if verbosity:
                text_payload = {"verbosity": verbosity}
        else:
            request_kwargs["temperature"] = temperature

        parse_used = False
        parsed_payload: Any = None

        responses_api = getattr(client, "responses", None)
        if structured_schema is not None:
            if not hasattr(responses_api, "parse"):
                raise RuntimeError(
                    "OpenAI SDK가 responses.parse를 지원하지 않습니다. 구조화 응답을 사용하려면 최신 SDK와 대응 모델이 필요합니다."
                )
            parse_kwargs = dict(request_kwargs)
            if text_payload is not None:
                parse_kwargs["text"] = text_payload
            response = responses_api.parse(text_format=structured_schema, **parse_kwargs)
            parse_used = True
            parsed_payload = getattr(response, "output_parsed", None)
        else:
            if text_payload is not None:
                request_kwargs["text"] = text_payload
            response = client.responses.create(**request_kwargs)

        text: Optional[str] = None
        if parse_used and parsed_payload is not None:
            payload = self._to_dict(parsed_payload)
            if isinstance(payload, (dict, list)):
                text = json.dumps(payload, ensure_ascii=False)
            elif payload is not None:
                text = str(payload)

        if not text:
            text = self._extract_openai_output_text(response)

        meta: Dict[str, Any] = {
            "id": getattr(response, "id", None),
            "model": getattr(response, "model", model_name),
        }

        usage = getattr(response, "usage", None)
        if usage is not None:
            meta["usage"] = self._to_dict(usage)

        if parse_used and parsed_payload is not None:
            meta["parsed"] = self._to_dict(parsed_payload)

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

        system_text = system_prompt
        schema_dict: Optional[Dict[str, Any]] = None
        if structured_schema is not None:
            schema_dict = self._schema_to_json_schema(structured_schema)
            if schema_dict:
                schema_hint = json.dumps(schema_dict, ensure_ascii=False)
                system_text = (
                    f"{system_prompt}\n\n"
                    "Respond with strict JSON matching this schema. Do not include explanations.\n"
                    f"Schema: {schema_hint}"
                )

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "system": system_text,
            "messages": [
                {"role": "user", "content": content}
            ],
            "temperature": temperature,
            "max_tokens": getattr(settings, "CLAUDE_MAX_TOKENS", 8192) or 8192,
        }

        if structured_schema is not None:
            logger.debug("Anthropic SDK은 JSON Schema 기반 structured output을 직접 지원하지 않아 프롬프트 기반 응답으로 대체합니다.")

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

    def _get_gemini_client(self) -> "genai.Client":  # type: ignore[name-defined]
        if genai is None:
            raise RuntimeError("google-genai 패키지가 설치되어 있지 않습니다. requirements를 확인하세요.")
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
        if self._gemini_client is None:
            self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._gemini_client

    # ------------------------------------------------------------------
    # 헬퍼 함수들
    # ------------------------------------------------------------------
    @staticmethod
    def _to_data_uri(image_info: Dict[str, str]) -> Optional[str]:
        mode = image_info.get("mode")
        if mode == "inline":
            mime = image_info.get("mime_type", "image/png")
            data = image_info.get("data")
            if not data:
                return None
            return f"data:{mime};base64,{data}"
        if mode == "url":
            return image_info.get("url")
        return None

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
    def _openai_uses_reasoning_controls(model_name: str) -> bool:
        name = (model_name or "").lower()
        return name.startswith("gpt-5") or name.startswith("gpt5")

    @staticmethod
    def _map_reasoning_effort(model_name: str, temperature: float) -> str:
        name = (model_name or "").lower()
        clamped = max(0.0, min(float(temperature), 1.0))
        if name.startswith("gpt-5-codex"):
            if clamped < 0.34:
                return "low"
            if clamped < 0.67:
                return "medium"
            return "high"
        if clamped < 0.2:
            return "minimal"
        if clamped < 0.4:
            return "low"
        if clamped < 0.7:
            return "medium"
        return "high"

    @staticmethod
    def _map_verbosity(temperature: float) -> Optional[str]:
        clamped = max(0.0, min(float(temperature), 1.0))
        if clamped <= 0.25:
            return "low"
        if clamped >= 0.75:
            return "high"
        return "medium"

    @staticmethod
    def _extract_openai_output_text(response: Any) -> Optional[str]:
        text = getattr(response, "output_text", None)
        if isinstance(text, str) and text.strip():
            return text

        outputs = getattr(response, "output", None)
        if outputs:
            collected: List[str] = []
            for item in outputs:
                content = item.get("content") if isinstance(item, dict) else getattr(item, "content", None)
                if not isinstance(content, list):
                    continue
                for block in content:
                    block_type = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if block_type not in {"text", "output_text"}:
                        continue
                    block_text = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
                    if block_text:
                        collected.append(str(block_text))
            if collected:
                return "".join(collected)
        return None

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
