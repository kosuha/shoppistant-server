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
        self.mcp.tool(self.get_site_html_structure)
        self.mcp.tool(self.execute_console_log)
    
    def get_session_data(self, session_id: str):
        """Helper function to get session data"""
        if self.session_tools:
            return self.session_tools.get_session_data(session_id)
        return None

    def _clean_html(self, html_content: str) -> str:
        """Remove script, style, meta tags from HTML and keep only HTML tags"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, meta tags
        for tag in soup(['script', 'style', 'meta']):
            tag.decompose()
        
        return str(soup)

    async def get_site_html_structure(self, url: str):
        """
        Retrieves HTML code from a website URL and converts it to a simple JSON format optimized for structure analysis.
        Removes script, style, meta tags and includes only meaningful text.
        Constructs selectors based on tag names, classes, and IDs to convert to nested JSON structure.
        
        Before example:
            <!-- Product information block -->
            <div class="product">
                <h2 id="pt123" class="title">iPhone 15</h2>
                <span class="price">₩1,290,000</span>
            </div>

        After(return) example:
            {
                "div.product": {
                    "h2#pt123.title": "iPhone 15",
                    "span.price": "₩1,290,000"
                }
            }

        Args:
            url: Site URL
            
        Returns:
            dict: HTML structure information in JSON format
        """
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        print(f"##### CALL TOOL: get_site_html_structure - URL: {url}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Load page
                await page.goto(url, wait_until='networkidle')
                
                # Get HTML source code
                html_content = await page.content()
                
                await browser.close()
            
            # Convert to simple structure after cleaning HTML
            json_html = self._parse_html_to_json(html_content)
            # print(json_html)  # Debug output
            return json_html

        except Exception as e:
            print(f"Error fetching site HTML structure: {str(e)}")
            return {"error": f"Failed to parse site HTML structure: {str(e)}"}

    def _is_meaningful_text(self, text: str) -> bool:
        """Determine if text is meaningful"""
        if not text or len(text.strip()) < 2:
            return False
        
        # Exclude cases with only whitespace or special characters
        stripped = text.strip()
        if not stripped or stripped in ['\n', '\t', '\r', ' ', '&nbsp;']:
            return False
            
        return True

    def _build_simple_structure(self, element, structure=None):
        """Convert HTML to simple nested JSON structure"""
        if structure is None:
            structure = {}
        
        if element.name is None:
            return structure
        
        # Generate selector
        selector = element.name
        if element.get('id'):
            selector += f"#{element.get('id')}"
        if element.get('class'):
            classes = element.get('class')
            # Include only meaningful classes
            meaningful_classes = [cls for cls in classes if not cls.startswith('css-')]
            if meaningful_classes:
                selector += f".{'.'.join(meaningful_classes[:2])}"
        
        # Extract direct text
        direct_text = ""
        if element.string:
            direct_text = element.string.strip()
        else:
            # Extract only direct text nodes (excluding child element text)
            for content in element.contents:
                if isinstance(content, str):
                    text = content.strip()
                    if text and self._is_meaningful_text(text):
                        direct_text += text + " "
            direct_text = direct_text.strip()
        
        # Process child elements
        children = {}
        for child in element.find_all(recursive=False):
            if child.name:
                child_structure = self._build_simple_structure(child)
                children.update(child_structure)
        
        # Add to structure
        if direct_text and children:
            # Case with both text and child elements
            structure[selector] = {
                "_text": direct_text,
                **children
            }
        elif direct_text:
            # Case with text only
            structure[selector] = direct_text
        elif children:
            # Case with child elements only
            structure[selector] = children
        else:
            # Empty element case (skip)
            pass
        
        return structure

    def _parse_html_to_json(self, html_content: str):
        """
        Convert HTML to simple nested JSON structure
        
        Args:
            html_content: HTML content to convert
        
        Returns:
            dict: Converted JSON structure
        """
        
        try:
            # Clean HTML
            cleaned_html = self._clean_html(html_content)
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(cleaned_html, 'html.parser')
            
            # Convert to simple structure
            structure = {}
            
            # Process from top-level elements
            root_elements = soup.find_all(recursive=False)
            for element in root_elements:
                if element.name:
                    element_structure = self._build_simple_structure(element)
                    structure.update(element_structure)
            
            return structure
            
        except Exception as e:
            return {"error": f"HTML parsing failed: {str(e)}"}

    def _flatten_structure(self, structure, count=0):
        """Flatten structure to count elements"""
        if isinstance(structure, dict):
            for key, value in structure.items():
                if key != "_text":
                    count += 1
                    if isinstance(value, dict):
                        count = self._flatten_structure(value, count)
        return count

    async def execute_console_log(self, url: str, console_command: str):
        """
        Execute console commands on a website and return the results.
        
        Args:
            url: Website URL to execute on
            console_command: JavaScript console command to execute
            
        Returns:
            dict: Console execution results
        """
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        print(f"##### CALL TOOL: execute_console_log - URL: {url}, Command: {console_command}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                
                # Set up listener for console log collection
                console_logs = []
                
                def handle_console(msg):
                    console_logs.append({
                        "type": msg.type,
                        "text": msg.text,
                        "location": msg.location
                    })
                
                page.on("console", handle_console)
                
                # Load page
                await page.goto(url, wait_until='networkidle')
                
                # Execute JavaScript console command
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
                    "console_logs": console_logs[-10:]  # Return only last 10 logs
                }
                
        except Exception as e:
            return {
                "error": f"Console command execution failed: {str(e)}",
                "url": url,
                "command": console_command
            }