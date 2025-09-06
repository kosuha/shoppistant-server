import uuid
import base64
import asyncio
from google import genai
from google.genai import types
from typing import List, Dict, Any, Tuple, Optional
import json
import logging
from database_helper import DatabaseHelper
from schemas import AIScriptResponse
from core.membership_config import MembershipConfig
from core.token_calculator import TokenUsageCalculator
from prompts.bren_assistant_prompt import get_english_prompt

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self, gemini_client: genai.Client, db_helper: DatabaseHelper):
        self.gemini_client = gemini_client
        self.db_helper = db_helper
        
    def _is_transient_error(self, e: Exception) -> bool:
        """일시적(재시도 가능) 오류 여부를 판별합니다."""
        msg = str(e).lower()
        return any(k in msg for k in [
            "503", "unavailable", "overloaded", "rate limit", "temporar"
        ])

    def _get_model_candidates(self, preferred: str) -> list:
        """선호 모델에서 시작하는 폴백 체인을 생성합니다."""
        chain = []
        if preferred:
            chain.append(preferred)
        for m in ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]:
            if m not in chain:
                chain.append(m)
        return chain


    def parse_metadata_context(self, metadata: str) -> Dict[str, Any]:
        """
        메타데이터에서 컨텍스트 정보를 파싱합니다.
        
        Args:
            metadata: JSON 형태의 메타데이터
            
        Returns:
            Dict: 파싱된 컨텍스트 정보
        """
        try:
            if not metadata:
                return {}

            parsed_metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
            
            context = {
                'pageContext': parsed_metadata.get('pageContext', ''),
                'userCode': parsed_metadata.get('userCode', {}),
                'pageUrl': parsed_metadata.get('pageUrl', ''),
                'domInfo': parsed_metadata.get('domInfo', {}),
                'current_script': parsed_metadata.get('current_script', {})  # 기존 호환성 유지
            }
            
            return context
        except (json.JSONDecodeError, TypeError):
            logger.error(f"메타데이터 파싱 실패: {metadata}")
            return {}
    

    async def generate_gemini_response(self, chat_history: List[Dict], user_id: str, metadata: Optional[str] = None, site_code: Optional[str] = None, image_data: Optional[List[str]] = None) -> Tuple[str, Optional[Dict]]:
        """
        대화 내역을 기반으로 AI 응답을 생성합니다.
        
        Args:
            chat_history: 대화 내역 리스트
            user_id: 사용자 ID
            metadata: 메타데이터 (현재 스크립트 정보 포함 가능)
            site_code: 클라이언트에서 선택된 사이트 코드
            image_data: 이미지 데이터 배열 (Base64 형식)
            
        Returns:
            tuple: (응답 텍스트, 메타데이터)
        """
        try:
            # 사용자 멤버십 정보 조회
            membership = await self.db_helper.get_user_membership(user_id)
            # 멤버십이 없거나 무료(0)인 경우 사용 불가
            if not membership or int(membership.get('membership_level', 0)) <= 0:
                return ("구독 후 이용 가능한 기능입니다.", None)
            membership_level = membership.get('membership_level', 0)
            
            # 세션 ID 생성
            session_id = str(uuid.uuid4())

            # 대화 내역을 Gemini 형식으로 변환
            contents = []
            for msg in chat_history:
                created_at = msg.get('created_at', '')
                if msg["message_type"] == "user":
                    contents.append(f"User ({created_at}): {msg['message']}")
                elif msg["message_type"] == "assistant":
                    contents.append(f"Assistant ({created_at}): {msg['message']}")
            
            conversation_context = "\n".join(contents)
            
            # 메타데이터에서 컨텍스트 정보 파싱
            context_info = self.parse_metadata_context(metadata)
            # 클라이언트에서 선호 모델을 보낸 경우 파악 (auto는 무시)
            preferred_from_client = None
            try:
                raw_meta = json.loads(metadata) if isinstance(metadata, str) else (metadata or {})
                if isinstance(raw_meta, dict):
                    m = raw_meta.get('ai_model_preferred')
                    if isinstance(m, str):
                        mk = m.strip()
                        if mk and mk != 'auto' and MembershipConfig.is_valid_model(mk):
                            preferred_from_client = mk
            except Exception:
                preferred_from_client = None
            
            # AI 요청 처리 (컨텍스트 정보 포함)
            return await self._generate_ai_response(context_info, conversation_context, session_id, image_data, membership_level, preferred_from_client)

        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            return f"AI 응답 생성 실패: {str(e)}", None

    async def _generate_ai_response(self, context_info: Dict[str, Any], conversation_context: str, session_id: str, image_data: Optional[List[str]] = None, membership_level: int = 0, preferred_from_client: Optional[str] = None) -> Tuple[str, Optional[Dict]]:
        """
        AI 요청 처리 - 직접 Gemini API 호출
        """
        try:
            # 멤버십별 AI 모델 및 설정 가져오기
            preferred_model = preferred_from_client or MembershipConfig.get_ai_model(membership_level)
            thinking_budget = MembershipConfig.get_thinking_budget(membership_level)
            
            
            # 이미지 데이터 처리
            image_parts = []
            if image_data:
                for i, img_data in enumerate(image_data):
                    try:
                        
                        # 데이터 형식 검증
                        if not img_data or not isinstance(img_data, str):
                            continue
                        
                        # 실제 데이터 내용 확인 (디버깅용)
                        
                        # data:image/jpeg;base64, 형식 확인
                        if not img_data.startswith('data:image/'):
                            continue
                        
                        if ',' not in img_data:
                            continue
                        
                        # 헤더와 데이터 분리
                        parts = img_data.split(',', 1)
                        if len(parts) != 2:
                            continue
                        
                        header, base64_data = parts
                        
                        # MIME 타입 추출
                        try:
                            mime_type = header.split(':')[1].split(';')[0]
                        except (IndexError, AttributeError):
                            continue
                        
                        # Base64 디코딩
                        try:
                            image_bytes = base64.b64decode(base64_data)
                        except Exception:
                            continue
                        
                        # Gemini API용 Part 생성
                        image_parts.append(types.Part.from_bytes(
                            data=image_bytes,
                            mime_type=mime_type
                        ))
                        
                    except Exception as e:
                        logger.error(f"이미지 {i+1} 처리 중 예외 발생: {e}")
                        continue
            
            # 프롬프트 텍스트 가져오기 (컨텍스트 정보를 직접 전달)
            prompt_text = get_english_prompt(context_info, conversation_context, image_data, session_id)
            
            # contents 구성 (텍스트 + 이미지)
            contents = [prompt_text]
            if image_parts:
                contents.extend(image_parts)
            
            # 멤버십에 따른 thinking 설정
            thinking_config_params = {"thinking_budget": thinking_budget} if thinking_budget != -1 else {"thinking_budget": -1}
            
            # 모델 과부하 대응: 재시도 + 모델 폴백
            model_used = None
            response = None
            last_err = None
            for idx, model in enumerate(self._get_model_candidates(preferred_model)):
                max_attempts = 3 if idx == 0 else 2
                for attempt in range(max_attempts):
                    try:
                        response = await self.gemini_client.aio.models.generate_content(
                            model=model,
                            contents=contents,
                            config=genai.types.GenerateContentConfig(
                                temperature=0.6,
                                thinking_config=types.ThinkingConfig(**thinking_config_params)
                            )
                        )
                        model_used = model
                        break
                    except Exception as gen_err:
                        last_err = gen_err
                        if self._is_transient_error(gen_err) and attempt < max_attempts - 1:
                            await asyncio.sleep(min(2.0, 0.5 * (2 ** attempt)))
                            continue
                        else:
                            break
                if model_used:
                    break

            if not model_used:
                if last_err and self._is_transient_error(last_err):
                    raise Exception("모델이 일시적으로 과부하 상태입니다. 잠시 후 다시 시도해주세요.")
                else:
                    raise last_err or Exception("AI 응답 생성 실패")

            # 토큰 사용량 및 비용 계산
            token_info = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                # 멤버십에 따른 모델명으로 비용 계산
                token_info = TokenUsageCalculator.calculate_cost(
                    response.usage_metadata,
                    model_name=(model_used or preferred_model),
                    input_type="text_image_video"  # 기본값, 오디오 처리 시 변경 가능
                )
            
            # 응답에서 텍스트 추출 (디버깅 로그 추가)
            structured_response = ""
            
            if hasattr(response, 'text') and response.text:
                structured_response = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    if hasattr(candidate.content, 'parts') and candidate.content.parts:
                        for i, part in enumerate(candidate.content.parts):
                            if hasattr(part, 'text') and part.text:
                                structured_response += part.text
            
            # JSON 추출 및 파싱 (코드 블록 외부 응답 제거)
            def extract_json_only(response_text):
                """응답에서 순수한 JSON만 추출 (외부 텍스트 제거)"""
                response_text = response_text.strip()
                
                # 패턴 1: ```json ... ``` 코드 블록 우선
                if '```json' in response_text:
                    json_start = response_text.find('```json') + 7
                    remaining_text = response_text[json_start:]
                    json_end = remaining_text.find('```')
                    
                    if json_end != -1:
                        return remaining_text[:json_end].strip()
                    else:
                        return remaining_text.strip()
                
                # 패턴 2: ``` ... ``` 코드 블록에서 JSON 찾기
                elif '```' in response_text:
                    start = response_text.find('```')
                    if start != -1:
                        # 언어 표시 스킵
                        content_start = start + 3
                        newline_pos = response_text.find('\n', content_start)
                        if newline_pos != -1:
                            content_start = newline_pos + 1
                        
                        end = response_text.find('```', content_start)
                        if end != -1:
                            block_content = response_text[content_start:end].strip()
                            # JSON 객체인지 확인
                            if block_content.startswith('{') and block_content.endswith('}'):
                                return block_content
                        else:
                            # 닫는 ```가 없는 경우
                            block_content = response_text[content_start:].strip()
                            if block_content.startswith('{'):
                                return block_content
                
                # 패턴 3: 균형잡힌 { ... } JSON 객체만 추출
                if '{' in response_text:
                    start_pos = response_text.find('{')
                    if start_pos != -1:
                        brace_count = 0
                        for i, char in enumerate(response_text[start_pos:], start_pos):
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    # 완전한 JSON 객체만 반환
                                    return response_text[start_pos:i + 1].strip()
                
                # 모든 패턴 실패 시 빈 JSON 반환
                return "{}"
            
            # 응답이 비어있거나 None인 경우 처리
            if not structured_response or not structured_response.strip():
                logger.warning("AI 응답이 비어있습니다.")
                # 구조화된 JSON 형태로 기본 응답 반환
                default_message = "AI 응답을 생성할 수 없었습니다. 다시 시도해주세요."
                return default_message, None
            
            # JSON 순수 추출
            json_text = extract_json_only(structured_response)
            
            # JSON 파싱 시도 전에 백슬래시 문제 해결
            def fix_json_escapes(text):
                """JSON 문자열에서 잘못된 이스케이프 시퀀스를 수정"""
                # 1. 줄 끝 백슬래시 제거 (JavaScript 문자열 연결에서 불필요)
                text = text.replace('\\\n', '\n')
                text = text.replace('\\\r\n', '\r\n')
                
                # 2. 문자열 내부의 백슬래시 처리
                # JSON 문자열 값 내부에서만 백슬래시를 이스케이프
                import re
                
                def escape_in_string(match):
                    """문자열 내부의 백슬래시만 이스케이프"""
                    string_content = match.group(1)
                    # 이미 이스케이프된 것은 건드리지 않음
                    string_content = re.sub(r'\\(?![\\"/bfnrt])', r'\\\\', string_content)
                    return '"' + string_content + '"'
                
                # JSON 문자열 값 찾아서 백슬래시 이스케이프
                text = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', escape_in_string, text)
                
                return text
            
            json_text = fix_json_escapes(json_text)
            
            # 코드 블록 추출 함수
            def extract_code_blocks(text):
                """AI 응답에서 JavaScript와 CSS 코드 블록을 추출합니다."""
                import re
                
                code_blocks = {
                    "javascript": None,
                    "css": None
                }
                
                # JavaScript 코드 블록 찾기
                js_patterns = [
                    r'```javascript\s*\n(.*?)\n```',
                    r'```js\s*\n(.*?)\n```',
                ]
                
                for pattern in js_patterns:
                    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
                    if matches:
                        # 여러 블록이 있으면 합치기
                        code_blocks["javascript"] = '\n\n'.join(matches)
                        break
                
                # CSS 코드 블록 찾기
                css_pattern = r'```css\s*\n(.*?)\n```'
                css_matches = re.findall(css_pattern, text, re.DOTALL | re.IGNORECASE)
                if css_matches:
                    # 여러 블록이 있으면 합치기
                    code_blocks["css"] = '\n\n'.join(css_matches)
                
                # 비어있는 값들은 제거
                return {k: v for k, v in code_blocks.items() if v and v.strip()}
            
            # 코드 액션 감지 함수
            def detect_code_action(text):
                """AI 응답에서 코드 액션을 감지합니다."""
                text_lower = text.lower()
                
                if any(keyword in text_lower for keyword in ['전체 교체', '완전히 교체', '모든 코드를 교체', '전부 바꾸기']):
                    return 'replace'
                elif any(keyword in text_lower for keyword in ['추가', '덧붙이기', '끝에 추가', '아래에 추가']):
                    return 'append'
                elif any(keyword in text_lower for keyword in ['삽입', '중간에 추가', '특정 위치에']):
                    return 'insert'
                elif any(keyword in text_lower for keyword in ['수정', '변경', '일부 변경', '부분 수정']):
                    return 'modify'
                else:
                    return 'replace'  # 기본값

            # JSON 파싱 시도
            parsed_response = None
            changes_data = None  # changes 형식으로 통일
            
            try:
                parsed_response = json.loads(json_text)
                
                # changes 형식만 처리 (완전 통일)
                if isinstance(parsed_response, dict):
                    changes = parsed_response.get('changes')
                    if changes and isinstance(changes, dict):
                        # 유효한 changes 데이터인지 확인
                        valid_changes = {}
                        if changes.get('javascript', {}).get('diff'):
                            valid_changes['javascript'] = {'diff': changes['javascript']['diff']}
                        if changes.get('css', {}).get('diff'):
                            valid_changes['css'] = {'diff': changes['css']['diff']}
                        
                        if valid_changes:
                            changes_data = valid_changes
            
            # JSON 파싱 실패 시 마크다운 코드 블록에서 changes 형식으로 변환
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 파싱 실패: {e}")
                
                # 마크다운에서 코드 블록 추출 후 changes 형식으로 변환
                if structured_response:
                    code_blocks = extract_code_blocks(structured_response)
                    if code_blocks:
                        changes_data = {}
                        if code_blocks.get('javascript'):
                            changes_data['javascript'] = {'diff': code_blocks['javascript']}
                        if code_blocks.get('css'):
                            changes_data['css'] = {'diff': code_blocks['css']}
                
                # 파싱 실패 시 기본 응답 구조
                parsed_response = {
                    "message": structured_response.strip() if structured_response else "응답을 처리할 수 없었습니다.",
                    "changes": changes_data
                }
                        
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 파싱 실패: {e}")
                # JSON 파싱 실패 시 원본 응답을 message로 사용                
                parsed_response = {
                    "message": structured_response.strip(),
                    "script_updates": None
                }
            
            if not isinstance(parsed_response, dict):
                logger.error("파싱된 응답이 딕셔너리가 아닙니다")
                parsed_response = {
                    "message": structured_response.strip() if structured_response else "응답을 처리할 수 없었습니다.",
                    "script_updates": None
                }
            
            # AIScriptResponse 스키마에 따라 파싱
            response_text = parsed_response.get('message', '')
            if not response_text:
                logger.warning("AI 응답에 'message' 필드가 없거나 비어있습니다.")
                # 전체 응답이 있다면 그것을 사용, 없다면 기본 메시지
                if structured_response and structured_response.strip():
                    response_text = structured_response.strip()
                else:
                    response_text = "요청을 처리했지만 응답 메시지를 생성할 수 없었습니다. 다시 시도해주세요."
            
            # # 스크립트 업데이트 정보 추출
            response_metadata = None
            # script_updates = parsed_response.get('script_updates')
            # if script_updates:
            #     response_metadata = {
            #         'script_updates': script_updates
            #     }
            
            # 응답에 토큰 정보 추가
            if token_info:
                if not response_metadata:
                    response_metadata = {}
                response_metadata['token_usage'] = token_info
            
            # 추출된 changes 데이터가 있으면 응답 메타데이터에 추가
            if changes_data:
                if not response_metadata:
                    response_metadata = {}
                response_metadata['changes'] = changes_data
            
            # 사용된 모델 및 폴백 여부를 메타데이터에 포함
            if not response_metadata:
                response_metadata = {}
            response_metadata['model_used'] = model_used or preferred_model
            response_metadata['fallback_used'] = (model_used is not None and model_used != preferred_model)
            return response_text, response_metadata
            
        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            if self._is_transient_error(e):
                return "현재 AI 모델이 과부하입니다. 잠시 후 다시 시도해주세요.", None
            return f"AI 응답 생성 실패: 관리자에게 문의하세요.", None