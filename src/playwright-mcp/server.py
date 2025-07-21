#!/usr/bin/env python3
"""
Playwright MCP 서버 - Python FastMCP 버전
"""

from fastmcp import FastMCP
import asyncio
from playwright.async_api import async_playwright
import base64
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastMCP 앱 생성
mcp = FastMCP(name="playwright-mcp-server")

# 전역 브라우저 상태
browser_state = {
    'playwright': None,
    'browser': None,
    'context': None,
    'page': None,
    'network_requests': [],
    'network_intercept_enabled': False
}

async def ensure_browser():
    """브라우저 인스턴스 확보"""
    print("##### Ensure Browser Instance")
    if browser_state['browser'] is None:
        browser_state['playwright'] = await async_playwright().start()
        browser_state['browser'] = await browser_state['playwright'].chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu'
            ]
        )
        browser_state['context'] = await browser_state['browser'].new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        browser_state['page'] = await browser_state['context'].new_page()
        logger.info("브라우저 인스턴스 생성 완료")

@mcp.tool()
async def browser_navigate(url: str) -> str:
    """웹페이지로 이동합니다."""
    print("##### CALL TOOL: browser_navigate")
    await ensure_browser()
    await browser_state['page'].goto(url, wait_until='networkidle')
    return f"Successfully navigated to: {url}"

@mcp.tool()
async def browser_click(selector: str) -> str:
    """엘리먼트를 클릭합니다."""
    print("##### CALL TOOL: browser_click")
    await ensure_browser()
    await browser_state['page'].click(selector)
    return f"Successfully clicked: {selector}"

@mcp.tool()
async def browser_type(selector: str, text: str) -> str:
    """입력 필드에 텍스트를 입력합니다."""
    print("##### CALL TOOL: browser_type")
    await ensure_browser()
    await browser_state['page'].fill(selector, text)
    return f'Successfully typed "{text}" into: {selector}'

@mcp.tool()
async def browser_get_text(selector: str) -> str:
    """엘리먼트의 텍스트를 가져옵니다."""
    print("##### CALL TOOL: browser_get_text")
    await ensure_browser()
    elements = await browser_state['page'].locator(selector).all_text_contents()
    return f"Text content: {', '.join(elements)}"

@mcp.tool()
async def browser_screenshot(full_page: bool = True) -> str:
    """현재 페이지의 스크린샷을 찍습니다."""
    print("##### CALL TOOL: browser_screenshot")
    await ensure_browser()
    screenshot = await browser_state['page'].screenshot(full_page=full_page, type='png')
    base64_image = base64.b64encode(screenshot).decode('utf-8')
    return f"Screenshot taken successfully (base64 length: {len(base64_image)})"

@mcp.tool()
async def browser_wait_for(selector: str, timeout: int = 30000) -> str:
    """엘리먼트가 나타날 때까지 기다립니다."""
    print("##### CALL TOOL: browser_wait_for")
    await ensure_browser()
    await browser_state['page'].wait_for_selector(selector, timeout=timeout)
    return f"Successfully waited for: {selector}"

@mcp.tool()
async def browser_evaluate(script: str) -> str:
    """JavaScript 코드를 실행합니다."""
    print("##### CALL TOOL: browser_evaluate")
    await ensure_browser()
    result = await browser_state['page'].evaluate(script)
    return f"Script result: {result}"

@mcp.tool()
async def browser_submit(selector: str) -> str:
    """폼을 제출합니다."""
    print("##### CALL TOOL: browser_submit")
    await ensure_browser()
    await browser_state['page'].locator(selector).press('Enter')
    return f"Successfully submitted form: {selector}"

@mcp.tool()
async def browser_upload_file(selector: str, file_path: str) -> str:
    """파일을 업로드합니다."""
    print("##### CALL TOOL: browser_upload_file")
    await ensure_browser()
    await browser_state['page'].set_input_files(selector, file_path)
    return f"Successfully uploaded file: {file_path} to {selector}"

@mcp.tool()
async def browser_download_file(url: str, download_path: str) -> str:
    """파일을 다운로드합니다."""
    print("##### CALL TOOL: browser_download_file")
    await ensure_browser()
    
    # 다운로드 시작 대기
    async with browser_state['page'].expect_download() as download_info:
        await browser_state['page'].goto(url)
    download = await download_info.value
    
    # 파일 저장
    await download.save_as(download_path)
    return f"Successfully downloaded file to: {download_path}"

@mcp.tool()
async def browser_get_cookies() -> str:
    """현재 페이지의 쿠키를 가져옵니다."""
    print("##### CALL TOOL: browser_get_cookies")
    await ensure_browser()
    cookies = await browser_state['context'].cookies()
    return f"Cookies: {cookies}"

