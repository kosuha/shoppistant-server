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
    
    def _get_client(self, use_admin: bool = False):
        """적절한 클라이언트 반환 - 일반적으로 admin client 사용"""
        return self.admin_client if use_admin or self.admin_client else self.supabase
    
    def _verify_user_access(self, user_id: str, resource_user_id: str):
        """사용자가 리소스에 접근할 권한이 있는지 서버에서 검증"""
        if user_id != resource_user_id:
            raise PermissionError(f"사용자 {user_id}는 다른 사용자의 리소스에 접근할 수 없습니다.")
    
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
            print(f"Fetching user sites for user_id: {user_id}")
            self._verify_user_access(requesting_user_id, user_id)
            
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').select('*').eq('user_id', user_id).order('created_at', desc=True).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"[SERVICE] 사용자 사이트 조회 실패: {e}")
            return []
    
    async def create_user_site(self, user_id: str, site_code: str, site_name: str = None, 
                             access_token: str = None, refresh_token: str = None, unit_code: str = None) -> Dict[str, Any]:
        """새로운 사이트 연결 생성"""
        try:
            site_data = {
                'user_id': user_id,
                'site_code': site_code,
                'site_name': site_name,
                'access_token': self._encrypt_token(access_token) if access_token else None,
                'refresh_token': self._encrypt_token(refresh_token) if refresh_token else None,
                'unit_code': unit_code
            }
            
            client = self._get_client(use_admin=True)
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
            
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').update(update_data).eq('user_id', user_id).eq('site_code', site_code).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"사이트 토큰 업데이트 실패: {e}")
            return False
    
    async def get_user_site_by_code(self, user_id: str, site_code: str) -> Optional[Dict[str, Any]]:
        """사이트 코드로 사용자 사이트 조회"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').select('*').eq('user_id', user_id).eq('site_code', site_code).execute()
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
                           message_type: str = 'user', metadata: Dict = None) -> Dict[str, Any]:
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
                'metadata': metadata or {}
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_messages').insert(message_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"메시지 생성 실패: {e}")
            return {}
    
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
    
    async def get_user_token(self, user_id: str) -> Optional[str]:
        """사용자 ID로 토큰 조회 - user_sites에서 첫 번째 사이트의 토큰 반환"""
        try:
            user_sites = await self.get_user_sites(user_id, user_id)
            if user_sites:
                # 첫 번째 사이트의 토큰 반환
                first_site = user_sites[0]
                access_token = first_site.get('access_token')
                if access_token:
                    return self._decrypt_token(access_token)
            return None
        except Exception as e:
            logger.error(f"사용자 토큰 조회 실패: {e}")
            return None
    
    async def update_site_name(self, user_id: str, site_code: str, site_name: str) -> bool:
        """사이트 이름 업데이트"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').update({
                'site_name': site_name
            }).eq('user_id', user_id).eq('site_code', site_code).execute()
            
            if result.data:
                logger.info(f"사이트 {site_code}의 이름이 '{site_name}'으로 업데이트됨")
                return True
            else:
                logger.warning(f"사이트 {site_code} 업데이트 실패")
                return False
        except Exception as e:
            logger.error(f"사이트 이름 업데이트 실패: {e}")
            return False

    async def update_site_unit_code(self, user_id: str, site_code: str, unit_code: str) -> bool:
        """사이트 유닛 코드 업데이트"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').update({
                'unit_code': unit_code
            }).eq('user_id', user_id).eq('site_code', site_code).execute()
            
            if result.data:
                logger.info(f"사이트 {site_code}의 유닛 코드가 '{unit_code}'로 업데이트됨")
                return True
            else:
                logger.warning(f"사이트 {site_code} 유닛 코드 업데이트 실패")
                return False
        except Exception as e:
            logger.error(f"사이트 유닛 코드 업데이트 실패: {e}")
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
                logger.info(f"스레드 {thread_id}의 제목이 '{title}'으로 업데이트됨")
                return True
            else:
                logger.warning(f"스레드 {thread_id} 제목 업데이트 실패")
                return False
        except Exception as e:
            logger.error(f"스레드 제목 업데이트 실패: {e}")
            return False
    
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
    
    # Site Scripts 관련 함수들
    async def create_site_script(self, user_id: str, site_code: str, script_content: str) -> Dict[str, Any]:
        """새로운 사이트 스크립트 생성"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                raise PermissionError("사이트에 접근할 권한이 없습니다.")
            
            # 기존 활성 스크립트가 있다면 비활성화
            await self._deactivate_existing_scripts(user_id, site_code)
            
            # 새 버전 계산
            version = await self._get_next_version(user_id, site_code)
            
            script_data = {
                'user_id': user_id,
                'site_code': site_code,
                'script_content': script_content,
                'version': version,
                'is_active': True
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').insert(script_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"사이트 스크립트 생성 실패: {e}")
            return {}
    
    async def update_site_script(self, user_id: str, site_code: str, script_content: str) -> Dict[str, Any]:
        """사이트 스크립트 업데이트 (새 버전 생성)"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                raise PermissionError("사이트에 접근할 권한이 없습니다.")
            
            # 현재 활성 스크립트와 동일한 내용인지 확인
            current_script = await self.get_site_script(user_id, site_code)
            if current_script and current_script.get('script_content') == script_content:
                logger.info(f"스크립트 내용이 기존과 동일함: site_code={site_code}")
                return current_script
            
            # 기존 활성 스크립트 비활성화
            await self._deactivate_existing_scripts(user_id, site_code)
            
            # 새 버전 계산
            version = await self._get_next_version(user_id, site_code)
            
            script_data = {
                'user_id': user_id,
                'site_code': site_code,
                'script_content': script_content,
                'version': version,
                'is_active': True
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('site_scripts').insert(script_data).execute()
            logger.info(f"사이트 스크립트 업데이트 완료: site_code={site_code}, version={version}")
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
                logger.info(f"활성 스크립트 조회 성공: site_code={site_code}")
                return result.data[0]
            else:
                logger.info(f"활성 스크립트 없음: site_code={site_code}")
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
            logger.info(f"사이트 스크립트 삭제 완료: site_code={site_code}")
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
            
            logger.info(f"기존 활성 스크립트 비활성화 완료: site_code={site_code}, count={len(result.data) if result.data else 0}")
            return True
        except Exception as e:
            logger.error(f"기존 스크립트 비활성화 실패: {e}")
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
            
            if result.data:
                logger.info(f"공개 스크립트 조회 성공: site_code={site_code}")
                return result.data[0]
            else:
                logger.info(f"공개 스크립트 없음: site_code={site_code}")
                return None
        except Exception as e:
            logger.error(f"공개 사이트 스크립트 조회 실패: {e}")
            return None
    
    async def get_site_domain_by_code_public(self, site_code: str) -> Optional[str]:
        """사이트 코드로 사이트 도메인 조회 (공개 접근용, 인증 불필요)"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').select('site_domain').eq('site_code', site_code).execute()
            
            if result.data:
                domain = result.data[0].get('site_domain', '')
                logger.info(f"사이트 도메인 조회 성공: site_code={site_code}, domain={domain}")
                return domain
            else:
                logger.info(f"사이트 도메인 없음: site_code={site_code}")
                return None
        except Exception as e:
            logger.error(f"사이트 도메인 조회 실패: {e}")
            return None