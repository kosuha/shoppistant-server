import base64
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from PIL import Image
import io
from .session_tools import SessionTools

class Screenshot:
    def __init__(self, mcp, session_tools: SessionTools = None):
        self.mcp = mcp
        self.session_tools = session_tools
        self._register_tools()
    
    def _register_tools(self):
        self.mcp.tool(self.capture_screenshot)
        self.mcp.tool(self.capture_fullpage_screenshot)
        self.mcp.tool(self.capture_element_screenshot)
    
    def get_session_data(self, session_id: str):
        """세션 데이터를 가져오는 헬퍼 함수"""
        if self.session_tools:
            return self.session_tools.get_session_data(session_id)
        return None

    def _optimize_image(self, image_bytes: bytes, max_size_kb: int = 200, quality: int = 85) -> bytes:
        """
        이미지를 최적화하여 크기를 줄입니다.
        
        Args:
            image_bytes: 원본 이미지 바이트
            max_size_kb: 최대 크기 (KB)
            quality: JPEG 품질 (1-100)
            
        Returns:
            bytes: 최적화된 이미지 바이트
        """
        try:
            # PIL Image로 변환
            image = Image.open(io.BytesIO(image_bytes))
            
            # RGBA -> RGB 변환 (JPEG 호환성)
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image, mask=image.split()[-1])
                image = background
            
            # 이미지 크기가 너무 큰 경우 리사이징
            max_dimension = 1920
            if image.width > max_dimension or image.height > max_dimension:
                ratio = min(max_dimension / image.width, max_dimension / image.height)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # 품질 조절하며 압축
            for q in range(quality, 10, -10):
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=q, optimize=True)
                compressed_bytes = output.getvalue()
                
                # 목표 크기 이하면 반환
                if len(compressed_bytes) <= max_size_kb * 1024:
                    return compressed_bytes
            
            # 최소 품질로도 크기가 큰 경우 추가 리사이징
            for scale in [0.8, 0.6, 0.4]:
                new_size = (int(image.width * scale), int(image.height * scale))
                resized = image.resize(new_size, Image.Resampling.LANCZOS)
                output = io.BytesIO()
                resized.save(output, format='JPEG', quality=20, optimize=True)
                compressed_bytes = output.getvalue()
                
                if len(compressed_bytes) <= max_size_kb * 1024:
                    return compressed_bytes
            
            # 최종적으로 최소 크기로 반환
            output = io.BytesIO()
            resized.save(output, format='JPEG', quality=10, optimize=True)
            return output.getvalue()
            
        except Exception as e:
            print(f"이미지 최적화 실패: {e}")
            return image_bytes

    async def capture_screenshot(self, url: str, width: int = 1280, height: int = 720, wait_seconds: int = 2):
        """
        웹사이트의 스크린샷을 캡처합니다.
        
        Args:
            url: 캡처할 웹사이트 URL
            width: 브라우저 창 너비 (기본값: 1280)
            height: 브라우저 창 높이 (기본값: 720)
            wait_seconds: 페이지 로드 후 대기 시간 (초, 기본값: 2)
            
        Returns:
            dict: 스크린샷 결과 (base64 인코딩된 이미지 데이터 포함)
        """
        print(f"##### CALL TOOL: capture_screenshot - URL: {url}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 브라우저 창 크기 설정
                await page.set_viewport_size({"width": width, "height": height})
                
                # 페이지 로드
                await page.goto(url, wait_until='networkidle')
                
                # 추가 대기 시간
                await asyncio.sleep(wait_seconds)
                
                # 스크린샷 캡처 (PNG 형식)
                screenshot_bytes = await page.screenshot(type='png')
                
                await browser.close()
                
                # 이미지 최적화
                optimized_bytes = self._optimize_image(screenshot_bytes)
                
                # base64 인코딩
                screenshot_base64 = base64.b64encode(optimized_bytes).decode('utf-8')
                
                return {
                    "success": True,
                    "url": url,
                    "screenshot": screenshot_base64,
                    "format": "jpeg",
                    "size": {
                        "width": width,
                        "height": height
                    },
                    "timestamp": datetime.now().isoformat(),
                    "original_size": len(screenshot_bytes),
                    "optimized_size": len(optimized_bytes)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"스크린샷 캡처 실패: {str(e)}",
                "url": url
            }

    async def capture_fullpage_screenshot(self, url: str, width: int = 1280, wait_seconds: int = 2):
        """
        웹사이트의 전체 페이지 스크린샷을 캡처합니다.
        
        Args:
            url: 캡처할 웹사이트 URL
            width: 브라우저 창 너비 (기본값: 1280)
            wait_seconds: 페이지 로드 후 대기 시간 (초, 기본값: 2)
            
        Returns:
            dict: 전체 페이지 스크린샷 결과 (base64 인코딩된 이미지 데이터 포함)
        """
        print(f"##### CALL TOOL: capture_fullpage_screenshot - URL: {url}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 브라우저 창 너비만 설정 (높이는 자동 조절)
                await page.set_viewport_size({"width": width, "height": 720})
                
                # 페이지 로드
                await page.goto(url, wait_until='networkidle')
                
                # 추가 대기 시간
                await asyncio.sleep(wait_seconds)
                
                # 전체 페이지 스크린샷 캡처
                screenshot_bytes = await page.screenshot(type='png', full_page=True)
                
                await browser.close()
                
                # 이미지 최적화 (전체 페이지는 더 작은 크기로)
                optimized_bytes = self._optimize_image(screenshot_bytes, max_size_kb=150)
                
                # base64 인코딩
                screenshot_base64 = base64.b64encode(optimized_bytes).decode('utf-8')
                
                return {
                    "success": True,
                    "url": url,
                    "screenshot": screenshot_base64,
                    "format": "jpeg",
                    "full_page": True,
                    "viewport_width": width,
                    "timestamp": datetime.now().isoformat(),
                    "original_size": len(screenshot_bytes),
                    "optimized_size": len(optimized_bytes)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"전체 페이지 스크린샷 캡처 실패: {str(e)}",
                "url": url
            }

    async def capture_element_screenshot(self, url: str, selector: str, width: int = 1280, height: int = 720, wait_seconds: int = 2):
        """
        웹사이트의 특정 요소 스크린샷을 캡처합니다.
        
        Args:
            url: 캡처할 웹사이트 URL
            selector: 캡처할 요소의 CSS 선택자
            width: 브라우저 창 너비 (기본값: 1280)
            height: 브라우저 창 높이 (기본값: 720)
            wait_seconds: 페이지 로드 후 대기 시간 (초, 기본값: 2)
            
        Returns:
            dict: 요소 스크린샷 결과 (base64 인코딩된 이미지 데이터 포함)
        """
        print(f"##### CALL TOOL: capture_element_screenshot - URL: {url}, Selector: {selector}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # 브라우저 창 크기 설정
                await page.set_viewport_size({"width": width, "height": height})
                
                # 페이지 로드
                await page.goto(url, wait_until='networkidle')
                
                # 추가 대기 시간
                await asyncio.sleep(wait_seconds)
                
                # 요소 찾기
                element = await page.query_selector(selector)
                if not element:
                    return {
                        "success": False,
                        "error": f"선택자 '{selector}'에 해당하는 요소를 찾을 수 없습니다.",
                        "url": url,
                        "selector": selector
                    }
                
                # 요소 스크린샷 캡처
                screenshot_bytes = await element.screenshot(type='png')
                
                await browser.close()
                
                # 이미지 최적화
                optimized_bytes = self._optimize_image(screenshot_bytes)
                
                # base64 인코딩
                screenshot_base64 = base64.b64encode(optimized_bytes).decode('utf-8')
                
                return {
                    "success": True,
                    "url": url,
                    "selector": selector,
                    "screenshot": screenshot_base64,
                    "format": "jpeg",
                    "timestamp": datetime.now().isoformat(),
                    "original_size": len(screenshot_bytes),
                    "optimized_size": len(optimized_bytes)
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"요소 스크린샷 캡처 실패: {str(e)}",
                "url": url,
                "selector": selector
            }