@mcp.tool()
async def browser_set_cookie(name: str, value: str, domain: str = None, path: str = "/") -> str:
    """쿠키를 설정합니다."""
    print("##### CALL TOOL: browser_set_cookie")
    await ensure_browser()
    cookie_data = {"name": name, "value": value, "path": path}
    if domain:
        cookie_data["domain"] = domain
    await browser_state['context'].add_cookies([cookie_data])
    return f"Successfully set cookie: {name}={value}"

@mcp.tool()
async def browser_clear_cookies() -> str:
    """모든 쿠키를 삭제합니다."""
    print("##### CALL TOOL: browser_clear_cookies")
    await ensure_browser()
    await browser_state['context'].clear_cookies()
    return "Successfully cleared all cookies"

@mcp.tool()
async def browser_get_page_source() -> str:
    """현재 페이지의 HTML 소스를 가져옵니다."""
    print("##### CALL TOOL: browser_get_page_source")
    await ensure_browser()
    content = await browser_state['page'].content()
    return f"Page source length: {len(content)} characters"

@mcp.tool()
async def browser_get_page_title() -> str:
    """현재 페이지의 제목을 가져옵니다."""
    print("##### CALL TOOL: browser_get_page_title")
    await ensure_browser()
    title = await browser_state['page'].title()
    return f"Page title: {title}"

@mcp.tool()
async def browser_get_current_url() -> str:
    """현재 페이지의 URL을 가져옵니다."""
    print("##### CALL TOOL: browser_get_current_url")
    await ensure_browser()
    url = browser_state['page'].url
    return f"Current URL: {url}"

@mcp.tool()
async def browser_new_tab(url: str = None) -> str:
    """새 탭을 생성합니다."""
    print("##### CALL TOOL: browser_new_tab")
    await ensure_browser()
    new_page = await browser_state['context'].new_page()
    if url:
        await new_page.goto(url)
    return f"Successfully created new tab" + (f" and navigated to: {url}" if url else "")

@mcp.tool()
async def browser_close_tab() -> str:
    """현재 탭을 닫습니다."""
    print("##### CALL TOOL: browser_close_tab")
    await ensure_browser()
    await browser_state['page'].close()
    pages = browser_state['context'].pages
    if pages:
        browser_state['page'] = pages[0]  # 첫 번째 페이지로 전환
    return "Successfully closed current tab"

@mcp.tool()
async def browser_switch_tab(tab_index: int) -> str:
    """지정된 탭으로 전환합니다."""
    print("##### CALL TOOL: browser_switch_tab")
    await ensure_browser()
    pages = browser_state['context'].pages
    if 0 <= tab_index < len(pages):
        browser_state['page'] = pages[tab_index]
        return f"Successfully switched to tab {tab_index}"
    else:
        return f"Tab index {tab_index} out of range (0-{len(pages)-1})"

@mcp.tool()
async def browser_hover(selector: str) -> str:
    """엘리먼트에 마우스를 올립니다."""
    print("##### CALL TOOL: browser_hover")
    await ensure_browser()
    await browser_state['page'].hover(selector)
    return f"Successfully hovered over: {selector}"

@mcp.tool()
async def browser_drag_and_drop(source_selector: str, target_selector: str) -> str:
    """엘리먼트를 드래그 앤 드롭합니다."""
    print("##### CALL TOOL: browser_drag_and_drop")
    await ensure_browser()
    await browser_state['page'].drag_and_drop(source_selector, target_selector)
    return f"Successfully dragged {source_selector} to {target_selector}"

@mcp.tool()
async def browser_press_key(key: str) -> str:
    """키보드 키를 누릅니다."""
    print("##### CALL TOOL: browser_press_key")
    await ensure_browser()
    await browser_state['page'].keyboard.press(key)
    return f"Successfully pressed key: {key}"

@mcp.tool()
async def browser_key_combination(keys: str) -> str:
    """키 조합을 누릅니다 (예: Ctrl+C, Cmd+V)."""
    print("##### CALL TOOL: browser_key_combination")
    await ensure_browser()
    key_list = keys.split('+')
    for key in key_list[:-1]:
        await browser_state['page'].keyboard.down(key)
    await browser_state['page'].keyboard.press(key_list[-1])
    for key in reversed(key_list[:-1]):
        await browser_state['page'].keyboard.up(key)
    return f"Successfully pressed key combination: {keys}"

@mcp.tool()
async def browser_set_viewport(width: int, height: int) -> str:
    """브라우저 뷰포트 크기를 설정합니다."""
    print("##### CALL TOOL: browser_set_viewport")
    await ensure_browser()
    await browser_state['page'].set_viewport_size({"width": width, "height": height})
    return f"Successfully set viewport to {width}x{height}"

