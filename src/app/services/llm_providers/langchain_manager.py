"""
LangChain 기반 LLM 매니저: 다양한 공급자(OpenAI, Anthropic, Google) 모델을 단일 인터페이스로 제공
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import json
import logging

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from core.config import settings
from core.model_catalog import get_provider_mapping, get_supported_models as catalog_get_supported_models

logger = logging.getLogger(__name__)

# 프론트/서버가 공통으로 쓸 수 있는 모델 키 매핑
# value: (provider, provider_model_name)
# MODEL_REGISTRY는 core.model_catalog에서 단일 관리

ALLOWED_PROVIDERS = {"google", "openai", "anthropic"}

class LangChainLLMManager:
    """요청한 모델 키에 따라 적절한 LangChain 챗 모델을 반환"""

    def __init__(self):
        # 환경 변수 유효성 체크는 지연 수행
        pass

    def is_supported(self, model_key: str) -> bool:
        return get_provider_mapping(model_key) is not None

    def get_llm(self, model_key: str, temperature: float = 0.6) -> Optional[BaseLanguageModel]:
        entry = get_provider_mapping(model_key)
        if not entry:
            return None
        provider, name = entry
        try:
            if provider == "google":
                # GOOGLE_API_KEY 또는 GEMINI_API_KEY 로 지원
                api_key = settings.GEMINI_API_KEY
                if not api_key:
                    logger.warning("GEMINI_API_KEY 누락 - Google 모델 사용 불가")
                    return None
                return ChatGoogleGenerativeAI(model=name, api_key=api_key, temperature=temperature)
            elif provider == "openai":
                if not settings.OPENAI_API_KEY:
                    logger.warning("OPENAI_API_KEY 누락 - OpenAI 모델 사용 불가")
                    return None
                return ChatOpenAI(model=name, api_key=settings.OPENAI_API_KEY, temperature=temperature)
            elif provider == "anthropic":
                if not settings.CLAUDE_API_KEY:
                    logger.warning("CLAUDE_API_KEY 누락 - Anthropic 모델 사용 불가")
                    return None
                # Claude 응답 잘림 방지를 위해 설정값으로 max_tokens 지정
                max_toks = getattr(settings, "CLAUDE_MAX_TOKENS", 16000) or 16000
                try:
                    return ChatAnthropic(model=name, api_key=settings.CLAUDE_API_KEY, temperature=temperature, max_tokens=max_toks)
                except TypeError:
                    # 일부 버전 호환: .bind로 설정 시도
                    base = ChatAnthropic(model=name, api_key=settings.CLAUDE_API_KEY, temperature=temperature)
                    return base.bind(max_tokens=max_toks)
        except Exception as e:
            logger.error(f"LLM 생성 실패 ({model_key}): {e}")
            return None

    def build_chain(self, system_prompt: str) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}")
        ])

    async def generate_with_meta(self, model_key: str, system_prompt: str, user_input: str,
                                 temperature: float = 0.6,
                                 images: Optional[List[str]] = None,
                                 structured_schema: Optional[Any] = None) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        멀티모달 입력 지원 생성 함수.
        images: data URI(예: data:image/png;base64,...) 또는 일반 URL 문자열 목록
        """
        llm = self.get_llm(model_key, temperature=temperature)
        if not llm:
            return None, {}

        try:
            mapping = get_provider_mapping(model_key)
            provider = mapping[0] if mapping else None
            # Gemini는 structured_output 사용 시 메타데이터가 유실되는 경우가 있어 비활성화
            use_structured = (structured_schema is not None) and (provider != "google")

            # 이미지가 없으면 기존 프롬프트 체인 사용
            if not images:
                prompt = self.build_chain(system_prompt)
                if use_structured:
                    try:
                        # include_raw=True로 원본 메타를 함께 받는다
                        structured_llm = llm.with_structured_output(structured_schema, include_raw=True)
                        chain = prompt | structured_llm
                        result = await chain.ainvoke({"input": user_input})
                    except Exception:
                        use_structured = False
                        chain = prompt | llm
                        result = await chain.ainvoke({"input": user_input})
                else:
                    chain = prompt | llm
                    result = await chain.ainvoke({"input": user_input})
            else:
                # 멀티모달 메시지 구성: 공통 포맷 사용 (text + image_url)
                human_content: List[Dict[str, Any]] = [{"type": "text", "text": user_input}]
                for img in images:
                    if not (isinstance(img, str) and img.strip()):
                        continue
                    url = img.strip()
                    if provider == "openai":
                        human_content.append({"type": "image_url", "image_url": {"url": url}})
                    elif provider == "google":
                        human_content.append({"type": "image_url", "image_url": url})
                    elif provider == "anthropic":
                        if url.startswith("data:image/") and "," in url:
                            try:
                                header, b64 = url.split(",", 1)
                                mime = header.split(":", 1)[1].split(";", 1)[0]
                                human_content.append({
                                    "type": "image",
                                    "source": {"type": "base64", "media_type": mime, "data": b64},
                                })
                            except Exception:
                                human_content.append({"type": "image", "source": {"type": "url", "url": url}})
                        else:
                            human_content.append({"type": "image", "source": {"type": "url", "url": url}})
                messages = [SystemMessage(content=system_prompt), HumanMessage(content=human_content)]
                if use_structured:
                    try:
                        structured_llm = llm.with_structured_output(structured_schema, include_raw=True)
                        result = await structured_llm.ainvoke(messages)
                    except Exception:
                        use_structured = False
                        result = await llm.ainvoke(messages)
                else:
                    result = await llm.ainvoke(messages)

            text: Optional[str]
            meta: Dict[str, Any] = {}
            # 구조화 출력 경로 처리: include_raw=True 시 { parsed, raw } 형태 지원
            if use_structured and not isinstance(result, AIMessage):
                try:
                    if isinstance(result, dict) and ("parsed" in result or "raw" in result):
                        parsed = result.get("parsed")
                        raw = result.get("raw")
                        # 텍스트 직렬화
                        if parsed is None:
                            payload = result
                        elif hasattr(parsed, "model_dump"):
                            payload = parsed.model_dump(exclude_none=True, exclude_unset=True)
                        elif hasattr(parsed, "dict"):
                            payload = parsed.dict()
                        else:
                            payload = parsed
                        if isinstance(payload, (dict, list)):
                            text = json.dumps(payload, ensure_ascii=False)
                        else:
                            text = str(payload)
                        # 메타는 raw에서 추출 시도
                        try:
                            meta = getattr(raw, "response_metadata", {}) or {}
                            # 추가로 additional_kwargs에 사용량이 실리는 경우 병합
                            try:
                                ak = getattr(raw, "additional_kwargs", {}) or {}
                                if isinstance(ak, dict):
                                    for k in ("usage_metadata", "usage", "token_usage"):
                                        if k in ak and k not in meta:
                                            meta[k] = ak[k]
                                    for k in ("prompt_token_count", "candidates_token_count", "total_token_count",
                                              "input_tokens", "output_tokens", "total_tokens"):
                                        if k in ak and k not in meta:
                                            meta[k] = ak[k]
                            except Exception:
                                pass
                            if not meta and hasattr(raw, "message"):
                                _msg = getattr(raw, "message")
                                meta = getattr(_msg, "response_metadata", {}) or {}
                                try:
                                    ak = getattr(_msg, "additional_kwargs", {}) or {}
                                    if isinstance(ak, dict):
                                        for k in ("usage_metadata", "usage", "token_usage"):
                                            if k in ak and k not in meta:
                                                meta[k] = ak[k]
                                        for k in ("prompt_token_count", "candidates_token_count", "total_token_count",
                                                  "input_tokens", "output_tokens", "total_tokens"):
                                            if k in ak and k not in meta:
                                                meta[k] = ak[k]
                                except Exception:
                                    pass
                            # ChatResult/LLMResult 형태 (generations) 처리
                            if not meta and hasattr(raw, "generations"):
                                try:
                                    gens = getattr(raw, "generations") or []
                                    # generations: List[List[ChatGeneration]]
                                    first = gens[0][0] if gens and gens[0] else None
                                    msg = getattr(first, "message", None)
                                    if msg is not None:
                                        meta = getattr(msg, "response_metadata", {}) or {}
                                        ak = getattr(msg, "additional_kwargs", {}) or {}
                                        if isinstance(ak, dict):
                                            for k in ("usage_metadata", "usage", "token_usage"):
                                                if k in ak and k not in meta:
                                                    meta[k] = ak[k]
                                            for k in ("prompt_token_count", "candidates_token_count", "total_token_count",
                                                      "input_tokens", "output_tokens", "total_tokens"):
                                                if k in ak and k not in meta:
                                                    meta[k] = ak[k]
                                except Exception:
                                    pass
                            # dict 형태로 떨어지는 경우
                            if not meta and isinstance(raw, dict):
                                try:
                                    for k in ("response_metadata", "usage_metadata", "usage", "token_usage"):
                                        if k in raw and not meta:
                                            meta = raw.get(k) if k == "response_metadata" else {k: raw.get(k)}
                                    # message가 dict로 들어있는 경우
                                    if (not meta) and isinstance(raw.get("message"), dict):
                                        rmsg = raw.get("message")
                                        meta = rmsg.get("response_metadata", {}) or {}
                                        for k in ("usage_metadata", "usage", "token_usage"):
                                            if k in rmsg and k not in meta:
                                                meta[k] = rmsg[k]
                                        for k in ("prompt_token_count", "candidates_token_count", "total_token_count",
                                                  "input_tokens", "output_tokens", "total_tokens"):
                                            if k in rmsg and k not in meta:
                                                meta[k] = rmsg[k]
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    else:
                        # 과거 경로: 파싱된 객체 직렬화
                        if hasattr(result, "model_dump"):
                            payload = result.model_dump(exclude_none=True, exclude_unset=True)
                        elif hasattr(result, "dict"):
                            payload = result.dict()
                        else:
                            payload = result
                        if isinstance(payload, (dict, list)):
                            text = json.dumps(payload, ensure_ascii=False)
                        else:
                            text = str(payload)
                except Exception:
                    text = str(result)
            else:
                if isinstance(result, AIMessage):
                    text = result.content if isinstance(result.content, str) else str(result.content)
                    meta = getattr(result, "response_metadata", {}) or {}
                    # additional_kwargs에도 사용량이 담기는 경우가 있어 병합
                    try:
                        ak = getattr(result, "additional_kwargs", {}) or {}
                        if isinstance(ak, dict):
                            for k in ("usage_metadata", "usage", "token_usage"):
                                if k in ak and k not in meta:
                                    meta[k] = ak[k]
                            for k in ("prompt_token_count", "candidates_token_count", "total_token_count",
                                      "input_tokens", "output_tokens", "total_tokens"):
                                if k in ak and k not in meta:
                                    meta[k] = ak[k]
                    except Exception:
                        pass
                else:
                    text = str(result)

            # include_raw=True 경로에서 raw가 있었지만 메타가 비었을 수 있으니 보조 확인
            if use_structured and not meta and isinstance(result, dict) and "raw" in result:
                raw = result.get("raw")
                try:
                    if hasattr(raw, "response_metadata"):
                        meta = getattr(raw, "response_metadata") or {}
                    elif hasattr(raw, "message"):
                        msg = getattr(raw, "message")
                        meta = getattr(msg, "response_metadata", {}) or {}
                except Exception:
                    pass

            # 메타 정규화: 객체가 들어온 경우 dict로 변환하여 downstream 파서가 처리 가능하도록 보장
            def _as_dict(val: Any) -> Optional[Dict[str, Any]]:
                if isinstance(val, dict):
                    return val
                for attr in ("model_dump", "dict"):
                    fn = getattr(val, attr, None)
                    if callable(fn):
                        try:
                            d = fn()
                            if isinstance(d, dict):
                                return d
                        except Exception:
                            pass
                if hasattr(val, "__dict__"):
                    try:
                        d = dict(getattr(val, "__dict__") or {})
                        if isinstance(d, dict):
                            return d
                    except Exception:
                        pass
                # Known Gemini fields
                try:
                    fields = {}
                    for k in ("prompt_token_count", "candidates_token_count", "total_token_count",
                              "input_tokens", "output_tokens", "total_tokens"):
                        if hasattr(val, k):
                            fields[k] = getattr(val, k)
                    return fields or None
                except Exception:
                    return None

            if isinstance(meta, dict):
                for k in ("usage_metadata", "usage", "token_usage"):
                    if k in meta and not isinstance(meta[k], dict) and meta[k] is not None:
                        converted = _as_dict(meta[k])
                        if isinstance(converted, dict):
                            meta[k] = converted

            if settings.DEBUG_HTTP_LOGS:
                try:
                    logger.info("[LC META] model=%s use_structured=%s result_type=%s meta_keys=%s", model_key, use_structured, type(result).__name__, list(meta.keys()) if isinstance(meta, dict) else type(meta))
                except Exception:
                    pass

            return text, meta
        except Exception as e:
            logger.error(f"LangChain 생성 실패 ({model_key}): {e}")
            return None, {}
