"""
데이터베이스 연결 및 CRUD 작업을 위한 헬퍼 모듈
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, date
from supabase import Client
import logging
import os
import math

logger = logging.getLogger(__name__)
UNSET = object()

class DatabaseHelper:
    def __init__(self, supabase_client: Client, admin_client: Client = None):
        self.supabase = supabase_client
        self.admin_client = admin_client or supabase_client

    def _get_client(self, use_admin: bool = False):
        """적절한 클라이언트 반환 - 일반적으로 admin client 사용"""
        return self.admin_client if use_admin or self.admin_client else self.supabase
    
    def _verify_user_access(self, user_id: str, resource_user_id: str):
        """사용자가 리소스에 접근할 권한이 있는지 서버에서 검증"""
        if user_id != resource_user_id:
            raise PermissionError(f"사용자 {user_id}는 다른 사용자의 리소스에 접근할 수 없습니다.")

    @staticmethod
    def _parse_iso_datetime(value: Any) -> Optional[datetime]:
        """ISO 포맷 문자열을 datetime 객체로 변환 (Z 접두 처리 포함)"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                normalized = value.replace('Z', '+00:00')
                return datetime.fromisoformat(normalized)
            except Exception:
                return None
        return None
    
    async def create_user_profile(self, user_id: str, display_name: str = None) -> Dict[str, Any]:
        """사용자 프로필 생성"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_profiles').insert({
                'id': user_id,
                'display_name': display_name,
                'preferences': {}
            }).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"사용자 프로필 생성 실패: {e}")
            return {}
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 프로필 조회"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_profiles').select('*').eq('id', user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"사용자 프로필 조회 실패: {e}")
            return None
    
    # User Sites 관련 함수들
    async def get_user_sites(self, requesting_user_id: str, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 연결된 사이트 목록 조회"""
        try:
            # 권한 검증
            self._verify_user_access(requesting_user_id, user_id)
            
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[SERVICE] 사용자 사이트 조회 실패: {e}")
            return []
    
    async def create_user_site(self, user_id: str, site_code: str, site_name: str = None, 
                             unit_code: str = None, domain: str = None) -> Dict[str, Any]:
        """새로운 사이트 연결 생성"""
        try:
            site_data = {
                'user_id': user_id,
                'site_code': site_code,
                'site_name': site_name,
                'unit_code': unit_code,
                'primary_domain': domain
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').insert(site_data).execute()
            
            # 사이트 생성 성공 시 기본 빈 스크립트 데이터도 생성
            if result.data:
                await self._create_default_script(user_id, site_code)
            
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"사이트 연결 생성 실패: {e}")
            return {}
    
    
    async def get_user_site_by_code(self, user_id: str, site_code: str) -> Optional[Dict[str, Any]]:
        """사이트 코드로 사용자 사이트 조회"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').select('*').eq('user_id', user_id).eq('site_code', site_code).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"사이트 조회 실패: {e}")
            return None
    
    # Chat Threads 관련 함수들
    async def create_chat_thread(self, user_id: str, site_code: str = None, title: str = None) -> Dict[str, Any]:
        """새로운 채팅 스레드 생성"""
        try:
            thread_data = {
                'user_id': user_id,
                'site_code': site_code,
                'title': title
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_threads').insert(thread_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"채팅 스레드 생성 실패: {e}")
            return {}
    
    async def get_user_threads(self, requesting_user_id: str, user_id: str) -> List[Dict[str, Any]]:
        """사용자의 모든 스레드 조회"""
        try:
            # 권한 검증
            self._verify_user_access(requesting_user_id, user_id)
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_threads').select('*').eq('user_id', user_id).order('last_message_at', desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"사용자 스레드 조회 실패: {e}")
            return []
    
    async def get_thread_by_id(self, requesting_user_id: str, thread_id: str) -> Optional[Dict[str, Any]]:
        """스레드 ID로 스레드 조회"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('chat_threads').select('*').eq('id', thread_id).execute()
            
            if result.data:
                thread = result.data[0]
                # 권한 검증 - 스레드 소유자인지 확인
                self._verify_user_access(requesting_user_id, thread['user_id'])
                return thread
            return None
        except Exception as e:
            logger.error(f"스레드 조회 실패: {e}")
            return None
    
    async def delete_thread(self, requesting_user_id: str, thread_id: str) -> bool:
        """스레드 삭제"""
        try:
            # 먼저 스레드 조회하여 권한 확인
            thread = await self.get_thread_by_id(requesting_user_id, thread_id)
            if not thread:
                return False
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_threads').delete().eq('id', thread_id).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"스레드 삭제 실패: {e}")
            return False
    
    # Chat Messages 관련 함수들
    async def create_message(self, requesting_user_id: str, thread_id: str, message: str, 
                           message_type: str = 'user', metadata: Dict = None, status: str = 'completed', 
                           image_data: List[str] = None, cost_usd: float = 0.0, ai_model: str = None) -> Dict[str, Any]:
        """새로운 메시지 생성"""
        try:
            # 스레드 소유권 확인
            thread = await self.get_thread_by_id(requesting_user_id, thread_id)
            if not thread:
                raise PermissionError("스레드에 접근할 권한이 없습니다.")
            
            message_data = {
                'thread_id': thread_id,
                'user_id': requesting_user_id,
                'message': message,
                'message_type': message_type,
                'status': status,
                'metadata': metadata or {},
                'image_data': image_data,
                'cost_usd': cost_usd,
                'ai_model': ai_model
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_messages').insert(message_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"메시지 생성 실패: {e}")
            return {}
    
    async def update_message_status(self, requesting_user_id: str, message_id: str, status: str, 
                                  message: str = None, metadata: Dict = None, cost_usd: float = None, ai_model: str = None) -> bool:
        """메시지 상태 업데이트"""
        try:
            # 메시지 소유권 확인
            client = self._get_client(use_admin=True)
            message_result = client.table('chat_messages').select('*').eq('id', message_id).execute()
            
            if not message_result.data:
                return False
                
            message_data = message_result.data[0]
            
            # 스레드 소유권 확인
            thread = await self.get_thread_by_id(requesting_user_id, message_data['thread_id'])
            if not thread:
                raise PermissionError("메시지에 접근할 권한이 없습니다.")
            
            # 업데이트할 데이터 준비
            update_data = {'status': status}
            if message is not None:
                update_data['message'] = message
            if metadata is not None:
                update_data['metadata'] = metadata
            if cost_usd is not None:
                update_data['cost_usd'] = cost_usd
            if ai_model is not None:
                update_data['ai_model'] = ai_model
            
            # 메시지 상태 업데이트
            result = client.table('chat_messages').update(update_data).eq('id', message_id).execute()
            return bool(result.data)
            
        except Exception as e:
            logger.error(f"메시지 상태 업데이트 실패: {e}")
            return False
    
    async def get_thread_messages(self, requesting_user_id: str, thread_id: str) -> List[Dict[str, Any]]:
        """스레드의 모든 메시지 조회"""
        try:
            # 스레드 소유권 확인
            thread = await self.get_thread_by_id(requesting_user_id, thread_id)
            if not thread:
                raise PermissionError("스레드에 접근할 권한이 없습니다.")
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_messages').select('*').eq('thread_id', thread_id).order('created_at', desc=False).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"스레드 메시지 조회 실패: {e}")
            return []
    
    async def check_duplicate_message(self, requesting_user_id: str, thread_id: str, message: str, 
                                    message_type: str = 'user', seconds: int = 1) -> bool:
        """중복 메시지 검사"""
        try:
            # 스레드 소유권 확인
            thread = await self.get_thread_by_id(requesting_user_id, thread_id)
            if not thread:
                return False  # 접근 권한 없으면 중복 아니라고 처리
            
            # 최근 몇 초 이내에 같은 메시지가 있는지 확인
            cutoff_time = datetime.now().replace(microsecond=0).isoformat()
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_messages').select('created_at').eq('thread_id', thread_id).eq('user_id', requesting_user_id).eq('message', message).eq('message_type', message_type).gte('created_at', cutoff_time).execute()
            
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"중복 메시지 검사 실패: {e}")
            return False
    
    # 시스템 로그 관련 함수들
    async def log_system_event(self, user_id: str = None, event_type: str = 'info', 
                             event_data: Dict = None, ip_address: str = None, 
                             user_agent: str = None) -> bool:
        """시스템 이벤트 로그 기록"""
        try:
            log_data = {
                'user_id': user_id,
                'event_type': event_type,
                'event_data': event_data or {},
                'ip_address': ip_address,
                'user_agent': user_agent
            }
            
            result = self.admin_client.table('system_logs').insert(log_data).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"시스템 로그 기록 실패: {e}")
            return False

    async def log_admin_action(
        self,
        actor_id: Optional[str],
        action: str,
        target_user: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """관리자 작업 감사 로그 기록"""
        event_payload: Dict[str, Any] = {
            'actor_id': actor_id,
            'action': action,
        }
        if metadata:
            event_payload['metadata'] = metadata

        return await self.log_system_event(
            user_id=target_user,
            event_type='admin_action',
            event_data=event_payload,
        )

    async def record_admin_refund_request(
        self,
        actor_id: Optional[str],
        actor_email: Optional[str],
        user_id: str,
        transaction_id: str,
        reason: Optional[str] = None,
    ) -> bool:
        """관리자 환불 요청을 시스템 로그에 기록"""
        if not transaction_id:
            raise ValueError("transaction_id is required")

        payload: Dict[str, Any] = {
            'transaction_id': transaction_id,
            'requested_by': actor_id,
            'requested_email': actor_email,
            'requested_at': datetime.utcnow().isoformat() + 'Z',
        }
        if reason:
            payload['reason'] = reason

        return await self.log_system_event(
            user_id=user_id,
            event_type='admin_refund_request',
            event_data=payload,
        )

    async def list_admin_events(
        self,
        event_type: str = "all",
        status: str = "all",
        start: Optional[str] = None,
        end: Optional[str] = None,
        query: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """관리자 이벤트 로그 목록 조회"""
        try:
            client = self._get_client(use_admin=True)

            def _normalize_date(value: str, is_end: bool = False) -> str:
                if not value:
                    return value
                if len(value) == 10:
                    suffix = "23:59:59" if is_end else "00:00:00"
                    return f"{value}T{suffix}Z"
                return value

            max_page_size = max(1, min(page_size, 100))
            fetch_limit = 500

            query_builder = (
                client.table('system_logs')
                .select('*')
                .eq('event_type', 'paddle_webhook')
                .order('created_at', desc=True)
                .limit(fetch_limit)
            )

            if start:
                query_builder = query_builder.gte('created_at', _normalize_date(start, False))
            if end:
                query_builder = query_builder.lte('created_at', _normalize_date(end, True))

            response = query_builder.execute()
            records = response.data or []

            normalized_type = (event_type or "all").lower()
            normalized_status = (status or "all").lower()
            search = (query or "").strip().lower()

            formatted_events: List[Dict[str, Any]] = []
            for record in records:
                formatted = self._format_admin_event_record(record)
                if not formatted:
                    continue

                summary = formatted['summary']

                if normalized_type != "all" and (summary.get('type') or "unknown") != normalized_type:
                    continue

                if normalized_status != "all" and (summary.get('status') or "unknown") != normalized_status:
                    continue

                if search:
                    haystack = [
                        summary.get('event_id') or "",
                        summary.get('user_email') or "",
                        summary.get('user_id') or "",
                        summary.get('transaction_id') or "",
                    ]
                    haystack = [str(item).lower() for item in haystack if item]
                    if not any(search in item for item in haystack):
                        continue

                formatted_events.append(summary)

            total_items = len(formatted_events)
            total_pages = max(1, math.ceil(total_items / max_page_size))
            current_page = max(1, min(page, total_pages))
            start_index = (current_page - 1) * max_page_size
            end_index = start_index + max_page_size

            paged_events = formatted_events[start_index:end_index]

            return {
                "events": paged_events,
                "pagination": {
                    "page": current_page,
                    "page_size": max_page_size,
                    "total_pages": total_pages,
                    "total_items": total_items,
                },
            }
        except Exception as e:
            logger.error(f"관리자 이벤트 목록 조회 실패: {e}")
            return {
                "events": [],
                "pagination": {
                    "page": 1,
                    "page_size": page_size,
                    "total_pages": 1,
                    "total_items": 0,
                },
                "error": str(e),
            }

    async def fetch_admin_event_record(self, event_id: str) -> Optional[Dict[str, Any]]:
        """단일 이벤트 레코드를 포맷팅해 반환"""
        try:
            client = self._get_client(use_admin=True)
            result = (
                client.table('system_logs')
                .select('*')
                .eq('event_type', 'paddle_webhook')
                .eq('event_data->>event_id', event_id)
                .order('created_at', desc=True)
                .limit(1)
                .execute()
            )
            record = result.data[0] if result.data else None
            if not record:
                return None
            return self._format_admin_event_record(record)
        except Exception as e:
            logger.error(f"관리자 이벤트 단일 조회 실패: {e}")
            return None

    async def get_admin_event_detail(self, event_id: str) -> Optional[Dict[str, Any]]:
        """관리자 이벤트 상세 정보 반환"""
        formatted = await self.fetch_admin_event_record(event_id)
        if not formatted:
            return None

        membership_effect = self._compose_membership_effect(formatted)
        wallet_effect = self._compose_wallet_effect(formatted)

        return {
            "event": formatted['summary'],
            "membership_effect": membership_effect,
            "wallet_effect": wallet_effect,
            "raw_payload": formatted.get('raw_payload'),
        }

    async def get_admin_event_raw_payload(self, event_id: str) -> Optional[Dict[str, Any]]:
        """재처리용 원본 페이로드 조회"""
        formatted = await self.fetch_admin_event_record(event_id)
        if not formatted:
            return None
        raw_payload = formatted.get('raw_payload')
        if raw_payload:
            return raw_payload
        payload = formatted.get('payload')
        return payload if isinstance(payload, dict) else None

    def _format_admin_event_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        event_data = record.get('event_data') or {}
        payload_raw = event_data.get('payload')
        if isinstance(payload_raw, dict) and 'payload' in payload_raw and isinstance(payload_raw['payload'], dict):
            payload_raw = payload_raw['payload']
        payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
        raw_payload = payload.pop('raw_payload', None)

        results = payload.get('results') if isinstance(payload.get('results'), dict) else payload.get('results')
        if not isinstance(results, dict):
            results = {}

        event_id = event_data.get('event_id') or record.get('event_id')
        event_category = payload.get('event_category') or event_data.get('event_category')
        status_label = (event_data.get('status') or '').lower()

        user_id = payload.get('user_id') or event_data.get('user_id') or record.get('user_id')
        user_email = payload.get('user_email') or event_data.get('user_email')
        transaction_id = payload.get('transaction_id') or event_data.get('transaction_id')

        def _to_float(value: Any) -> Optional[float]:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        amount = _to_float(payload.get('credit_amount_usd'))
        currency = payload.get('currency')

        summary_status = self._infer_admin_event_status(status_label, results)
        summary_type = (event_category or 'unknown').lower()
        description_parts: List[str] = []
        if event_category:
            description_parts.append(event_category.capitalize())
        if transaction_id:
            description_parts.append(f"tx {transaction_id}")
        description = " • ".join(description_parts) if description_parts else (event_category or "event")

        summary = {
            "id": event_id or record.get('id'),
            "event_id": event_id,
            "type": summary_type,
            "status": summary_status,
            "status_label": status_label or None,
            "description": description,
            "amount": amount,
            "currency": currency,
            "occurred_at": record.get('created_at'),
            "user_id": user_id,
            "user_email": user_email,
            "transaction_id": transaction_id,
        }

        return {
            "summary": summary,
            "results": results,
            "payload": payload,
            "raw_payload": raw_payload,
            "status_label": status_label,
            "event_category": event_category,
            "record_id": record.get('id'),
        }

    @staticmethod
    def _infer_admin_event_status(base_status: Optional[str], results: Dict[str, Any]) -> str:
        status = (base_status or '').lower()
        has_success = False
        has_error = False

        for value in results.values():
            if not isinstance(value, dict):
                continue
            if value.get('success') is True:
                has_success = True
            if value.get('success') is False or value.get('error') or value.get('reason'):
                has_error = True

        if has_error and has_success:
            return 'partial'
        if has_error:
            return 'error'
        if has_success:
            return 'success'

        if status in {"processed", "replayed"}:
            return 'success'
        if status == 'duplicate':
            return 'duplicate'
        if status:
            return status
        return 'unknown'

    def _compose_membership_effect(self, formatted: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        results = formatted.get('results') or {}
        payload = formatted.get('payload') or {}

        for key in ("membership", "membership_refund", "cancellation"):
            entry = results.get(key)
            if not isinstance(entry, dict):
                continue
            data = entry.get('data')
            if isinstance(data, dict):
                return {
                    "previous_level": data.get('previous_level'),
                    "next_level": data.get('membership_level') or data.get('new_level'),
                    "expires_at": data.get('expires_at') or data.get('new_expires_at') or data.get('effective_at'),
                }
            action = entry.get('action')
            if action:
                return {
                    "previous_level": None,
                    "next_level": None,
                    "expires_at": entry.get('effective_at'),
                }

        membership_level = payload.get('membership_level')
        expires_at = payload.get('next_billing_at')
        if membership_level is not None or expires_at:
            return {
                "previous_level": None,
                "next_level": membership_level,
                "expires_at": expires_at,
            }
        return None

    def _compose_wallet_effect(self, formatted: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = formatted.get('payload') or {}
        event_category = (formatted.get('event_category') or '').lower()

        def _to_float(value: Any) -> Optional[float]:
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        amount = _to_float(payload.get('credit_amount_usd'))
        units = _to_float(payload.get('credit_units'))

        if amount is None and units is None:
            return None

        direction = -1.0 if event_category == 'refund' else 1.0

        delta_amount = amount * direction if amount is not None else None
        delta_credits = units * direction if units is not None else None

        return {
            "delta_credits": delta_credits,
            "delta_amount": delta_amount,
            "balance_after": None,
        }

    async def has_processed_webhook_event(self, provider: str, event_id: str) -> bool:
        """지정한 공급자 웹훅 이벤트가 이미 처리되었는지 확인"""
        try:
            if not event_id:
                return False

            event_type = f"{provider}_webhook"
            client = self._get_client(use_admin=True)
            result = (
                client.table('system_logs')
                .select('id')
                .eq('event_type', event_type)
                .contains('event_data', {'event_id': event_id})
                .limit(1)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"웹훅 이벤트 중복 확인 실패: {e}")
            return False

    async def record_webhook_event(self, provider: str, event_id: str, status: str, payload: Dict[str, Any] = None) -> bool:
        """웹훅 이벤트 처리 기록"""
        try:
            if not event_id:
                return False

            event_type = f"{provider}_webhook"
            event_payload = {
                'event_id': event_id,
                'status': status,
            }
            if payload:
                event_payload['payload'] = payload

            return await self.log_system_event(event_type=event_type, event_data=event_payload)
        except Exception as e:
            logger.error(f"웹훅 이벤트 기록 실패: {e}")
            return False
    
    # 유틸리티 함수들
    
    
    
    async def update_site_name(self, user_id: str, site_code: str, site_name: str) -> bool:
        """사이트 이름 업데이트"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').update({
                'site_name': site_name
            }).eq('user_id', user_id).eq('site_code', site_code).execute()
            
            if result.data:
                return True
            else:
                logger.warning(f"사이트 {site_code} 업데이트 실패")
                return False
        except Exception as e:
            logger.error(f"사이트 이름 업데이트 실패: {e}")
            return False
    
    async def delete_site(self, user_id: str, site_id: str) -> bool:
        """사이트 삭제"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').delete().eq('user_id', user_id).eq('id', site_id).execute()
            
            if result.data:
                return True
            else:
                logger.warning(f"사이트 {site_id} 삭제 실패")
                return False
        except Exception as e:
            logger.error(f"사이트 삭제 실패: {e}")
            return False

    async def update_site_unit_code(self, user_id: str, site_code: str, unit_code: str) -> bool:
        """사이트 유닛 코드 업데이트"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').update({
                'unit_code': unit_code
            }).eq('user_id', user_id).eq('site_code', site_code).execute()
            
            if result.data:
                return True
            else:
                logger.warning(f"사이트 {site_code} 유닛 코드 업데이트 실패")
                return False
        except Exception as e:
            logger.error(f"사이트 유닛 코드 업데이트 실패: {e}")
            return False

    async def update_site_domain(self, user_id: str, site_code: str, primary_domain: str) -> bool:
        """사이트 도메인 업데이트"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').update({
                'primary_domain': primary_domain
            }).eq('user_id', user_id).eq('site_code', site_code).execute()
            
            if result.data:
                return True
            else:
                logger.warning(f"사이트 {site_code} 도메인 업데이트 실패")
                return False
        except Exception as e:
            logger.error(f"사이트 도메인 업데이트 실패: {e}")
            return False
    
    async def update_thread_title(self, thread_id: str, title: str) -> bool:
        """스레드 제목 업데이트"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('chat_threads').update({
                'title': title,
                'updated_at': datetime.now().isoformat()
            }).eq('id', thread_id).execute()
            
            if result.data:
                return True
            else:
                logger.warning(f"스레드 {thread_id} 제목 업데이트 실패")
                return False
        except Exception as e:
            logger.error(f"스레드 제목 업데이트 실패: {e}")
            return False
    
    # Site Scripts 관련 함수들
    
    async def update_site_script_separated(
        self,
        user_id: str,
        site_code: str,
        css_content: str,
        script_content: str,
        draft_css_content: str,
        draft_script_content: str,
    ) -> Dict[str, Any]:
        """사이트 스크립트 업데이트 (배포 및 초안 동기화)"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                raise PermissionError("사이트에 접근할 권한이 없습니다.")
            
            # 현재 활성 스크립트 조회
            current_script = await self.get_site_script(user_id, site_code)
            
            # 현재 활성 스크립트와 동일한 내용인지 확인
            if (
                current_script and
                current_script.get('css_content', '') == css_content and
                current_script.get('script_content', '') == script_content and
                current_script.get('draft_css_content', '') == draft_css_content and
                current_script.get('draft_script_content', '') == draft_script_content
            ):
                return current_script
            
            client = self._get_client(use_admin=True)
            
            if current_script:
                # 기존 활성 스크립트가 있으면 CSS/JS 내용 수정
                script_id = current_script['id']
                now_iso = datetime.now().isoformat()
                result = client.table('site_scripts').update({
                    'css_content': css_content,
                    'script_content': script_content,
                    'draft_css_content': draft_css_content,
                    'draft_script_content': draft_script_content,
                    'draft_updated_at': now_iso,
                    'updated_at': now_iso
                }).eq('id', script_id).execute()
                return result.data[0] if result.data else {}
            else:
                # 활성 스크립트가 없으면 새로 생성
                script_data = {
                    'user_id': user_id,
                    'site_code': site_code,
                    'css_content': css_content,
                    'script_content': script_content,
                    'draft_css_content': draft_css_content,
                    'draft_script_content': draft_script_content,
                    'draft_updated_at': datetime.now().isoformat(),
                    'version': 1,
                    'is_active': True
                }
                result = client.table('site_scripts').insert(script_data).execute()
                return result.data[0] if result.data else {}
            
        except Exception as e:
            logger.error(f"CSS/JS 스크립트 업데이트 실패: {e}")
            return {}

    async def update_site_script_draft(self, user_id: str, site_code: str, css_content: str, script_content: str) -> Dict[str, Any]:
        """사이트 스크립트 임시 저장 (초안)"""
        try:
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                raise PermissionError("사이트에 접근할 권한이 없습니다.")

            current_script = await self.get_site_script(user_id, site_code)
            client = self._get_client(use_admin=True)
            now_iso = datetime.now().isoformat()

            payload = {
                'draft_css_content': css_content,
                'draft_script_content': script_content,
                'draft_updated_at': now_iso,
            }

            if current_script:
                script_id = current_script['id']
                result = client.table('site_scripts').update(payload).eq('id', script_id).execute()
                return result.data[0] if result.data else {}
            else:
                script_data = {
                    'user_id': user_id,
                    'site_code': site_code,
                    'css_content': '',
                    'script_content': '',
                    **payload,
                    'version': 1,
                    'is_active': False
                }
                result = client.table('site_scripts').insert(script_data).execute()
                return result.data[0] if result.data else {}

        except Exception as e:
            logger.error(f"스크립트 초안 저장 실패: {e}")
            return {}

    async def update_site_script(self, user_id: str, site_code: str, script_content: str) -> Dict[str, Any]:
        """사이트 스크립트 업데이트 (기존 통합 방식 - 하위 호환성)"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                raise PermissionError("사이트에 접근할 권한이 없습니다.")
            
            # 현재 활성 스크립트 조회
            current_script = await self.get_site_script(user_id, site_code)
            
            # 현재 활성 스크립트와 동일한 내용인지 확인
            if current_script and current_script.get('script_content') == script_content:
                return current_script
            
            client = self._get_client(use_admin=True)
            
            if current_script:
                # 기존 활성 스크립트가 있으면 내용만 수정
                script_id = current_script['id']
                now_iso = datetime.now().isoformat()
                result = client.table('site_scripts').update({
                    'script_content': script_content,
                    'draft_script_content': script_content,
                    'draft_css_content': '',
                    'draft_updated_at': now_iso,
                    'updated_at': now_iso
                }).eq('id', script_id).execute()
                return result.data[0] if result.data else {}
            else:
                # 활성 스크립트가 없으면 새로 생성
                script_data = {
                    'user_id': user_id,
                    'site_code': site_code,
                    'script_content': script_content,
                    'draft_script_content': script_content,
                    'draft_css_content': '',
                    'draft_updated_at': datetime.now().isoformat(),
                    'version': 1,
                    'is_active': True
                }
                result = client.table('site_scripts').insert(script_data).execute()
                return result.data[0] if result.data else {}
            
        except Exception as e:
            logger.error(f"사이트 스크립트 업데이트 실패: {e}")
            return {}
    
    async def get_site_script(self, user_id: str, site_code: str) -> Optional[Dict[str, Any]]:
        """현재 활성화된 사이트 스크립트 조회"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                logger.warning(f"사이트 접근 권한 없음: user_id={user_id}, site_code={site_code}")
                return None
            
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').select('*').eq('user_id', user_id).eq('site_code', site_code).eq('is_active', True).execute()
            
            if result.data:
                return result.data[0]
            else:
                return None
        except Exception as e:
            logger.error(f"사이트 스크립트 조회 실패: {e}")
            return None
    
    async def get_site_script_by_id(self, user_id: str, script_id: str) -> Optional[Dict[str, Any]]:
        """스크립트 ID로 스크립트 조회"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').select('*').eq('id', script_id).eq('user_id', user_id).execute()
            
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"스크립트 ID 조회 실패: {e}")
            return None
    
    async def get_site_script_history(self, user_id: str, site_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """사이트 스크립트 버전 히스토리 조회"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                return []
            
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').select('*').eq('user_id', user_id).eq('site_code', site_code).order('version', desc=True).limit(limit).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"사이트 스크립트 히스토리 조회 실패: {e}")
            return []
    
    async def delete_site_script(self, user_id: str, site_code: str) -> bool:
        """사이트의 활성 스크립트 삭제 (비활성화)"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                return False
            
            # 모든 스크립트 비활성화
            await self._deactivate_existing_scripts(user_id, site_code)
            return True
        except Exception as e:
            logger.error(f"사이트 스크립트 삭제 실패: {e}")
            return False
    
    async def _deactivate_existing_scripts(self, user_id: str, site_code: str) -> bool:
        """기존 활성 스크립트들을 비활성화"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').update({
                'is_active': False,
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user_id).eq('site_code', site_code).eq('is_active', True).execute()
            
            return True
        except Exception as e:
            logger.error(f"기존 스크립트 비활성화 실패: {e}")
            return False
    
    async def _delete_existing_scripts(self, user_id: str, site_code: str) -> bool:
        """기존 스크립트들을 모두 삭제 (unique constraint 문제 해결용)"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').delete().eq('user_id', user_id).eq('site_code', site_code).execute()
            
            return True
        except Exception as e:
            logger.error(f"기존 스크립트 삭제 실패: {e}")
            return False
    
    async def _get_next_version(self, user_id: str, site_code: str) -> int:
        """다음 스크립트 버전 번호 계산"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').select('version').eq('user_id', user_id).eq('site_code', site_code).order('version', desc=True).limit(1).execute()
            
            if result.data:
                return result.data[0]['version'] + 1
            else:
                return 1
        except Exception as e:
            logger.error(f"다음 버전 계산 실패: {e}")
            return 1
    
    async def get_site_script_by_code_public(self, site_code: str) -> Optional[Dict[str, Any]]:
        """사이트 코드로 활성 스크립트 조회 (공개 접근용, 인증 불필요)"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').select('*').eq('site_code', site_code).eq('is_active', True).execute()
            
            script_data = None
            if result.data:
                script_data = result.data[0]
            else:
                # 스크립트가 없어도 Free 사용자용 태그를 위해 기본 구조 생성
                script_data = {
                    'site_code': site_code,
                    'script_content': '',
                    'user_id': None,
                    'version': 1,
                    'is_active': True
                }
            
            # Free 사용자의 사이트인 경우 태그 스크립트 추가
            if script_data:
                # 사이트의 사용자 정보 조회
                site_result = client.table('user_sites').select('user_id').eq('site_code', site_code).execute()
                
                if site_result.data:
                    user_id = site_result.data[0]['user_id']
                    
#                     # 사용자 멤버십 조회
#                     membership_result = client.table('user_memberships').select('membership_level').eq('user_id', user_id).execute()
                    
#                     # 멤버십이 없거나 BASIC 레벨(0)인 경우 태그 스크립트 추가
#                     is_free_user = not membership_result.data or membership_result.data[0].get('membership_level', 0) == 0
                    
#                     if is_free_user:
#                         # Free 사용자용 태그 스크립트
#                         website_base_url = os.getenv("WEB_BASE_URL", "/")  # 실제 ImWeb URL로 변경
#                         free_tag_script = f"""

# var siteToppingLink = document.createElement('a');
# siteToppingLink.href = '{website_base_url}';
# siteToppingLink.innerText = 'powered by Site Topping';
# siteToppingLink.target = '_blank';
# siteToppingLink.style.position = 'fixed';
# siteToppingLink.style.bottom = '0px';
# siteToppingLink.style.left = '10px';
# siteToppingLink.style.fontSize = '10px';
# siteToppingLink.style.padding = '2px 4px';
# siteToppingLink.style.backgroundColor = 'white';
# siteToppingLink.style.border = '1px solid #ccc';
# siteToppingLink.style.borderRadius = '5px 5px 0px 0px';
# siteToppingLink.style.borderBottom = 'none';
# siteToppingLink.style.zIndex = '9999';
# siteToppingLink.style.textDecoration = 'none';
# siteToppingLink.style.color = 'black';
# document.body.appendChild(siteToppingLink);
# """
                        
#                         # 기존 스크립트 내용에 태그 스크립트 추가
#                         original_content = script_data.get('script_content', '')
#                         script_data['script_content'] = original_content + free_tag_script
            
            return script_data
        except Exception as e:
            logger.error(f"공개 사이트 스크립트 조회 실패: {e}")
            return None
    
    async def get_site_domain_by_code_public(self, site_code: str) -> Optional[str]:
        """사이트 코드로 사이트 도메인 조회 (공개 접근용, 인증 불필요)"""
        try:
            client = self._get_client(use_admin=True)
            # DB에서 primary_domain 조회
            result = client.table('user_sites').select('primary_domain').eq('site_code', site_code).execute()
            
            if result.data:
                site_data = result.data[0]
                domain = site_data.get('primary_domain', '')
                
                if domain:
                    if not domain.startswith(('http://', 'https://')):
                        domain = f"https://{domain}"
                    return domain
                return None
            else:
                return None
        except Exception as e:
            logger.error(f"사이트 도메인 조회 실패: {e}")
            return None
    
    async def _create_default_script(self, user_id: str, site_code: str) -> None:
        """사이트 생성 시 기본 빈 스크립트 데이터 생성"""
        try:
            script_data = {
                'user_id': user_id,
                'site_code': site_code,
                'script_content': '',
                'version': 1,
                'is_active': True
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').insert(script_data).execute()
                
        except Exception as e:
            logger.error(f"기본 스크립트 데이터 생성 중 오류: {e}")
            # 스크립트 생성 실패해도 사이트 생성은 유지

    # User Memberships 관련 함수들
    async def get_user_membership(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 멤버십 정보 조회"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').select('*').eq('user_id', user_id).execute()
            
            if result.data:
                membership = result.data[0]
                # 만료일 체크
                if membership.get('expires_at'):
                    expires_at = datetime.fromisoformat(membership['expires_at'].replace('Z', '+00:00'))
                    if expires_at < datetime.now().replace(tzinfo=expires_at.tzinfo):
                        # 만료된 멤버십은 다운그레이드 처리 후, 비회원으로 취급
                        await self._downgrade_expired_membership(user_id)
                        return None
                # 저장된 멤버십 레벨을 그대로 반환
                return membership
            # 멤버십 레코드가 없으면 비회원으로 취급
            return None
        except Exception as e:
            logger.error(f"사용자 멤버십 조회 실패: {e}")
            return None

    async def create_user_membership(
        self,
        user_id: str,
        membership_level: int = 0,
        expires_at: datetime = None,
        next_billing_at: datetime = None,
        cancel_at_period_end: bool = False,
        cancel_requested_at: datetime | None = None,
    ) -> Dict[str, Any]:
        """새로운 사용자 멤버십 생성"""
        try:
            membership_data = {
                'user_id': user_id,
                'membership_level': membership_level,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'next_billing_at': next_billing_at.isoformat() if next_billing_at else None,
                'cancel_at_period_end': cancel_at_period_end,
                'cancel_requested_at': cancel_requested_at.isoformat() if cancel_requested_at else None,
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').insert(membership_data).execute()
            
            if result.data:
                return result.data[0]
            return {}
        except Exception as e:
            logger.error(f"사용자 멤버십 생성 실패: {e}")
            return {}

    async def update_user_membership(
        self,
        user_id: str,
        membership_level: int,
        expires_at: datetime = None,
        next_billing_at: datetime = None,
        cancel_at_period_end: Any = UNSET,
        cancel_requested_at: Any = UNSET,
    ) -> bool:
        """사용자 멤버십 업데이트"""
        try:
            update_data = {
                'membership_level': membership_level,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'next_billing_at': next_billing_at.isoformat() if next_billing_at else None,
                'updated_at': datetime.now().isoformat()
            }

            if cancel_at_period_end is not UNSET:
                update_data['cancel_at_period_end'] = bool(cancel_at_period_end)

            if cancel_requested_at is not UNSET:
                update_data['cancel_requested_at'] = (
                    cancel_requested_at.isoformat()
                    if isinstance(cancel_requested_at, datetime)
                    else cancel_requested_at
                )

            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').update(update_data).eq('user_id', user_id).execute()
            
            if result.data:
                return True
            else:
                logger.warning(f"사용자 멤버십 업데이트 실패: user_id={user_id}")
                return False
        except Exception as e:
            logger.error(f"사용자 멤버십 업데이트 실패: {e}")
            return False

    async def ensure_user_membership(self, user_id: str) -> Dict[str, Any]:
        """사용자 멤버십 존재 확인 및 생성 (없으면 기본 멤버십 생성)"""
        try:
            membership = await self.get_user_membership(user_id)
            if not membership:
                # 기본 멤버십 생성
                membership = await self.create_user_membership(user_id, 0, None, None)
            return membership
        except Exception as e:
            logger.error(f"사용자 멤버십 확인/생성 실패: {e}")
            return {}

    async def check_membership_level(self, user_id: str, required_level: int) -> bool:
        """사용자가 특정 멤버십 레벨 이상인지 확인"""
        try:
            membership = await self.get_user_membership(user_id)
            if not membership:
                # 멤버십이 없으면 어떤 레벨도 허용하지 않음
                return False
            
            current_level = membership.get('membership_level', 0)
            return current_level >= required_level
        except Exception as e:
            logger.error(f"멤버십 레벨 확인 실패: {e}")
            return False

    async def get_expired_memberships(self) -> List[Dict[str, Any]]:
        """만료된 멤버십 목록 조회 (배치 작업용)"""
        try:
            current_time = datetime.now().isoformat()
            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').select('*').lt('expires_at', current_time).gt('membership_level', 0).execute()
            
            return result.data or []
        except Exception as e:
            logger.error(f"만료된 멤버십 조회 실패: {e}")
            return []

    async def schedule_membership_cancellation(self, user_id: str) -> bool:
        """멤버십을 만료 시점에 종료하도록 예약"""
        try:
            membership = await self.get_user_membership(user_id)
            if not membership or int(membership.get('membership_level', 0)) <= 0:
                return False

            return await self.update_user_membership(
                user_id,
                membership_level=membership.get('membership_level', 0),
                expires_at=self._parse_iso_datetime(membership.get('expires_at')),
                next_billing_at=self._parse_iso_datetime(membership.get('next_billing_at')),
                cancel_at_period_end=True,
                cancel_requested_at=datetime.now()
            )
        except Exception as e:
            logger.error(f"멤버십 해지 예약 실패: {e}")
            return False

    async def clear_membership_cancellation(self, user_id: str) -> bool:
        """예약된 멤버십 해지 상태 초기화"""
        try:
            membership = await self.get_user_membership(user_id)
            if not membership:
                return False

            return await self.update_user_membership(
                user_id,
                membership_level=membership.get('membership_level', 0),
                expires_at=self._parse_iso_datetime(membership.get('expires_at')),
                next_billing_at=self._parse_iso_datetime(membership.get('next_billing_at')),
                cancel_at_period_end=False,
                cancel_requested_at=None
            )
        except Exception as e:
            logger.error(f"멤버십 해지 초기화 실패: {e}")
            return False

    async def _downgrade_expired_membership(self, user_id: str) -> bool:
        """만료된 멤버십을 기본 등급으로 다운그레이드"""
        try:
            update_data = {
                'membership_level': 0,
                'expires_at': None,
                'next_billing_at': None,
                'cancel_at_period_end': False,
                'cancel_requested_at': None,
                'updated_at': datetime.now().isoformat()
            }

            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').update(update_data).eq('user_id', user_id).execute()
            
            if result.data:
                # 시스템 로그 기록
                await self.log_system_event(
                    user_id=user_id,
                    event_type='membership_downgrade',
                    event_data={'reason': 'expired', 'new_level': 0}
                )
                return True
            return False
        except Exception as e:
            logger.error(f"멤버십 다운그레이드 실패: {e}")
            return False

    async def batch_downgrade_expired_memberships(self) -> int:
        """만료된 모든 멤버십을 일괄 다운그레이드 (배치 작업용)"""
        try:
            expired_memberships = await self.get_expired_memberships()
            downgraded_count = 0
            
            for membership in expired_memberships:
                user_id = membership['user_id']
                if await self._downgrade_expired_membership(user_id):
                    downgraded_count += 1
            
            if downgraded_count > 0:
                await self.log_system_event(
                    event_type='batch_membership_downgrade',
                    event_data={'downgraded_count': downgraded_count}
                )
            
            return downgraded_count
        except Exception as e:
            logger.error(f"배치 멤버십 다운그레이드 실패: {e}")
            return 0
    
    # Daily Request Tracking 관련 함수들
    async def increment_daily_request(self, user_id: str, endpoint: str = None) -> bool:
        """사용자의 일일 요청 수 증가"""
        try:
            today = date.today().isoformat()
            client = self._get_client(use_admin=True)
            
            # 기존 레코드가 있는지 확인
            existing = client.table('daily_request_logs').select('*').eq(
                'user_id', user_id
            ).eq('request_date', today).execute()
            
            if existing.data:
                # 기존 레코드 업데이트
                new_count = existing.data[0]['request_count'] + 1
                result = client.table('daily_request_logs').update({
                    'request_count': new_count,
                    'updated_at': datetime.now().isoformat()
                }).eq('user_id', user_id).eq('request_date', today).execute()
            else:
                # 새 레코드 생성
                result = client.table('daily_request_logs').insert({
                    'user_id': user_id,
                    'request_date': today,
                    'request_count': 1,
                    'endpoint': endpoint
                }).execute()
            
            return bool(result.data)
        except Exception as e:
            logger.error(f"일일 요청 수 증가 실패: {e}")
            return False
    
    async def get_daily_request_count(self, user_id: str, target_date: date = None) -> int:
        """사용자의 특정 날짜 요청 수 조회"""
        try:
            if target_date is None:
                target_date = date.today()
            
            date_str = target_date.isoformat()
            client = self._get_client(use_admin=True)
            
            result = client.table('daily_request_logs').select('request_count').eq(
                'user_id', user_id
            ).eq('request_date', date_str).execute()
            
            return result.data[0]['request_count'] if result.data else 0
        except Exception as e:
            logger.error(f"일일 요청 수 조회 실패: {e}")
            return 0
    
    # Token Wallet & Transactions
    async def get_user_wallet(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 토큰 지갑 조회 (없으면 생성)"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_token_wallets').select('*').eq('user_id', user_id).execute()
            if result.data and len(result.data) > 0:
                return result.data[0]
            # ensure wallet exists explicitly
            try:
                client.rpc('ensure_user_wallet', { 'p_user_id': user_id }).execute()
            except Exception:
                pass
            result2 = client.table('user_token_wallets').select('*').eq('user_id', user_id).execute()
            return result2.data[0] if result2.data else None
        except Exception as e:
            logger.error(f"지갑 조회 실패: {e}")
            return None

    async def credit_wallet(
        self,
        user_id: str,
        amount_usd: float,
        metadata: Dict[str, Any] = None,
        source_event_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """지갑 충전 및 거래 기록"""
        try:
            client = self._get_client(use_admin=True)
            metadata = dict(metadata or {})

            if source_event_id:
                metadata.setdefault('source', 'paddle')
                metadata['event_id'] = source_event_id

                existing = (
                    client.table('token_transactions')
                    .select('id')
                    .eq('user_id', user_id)
                    .eq('type', 'credit')
                    .contains('metadata', {'event_id': source_event_id})
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    return None
            # credit via RPC to bypass RLS
            rpc_res = client.rpc('wallet_credit', { 'p_user_id': user_id, 'p_amount': amount_usd }).execute()
            new_balance = rpc_res.data if hasattr(rpc_res, 'data') else None
            # record transaction
            tx = client.table('token_transactions').insert({
                'user_id': user_id,
                'type': 'credit',
                'amount_usd': amount_usd,
                'balance_after': new_balance,
                'metadata': metadata
            }).execute()
            return tx.data[0] if tx.data else {'balance_after': new_balance}
        except Exception as e:
            logger.error(f"지갑 충전 실패: {e}")
            return None

    async def debit_wallet(
        self,
        user_id: str,
        amount_usd: float,
        metadata: Dict[str, Any] = None,
        source_event_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        """지갑 차감 및 거래 기록"""
        try:
            client = self._get_client(use_admin=True)
            metadata = dict(metadata or {})

            if source_event_id:
                metadata.setdefault('source', 'paddle')
                metadata['event_id'] = source_event_id

                existing = (
                    client.table('token_transactions')
                    .select('id')
                    .eq('user_id', user_id)
                    .eq('type', 'debit')
                    .contains('metadata', {'event_id': source_event_id})
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    return None

            rpc_res = client.rpc('wallet_debit', { 'p_user_id': user_id, 'p_amount': amount_usd }).execute()
            new_balance = rpc_res.data if hasattr(rpc_res, 'data') else None

            tx = client.table('token_transactions').insert({
                'user_id': user_id,
                'type': 'debit',
                'amount_usd': amount_usd,
                'balance_after': new_balance,
                'metadata': metadata
            }).execute()
            return tx.data[0] if tx.data else {'balance_after': new_balance}
        except Exception as e:
            logger.error(f"지갑 차감 실패: {e}")
            return None

    async def debit_wallet_for_ai(self, user_id: str, amount_usd: float, usage: Dict[str, Any], thread_id: str = None, message_id: str = None) -> Dict[str, Any]:
        """AI 호출 비용 차감 및 거래 기록. 잔액 부족 시 exceeded=True 반환"""
        try:
            client = self._get_client(use_admin=True)
            try:
                rpc_res = client.rpc('wallet_debit', { 'p_user_id': user_id, 'p_amount': amount_usd }).execute()
                new_balance = rpc_res.data if hasattr(rpc_res, 'data') else None
            except Exception as e:
                # detect insufficient funds from message
                msg = str(e)
                if 'INSUFFICIENT_FUNDS' in msg or 'insufficient' in msg.lower():
                    wallet = await self.get_user_wallet(user_id)
                    return { 'success': False, 'exceeded': True, 'balance': wallet.get('balance_usd', 0) if wallet else 0 }
                raise

            # record transaction
            tx_meta = {
                'model_pricing': usage,
            }
            tx = client.table('token_transactions').insert({
                'user_id': user_id,
                'type': 'debit',
                'amount_usd': amount_usd,
                'balance_after': new_balance,
                'model_name': usage.get('model_name'),
                'input_tokens': usage.get('input_tokens'),
                'output_tokens': usage.get('output_tokens'),
                'thoughts_tokens': usage.get('thoughts_tokens'),
                'thread_id': thread_id,
                'message_id': message_id,
                'metadata': tx_meta
            }).execute()
            return { 'success': True, 'balance': new_balance, 'transaction': (tx.data[0] if tx.data else None) }
        except Exception as e:
            logger.error(f"AI 비용 차감 실패: {e}")
            return { 'success': False, 'error': str(e) }

    async def get_token_transactions(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """사용자 토큰 거래 내역 조회"""
        try:
            client = self._get_client(use_admin=True)
            res = client.table('token_transactions').select('*').eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"토큰 거래 내역 조회 실패: {e}")
            return []

    async def check_daily_request_limit(self, user_id: str, limit: int) -> Dict[str, Any]:
        """사용자의 일일 요청 제한 확인"""
        try:
            current_count = await self.get_daily_request_count(user_id)
            
            return {
                'current_count': current_count,
                'limit': limit,
                'remaining': max(0, limit - current_count),
                'exceeded': current_count >= limit,
                'reset_time': datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            }
        except Exception as e:
            logger.error(f"일일 요청 제한 확인 실패: {e}")
            return {
                'current_count': 0,
                'limit': limit,
                'remaining': limit,
                'exceeded': False,
                'error': str(e)
            }
    
    async def get_user_request_history(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """사용자의 최근 요청 히스토리 조회"""
        try:
            from datetime import timedelta
            
            start_date = (date.today() - timedelta(days=days-1)).isoformat()
            client = self._get_client(use_admin=True)
            
            result = client.table('daily_request_logs').select('*').eq(
                'user_id', user_id
            ).gte('request_date', start_date).order('request_date', desc=True).execute()
            
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"사용자 요청 히스토리 조회 실패: {e}")
            return []
    
    async def cleanup_old_request_logs(self, days_to_keep: int = 30) -> int:
        """오래된 요청 로그 정리 (배치 작업용)"""
        try:
            from datetime import timedelta
            
            cutoff_date = (date.today() - timedelta(days=days_to_keep)).isoformat()
            client = self._get_client(use_admin=True)
            
            result = client.table('daily_request_logs').delete().lt(
                'request_date', cutoff_date
            ).execute()
            
            deleted_count = len(result.data) if result.data else 0
            return deleted_count
        except Exception as e:
            logger.error(f"요청 로그 정리 실패: {e}")
            return 0

    async def list_admin_users(
        self,
        query: Optional[str] = None,
        status: str = "all",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """관리자용 사용자 목록 조회 (멤버십/지갑 요약 포함)"""
        try:
            client = self._get_client(use_admin=True)
            base_query = (
                client.table('user_profiles')
                .select('id,email,created_at')
                .order('created_at', desc=True)
            )

            if query:
                base_query = base_query.ilike('email', f"%{query}%")

            response = base_query.execute()
            profiles = response.data or []

            enriched: List[Dict[str, Any]] = []
            normalized_status = status.lower() if status else "all"

            for profile in profiles:
                user_id = profile.get('id')
                if not user_id:
                    continue

                membership = await self.get_user_membership(user_id)
                membership_status = self._derive_membership_status(membership)

                if normalized_status != "all" and membership_status != normalized_status:
                    continue

                wallet = await self.get_user_wallet(user_id)
                last_tx = await self.get_token_transactions(user_id, limit=1)
                last_payment_at = None
                if last_tx:
                    last_payment_at = last_tx[0].get('created_at')

                enriched.append(
                    {
                        "id": user_id,
                        "email": profile.get("email"),
                        "created_at": profile.get("created_at"),
                        "membership_level": int(membership.get('membership_level', 0)) if membership else 0,
                        "membership_status": membership_status,
                        "expires_at": membership.get('expires_at') if membership else None,
                        "next_billing_at": membership.get('next_billing_at') if membership else None,
                        "wallet_balance": (wallet or {}).get('balance_usd'),
                        "last_payment_at": last_payment_at,
                    }
                )

            total_items = len(enriched)
            page_size = page_size if page_size > 0 else 20
            total_pages = max(1, math.ceil(total_items / page_size))
            page = max(1, min(page, total_pages))
            start = (page - 1) * page_size
            end = start + page_size
            paged = enriched[start:end]

            return {
                "users": paged,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "total_items": total_items,
                },
            }
        except Exception as e:
            logger.error(f"관리자 사용자 목록 조회 실패: {e}")
            return {
                "users": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_pages": 1,
                    "total_items": 0,
                },
                "error": str(e),
            }

    @staticmethod
    def _derive_membership_status(membership: Optional[Dict[str, Any]]) -> str:
        """멤버십 상태를 문자열로 변환"""
        if not membership or int(membership.get("membership_level", 0)) <= 0:
            return "free"

        cancel_at_period_end = membership.get("cancel_at_period_end") in (True, "true", "True")
        expires_at = membership.get("expires_at")
        expires_dt = DatabaseHelper._parse_iso_datetime(expires_at)
        now = datetime.now(tz=expires_dt.tzinfo) if expires_dt and expires_dt.tzinfo else datetime.utcnow()

        if expires_dt and expires_dt < now:
            return "expired"
        if cancel_at_period_end:
            return "cancelled"
        return "active"
    
    # 사용자 계정 삭제 관련 함수들
    async def delete_all_user_data(self, user_id: str) -> bool:
        """사용자의 모든 데이터 완전 삭제"""
        try:
            client = self._get_client(use_admin=True)
            deleted_tables = []
            
            # 1. 채팅 메시지 삭제
            try:
                result = client.table('chat_messages').delete().eq('user_id', user_id).execute()
                deleted_tables.append(f"chat_messages: {len(result.data) if result.data else 0}개")
            except Exception as e:
                logger.warning(f"채팅 메시지 삭제 실패: {e}")
            
            # 2. 채팅 스레드 삭제
            try:
                result = client.table('chat_threads').delete().eq('user_id', user_id).execute()
                deleted_tables.append(f"chat_threads: {len(result.data) if result.data else 0}개")
            except Exception as e:
                logger.warning(f"채팅 스레드 삭제 실패: {e}")
            
            # 3. 사이트 스크립트 삭제
            try:
                result = client.table('site_scripts').delete().eq('user_id', user_id).execute()
                deleted_tables.append(f"site_scripts: {len(result.data) if result.data else 0}개")
            except Exception as e:
                logger.warning(f"사이트 스크립트 삭제 실패: {e}")
            
            # 4. 사용자 사이트 삭제
            try:
                result = client.table('user_sites').delete().eq('user_id', user_id).execute()
                deleted_tables.append(f"user_sites: {len(result.data) if result.data else 0}개")
            except Exception as e:
                logger.warning(f"사용자 사이트 삭제 실패: {e}")
            
            # 5. 사용자 멤버십 삭제
            try:
                result = client.table('user_memberships').delete().eq('user_id', user_id).execute()
                deleted_tables.append(f"user_memberships: {len(result.data) if result.data else 0}개")
            except Exception as e:
                logger.warning(f"사용자 멤버십 삭제 실패: {e}")
            
            # 6. 일일 요청 로그 삭제
            try:
                result = client.table('daily_request_logs').delete().eq('user_id', user_id).execute()
                deleted_tables.append(f"daily_request_logs: {len(result.data) if result.data else 0}개")
            except Exception as e:
                logger.warning(f"일일 요청 로그 삭제 실패: {e}")
            
            # 7. 시스템 로그에서 해당 사용자 관련 데이터 삭제 (선택적)
            try:
                result = client.table('system_logs').delete().eq('user_id', user_id).execute()
                deleted_tables.append(f"system_logs: {len(result.data) if result.data else 0}개")
            except Exception as e:
                logger.warning(f"시스템 로그 삭제 실패: {e}")
            
            logger.info(f"사용자 데이터 삭제 완료 - 사용자 ID: {user_id}, 삭제된 데이터: {', '.join(deleted_tables)}")
            return True
            
        except Exception as e:
            logger.error(f"사용자 데이터 삭제 실패: {e}")
            return False
    
    async def delete_user_profile(self, user_id: str) -> bool:
        """사용자 프로필 삭제"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_profiles').delete().eq('id', user_id).execute()
            
            if result.data:
                logger.info(f"사용자 프로필 삭제 완료: {user_id}")
                return True
            else:
                logger.warning(f"사용자 프로필 삭제 실패 (프로필이 존재하지 않음): {user_id}")
                return True  # 이미 삭제된 것으로 간주
        except Exception as e:
            logger.error(f"사용자 프로필 삭제 실패: {e}")
            return False