@mcp.tool()
async def browser_emulate_device(device_name: str) -> str:
    """모바일 디바이스를 에뮬레이트합니다."""
    print("##### CALL TOOL: browser_emulate_device")
    from playwright.async_api import devices
    
    if browser_state['context']:
        await browser_state['context'].close()
    
    device_config = devices.get(device_name)
    if not device_config:
        available_devices = list(devices.keys())[:10]  # 처음 10개만 표시
        return f"Device '{device_name}' not found. Available devices: {available_devices}..."
    
    browser_state['context'] = await browser_state['browser'].new_context(**device_config)
    browser_state['page'] = await browser_state['context'].new_page()
    
    return f"Successfully emulated device: {device_name}"

@mcp.tool()
async def browser_scroll(direction: str, pixels: int = 500) -> str:
    """페이지를 스크롤합니다."""
    print("##### CALL TOOL: browser_scroll")
    await ensure_browser()
    
    if direction.lower() == 'down':
        await browser_state['page'].mouse.wheel(0, pixels)
    elif direction.lower() == 'up':
        await browser_state['page'].mouse.wheel(0, -pixels)
    elif direction.lower() == 'left':
        await browser_state['page'].mouse.wheel(-pixels, 0)
    elif direction.lower() == 'right':
        await browser_state['page'].mouse.wheel(pixels, 0)
    else:
        return f"Invalid direction: {direction}. Use 'up', 'down', 'left', or 'right'"
    
    return f"Successfully scrolled {direction} by {pixels} pixels"

@mcp.tool()
async def browser_scroll_to_element(selector: str) -> str:
    """특정 엘리먼트까지 스크롤합니다."""
    print("##### CALL TOOL: browser_scroll_to_element")
    await ensure_browser()
    await browser_state['page'].locator(selector).scroll_into_view_if_needed()
    return f"Successfully scrolled to element: {selector}"

@mcp.tool()
async def browser_get_element_count(selector: str) -> str:
    """선택자와 일치하는 엘리먼트 개수를 반환합니다."""
    print("##### CALL TOOL: browser_get_element_count")
    await ensure_browser()
    count = await browser_state['page'].locator(selector).count()
    return f"Element count for '{selector}': {count}"

@mcp.tool()
async def browser_get_element_attribute(selector: str, attribute: str) -> str:
    """엘리먼트의 속성값을 가져옵니다."""
    print("##### CALL TOOL: browser_get_element_attribute")
    await ensure_browser()
    value = await browser_state['page'].locator(selector).get_attribute(attribute)
    return f"Attribute '{attribute}' of '{selector}': {value}"

@mcp.tool()
async def browser_is_element_visible(selector: str) -> str:
    """엘리먼트가 보이는지 확인합니다."""
    print("##### CALL TOOL: browser_is_element_visible")
    await ensure_browser()
    is_visible = await browser_state['page'].locator(selector).is_visible()
    return f"Element '{selector}' is visible: {is_visible}"

@mcp.tool()
async def browser_enable_network_intercept() -> str:
    """네트워크 요청 인터셉트를 활성화합니다."""
    print("##### CALL TOOL: browser_enable_network_intercept")
    await ensure_browser()
    
    browser_state['network_requests'] = []
    browser_state['network_intercept_enabled'] = True
    
    async def handle_request(request):
        request_data = {
            'url': request.url,
            'method': request.method,
            'headers': dict(request.headers),
            'resource_type': request.resource_type
        }
        browser_state['network_requests'].append(request_data)
        await request.continue_()
    
    await browser_state['page'].route("**/*", handle_request)
    return "Network intercept enabled successfully"

@mcp.tool()
async def browser_disable_network_intercept() -> str:
    """네트워크 요청 인터셉트를 비활성화합니다."""
    print("##### CALL TOOL: browser_disable_network_intercept")
    await ensure_browser()
    
    browser_state['network_intercept_enabled'] = False
    await browser_state['page'].unroute("**/*")
    return "Network intercept disabled successfully"

@mcp.tool()
async def browser_get_network_requests() -> str:
    """인터셉트된 네트워크 요청을 가져옵니다."""
    print("##### CALL TOOL: browser_get_network_requests")
    if not browser_state['network_intercept_enabled']:
        return "Network intercept is not enabled. Use browser_enable_network_intercept first."
    
    requests_count = len(browser_state['network_requests'])
    return f"Intercepted {requests_count} network requests. Requests: {browser_state['network_requests']}"

