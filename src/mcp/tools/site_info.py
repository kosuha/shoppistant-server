import requests
import json
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from .session_tools import SessionTools

class SiteInfo:
    def __init__(self, mcp, session_tools: SessionTools = None):
        self.mcp = mcp
        self.session_tools = session_tools
        self._register_tools()
    
    def _register_tools(self):
        self.mcp.tool(self.get_site_info)
        self.mcp.tool(self.get_site_html_structure)
        self.mcp.tool(self.execute_console_log)
    
    def get_session_data(self, session_id: str):
        """세션 데이터를 가져오는 헬퍼 함수"""
        if self.session_tools:
            return self.session_tools.get_session_data(session_id)
        return None
    
    async def get_site_info(self, session_id: str, site_name: str = None, site_code: str = None):
        """
        사이트 이름 또는 사이트 코드로 사이트 정보를 조회합니다.

        사이트 정보:
            siteCode: 사이트 코드
            unitCode: 사이트 유닛 코드
            name: 사이트 이름
            companyName: 회사/단체 이름
            presidentName: 대표자 이름
            phone: 사이트 전화번호
            email: 사이트 이메일
            address1: 사이트 건물주소
            address2: 사이트 상세주소
            companyRegistrationNo: 사업자 등록번호
            primaryDomain: 사이트 기본 도메인
        
        Args:
            session_id: 세션 ID
            site_name: 특정 사이트 이름 (없으면 첫 번째 사이트)
            site_code: 특정 사이트 코드 (없으면 첫 번째 사이트)
        """
        print("##### CALL TOOL: get_site_info")
        try:
            session_data = self.get_session_data(session_id)
            
            if not session_data:
                return {"error": "세션이 존재하지 않습니다."}
            
            sites = session_data.get("sites", [])
            if not sites:
                return {"error": "세션에 사이트 정보가 없습니다."}
            
            target_site = None
            if site_code:
                target_site = next((site for site in sites if site["site_code"] == site_code), None)
                if not target_site:
                    return {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
            else:
                target_site = sites[0]
            
            access_token = target_site["access_token"]

            response = requests.get("https://openapi.imweb.me/site-info",
                headers={
                    "Authorization": f"Bearer {access_token}",
                }
            )
            if response.status_code != 200:
                print(f"사이트 호출 실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            response_data = response.json()
            site_info = response_data.get("data", {})
            unit_code = site_info.get("unitList", [{}])[0].get("unitCode", "")
            if not unit_code:
                return {"error": "사이트 단위 정보가 없습니다."}

            response = requests.get(
                f"https://openapi.imweb.me/site-info/unit/{unit_code}",
                headers={
                    "Authorization": f"Bearer {access_token}"
                }
            )
            if response.status_code != 200:
                print(f"사이트 단위 정보 조회 실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            unit_info = response.json().get("data", {})
            return {
                "siteCode": unit_info.get("siteCode", ""),
                "unitCode": unit_info.get("unitCode", ""),
                "name": unit_info.get("name", ""),
                "companyName": unit_info.get("companyName", ""),
                "presidentName": unit_info.get("presidentName", ""),
                "phone": unit_info.get("phone", ""),
                "email": unit_info.get("email", ""),
                "address1": unit_info.get("address1", ""),
                "address2": unit_info.get("address2", ""),
                "companyRegistrationNo": unit_info.get("companyRegistrationNo", ""),
                "primaryDomain": unit_info.get("primaryDomain", ""),
            }
            
        except Exception as e:
            return {"error": str(e)}

    def _clean_html(self, html_content: str) -> str:
        """HTML에서 script, style, meta 태그를 제거하고 HTML 태그만 남김"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # script, style, meta 태그 제거
        for tag in soup(['script', 'style', 'meta']):
            tag.decompose()
        
        return str(soup)

    async def get_site_html_structure(self, url: str):
        """
        웹사이트의 url을 통해 HTML 코드를 가져와 간단한 JSON 형태로 변환하여 구조 분석에 최적화된 형태로 제공합니다.
        script, style, meta 태그는 제거하고, 의미 있는 텍스트만 포함합니다.
        태그 이름, 클래스, ID를 기반으로 선택자를 구성하여 중첩된 JSON 구조로 변환합니다.
        
        Before 예시:
            <!-- 상품 정보 블록 -->
            <div class="product">
                <h2 id="pt123" class="title">iPhone 15</h2>
                <span class="price">₩1,290,000</span>
            </div>

        After(return) 예시:
            {
                "div.product": {
                    "h2#pt123.title": "iPhone 15",
                    "span.price": "₩1,290,000"
                }
            }

        Args:
            url: 사이트 URL
            
        Returns:
            dict: JSON 형태의 HTML 구조 정보
        """
        print(f"##### CALL TOOL: get_site_html_structure - URL: {url}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 페이지 로드
                await page.goto(url, wait_until='networkidle')
                
                # HTML 소스코드 가져오기
                html_content = await page.content()
                
                await browser.close()
            
            # HTML 정리 후 간단한 구조로 변환
            json_html = await self._parse_html_to_json(html_content)
            print(json_html)  # 디버깅용 출력
            return json_html

        except Exception as e:
            return {"error": f"사이트 HTML 구조 파싱 실패: {str(e)}"}

    def _is_meaningful_text(self, text: str) -> bool:
        """의미있는 텍스트인지 판단"""
        if not text or len(text.strip()) < 2:
            return False
        
        # 공백, 특수문자만 있는 경우 제외
        stripped = text.strip()
        if not stripped or stripped in ['\n', '\t', '\r', ' ', '&nbsp;']:
            return False
            
        return True

    def _build_simple_structure(self, element, structure=None):
        """HTML을 간단한 중첩 JSON 구조로 변환"""
        if structure is None:
            structure = {}
        
        if element.name is None:
            return structure
        
        # 선택자 생성
        selector = element.name
        if element.get('id'):
            selector += f"#{element.get('id')}"
        if element.get('class'):
            classes = element.get('class')
            # 의미 있는 클래스만 포함 (길이 제한)
            meaningful_classes = [cls for cls in classes if len(cls) < 30 and not cls.startswith('css-')]
            if meaningful_classes:
                selector += f".{'.'.join(meaningful_classes[:2])}"
        
        # 직접 텍스트 추출
        direct_text = ""
        if element.string:
            direct_text = element.string.strip()
        else:
            # 직접 텍스트 노드만 추출 (자식 요소 텍스트 제외)
            for content in element.contents:
                if isinstance(content, str):
                    text = content.strip()
                    if text and self._is_meaningful_text(text):
                        direct_text += text + " "
            direct_text = direct_text.strip()
        
        # 자식 요소들 처리
        children = {}
        for child in element.find_all(recursive=False):
            if child.name:
                child_structure = self._build_simple_structure(child)
                children.update(child_structure)
        
        # 구조에 추가
        if direct_text and children:
            # 텍스트와 자식 요소 모두 있는 경우
            structure[selector] = {
                "_text": direct_text,
                **children
            }
        elif direct_text:
            # 텍스트만 있는 경우
            structure[selector] = direct_text
        elif children:
            # 자식 요소만 있는 경우
            structure[selector] = children
        else:
            # 빈 요소인 경우 (건너뛰기)
            pass
        
        return structure

    def _parse_html_to_json(self, html_content: str):
        """
        HTML을 간단한 중첩 JSON 구조로 변환
        
        Args:
            html_content: 변환할 HTML 내용
        
        Returns:
            dict: 변환된 JSON 구조
        """
        
        try:
            # HTML 정리
            cleaned_html = self._clean_html(html_content)
            
            # BeautifulSoup으로 파싱
            soup = BeautifulSoup(cleaned_html, 'html.parser')
            
            # 간단한 구조로 변환
            structure = {}
            
            # 최상위 요소부터 처리
            root_elements = soup.find_all(recursive=False)
            for element in root_elements:
                if element.name:
                    element_structure = self._build_simple_structure(element)
                    structure.update(element_structure)
            
            return structure
            
        except Exception as e:
            return {"error": f"HTML 파싱 실패: {str(e)}"}

    def _flatten_structure(self, structure, count=0):
        """구조를 평탄화하여 요소 개수 계산"""
        if isinstance(structure, dict):
            for key, value in structure.items():
                if key != "_text":
                    count += 1
                    if isinstance(value, dict):
                        count = self._flatten_structure(value, count)
        return count

    async def execute_console_log(self, url: str, console_command: str):
        """
        웹사이트에서 콘솔 명령을 실행하고 결과를 반환합니다.
        
        Args:
            url: 실행할 웹사이트 URL
            console_command: 실행할 JavaScript 콘솔 명령
            
        Returns:
            dict: 콘솔 실행 결과
        """
        print(f"##### CALL TOOL: execute_console_log - URL: {url}, Command: {console_command}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 콘솔 로그 수집을 위한 리스너 설정
                console_logs = []
                
                def handle_console(msg):
                    console_logs.append({
                        "type": msg.type,
                        "text": msg.text,
                        "location": msg.location
                    })
                
                page.on("console", handle_console)
                
                # 페이지 로드
                await page.goto(url, wait_until='networkidle')
                
                # JavaScript 콘솔 명령 실행
                try:
                    result = await page.evaluate(console_command)
                    execution_result = {
                        "success": True,
                        "result": result,
                        "type": type(result).__name__
                    }
                except Exception as eval_error:
                    execution_result = {
                        "success": False,
                        "error": str(eval_error),
                        "type": "error"
                    }
                
                await browser.close()
                
                return {
                    "url": url,
                    "command": console_command,
                    "execution": execution_result,
                    "console_logs": console_logs[-10:]  # 최근 10개 로그만 반환
                }
                
        except Exception as e:
            return {
                "error": f"콘솔 명령 실행 실패: {str(e)}",
                "url": url,
                "command": console_command
            }
    