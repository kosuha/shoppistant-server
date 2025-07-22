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

    async def deploy_script_to_imweb(self, access_token: str, unit_code: str, position: str, script_content: str, method: str = "PUT") -> Dict[str, Any]:
        """
        아임웹 API를 통해 스크립트를 배포합니다.
        
        Args:
            access_token: 아임웹 API 액세스 토큰
            unit_code: 사이트 유닛 코드
            position: 스크립트 위치 (header, body, footer)
            script_content: 스크립트 내용
            method: HTTP 메서드 (PUT for update, POST for create)
            
        Returns:
            Dict: 배포 결과
        """
        try:
            url = "https://openapi.imweb.me/script"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
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
                logger.error(f"아임웹 스크립트 배포 실패: {response.status_code} - {response.text}")
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            logger.error(f"아임웹 스크립트 배포 실패: {e}")
            return {"success": False, "error": str(e)}

    async def get_site_scripts(self, user_id: str, site_id: str) -> Dict[str, Any]:
        """
        특정 사이트의 현재 스크립트를 조회합니다.
        
        Args:
            user_id: 사용자 ID
            site_id: 사이트 ID (사이트 코드)
            
        Returns:
            Dict: 스크립트 조회 결과
        """
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.db_helper.get_user_site_by_code(user_id, site_id)
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
            
            # 토큰 복호화
            decrypted_token = self.db_helper._decrypt_token(access_token)
            
            # 아임웹 API로 스크립트 조회
            script_result = await self.get_scripts_from_imweb(decrypted_token, unit_code)
            
            if not script_result["success"]:
                return {"success": False, "error": f"스크립트 조회 실패: {script_result['error']}", "status_code": 500}
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='script_retrieved',
                event_data={'site_code': site_id, 'action': 'get_scripts'}
            )
            
            return {"success": True, "data": script_result["data"]}
            
        except Exception as e:
            logger.error(f"스크립트 조회 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}

    async def deploy_site_scripts(self, user_id: str, site_id: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        """
        특정 사이트에 스크립트를 배포합니다.
        
        Args:
            user_id: 사용자 ID
            site_id: 사이트 ID (사이트 코드)
            scripts_data: 배포할 스크립트 데이터 (header, body, footer)
            
        Returns:
            Dict: 스크립트 배포 결과
        """
        try:
            # 사용자가 해당 사이트에 접근 권한이 있는지 확인
            site = await self.db_helper.get_user_site_by_code(user_id, site_id)
            if not site:
                return {"success": False, "error": "사이트를 찾을 수 없거나 접근 권한이 없습니다.", "status_code": 404}
            
            # 액세스 토큰 확인
            access_token = site.get('access_token')
            if not access_token:
                return {"success": False, "error": "사이트의 API 토큰이 설정되지 않았습니다.", "status_code": 400}
            
            # 스크립트 데이터 추출 및 검증
            scripts_to_deploy = {}
            for position in ["header", "body", "footer"]:
                script_content = scripts_data.get(position)
                if script_content:
                    # 스크립트 검증
                    validation_result = self.validate_script_content(script_content)
                    if not validation_result.is_valid:
                        error_messages = [err.message for err in validation_result.errors]
                        return {
                            "success": False,
                            "error": f"{position} 스크립트 검증 실패: {'; '.join(error_messages)}",
                            "status_code": 400
                        }
                    scripts_to_deploy[position] = script_content
            
            if not scripts_to_deploy:
                return {"success": False, "error": "배포할 스크립트가 없습니다.", "status_code": 400}
            
            # 사이트 유닛 코드 확인
            unit_code = site.get('unit_code')
            if not unit_code:
                return {"success": False, "error": "사이트의 유닛 코드가 설정되지 않았습니다.", "status_code": 400}
            
            # 토큰 복호화
            decrypted_token = self.db_helper._decrypt_token(access_token)
            
            # 각 위치별로 스크립트 배포
            deployment_results = {}
            for position, script_content in scripts_to_deploy.items():
                try:
                    # 먼저 PUT으로 기존 스크립트 수정 시도
                    deploy_result = await self.deploy_script_to_imweb(
                        decrypted_token, unit_code, position, script_content, method="PUT"
                    )
                    
                    if not deploy_result["success"]:
                        # PUT 실패시 POST로 새로운 스크립트 생성 시도
                        deploy_result = await self.deploy_script_to_imweb(
                            decrypted_token, unit_code, position, script_content, method="POST"
                        )
                        
                        if not deploy_result["success"]:
                            return {
                                "success": False,
                                "error": f"{position} 스크립트 배포 실패: {deploy_result.get('error', '알 수 없는 오류')}",
                                "status_code": 500
                            }
                    
                    deployment_results[position] = script_content
                    logger.info(f"스크립트 배포 성공: {site_id} - {position}")
                    
                except Exception as deploy_error:
                    logger.error(f"{position} 스크립트 배포 실패: {deploy_error}")
                    return {
                        "success": False,
                        "error": f"{position} 스크립트 배포 실패: {str(deploy_error)}",
                        "status_code": 500
                    }
            
            from datetime import datetime
            deployed_at = datetime.now().isoformat() + "Z"
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='script_deployed',
                event_data={
                    'site_code': site_id,
                    'action': 'deploy_scripts',
                    'deployed_positions': list(deployment_results.keys()),
                    'deployed_at': deployed_at
                }
            )
            
            return {
                "success": True,
                "data": {
                    "deployed_at": deployed_at,
                    "site_id": site_id,
                    "deployed_scripts": deployment_results
                },
                "message": f"{len(deployment_results)}개 스크립트가 성공적으로 배포되었습니다."
            }
            
        except Exception as e:
            logger.error(f"스크립트 배포 실패: {e}")
            return {"success": False, "error": str(e), "status_code": 500}