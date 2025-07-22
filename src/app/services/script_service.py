import requests
import logging
from typing import Dict, Any
from database_helper import DatabaseHelper
from schemas import ScriptValidationError, ScriptValidationResult

logger = logging.getLogger(__name__)

class ScriptService:
    def __init__(self, db_helper: DatabaseHelper):
        self.db_helper = db_helper

    def validate_script_content(self, script_content: str) -> ScriptValidationResult:
        """
        스크립트 내용의 기본 검증을 수행합니다.
        
        Args:
            script_content: 검증할 스크립트 내용
            
        Returns:
            ScriptValidationResult: 검증 결과
        """
        errors = []
        warnings = []
        
        # 크기 검증 (100KB 제한)
        max_size = 100 * 1024  # 100KB
        if len(script_content.encode('utf-8')) > max_size:
            errors.append(ScriptValidationError(
                field="script_content",
                error_type="size_limit_exceeded",
                message=f"스크립트 크기가 {max_size}바이트를 초과합니다."
            ))
        
        # 기본 XSS 패턴 검사 (간단한 패턴들만)
        dangerous_patterns = [
            "document.write",
            "eval(",
            "innerHTML",
            "outerHTML"
        ]
        
        for pattern in dangerous_patterns:
            if pattern in script_content.lower():
                warnings.append(f"잠재적으로 위험한 패턴 발견: {pattern}")
        
        return ScriptValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def get_scripts_from_imweb(self, access_token: str, unit_code: str) -> Dict[str, Any]:
        """
        아임웹 API를 통해 스크립트를 조회합니다.
        
        Args:
            access_token: 아임웹 API 액세스 토큰
            unit_code: 사이트 유닛 코드
            
        Returns:
            Dict: 스크립트 정보 또는 에러 정보
        """
        try:
            response = requests.get(
                "https://openapi.imweb.me/script",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params={
                    "unitCode": unit_code
                },
                timeout=10
            )
            
            if response.status_code == 200:
                response_data = response.json()
                scripts_list = response_data.get("data", [])
                
                # 위치별 스크립트 정리
                scripts = {"header": "", "body": "", "footer": ""}
                for script in scripts_list:
                    position = script.get("position", "").lower()
                    content = script.get("scriptContent", "")
                    if position in scripts:
                        scripts[position] = content
                        
                return {"success": True, "data": scripts}
            else:
                logger.error(f"아임웹 스크립트 조회 실패: {response.status_code} - {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            logger.error(f"아임웹 스크립트 조회 실패: {e}")
            return {"success": False, "error": str(e)}

    async def deploy_script_to_imweb(self, access_token: str, unit_code: str, position: str, script_content: str = None, method: str = "PUT") -> Dict[str, Any]:
        print(f"[SCRIPT SERVICE] deploy_script_to_imweb 호출: script_content={script_content}...")
        """
        아임웹 API를 통해 스크립트를 배포합니다.
        
        Args:
            access_token: 아임웹 API 액세스 토큰
            unit_code: 사이트 유닛 코드
            position: 스크립트 위치 (header, body, footer)
            script_content: 스크립트 내용 (DELETE일 때는 None 가능)
            method: HTTP 메서드 (PUT for update, POST for create, DELETE for remove)
            
        Returns:
            Dict: 배포 결과
        """
        try:
            url = "https://openapi.imweb.me/script"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            if method == "DELETE":
                # DELETE 요청 시에는 쿼리 파라미터로 전송
                params = {
                    "unitCode": unit_code,
                    "position": position
                }
                response = requests.delete(url, headers=headers, params=params, timeout=10)
            else:
                # PUT, POST 요청 시에는 JSON 바디로 전송
                data = {
                    "unitCode": unit_code,
                    "position": position,
                    "scriptContent": script_content
                }
                
                if method == "PUT":
                    response = requests.put(url, headers=headers, json=data, timeout=10)
                else:
                    response = requests.post(url, headers=headers, json=data, timeout=10)
            
            if response.status_code == 200:
                response_data = response.json()
                return {"success": True, "data": response_data.get("data", {})}
            else:
                logger.error(f"아임웹 스크립트 {method} 실패: {response.status_code} - {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            logger.error(f"아임웹 스크립트 {method} 실패: {e}")
            return {"success": False, "error": str(e)}

    async def get_site_scripts(self, user_id: str, site_code: str) -> Dict[str, Any]:
        print(f"[SERVICE] get_site_scripts 스크립트 조회 요청: user_id={user_id}, site_code={site_code}")
        """
        특정 사이트의 현재 스크립트를 데이터베이스에서 조회합니다.
        
        Args:
            user_id: 사용자 ID
            site_code: 사이트 ID (사이트 코드)
            
        Returns:
            Dict: 스크립트 조회 결과
        """
        try:
            # 데이터베이스에서 활성 스크립트 조회
            script_data = await self.db_helper.get_site_script(user_id, site_code)
            
            if script_data:
                logger.info(f"사이트 {site_code}의 스크립트를 DB에서 조회 성공")
                script_content = script_data.get('script_content', '')
                
                return {
                    "success": True, 
                    "data": {
                        "script": script_content
                    }
                }
            else:
                logger.debug(f"사이트 {site_code}의 활성 스크립트가 없음")
                return {
                    "success": True,
                    "data": {
                        "script": ""
                    }
                }
            
        except Exception as e:
            logger.error(f"스크립트 조회 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def deploy_site_scripts(self, user_id: str, site_code: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        """
        특정 사이트에 스크립트를 배포합니다. (DB 저장 + 아임웹 footer에 모듈 스크립트 배포)
        
        Args:
            user_id: 사용자 ID
            site_code: 사이트 ID (사이트 코드)
            scripts_data: 배포할 스크립트 데이터
            
        Returns:
            Dict: 스크립트 배포 결과
        """
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.db_helper.get_user_site_by_code(user_id, site_code)
            if not site:
                return {"success": False, "error": "사이트를 찾을 수 없거나 접근 권한이 없습니다.", "status_code": 404}
            
            # 액세스 토큰 확인
            access_token = site.get('access_token')
            if not access_token:
                return {"success": False, "error": "사이트의 API 토큰이 설정되지 않았습니다.", "status_code": 400}
            
            # 사이트 유닛 코드 확인
            unit_code = site.get('unit_code')
            if not unit_code:
                return {"success": False, "error": "사이트의 유닛 코드가 설정되지 않았습니다.", "status_code": 400}
            
            # 스크립트가 비어있으면 삭제
            if not scripts_data:
                # DB에서 기존 스크립트 삭제 (비활성화)
                await self.db_helper.delete_site_script(user_id, site_code)
                
                # 아임웹에서도 footer 스크립트 삭제
                decrypted_token = self.db_helper._decrypt_token(access_token)
                await self.deploy_script_to_imweb(decrypted_token, unit_code, "footer", method="DELETE")
                
                from datetime import datetime
                deployed_at = datetime.now().isoformat() + "Z"
                
                return {
                    "success": True,
                    "data": {
                        "deployed_at": deployed_at,
                        "site_code": site_code,
                        "deployed_scripts": {"header": "", "body": "", "footer": ""}
                    },
                    "message": "스크립트가 삭제되었습니다."
                }
            
            # 스크립트 검증
            validation_result = self.validate_script_content(scripts_data.get("script", ""))
            if not validation_result.is_valid:
                error_messages = [err.message for err in validation_result.errors]
                return {
                    "success": False,
                    "error": f"스크립트 검증 실패: {'; '.join(error_messages)}",
                    "status_code": 400
                }
            
            # 1단계: DB에 스크립트 저장
            script_record = await self.db_helper.update_site_script(user_id, site_code, scripts_data.get("script", ""))
            if not script_record:
                return {"success": False, "error": "스크립트 데이터베이스 저장 실패", "status_code": 500}
            
            # 2단계: 아임웹 footer에 모듈 스크립트 배포
            import os
            server_base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")
            module_script = f"<script>document.head.appendChild(Object.assign(document.createElement('script'),{{'src':'{server_base_url}/api/v1/sites/{site_code}/script','type':'module'}}))</script>"
            
            decrypted_token = self.db_helper._decrypt_token(access_token)
            
            # 먼저 PUT으로 기존 스크립트 수정 시도
            deploy_result = await self.deploy_script_to_imweb(
                decrypted_token, unit_code, "footer", module_script, method="PUT"
            )
            
            if not deploy_result["success"]:
                # PUT 실패시 POST로 새로운 스크립트 생성 시도
                deploy_result = await self.deploy_script_to_imweb(
                    decrypted_token, unit_code, "footer", module_script, method="POST"
                )
                
                if not deploy_result["success"]:
                    logger.error(f"아임웹 모듈 스크립트 배포 실패: {deploy_result.get('error', '알 수 없는 오류')}")
                    return {
                        "success": False,
                        "error": f"아임웹 스크립트 배포 실패: {deploy_result.get('error', '알 수 없는 오류')}",
                        "status_code": 500
                    }
            
            from datetime import datetime
            deployed_at = datetime.now().isoformat() + "Z"
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='script_deployed',
                event_data={
                    'site_code': site_code,
                    'action': 'deploy_script_with_module',
                    'script_version': script_record.get('version'),
                    'deployed_at': deployed_at,
                    'module_url': f"{server_base_url}/api/v1/sites/{site_code}/script"
                }
            )
            
            return {
                "success": True,
                "data": {
                    "deployed_at": deployed_at,
                    "site_code": site_code,
                    "script_version": script_record.get('version'),
                    "module_url": f"{server_base_url}/api/v1/sites/{site_code}/script",
                    "deployed_scripts": {
                        "script": script_record.get('script_content', ''),
                    }
                },
                "message": "스크립트가 데이터베이스에 저장되고 아임웹에 모듈 형태로 배포되었습니다."
            }
            
        except Exception as e:
            logger.error(f"스크립트 배포 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}