@mcp.tool()
async def browser_clear_network_requests() -> str:
    """인터셉트된 네트워크 요청 목록을 지웁니다."""
    print("##### CALL TOOL: browser_clear_network_requests")
    browser_state['network_requests'] = []
    return "Network requests cleared successfully"

@mcp.tool()
async def browser_block_urls(url_patterns: list) -> str:
    """특정 URL 패턴을 차단합니다."""
    print("##### CALL TOOL: browser_block_urls")
    await ensure_browser()
    
    async def handle_request(request):
        for pattern in url_patterns:
            if pattern in request.url:
                await request.abort()
                return
        await request.continue_()
    
    await browser_state['page'].route("**/*", handle_request)
    return f"Successfully blocked URL patterns: {url_patterns}"

@mcp.tool()
async def browser_select_option(selector: str, value: str) -> str:
    """선택 박스에서 옵션을 선택합니다."""
    print("##### CALL TOOL: browser_select_option")
    await ensure_browser()
    await browser_state['page'].select_option(selector, value)
    return f"Successfully selected option '{value}' in: {selector}"

@mcp.tool()
async def browser_check_checkbox(selector: str) -> str:
    """체크박스를 선택합니다."""
    print("##### CALL TOOL: browser_check_checkbox")
    await ensure_browser()
    await browser_state['page'].check(selector)
    return f"Successfully checked checkbox: {selector}"

@mcp.tool()
async def browser_uncheck_checkbox(selector: str) -> str:
    """체크박스 선택을 해제합니다."""
    print("##### CALL TOOL: browser_uncheck_checkbox")
    await ensure_browser()
    await browser_state['page'].uncheck(selector)
    return f"Successfully unchecked checkbox: {selector}"

@mcp.tool()
async def browser_right_click(selector: str) -> str:
    """엘리먼트에 마우스 우클릭을 합니다."""
    print("##### CALL TOOL: browser_right_click")
    await ensure_browser()
    await browser_state['page'].click(selector, button='right')
    return f"Successfully right-clicked: {selector}"

@mcp.tool()
async def browser_double_click(selector: str) -> str:
    """엘리먼트를 더블클릭합니다."""
    print("##### CALL TOOL: browser_double_click")
    await ensure_browser()
    await browser_state['page'].dblclick(selector)
    return f"Successfully double-clicked: {selector}"

@mcp.tool()
async def browser_get_all_text() -> str:
    """페이지의 모든 텍스트를 가져옵니다."""
    print("##### CALL TOOL: browser_get_all_text")
    await ensure_browser()
    text = await browser_state['page'].inner_text('body')
    return f"Page text length: {len(text)} characters. Text: {text[:1000]}..." if len(text) > 1000 else f"Page text: {text}"

@mcp.tool()
async def browser_get_inner_html(selector: str) -> str:
    """엘리먼트의 innerHTML을 가져옵니다."""
    print("##### CALL TOOL: browser_get_inner_html")
    await ensure_browser()
    html = await browser_state['page'].inner_html(selector)
    return f"Inner HTML of '{selector}': {html}"

@mcp.tool()
async def browser_go_back() -> str:
    """이전 페이지로 돌아갑니다."""
    print("##### CALL TOOL: browser_go_back")
    await ensure_browser()
    await browser_state['page'].go_back()
    return "Successfully navigated back"

@mcp.tool()
async def browser_go_forward() -> str:
    """다음 페이지로 이동합니다."""
    print("##### CALL TOOL: browser_go_forward")
    await ensure_browser()
    await browser_state['page'].go_forward()
    return "Successfully navigated forward"

@mcp.tool()
async def browser_reload() -> str:
    """페이지를 새로고침합니다."""
    print("##### CALL TOOL: browser_reload")
    await ensure_browser()
    await browser_state['page'].reload()
    return "Successfully reloaded page"

@mcp.tool()
async def browser_close() -> str:
    """브라우저를 닫습니다."""
    print("##### CALL TOOL: browser_close")
    if browser_state['browser']:
        await browser_state['browser'].close()
        await browser_state['playwright'].stop()
        browser_state.update({
            'playwright': None,
            'browser': None,
            'context': None,
            'page': None
        })
        logger.info("브라우저 인스턴스 종료 완료")
    return "Browser closed successfully"

if __name__ == "__main__":
    # 서버 시작 시 정리 핸들러 등록
    import signal
    import sys
    
    async def cleanup():
        await browser_close()
        sys.exit(0)
    
    def signal_handler(signum, frame):
        _ = signum, frame  # 사용하지 않는 파라미터 처리
        asyncio.create_task(cleanup())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("Playwright MCP Server 시작 중...")
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8002,
        path="/",
        log_level="info",
    )