import uuid
import base64
from fastmcp import Client
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
    def __init__(self, gemini_client: genai.Client, mcp_client: Optional[Client], db_helper: DatabaseHelper):
        # MCP 클라이언트는 선택적입니다. (runtime에 나중에 설정 가능)
        self.gemini_client = gemini_client
        self.mcp_client = mcp_client  # None일 수 있음
        self.db_helper = db_helper
        self.playwright_mcp_client = mcp_client  # 호환성을 위해 추가
        
        logger.info(f"AIService 초기화 완료 - MCP 클라이언트: {mcp_client is not None}")

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
        대화 내역을 기반으로 두 단계 AI 응답을 생성합니다.
        1단계: MCP 도구를 사용하여 데이터 수집
        2단계: thinking 설정으로 구조화된 출력 생성
        
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
            
            # 사용자의 모든 사이트 정보 가져오기
            user_sites = await self.db_helper.get_user_sites(user_id, user_id)
            if not user_sites:
                logger.warning(f"사용자 {user_id}의 사이트 정보가 없습니다.")
                return "아임웹 사이트가 연결되지 않았습니다. 먼저 사이트를 연결해주세요.", None
            
            # 클라이언트에서 전달받은 사이트 코드 사용
            logger.info(f"선택된 사이트 코드: {site_code}")
            
            # 세션 ID 생성
            session_id = str(uuid.uuid4())
            
            # MCP 서버에 선택된 사이트 정보 설정
            # MCP 클라이언트 확인 및 대기
            logger.info(f"MCP 클라이언트 상태 확인: {self.mcp_client is not None}")
            if self.mcp_client is None:
                logger.error("MCP 클라이언트가 초기화되지 않았습니다. AI 응답을 생성할 수 없습니다.")
                return "MCP 클라이언트가 초기화되지 않았습니다. 서버 관리자에게 문의하세요.", None
            
            logger.info(f"MCP 클라이언트 타입: {type(self.mcp_client)}")
            if self.mcp_client:
                try:
                    # 선택된 사이트 정보 찾기
                    selected_site = None
                    
                    if site_code:
                        # 특정 사이트 코드로 필터링
                        for site in user_sites:
                            if site.get('site_code') == site_code:
                                selected_site = site
                                break
                        
                        if not selected_site:
                            return f"사이트 코드 '{site_code}'에 해당하는 사이트를 찾을 수 없습니다.", None
                    else:
                        # 사이트 코드가 없으면 첫 번째 사이트 사용
                        if user_sites:
                            selected_site = user_sites[0]
                    
                    if not selected_site:
                        return "연결된 사이트 정보가 없습니다. 먼저 사이트를 연결해주세요.", None
                    
                    # 선택된 사이트의 도메인 정보 준비
                    current_site_code = selected_site.get('site_code')
                    domain = selected_site.get('primary_domain') or selected_site.get('domain')
                    
                    if not current_site_code or not domain:
                        return "선택된 사이트에 필요한 정보(site_code, domain)가 없습니다.", None
                    
                    site_data = {
                        "site_name": selected_site.get('site_name', current_site_code) or current_site_code,
                        "site_code": current_site_code,
                        "domain": domain
                    }
                    
                    print(f"세션 ID: {session_id}, 사용자 ID: {user_id}, 선택된 사이트: {site_data}")
                    logger.info(f"세션 ID: {session_id}, 사용자 ID: {user_id}, 선택된 사이트: {current_site_code}")
                    
                    # MCP 도구 호출 (단일 사이트 세션 설정)
                    await self.mcp_client.call_tool("set_session_token", {
                        "session_id": session_id,
                        "user_id": user_id,
                        "site": site_data
                    })
                except Exception as e:
                    print(f"세션 사이트 설정 실패: {e}")
                    logger.error(f"세션 사이트 설정 실패: {e}")
                    return "세션 설정에 실패했습니다.", None

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

            # MCP 도구 사용 가능 여부 확인
            available_tools = []
            if self.mcp_client:
                available_tools.append(self.mcp_client.session)
            
            # 두 단계 AI 요청 처리 (멤버십 레벨 포함)
            return await self._two_stage_ai_response(current_scripts_info, conversation_context, available_tools, session_id, image_data, membership_level)

        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            return f"AI 응답 생성 실패: {str(e)}", None

    async def _two_stage_ai_response(self, current_scripts_info: str, conversation_context: str, available_tools: List, session_id: str, image_data: Optional[List[str]] = None, membership_level: int = 0) -> Tuple[str, Optional[Dict]]:
        """
        두 단계 AI 요청 처리
        1단계: MCP 도구 사용으로 데이터 수집
        2단계: thinking 설정으로 구조화된 출력 생성
        """
        try:
            # 멤버십별 AI 모델 및 설정 가져오기
            ai_model = MembershipConfig.get_ai_model(membership_level)
            thinking_budget = MembershipConfig.get_thinking_budget(membership_level)
            
            logger.info(f"멤버십 레벨 {membership_level}: AI 모델={ai_model}, 사고 예산={thinking_budget}")
            
            # 1단계: MCP 도구가 필요한 경우 도구 사용
            structured_response = ""
            if available_tools:
                logger.info("1단계: MCP 도구를 사용하여 데이터 수집 시작")
                
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
                tool_prompt_text = get_english_prompt(current_scripts_info, conversation_context, image_data, session_id)
                
                # contents 구성 (텍스트 + 이미지)
                contents = [tool_prompt_text]
                if image_parts:
                    contents.extend(image_parts)
                
                # 멤버십에 따른 thinking 설정
                thinking_config_params = {"thinking_budget": thinking_budget} if thinking_budget != -1 else {"thinking_budget": -1}
                
                tool_response = await self.gemini_client.aio.models.generate_content(
                    model=ai_model,
                    contents=contents,
                    config=genai.types.GenerateContentConfig(
                        temperature=0.6,
                        tools=available_tools,
                        thinking_config=types.ThinkingConfig(**thinking_config_params)
                    )
                )

                # print("#########\n", tool_response)
                
                # 토큰 사용량 및 비용 계산
                token_info = None
                if hasattr(tool_response, 'usage_metadata') and tool_response.usage_metadata:
                    # 멤버십에 따른 모델명으로 비용 계산
                    token_info = TokenUsageCalculator.calculate_cost(
                        tool_response.usage_metadata, 
                        model_name=ai_model,
                        input_type="text_image_video"  # 기본값, 오디오 처리 시 변경 가능
                    )
                
                # 도구 사용 응답에서 데이터 추출
                if hasattr(tool_response, 'text') and tool_response.text:
                    structured_response = tool_response.text
                elif hasattr(tool_response, 'candidates') and tool_response.candidates:
                    candidate = tool_response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    structured_response += part.text
                
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
                return "AI 응답을 생성할 수 없었습니다. 다시 시도해주세요.", None
            
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
            except json.JSONDecodeError as e:
                # JSON 파싱 실패 시 원본 응답을 message로 사용                
                parsed_response = {
                    "message": structured_response.strip(),
                    "script_updates": None
                }
            if not isinstance(parsed_response, dict):
                raise ValueError("구조화된 출력이 올바른 딕셔너리 형태가 아닙니다")
            
            # AIScriptResponse 스키마에 따라 파싱
            response_text = parsed_response.get('message', '')
            if not response_text:
                # message 필드가 없는 경우 기본 응답 생성
                # logger.warning("AI 응답에 'message' 필드가 없습니다. 기본 응답을 생성합니다.")
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
            
            # logger.info(f"2단계 완료: 메시지 {len(response_text)}자, 메타데이터: {bool(response_metadata)}")
            return response_text, response_metadata
            
        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            return f"AI 응답 생성 실패: 관리자에게 문의하세요.", None