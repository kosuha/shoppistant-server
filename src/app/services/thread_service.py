import json
import logging
from typing import Dict, Any, Optional, List
from services.script_service import ScriptService
from database_helper import DatabaseHelper
from services.ai_service import AIService
from core.membership_config import MembershipConfig

logger = logging.getLogger(__name__)


class ThreadService:
    def __init__(self, db_helper: DatabaseHelper, ai_service: AIService, script_service: ScriptService):
        self.db_helper = db_helper
        self.ai_service = ai_service
        self.script_service = script_service
    
    async def _check_membership_limits(self, user_id: str, action: str, **kwargs) -> Dict[str, Any]:
        """멤버십 제한사항 확인"""
        try:
            # 사용자 멤버십 정보 조회
            membership = await self.db_helper.get_user_membership(user_id)
            membership_level = membership.get('membership_level', 0) if membership else 0
            
            features = MembershipConfig.get_features(membership_level)
            
            # 이미지 업로드 가능 여부 확인
            if action == 'image_upload':
                if not features.is_image_uploads:
                    return {
                        "allowed": False,
                        "error": f"멤버십 레벨 {membership_level}에서는 이미지 업로드가 허용되지 않습니다.",
                        "required_level": 1
                    }
            
            # 사이트 연결 수 제한 확인
            elif action == 'site_connection':
                if features.max_sites != -1:
                    user_sites = await self.db_helper.get_user_sites(user_id, user_id)
                    current_sites = len(user_sites)
                    if current_sites >= features.max_sites:
                        return {
                            "allowed": False,
                            "error": f"멤버십 레벨 {membership_level}에서는 최대 {features.max_sites}개의 사이트만 연결할 수 있습니다.",
                            "limit": features.max_sites,
                            "current": current_sites
                        }
            
            return {"allowed": True, "membership_level": membership_level, "features": features}
            
        except Exception as e:
            logger.error(f"멤버십 제한 확인 실패: {e}")
            # 에러 시 기본 등급으로 처리
            return {"allowed": True, "membership_level": 0}

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

    async def create_message(self, user_id: str, site_code: str, thread_id: str, message: str, message_type: str = "user", metadata: Optional[str] = None, auto_deploy: bool = False, image_data: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        새로운 메시지를 생성합니다.
        사용자가 메시지를 보내면 자동으로 AI 응답을 생성하여 저장합니다.
        
        Args:
            user_id: 사용자 ID
            site_code: 사이트 코드
            thread_id: 스레드 ID
            message: 메시지 내용
            message_type: 메시지 타입 (user/assistant/system, 기본값: user)
            metadata: 메타데이터 (선택사항)
            auto_deploy: 자동 배포 여부 (기본값: False)
            image_data: 이미지 데이터 배열 (Base64 형식, 선택사항)
            
        Returns:
            Dict: 메시지 생성 결과
        """
        try:
            if not message or not message.strip():
                return {"success": False, "error": "메시지 내용이 필요합니다.", "status_code": 400}

            # 메시지 길이 제한 (2000자)
            message = message[:2000]

            # 스레드가 존재하고 사용자 소유인지 확인
            thread = await self.db_helper.get_thread_by_id(user_id, thread_id)
            if not thread:
                return {"success": False, "error": "스레드를 찾을 수 없습니다.", "status_code": 404}

            # 멤버십 제한사항 확인
            if image_data:
                limit_check = await self._check_membership_limits(user_id, 'image_upload', image_count=len(image_data))
                if not limit_check.get('allowed', True):
                    return {"success": False, "error": limit_check['error'], "status_code": 403}
            
            if auto_deploy:
                limit_check = await self._check_membership_limits(user_id, 'auto_deploy')
                if not limit_check.get('allowed', True):
                    return {"success": False, "error": limit_check['error'], "status_code": 403}

            # 1. 중복 메시지 검사
            if message_type == "user":
                is_duplicate = await self.db_helper.check_duplicate_message(user_id, thread_id, message, message_type)
                if is_duplicate:
                    return {"success": False, "error": "중복 메시지입니다. 잠시 후 다시 시도해주세요.", "status_code": 409}

            # 스레드의 첫 메시지인 경우, 스레드의 title을 메시지로 설정
            if not thread.get('title'):
                try:
                    # 스레드 제목을 메시지로 설정
                    await self.db_helper.update_thread_title(thread_id, message)
                    thread['title'] = message  # 메모리에서도 업데이트
                except Exception as title_error:
                    logger.error(f"스레드 제목 업데이트 실패: {title_error}")

            # 2. 사용자 메시지 저장 (사용자 메시지는 즉시 completed 상태)
            user_message = await self.db_helper.create_message(
                requesting_user_id=user_id,
                thread_id=thread_id,
                message=message,
                message_type=message_type,
                metadata=metadata,
                status='completed' if message_type == 'user' else 'pending',
                image_data=image_data
            )
            
            if not user_message:
                return {"success": False, "error": "메시지 저장에 실패했습니다.", "status_code": 500}

            # 3. AI 응답 생성 (user 메시지 타입인 경우에만)
            ai_message = None
            if message_type == "user":
                try:
                    # 먼저 pending 상태의 AI 메시지 생성
                    ai_message = await self.db_helper.create_message(
                        requesting_user_id=user_id,
                        thread_id=thread_id,
                        message="",
                        message_type="assistant",
                        metadata=None,
                        status='pending'
                    )
                    
                    if ai_message:
                        # 상태를 in_progress로 업데이트
                        await self.db_helper.update_message_status(
                            requesting_user_id=user_id,
                            message_id=ai_message['id'],
                            status='in_progress'
                        )
                        
                        # SSE 브로드캐스트
                        await self._broadcast_status_update(thread_id, ai_message['id'], 'in_progress')
                    
                    # 스레드의 전체 대화 내역 조회 (새로 추가된 사용자 메시지 포함)
                    chat_history = await self.db_helper.get_thread_messages(user_id, thread_id)
                    
                    # 일일 요청 제한 확인
                    membership = await self.db_helper.get_user_membership(user_id)
                    membership_level = membership.get('membership_level', 0) if membership else 0
                    features = MembershipConfig.get_features(membership_level)
                    
                    # skip_ai_generation 변수를 먼저 초기화
                    skip_ai_generation = False
                    
                    if features.daily_requests != -1:
                        current_count = await self.db_helper.get_daily_request_count(user_id)
                        if current_count >= features.daily_requests:
                            # 제한 초과 시 AI 응답 대신 안내 메시지 전송
                            limit_message = f"죄송합니다. 오늘의 메시지 전송 횟수({features.daily_requests}회)를 모두 사용하셨습니다.\n\n" \
                                          f"내일 0시에 요청 횟수가 초기화됩니다.\n" \
                                          f"더 많은 메시지를 보내시려면 요금제를 업그레이드해주세요!"
                            
                            # 제한 안내 메시지로 AI 응답 대체
                            ai_response = limit_message
                            ai_metadata = {"rate_limited": True, "daily_limit": features.daily_requests}
                            
                            # AI 응답 생성을 건너뛰고 바로 메시지 업데이트로 이동
                            skip_ai_generation = True
                    
                    if not skip_ai_generation:
                        # AI 응답 생성 (메타데이터 및 사이트 코드, 이미지 데이터 포함)
                        ai_response_result = await self.ai_service.generate_gemini_response(chat_history, user_id, metadata, site_code, image_data)
                        
                        # 일일 요청 수 증가 (정상 AI 응답인 경우에만)
                        await self.db_helper.increment_daily_request(user_id, 'message_send')
                    
                    # AI 응답 결과 처리
                    if not skip_ai_generation:
                        # AI 응답 결과 검증
                        if ai_response_result is None:
                            raise ValueError("AI 서비스에서 None을 반환했습니다.")
                        
                        # 튜플 언패킹
                        if isinstance(ai_response_result, tuple) and len(ai_response_result) == 2:
                            ai_response, ai_metadata = ai_response_result
                        else:
                            raise ValueError(f"AI 서비스에서 예상치 못한 형태의 응답을 받았습니다: {type(ai_response_result)}")
                    # skip_ai_generation이 True인 경우 ai_response와 ai_metadata는 이미 설정됨
                    
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
                    
                    # AI 응답 완료 - 메시지 업데이트 (비용 및 모델 정보 포함)
                    if ai_message:
                        # 토큰 비용 정보 및 모델 정보 추출
                        cost_usd = 0.0
                        ai_model = None
                        if ai_metadata and 'token_usage' in ai_metadata:
                            cost_usd = ai_metadata['token_usage'].get('total_cost_usd', 0.0)
                            ai_model = ai_metadata['token_usage'].get('model_name', None)
                        
                        # AI 응답에서 changes 데이터 처리 (통일된 형식)
                        changes_data = None
                        if ai_metadata:
                            changes_data = ai_metadata.get('changes')
                            if changes_data:
                        
                        # AI 응답 업데이트 전 로깅
                        
                        success = await self.db_helper.update_message_status(
                            requesting_user_id=user_id,
                            message_id=ai_message['id'],
                            status='completed',
                            message=ai_response,
                            metadata=ai_metadata_json,
                            cost_usd=cost_usd,
                            ai_model=ai_model
                        )
                        
                        if not success:
                            logger.warning("AI 응답 업데이트에 실패했습니다.")
                        else:
                            # 응답을 위해 ai_message 업데이트 (클라이언트가 받을 수 있도록)
                            ai_message['message'] = ai_response
                            ai_message['status'] = 'completed'
                            ai_message['metadata'] = ai_metadata_json
                            ai_message['cost_usd'] = cost_usd
                            ai_message['ai_model'] = ai_model
                            
                            # Changes 데이터를 클라이언트 응답에 추가
                            if changes_data:
                                ai_message['changes'] = changes_data
                            
                            
                            # SSE 브로드캐스트 - 완료 상태 (메타데이터 포함)
                            await self._broadcast_status_update(thread_id, ai_message['id'], 'completed', ai_response, ai_metadata)
                    else:
                        logger.warning("AI 메시지 생성에 실패했습니다.")
                        
                except Exception as ai_error:
                    # AI 응답 생성 실패 시 에러 상태로 업데이트
                    logger.error(f"AI 응답 생성 실패: {str(ai_error)}")
                    if ai_message:
                        await self.db_helper.update_message_status(
                            requesting_user_id=user_id,
                            message_id=ai_message['id'],
                            status='error',
                            message=f"AI 응답 생성 중 오류가 발생했습니다: {str(ai_error)}"
                        )
                        # SSE 브로드캐스트 - 에러 상태
                        await self._broadcast_status_update(thread_id, ai_message['id'], 'error', f"AI 응답 생성 중 오류가 발생했습니다: {str(ai_error)}")

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

    async def update_message_status(self, user_id: str, message_id: str, status: str, 
                                  message: str = None, metadata: dict = None) -> Dict[str, Any]:
        """
        메시지 상태를 업데이트합니다.
        
        Args:
            user_id: 사용자 ID
            message_id: 메시지 ID
            status: 새로운 상태 ('pending', 'in_progress', 'completed', 'error')
            message: 메시지 내용 (선택적)
            metadata: 메타데이터 (선택적)
            
        Returns:
            Dict: 업데이트 결과
        """
        try:
            if status not in ["pending", "in_progress", "completed", "error"]:
                return {"success": False, "error": "유효하지 않은 상태값입니다.", "status_code": 400}
            
            success = await self.db_helper.update_message_status(
                requesting_user_id=user_id,
                message_id=message_id,
                status=status,
                message=message,
                metadata=metadata
            )
            
            if not success:
                return {"success": False, "error": "메시지 상태 업데이트에 실패했습니다.", "status_code": 500}
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='message_status_updated',
                event_data={'message_id': message_id, 'new_status': status}
            )
            
            return {
                "success": True,
                "data": {"message_id": message_id, "status": status},
                "message": "메시지 상태가 성공적으로 업데이트되었습니다."
            }
            
        except Exception as e:
            logger.error(f"메시지 상태 업데이트 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def _broadcast_status_update(self, thread_id: str, message_id: str, status: str, message: str = None, metadata: dict = None):
        """메시지 상태 변화를 SSE 구독자들에게 브로드캐스트"""
        try:
            # 순환 import 방지를 위해 동적 import
            from routers.sse_router import broadcast_message_status
            await broadcast_message_status(thread_id, message_id, status, message, metadata)
        except Exception as e:
            logger.error(f"SSE 브로드캐스트 실패: {e}")