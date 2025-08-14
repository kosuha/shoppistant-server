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
        """Helper function to get session data"""
        if self.session_tools:
            return self.session_tools.get_session_data(session_id)
        return None

    def _optimize_image(self, image_bytes: bytes, max_size_kb: int = 200, quality: int = 85) -> bytes:
        """
        Optimize image to reduce size.
        
        Args:
            image_bytes: Original image bytes
            max_size_kb: Maximum size (KB)
            quality: JPEG quality (1-100)
            
        Returns:
            bytes: Optimized image bytes
        """
        try:
            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_bytes))
            
            # RGBA -> RGB conversion (JPEG compatibility)
            if image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'RGBA':
                    background.paste(image, mask=image.split()[-1])
                else:
                    background.paste(image, mask=image.split()[-1])
                image = background
            
            # Resize if image is too large
            max_dimension = 1920
            if image.width > max_dimension or image.height > max_dimension:
                ratio = min(max_dimension / image.width, max_dimension / image.height)
                new_size = (int(image.width * ratio), int(image.height * ratio))
                image = image.resize(new_size, Image.Resampling.LANCZOS)
            
            # Compress with quality adjustment
            for q in range(quality, 10, -10):
                output = io.BytesIO()
                image.save(output, format='JPEG', quality=q, optimize=True)
                compressed_bytes = output.getvalue()
                
                # Return if under target size
                if len(compressed_bytes) <= max_size_kb * 1024:
                    return compressed_bytes
            
            # Additional resizing if still too large even with minimum quality
            for scale in [0.8, 0.6, 0.4]:
                new_size = (int(image.width * scale), int(image.height * scale))
                resized = image.resize(new_size, Image.Resampling.LANCZOS)
                output = io.BytesIO()
                resized.save(output, format='JPEG', quality=20, optimize=True)
                compressed_bytes = output.getvalue()
                
                if len(compressed_bytes) <= max_size_kb * 1024:
                    return compressed_bytes
            
            # Finally return with minimum size
            output = io.BytesIO()
            resized.save(output, format='JPEG', quality=10, optimize=True)
            return output.getvalue()
            
        except Exception as e:
            return image_bytes

    async def capture_screenshot(self, url: str, width: int = 1280, height: int = 720, wait_seconds: int = 2):
        """
        Capture a screenshot of a website.
        
        Args:
            url: Website URL to capture
            width: Browser window width (default: 1280)
            height: Browser window height (default: 720)
            wait_seconds: Wait time after page load (seconds, default: 2)
            
        Returns:
            dict: Screenshot result (including base64 encoded image data)
        """
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Set browser window size
                await page.set_viewport_size({"width": width, "height": height})
                
                # Load page
                await page.goto(url, wait_until='networkidle')
                
                # Additional wait time
                await asyncio.sleep(wait_seconds)
                
                # Capture screenshot (PNG format)
                screenshot_bytes = await page.screenshot(type='png')
                
                await browser.close()
                
                # Optimize image
                optimized_bytes = self._optimize_image(screenshot_bytes)
                
                # Base64 encoding
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
                "error": f"Screenshot capture failed: {str(e)}",
                "url": url
            }

    async def capture_fullpage_screenshot(self, url: str, width: int = 1280, wait_seconds: int = 2):
        """
        Capture a full page screenshot of a website.
        
        Args:
            url: Website URL to capture
            width: Browser window width (default: 1280)
            wait_seconds: Wait time after page load (seconds, default: 2)
            
        Returns:
            dict: Full page screenshot result (including base64 encoded image data)
        """
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Set browser window width only (height auto-adjusts)
                await page.set_viewport_size({"width": width, "height": 720})
                
                # Load page
                await page.goto(url, wait_until='networkidle')
                
                # Additional wait time
                await asyncio.sleep(wait_seconds)
                
                # Capture full page screenshot
                screenshot_bytes = await page.screenshot(type='png', full_page=True)
                
                await browser.close()
                
                # Optimize image (smaller size for full page)
                optimized_bytes = self._optimize_image(screenshot_bytes, max_size_kb=150)
                
                # Base64 encoding
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
                "error": f"Full page screenshot capture failed: {str(e)}",
                "url": url
            }

    async def capture_element_screenshot(self, url: str, selector: str, width: int = 1280, height: int = 720, wait_seconds: int = 2):
        """
        Capture a screenshot of a specific element on a website.
        
        Args:
            url: Website URL to capture
            selector: CSS selector of the element to capture
            width: Browser window width (default: 1280)
            height: Browser window height (default: 720)
            wait_seconds: Wait time after page load (seconds, default: 2)
            
        Returns:
            dict: Element screenshot result (including base64 encoded image data)
        """
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Set browser window size
                await page.set_viewport_size({"width": width, "height": height})
                
                # Load page
                await page.goto(url, wait_until='networkidle')
                
                # Additional wait time
                await asyncio.sleep(wait_seconds)
                
                # Find element
                element = await page.query_selector(selector)
                if not element:
                    return {
                        "success": False,
                        "error": f"Could not find element matching selector '{selector}'.",
                        "url": url,
                        "selector": selector
                    }
                
                # Capture element screenshot
                screenshot_bytes = await element.screenshot(type='png')
                
                await browser.close()
                
                # Optimize image
                optimized_bytes = self._optimize_image(screenshot_bytes)
                
                # Base64 encoding
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
                "error": f"Element screenshot capture failed: {str(e)}",
                "url": url,
                "selector": selector
            }