from fastmcp import Client
from google import genai
from google.genai import types
from typing import List, Dict, Any, Tuple, Optional
import json
import logging
from database_helper import DatabaseHelper
from schemas import AIScriptResponse

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self, gemini_client: genai.Client, playwright_mcp_client: Optional[Client], db_helper: DatabaseHelper):
        self.gemini_client = gemini_client
        self.playwright_mcp_client = playwright_mcp_client
        self.db_helper = db_helper

    def parse_metadata_scripts(self, metadata: str) -> dict:
        """
        메타데이터에서 현재 스크립트 정보를 파싱합니다.
        
        Args:
            metadata: JSON 형태의 메타데이터
            
        Returns:
            dict: 파싱된 스크립트 정보
        """
        try:
            if not metadata:
                return {}
                
            parsed_metadata = json.loads(metadata) if isinstance(metadata, str) else metadata
            current_scripts = parsed_metadata.get('current_scripts', {})
            
            return {
                'header': current_scripts.get('header', ''),
                'body': current_scripts.get('body', ''),
                'footer': current_scripts.get('footer', '')
            }
        except (json.JSONDecodeError, TypeError):
            return {}

    async def generate_gemini_response(self, chat_history: List[Dict], user_id: str, metadata: Optional[str] = None) -> Tuple[str, Optional[Dict]]:
        """
        대화 내역을 기반으로 Gemini API를 호출하여 AI 응답을 생성합니다.
        구조화된 출력을 사용합니다.
        
        Args:
            chat_history: 대화 내역 리스트
            user_id: 사용자 ID
            metadata: 메타데이터 (현재 스크립트 정보 포함 가능)
            
        Returns:
            tuple: (응답 텍스트, 메타데이터)
        """
        try:
            # 1. 사용자의 모든 사이트 정보 가져오기 (토큰 검증 목적)
            user_sites = await self.db_helper.get_user_sites(user_id, user_id)
            if not user_sites:
                return "아임웹 사이트가 연결되지 않았습니다. 먼저 사이트를 연결해주세요.", None
            
            # 2. 현재 스크립트 정보 추출
            current_scripts = self.parse_metadata_scripts(metadata)
            
            # 3. 최신 사용자 메시지 확인
            latest_user_message = ""
            if chat_history:
                for msg in reversed(chat_history):
                    if msg.get("message_type") == "user":
                        latest_user_message = msg.get("message", "")
                        break
            
            # 5. 대화 내역을 Gemini 형식으로 변환
            contents = []
            for msg in chat_history:
                created_at = msg.get('created_at', '')
                if msg["message_type"] == "user":
                    contents.append(f"User ({created_at}): {msg['message']}")
                elif msg["message_type"] == "assistant":
                    contents.append(f"Assistant ({created_at}): {msg['message']}")
            
            conversation_context = "\n".join(contents)
            
            # 7. 현재 스크립트 정보 문자열 생성
            current_scripts_info = ""
            if current_scripts:
                if current_scripts.get('header'):
                    current_scripts_info += f"\n- 헤더 스크립트: {current_scripts['header'][:200]}{'...' if len(current_scripts['header']) > 200 else ''}"
                if current_scripts.get('body'):
                    current_scripts_info += f"\n- 바디 스크립트: {current_scripts['body'][:200]}{'...' if len(current_scripts['body']) > 200 else ''}"
                if current_scripts.get('footer'):
                    current_scripts_info += f"\n- 푸터 스크립트: {current_scripts['footer'][:200]}{'...' if len(current_scripts['footer']) > 200 else ''}"
            
            if not current_scripts_info:
                current_scripts_info = "\n- 현재 등록된 스크립트가 없습니다."
            
            # 8. 시스템 프롬프트 구성
            prompt = f"""
            당신은 아임웹 사이트에 스크립트를 추가하는 것을 도와주는 AI 어시스턴트입니다. 

            당신은 playwright를 사용하여 사용자의 아임웹 사이트 소스코드를 상세하게 분석하고,
            사용자의 요구에 따라 적절한 스크립트를 작성합니다.
            아임웹 스크립트는 JavaScript 코드만 포함할 수 있으며, header, body, footer 위치에 따라 구분됩니다.
            사용자의 요구 사항을 고려하여 head, body, footer 중 적절한 위치에 스크립트를 작성하세요.
            보통 footer에 스크립트를 작성하는 것이 일반적입니다.

            # 현재 사이트의 스크립트 상황:
            {current_scripts_info}

            # 스크립트 코딩 규칙:
            코딩 전 반드시 사용자의 요구 사항을 이해하고, 필요한 경우 추가 질문을 통해 명확히 하세요.
            사용자의 아임웹 사이트 소스코드를 분석하여, 요구 사항에 맞는 스크립트를 작성하세요.
            JavaScript 코드를 삽입할 때는 반드시 <script> 태그로 감싸야 합니다.
            사용자의 특별한 요청이 없다면 특정 엘리먼트를 선택하거나 조작할 때는 태그의 구조, 클래스, ID 등을 활용하세요.
            엘리먼트 내부의 텍스트만 이용하여 엘리먼트를 찾는 방법은 위험할 수 있습니다.
            선택하려는 엘리먼트의 클래스, ID, 부모자식 구조를 이용해서 queryselector 또는 queryselectorAll을 사용하는 것을 권장합니다.
            기존 엘리먼트의 속성을 변경하는 것은 아임웹 정책상 허용되지 않는 경우가 많으니, 새로운 엘리먼트를 추가하는 방법을 권장합니다.
            스타일을 지정할때는 아임웹의 스타일과 겹치지 않게 반드시 important를 사용하세요.
            기존 스크립트가 있다면 사용자의 요구에 맞게 기존 스크립트를 수정하거나 대체하세요.
            기존 스크립트가 없다면 사용자의 요구에 맞게 새로운 스크립트를 작성하세요.
            당신이 작성한 스크립트는 사용자가 사용하는 스크립트 에디터에 즉시 반영됩니다.

            # 규칙:
            친절하게 마지막 질문에 답변해주세요.
            사용자의 요구를 충족하기위해 어떤 도구를 사용해야하는지 반드시 단계별로 계획을 세우고 순차적으로 도구를 호출하여 계획을 실행하세요.
            답변은 정보를 보기 좋게 마크다운 형식으로 정리해서 작성하세요.
            도구 호출에 실패한 경우 에러 'message'를 반드시 사용자에게 알리세요.

            # 대화 내역:
            {conversation_context}
            """

            # 8. Playwright MCP 도구 사용 가능 여부 확인
            available_tools = []
            if self.playwright_mcp_client:
                available_tools.append(self.playwright_mcp_client.session)
            
            response_text = ""
            response_metadata = None
            
            # 구조화된 출력으로 스크립트 수정 요청 처리
            try:
                if available_tools:
                    structured_response = await self.gemini_client.aio.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            temperature=0.7,
                            tools=available_tools,
                            response_mime_type="application/json",
                            response_schema=AIScriptResponse.model_json_schema(),
                            thinking_config=types.ThinkingConfig(thinking_budget=-1)
                        ),
                    )
                else:
                    structured_response = self.gemini_client.models.generate_content(
                        model="gemini-2.5-flash",
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            temperature=0.6,
                            response_mime_type="application/json",
                            response_schema=AIScriptResponse.model_json_schema()
                        )
                    )
                
                # 구조화된 응답에서 JSON 텍스트 추출
                json_text = ""
                
                # 1. structured_response.text 우선 사용
                if hasattr(structured_response, 'text') and structured_response.text:
                    json_text = structured_response.text
                # 2. candidates에서 추출 (fallback)
                elif hasattr(structured_response, 'candidates') and structured_response.candidates:
                    candidate = structured_response.candidates[0]
                    if hasattr(candidate, 'content') and candidate.content:
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            for part in candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    json_text += part.text
                
                # 구조화된 응답 파싱 (항상 JSON이어야 함)
                if not json_text:
                    raise ValueError("구조화된 출력에서 텍스트를 추출할 수 없습니다")
                
                try:
                    parsed_response = json.loads(json_text)
                    if not isinstance(parsed_response, dict):
                        raise ValueError("구조화된 출력이 올바른 딕셔너리 형태가 아닙니다")
                    
                    # AIScriptResponse 스키마에 따라 파싱
                    response_text = parsed_response.get('message', '')
                    if not response_text:
                        raise ValueError("구조화된 출력에 'message' 필드가 없습니다")
                    
                    # 스크립트 업데이트 정보 추출
                    response_metadata = None
                    script_updates = parsed_response.get('script_updates')
                    if script_updates:
                        response_metadata = {
                            'script_updates': script_updates
                        }
                    
                    logger.info(f"구조화된 출력 파싱 성공 - 메시지: {len(response_text)}자, 메타데이터: {bool(response_metadata)}")
                    
                except (json.JSONDecodeError, ValueError) as parse_error:
                    logger.error(f"구조화된 출력 파싱 실패: {parse_error}")
                    logger.debug(f"원본 응답: {json_text[:500]}...")
                    raise ValueError(f"구조화된 출력 파싱 실패: {parse_error}")
                        
            except Exception as structured_error:
                logger.error(f"구조화된 출력 생성 실패: {structured_error}")
                # 구조화된 출력 실패시 오류 반환 (fallback 제거)
                response_text = f"구조화된 출력 생성에 실패했습니다: {str(structured_error)}"
                response_metadata = None
            
            # 응답 반환
            return response_text, response_metadata
            
        except Exception as e:
            logger.error(f"AI 응답 생성 실패: {e}")
            return f"AI 응답 생성 실패: {str(e)}", None