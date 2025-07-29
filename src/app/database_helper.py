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
                           image_data: List[str] = None) -> Dict[str, Any]:
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
                'image_data': image_data
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('chat_messages').insert(message_data).execute()
            return result.data[0] if result.data else {}
        except Exception as e:
            logger.error(f"메시지 생성 실패: {e}")
            return {}
    
    async def update_message_status(self, requesting_user_id: str, message_id: str, status: str, 
                                  message: str = None, metadata: Dict = None) -> bool:
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
    
    # 유틸리티 함수들
    
    
    
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
    
    async def delete_site(self, user_id: str, site_id: str) -> bool:
        """사이트 삭제"""
        try:
            client = self._get_client(use_admin=True)
            result = client.table('user_sites').delete().eq('user_id', user_id).eq('id', site_id).execute()
            
            if result.data:
                logger.info(f"사이트 {site_id} 삭제 완료")
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
                logger.info(f"사이트 {site_code}의 유닛 코드가 '{unit_code}'로 업데이트됨")
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
                logger.info(f"사이트 {site_code}의 도메인이 '{primary_domain}'로 업데이트됨")
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
        """사이트 스크립트 업데이트"""
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.get_user_site_by_code(user_id, site_code)
            if not site:
                raise PermissionError("사이트에 접근할 권한이 없습니다.")
            
            # 현재 활성 스크립트 조회
            current_script = await self.get_site_script(user_id, site_code)
            
            # 현재 활성 스크립트와 동일한 내용인지 확인
            if current_script and current_script.get('script_content') == script_content:
                logger.info(f"스크립트 내용이 기존과 동일함: site_code={site_code}")
                return current_script
            
            client = self._get_client(use_admin=True)
            
            # 기존 활성 스크립트가 있으면 덮어쓰기
            if current_script:
                script_id = current_script['id']
                result = client.table('site_scripts').update({
                    'script_content': script_content,
                    'updated_at': datetime.now().isoformat()
                }).eq('id', script_id).execute()
                logger.info(f"사이트 스크립트 덮어쓰기 완료: site_code={site_code}, script_id={script_id}")
                return result.data[0] if result.data else {}
            else:
                # 기존 스크립트가 없으면 새로 생성
                version = await self._get_next_version(user_id, site_code)
                script_data = {
                    'user_id': user_id,
                    'site_code': site_code,
                    'script_content': script_content,
                    'version': version,
                    'is_active': True
                }
                result = client.table('site_scripts').insert(script_data).execute()
                logger.info(f"새 사이트 스크립트 생성 완료: site_code={site_code}, version={version}")
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
            # DB에서 primary_domain 조회
            result = client.table('user_sites').select('primary_domain').eq('site_code', site_code).execute()
            
            if result.data:
                site_data = result.data[0]
                domain = site_data.get('primary_domain', '')
                
                if domain:
                    if not domain.startswith(('http://', 'https://')):
                        domain = f"https://{domain}"
                    logger.info(f"사이트 도메인 조회 성공: site_code={site_code}, domain={domain}")
                    return domain
                
                logger.info(f"사이트 도메인이 비어있음: site_code={site_code}")
                return None
            else:
                logger.info(f"사이트 도메인 없음: site_code={site_code}")
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
            
            if result.data:
                logger.info(f"기본 스크립트 데이터 생성 완료: site_code={site_code}")
            else:
                logger.warning(f"기본 스크립트 데이터 생성 실패: site_code={site_code}")
                
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
                        # 만료된 멤버십은 자동으로 기본 등급으로 다운그레이드
                        await self._downgrade_expired_membership(user_id)
                        membership['membership_level'] = 0
                        membership['expires_at'] = None
                
                return membership
            return None
        except Exception as e:
            logger.error(f"사용자 멤버십 조회 실패: {e}")
            return None

    async def create_user_membership(self, user_id: str, membership_level: int = 0, 
                                   expires_at: datetime = None) -> Dict[str, Any]:
        """새로운 사용자 멤버십 생성"""
        try:
            membership_data = {
                'user_id': user_id,
                'membership_level': membership_level,
                'expires_at': expires_at.isoformat() if expires_at else None
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').insert(membership_data).execute()
            
            if result.data:
                logger.info(f"사용자 멤버십 생성 완료: user_id={user_id}, level={membership_level}")
                return result.data[0]
            return {}
        except Exception as e:
            logger.error(f"사용자 멤버십 생성 실패: {e}")
            return {}

    async def update_user_membership(self, user_id: str, membership_level: int, 
                                   expires_at: datetime = None) -> bool:
        """사용자 멤버십 업데이트"""
        try:
            update_data = {
                'membership_level': membership_level,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'updated_at': datetime.now().isoformat()
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').update(update_data).eq('user_id', user_id).execute()
            
            if result.data:
                logger.info(f"사용자 멤버십 업데이트 완료: user_id={user_id}, level={membership_level}")
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
                membership = await self.create_user_membership(user_id, 0, None)
                logger.info(f"기본 멤버십 생성: user_id={user_id}")
            return membership
        except Exception as e:
            logger.error(f"사용자 멤버십 확인/생성 실패: {e}")
            return {}

    async def check_membership_level(self, user_id: str, required_level: int) -> bool:
        """사용자가 특정 멤버십 레벨 이상인지 확인"""
        try:
            membership = await self.get_user_membership(user_id)
            if not membership:
                return required_level <= 0  # 기본 레벨(0)만 허용
            
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

    async def _downgrade_expired_membership(self, user_id: str) -> bool:
        """만료된 멤버십을 기본 등급으로 다운그레이드"""
        try:
            update_data = {
                'membership_level': 0,
                'expires_at': None,
                'updated_at': datetime.now().isoformat()
            }
            
            client = self._get_client(use_admin=True)
            result = client.table('user_memberships').update(update_data).eq('user_id', user_id).execute()
            
            if result.data:
                logger.info(f"만료된 멤버십 다운그레이드 완료: user_id={user_id}")
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
                logger.info(f"배치 다운그레이드 완료: {downgraded_count}건 처리")
                await self.log_system_event(
                    event_type='batch_membership_downgrade',
                    event_data={'downgraded_count': downgraded_count}
                )
            
            return downgraded_count
        except Exception as e:
            logger.error(f"배치 멤버십 다운그레이드 실패: {e}")
            return 0