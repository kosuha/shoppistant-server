import json
import logging
from typing import Dict, Any, Optional
from services.script_service import ScriptService
from database_helper import DatabaseHelper
from services.ai_service import AIService

logger = logging.getLogger(__name__)


class ThreadService:
    def __init__(self, db_helper: DatabaseHelper, ai_service: AIService, script_service: ScriptService):
        self.db_helper = db_helper
        self.ai_service = ai_service
        self.script_service = script_service

    async def create_thread(self, user_id: str, site_code: Optional[str] = None) -> Dict[str, Any]:
        """
        새로운 채팅 스레드를 생성합니다.
        
        Args:
            user_id: 사용자 ID
            site_code: 사이트 ID (선택사항)
            
        Returns:
            Dict: 스레드 생성 결과
        """
        try:
            # site_code가 없으면 기본값 사용
            if not site_code:
                site_code = "default"
                
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인 (default는 항상 허용)
            if site_code != "default":
                user_sites = await self.db_helper.get_user_sites(user_id, user_id)
                site_exists = any(site["id"] == site_code for site in user_sites)
                if not site_exists:
                    return {"success": False, "error": "해당 사이트에 접근 권한이 없습니다.", "status_code": 403}

            # 새 스레드를 데이터베이스에 생성
            thread_data = await self.db_helper.create_chat_thread(user_id, site_code)
            
            if not thread_data:
                return {"success": False, "error": "스레드 생성에 실패했습니다.", "status_code": 500}
            
            thread_id = thread_data.get("id")
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='thread_created',
                event_data={'thread_id': thread_id, 'site_code': site_code}
            )
            
            return {"success": True, "data": {"threadId": thread_id}}
            
        except Exception as e:
            logger.error(f"스레드 생성 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def get_user_threads(self, user_id: str) -> Dict[str, Any]:
        """
        사용자의 모든 스레드 목록을 조회합니다.
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Dict: 스레드 목록 조회 결과
        """
        try:
            user_threads = await self.db_helper.get_user_threads(user_id, user_id)
            return {"success": True, "data": {"threads": user_threads}}
            
        except Exception as e:
            logger.error(f"스레드 조회 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def get_thread_by_id(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        """
        특정 스레드의 상세 정보를 조회합니다.
        
        Args:
            user_id: 사용자 ID
            thread_id: 스레드 ID
            
        Returns:
            Dict: 스레드 상세 정보 조회 결과
        """
        try:
            thread = await self.db_helper.get_thread_by_id(user_id, thread_id)
            
            if not thread:
                return {"success": False, "error": "스레드를 찾을 수 없습니다.", "status_code": 404}
            
            return {"success": True, "data": {"thread": thread}}
            
        except Exception as e:
            logger.error(f"스레드 조회 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def delete_thread(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        """
        특정 스레드를 삭제합니다.
        
        Args:
            user_id: 사용자 ID
            thread_id: 스레드 ID
            
        Returns:
            Dict: 스레드 삭제 결과
        """
        try:
            # 먼저 스레드가 존재하고 사용자 소유인지 확인
            thread = await self.db_helper.get_thread_by_id(user_id, thread_id)
            
            if not thread:
                return {"success": False, "error": "스레드를 찾을 수 없습니다.", "status_code": 404}
            
            # 스레드 삭제 (관련 메시지들도 CASCADE로 자동 삭제됨)
            success = await self.db_helper.delete_thread(user_id, thread_id)
            
            if not success:
                return {"success": False, "error": "스레드 삭제에 실패했습니다.", "status_code": 500}
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='thread_deleted',
                event_data={'thread_id': thread_id}
            )
            
            return {"success": True, "message": "스레드가 성공적으로 삭제되었습니다."}
            
        except Exception as e:
            logger.error(f"스레드 삭제 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def update_thread_title(self, user_id: str, thread_id: str, new_title: str) -> Dict[str, Any]:
        """
        스레드 제목을 업데이트합니다.
        
        Args:
            user_id: 사용자 ID
            thread_id: 스레드 ID
            new_title: 새로운 제목
            
        Returns:
            Dict: 제목 업데이트 결과
        """
        try:
            if not new_title or not new_title.strip():
                return {"success": False, "error": "제목이 필요합니다.", "status_code": 400}
            
            if len(new_title) > 200:
                return {"success": False, "error": "제목은 200자를 초과할 수 없습니다.", "status_code": 400}
            
            # 스레드 존재 및 권한 확인
            thread = await self.db_helper.get_thread_by_id(user_id, thread_id)
            if not thread:
                return {"success": False, "error": "스레드를 찾을 수 없습니다.", "status_code": 404}
            
            # 제목 업데이트
            success = await self.db_helper.update_thread_title(thread_id, new_title.strip())
            if not success:
                return {"success": False, "error": "스레드 제목 업데이트에 실패했습니다.", "status_code": 500}
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='thread_title_updated',
                event_data={'thread_id': thread_id, 'new_title': new_title, 'old_title': thread.get('title')}
            )
            
            return {
                "success": True,
                "data": {"thread_id": thread_id, "title": new_title},
                "message": "스레드 제목이 성공적으로 업데이트되었습니다."
            }
            
        except Exception as e:
            logger.error(f"스레드 제목 업데이트 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def get_thread_messages(self, user_id: str, thread_id: str) -> Dict[str, Any]:
        """
        특정 스레드의 모든 메시지를 조회합니다.
        
        Args:
            user_id: 사용자 ID
            thread_id: 스레드 ID
            
        Returns:
            Dict: 메시지 목록 조회 결과
        """
        try:
            # 먼저 스레드가 존재하고 사용자 소유인지 확인
            thread = await self.db_helper.get_thread_by_id(user_id, thread_id)
            if not thread:
                return {"success": False, "error": "스레드를 찾을 수 없습니다.", "status_code": 404}
            
            # 메시지 조회
            messages = await self.db_helper.get_thread_messages(user_id, thread_id)
            
            return {"success": True, "data": {"messages": messages}}
            
        except Exception as e:
            logger.error(f"메시지 조회 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def create_message(self, user_id: str, site_code: str, thread_id: str, message: str, message_type: str = "user", metadata: Optional[str] = None, auto_deploy: bool = False) -> Dict[str, Any]:
        print(f"[THREAD SERVICE] create_message 메시지 생성 요청: user={user_id}, thread={thread_id}, type={message_type} message={message[:50]} metadata={metadata} auto_deploy={auto_deploy}")
        """
        새로운 메시지를 생성합니다.
        사용자가 메시지를 보내면 자동으로 AI 응답을 생성하여 저장합니다.
        
        Args:
            user_id: 사용자 ID
            thread_id: 스레드 ID
            message: 메시지 내용
            message_type: 메시지 타입 (user/assistant/system, 기본값: user)
            metadata: 메타데이터 (선택사항)
            auto_deploy: 자동 배포 여부 (기본값: False)
            
        Returns:
            Dict: 메시지 생성 결과
        """
        try:
            if not message or not message.strip():
                return {"success": False, "error": "메시지 내용이 필요합니다.", "status_code": 400}

            # 메시지 길이 제한 (2000자)
            message = message[:2000]

            print(f"[THREAD SERVICE] create_message 메시지 내용: {message[:50]}...")  # 메시지 내용 미리보기

            # 스레드가 존재하고 사용자 소유인지 확인
            thread = await self.db_helper.get_thread_by_id(user_id, thread_id)
            if not thread:
                return {"success": False, "error": "스레드를 찾을 수 없습니다.", "status_code": 404}

            print(f"[THREAD SERVICE] 스레드 소유확인")

            # 1. 중복 메시지 검사
            if message_type == "user":
                is_duplicate = await self.db_helper.check_duplicate_message(user_id, thread_id, message, message_type)
                if is_duplicate:
                    return {"success": False, "error": "중복 메시지입니다. 잠시 후 다시 시도해주세요.", "status_code": 409}

            print(f"[THREAD SERVICE] 메시지 중복확인")

            # 스레드의 첫 메시지인 경우, 스레드의 title을 메시지로 설정
            if not thread.get('title'):
                try:
                    # 스레드 제목을 메시지로 설정
                    await self.db_helper.update_thread_title(thread_id, message)
                    thread['title'] = message  # 메모리에서도 업데이트
                except Exception as title_error:
                    logger.error(f"스레드 제목 업데이트 실패: {title_error}")

            print(f"[THREAD SERVICE] 스레드 제목 업데이트: {thread.get('title')}")

            # 2. 사용자 메시지 저장
            user_message = await self.db_helper.create_message(
                requesting_user_id=user_id,
                thread_id=thread_id,
                message=message,
                message_type=message_type,
                metadata=metadata
            )
            print(f"[THREAD SERVICE] 사용자 메시지 저장 완료: {user_message}")
            
            if not user_message:
                return {"success": False, "error": "메시지 저장에 실패했습니다.", "status_code": 500}

            # 3. AI 응답 생성 (user 메시지 타입인 경우에만)
            ai_message = None
            if message_type == "user":
                try:
                    # 스레드의 전체 대화 내역 조회 (새로 추가된 사용자 메시지 포함)
                    chat_history = await self.db_helper.get_thread_messages(user_id, thread_id)
                    
                    # AI 응답 생성 (메타데이터 포함)
                    ai_response_result = await self.ai_service.generate_gemini_response(chat_history, user_id, metadata)
                    
                    # AI 응답 결과 검증
                    if ai_response_result is None:
                        raise ValueError("AI 서비스에서 None을 반환했습니다.")
                    
                    # 튜플 언패킹
                    if isinstance(ai_response_result, tuple) and len(ai_response_result) == 2:
                        ai_response, ai_metadata = ai_response_result
                    else:
                        raise ValueError(f"AI 서비스에서 예상치 못한 형태의 응답을 받았습니다: {type(ai_response_result)}")
                    
                    if ai_metadata and auto_deploy:
                        if not isinstance(ai_metadata, dict):
                            raise TypeError(f"AI 메타데이터는 dict 타입이어야 합니다. 현재 타입: {type(ai_metadata)}")
                        script_dict = ai_metadata.get("script_updates", {}).get("script", {})
                        if script_dict:
                            script_content = script_dict.get("content", "")
                            result = await self.script_service.deploy_site_scripts(user_id, site_code, {"script": script_content})
                            if not result["success"]:
                                raise ValueError(f"스크립트 자동 배포 실패: {result['error']}")

                    # AI 메타데이터를 JSON 문자열로 변환
                    ai_metadata_json = None
                    if ai_metadata:
                        try:
                            ai_metadata_json = json.dumps(ai_metadata, ensure_ascii=False)
                        except (TypeError, ValueError) as json_error:
                            logger.warning(f"AI 메타데이터 직렬화 실패: {json_error}")
                            ai_metadata_json = None
                    
                    # AI 응답 저장
                    ai_message = await self.db_helper.create_message(
                        requesting_user_id=user_id,
                        thread_id=thread_id,
                        message=ai_response,
                        message_type="assistant",
                        metadata=ai_metadata_json
                    )
                    
                    if not ai_message:
                        logger.warning("AI 응답 저장에 실패했습니다.")
                        
                except Exception as ai_error:
                    # AI 응답 생성 실패는 에러를 던지지 않고 로그만 남김
                    logger.error(f"AI 응답 생성 실패: {str(ai_error)}")

            # 4. 로그 기록
            try:
                await self.db_helper.log_system_event(
                    user_id=user_id,
                    event_type='message_created',
                    event_data={
                        'thread_id': thread_id,
                        'message_type': message_type,
                        'has_ai_response': bool(ai_message)
                    }
                )
            except Exception as log_error:
                logger.error(f"로그 기록 실패: {str(log_error)}")

            # 응답 구성
            response_data = {
                "success": True,
                "data": {"user_message": user_message},
                "message": "메시지가 성공적으로 저장되었습니다."
            }
            
            if ai_message:
                response_data["data"]["ai_message"] = ai_message

            return response_data
            
        except Exception as e:
            logger.error(f"메시지 생성 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}