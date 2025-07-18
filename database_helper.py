"""
데이터베이스 연결 및 CRUD 작업을 위한 헬퍼 모듈
"""
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
from supabase import Client
import logging

logger = logging.getLogger(__name__)

class DatabaseHelper:
    def __init__(self, supabase_client: Client, admin_client: Client = None):
        self.supabase = supabase_client
        self.admin_client = admin_client or supabase_client
        self.user_clients = {}  # 사용자별 클라이언트 저장소
    
    def set_user_client(self, user_id: str, client: Client):
        """사용자별 인증된 클라이언트 설정"""
        self.user_clients[user_id] = client
    
    def get_user_client(self, user):
        """사용자별 클라이언트 반환, 없으면 기본 클라이언트 사용"""
        if user and hasattr(user, 'id'):
            return self.user_clients.get(user.id, self.supabase)
        return self.supabase
    
    async def create_user_profile(self, user_id: str, display_name: str = None) -> Dict[str, Any]:
        """사용자 프로필 생성"""
        try:
            result = self.supabase.table('user_profiles').insert({
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
            result = self.supabase.table('user_profiles').select('*').eq('id', user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"사용자 프로필 조회 실패: {e}")
            return None
    
    # User Sites 관련 함수들
    async def get_user_sites(self, user_id: str, user=None) -> List[Dict[str, Any]]:
        """사용자의 연결된 사이트 목록 조회"""
        try:
            client = self.get_user_client(user)
            result = client.table('user_sites').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"사용자 사이트 조회 실패: {e}")
            return []
    
    async def create_user_site(self, user_id: str, site_code: str, site_name: str = None, 
                             access_token: str = None, refresh_token: str = None, user=None) -> Dict[str, Any]:
        """새로운 사이트 연결 생성"""
        try:
            site_data = {
                'user_id': user_id,
                'site_code': site_code,
                'site_name': site_name,
                'access_token': self._encrypt_token(access_token) if access_token else None,
                'refresh_token': self._encrypt_token(refresh_token) if refresh_token else None
            }
            
            client = self.get_user_client(user)
            result = client.table('user_sites').insert(site_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"사이트 연결 생성 실패: {e}")
            return {}
    
    async def update_user_site_tokens(self, user_id: str, site_code: str, 
                                    access_token: str = None, refresh_token: str = None) -> bool:
        """사용자 사이트의 토큰 업데이트"""
        try:
            update_data = {}
            if access_token:
                update_data['access_token'] = self._encrypt_token(access_token)
            if refresh_token:
                update_data['refresh_token'] = self._encrypt_token(refresh_token)
            
            result = self.supabase.table('user_sites').update(update_data).eq('user_id', user_id).eq('site_code', site_code).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"사이트 토큰 업데이트 실패: {e}")
            return False
    
    async def get_user_site_by_code(self, user_id: str, site_code: str) -> Optional[Dict[str, Any]]:
        """사이트 코드로 사용자 사이트 조회"""
        try:
            result = self.supabase.table('user_sites').select('*').eq('user_id', user_id).eq('site_code', site_code).execute()
            if result.data:
                site_data = result.data[0]
                # 토큰 복호화
                if site_data.get('access_token'):
                    site_data['access_token'] = self._decrypt_token(site_data['access_token'])
                if site_data.get('refresh_token'):
                    site_data['refresh_token'] = self._decrypt_token(site_data['refresh_token'])
                return site_data
            return None
        except Exception as e:
            logger.error(f"사이트 조회 실패: {e}")
            return None
    
    # Chat Threads 관련 함수들
    async def create_chat_thread(self, user_id: str, site_id: str = None, title: str = None, user=None) -> Dict[str, Any]:
        """새로운 채팅 스레드 생성"""
        try:
            thread_data = {
                'user_id': user_id,
                'site_id': site_id,
                'title': title
            }
            
            client = self.get_user_client(user)
            result = client.table('chat_threads').insert(thread_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"채팅 스레드 생성 실패: {e}")
            return {}
    
    async def get_user_threads(self, user_id: str, user=None) -> List[Dict[str, Any]]:
        """사용자의 모든 스레드 조회"""
        try:
            client = self.get_user_client(user)
            result = client.table('chat_threads').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"사용자 스레드 조회 실패: {e}")
            return []
    
    async def get_thread_by_id(self, user_id: str, thread_id: str, user=None) -> Optional[Dict[str, Any]]:
        """스레드 ID로 스레드 조회"""
        try:
            client = self.get_user_client(user)
            result = client.table('chat_threads').select('*').eq('id', thread_id).eq('user_id', user_id).execute()
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"스레드 조회 실패: {e}")
            return None
    
    async def delete_thread(self, user_id: str, thread_id: str, user=None) -> bool:
        """스레드 삭제"""
        try:
            client = self.get_user_client(user)
            result = client.table('chat_threads').delete().eq('id', thread_id).eq('user_id', user_id).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"스레드 삭제 실패: {e}")
            return False
    
    # Chat Messages 관련 함수들
    async def create_message(self, thread_id: str, user_id: str, message: str, 
                           message_type: str = 'user', metadata: Dict = None, user=None) -> Dict[str, Any]:
        """새로운 메시지 생성"""
        try:
            message_data = {
                'thread_id': thread_id,
                'user_id': user_id,
                'message': message,
                'message_type': message_type,
                'metadata': metadata or {}
            }
            
            client = self.get_user_client(user)
            result = client.table('chat_messages').insert(message_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"메시지 생성 실패: {e}")
            return {}
    
    async def get_thread_messages(self, thread_id: str, user_id: str, user=None) -> List[Dict[str, Any]]:
        """스레드의 모든 메시지 조회"""
        try:
            client = self.get_user_client(user)
            result = client.table('chat_messages').select('*').eq('thread_id', thread_id).eq('user_id', user_id).order('created_at', desc=False).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"스레드 메시지 조회 실패: {e}")
            return []
    
    async def check_duplicate_message(self, thread_id: str, user_id: str, message: str, 
                                    message_type: str = 'user', seconds: int = 1, user=None) -> bool:
        """중복 메시지 검사"""
        try:
            # 최근 몇 초 이내에 같은 메시지가 있는지 확인
            cutoff_time = datetime.now().replace(microsecond=0).isoformat()
            
            client = self.get_user_client(user)
            result = client.table('chat_messages').select('created_at').eq('thread_id', thread_id).eq('user_id', user_id).eq('message', message).eq('message_type', message_type).gte('created_at', cutoff_time).execute()
            
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
    
    # 유틸리티 함수들
    def _encrypt_token(self, token: str) -> str:
        """토큰 암호화 (실제 구현에서는 더 강력한 암호화 사용)"""
        if not token:
            return token
        try:
            import base64
            return base64.b64encode(token.encode()).decode()
        except Exception as e:
            logger.error(f"토큰 암호화 실패: {e}")
            return token
    
    def _decrypt_token(self, encrypted_token: str) -> str:
        """토큰 복호화"""
        if not encrypted_token:
            return encrypted_token
        try:
            import base64
            return base64.b64decode(encrypted_token.encode()).decode()
        except Exception as e:
            logger.error(f"토큰 복호화 실패: {e}")
            return encrypted_token
    
    async def get_user_token_by_site_code(self, user_id: str, site_code: str) -> Optional[str]:
        """사이트 코드로 사용자 토큰 조회"""
        site_data = await self.get_user_site_by_code(user_id, site_code)
        return site_data.get('access_token') if site_data else None
    
    async def health_check(self) -> Dict[str, Any]:
        """데이터베이스 연결 상태 확인"""
        try:
            # admin_client가 있는지 확인
            if not self.admin_client:
                logger.error("admin_client가 None입니다")
                raise Exception("admin_client not available")
            
            # system_stats 테이블로 헬스체크
            result = self.admin_client.table('system_stats').select('count').eq('stat_name', 'health_check').execute()
            return {
                'status': 'healthy',
                'connected': True,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"데이터베이스 헬스 체크 실패: {e}")
            return {
                'status': 'unhealthy',
                'connected': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }