import uuid
import base64
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
        
        logger.info("AIService 초기화 완료")

    def parse_metadata_scripts(self, metadata: str) -> str:
        """
        메타데이터에서 현재 스크립트 정보를 파싱합니다.
        
        Args:
            metadata: JSON 형태의 메타데이터
            
        Returns:
            str: 파싱된 스크립트 정보
        """
        try:
            if not metadata:
                return ""

            parsed_metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
            current_script = parsed_metadata.get('current_script', {})
            
            return current_script
        except (json.JSONDecodeError, TypeError):
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
            membership_level = membership.get('membership_level', 0) if membership else 0
            
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
            
            # 현재 스크립트 정보 문자열 생성
            current_script = self.parse_metadata_scripts(metadata)
            current_scripts_info = ""
            if current_script:
                current_scripts_info += f"{current_script}\n"
            else:
                current_scripts_info = ""
            
            # AI 요청 처리 (멤버십 레벨 포함)
            return await self._generate_ai_response(current_scripts_info, conversation_context, session_id, image_data, membership_level)

        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            return f"AI 응답 생성 실패: {str(e)}", None

    async def _generate_ai_response(self, current_scripts_info: str, conversation_context: str, session_id: str, image_data: Optional[List[str]] = None, membership_level: int = 0) -> Tuple[str, Optional[Dict]]:
        """
        AI 요청 처리 - 직접 Gemini API 호출
        """
        try:
            # 멤버십별 AI 모델 및 설정 가져오기
            ai_model = MembershipConfig.get_ai_model(membership_level)
            thinking_budget = MembershipConfig.get_thinking_budget(membership_level)
            
            logger.info(f"멤버십 레벨 {membership_level}: AI 모델={ai_model}, 사고 예산={thinking_budget}")
            
            # 이미지 데이터 처리
            image_parts = []
            if image_data:
                for i, img_data in enumerate(image_data):
                    try:
                        logger.info(f"이미지 {i+1} 데이터 길이: {len(img_data) if img_data else 0}")
                        
                        # 데이터 형식 검증
                        if not img_data or not isinstance(img_data, str):
                            continue
                        
                        # 실제 데이터 내용 확인 (디버깅용)
                        logger.info(f"이미지 {i+1} 실제 데이터: '{img_data[:100]}...'")
                        
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
            
            # 프롬프트 텍스트 가져오기
            prompt_text = get_english_prompt(current_scripts_info, conversation_context, image_data, session_id)
            
            # contents 구성 (텍스트 + 이미지)
            contents = [prompt_text]
            if image_parts:
                contents.extend(image_parts)
            
            # 멤버십에 따른 thinking 설정
            thinking_config_params = {"thinking_budget": thinking_budget} if thinking_budget != -1 else {"thinking_budget": -1}
            
            response = await self.gemini_client.aio.models.generate_content(
                model=ai_model,
                contents=contents,
                config=genai.types.GenerateContentConfig(
                    temperature=0.6,
                    thinking_config=types.ThinkingConfig(**thinking_config_params)
                )
            )

            # 토큰 사용량 및 비용 계산
            token_info = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                # 멤버십에 따른 모델명으로 비용 계산
                token_info = TokenUsageCalculator.calculate_cost(
                    response.usage_metadata, 
                    model_name=ai_model,
                    input_type="text_image_video"  # 기본값, 오디오 처리 시 변경 가능
                )
            
            # 응답에서 텍스트 추출 (디버깅 로그 추가)
            structured_response = ""
            logger.info(f"Gemini API 응답 구조 확인:")
            logger.info(f"- hasattr(response, 'text'): {hasattr(response, 'text')}")
            if hasattr(response, 'text'):
                logger.info(f"- response.text: {response.text}")
            logger.info(f"- hasattr(response, 'candidates'): {hasattr(response, 'candidates')}")
            if hasattr(response, 'candidates'):
                logger.info(f"- len(response.candidates): {len(response.candidates) if response.candidates else 0}")
            
            if hasattr(response, 'text') and response.text:
                structured_response = response.text
                logger.info(f"응답 텍스트 추출 성공 (response.text): {len(structured_response)}자")
            elif hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                logger.info(f"첫 번째 후보에서 텍스트 추출 시도")
                logger.info(f"- hasattr(candidate, 'content'): {hasattr(candidate, 'content')}")
                if hasattr(candidate, 'content') and candidate.content:
                    logger.info(f"- hasattr(candidate.content, 'parts'): {hasattr(candidate.content, 'parts')}")
                    if hasattr(candidate.content, 'parts') and candidate.content.parts:
                        logger.info(f"- len(candidate.content.parts): {len(candidate.content.parts)}")
                        for i, part in enumerate(candidate.content.parts):
                            logger.info(f"- part[{i}] hasattr text: {hasattr(part, 'text')}")
                            if hasattr(part, 'text') and part.text:
                                logger.info(f"- part[{i}] text length: {len(part.text)}")
                                structured_response += part.text
            else:
                logger.error("응답에서 텍스트를 추출할 수 없습니다.")
                logger.info(f"응답 전체 구조: {type(response)}")
                logger.info(f"응답 속성들: {dir(response)}")
            
            logger.info(f"최종 추출된 응답 길이: {len(structured_response)}자")
            print("#########\n", structured_response)
            
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
            
            # JSON 파싱 시도
            parsed_response = None
            try:
                parsed_response = json.loads(json_text)
                logger.info("JSON 파싱 성공")
            except json.JSONDecodeError as e:
                logger.warning(f"JSON 파싱 실패: {e}")
                logger.info(f"원본 응답을 그대로 사용: {structured_response[:200]}...")
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
                    logger.info("원본 응답을 message로 사용합니다.")
                else:
                    response_text = "요청을 처리했지만 응답 메시지를 생성할 수 없었습니다. 다시 시도해주세요."
            
            # 스크립트 업데이트 정보 추출
            response_metadata = None
            script_updates = parsed_response.get('script_updates')
            if script_updates:
                response_metadata = {
                    'script_updates': script_updates
                }
            
            # 응답에 토큰 정보 추가
            if token_info:
                if not response_metadata:
                    response_metadata = {}
                response_metadata['token_usage'] = token_info
            
            logger.info(f"최종 응답: 메시지 {len(response_text)}자, 메타데이터: {bool(response_metadata)}")
            logger.info(f"최종 응답 내용 미리보기: '{response_text[:100]}...'")
            return response_text, response_metadata
            
        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            return f"AI 응답 생성 실패: 관리자에게 문의하세요.", None