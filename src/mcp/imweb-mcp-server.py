from fastmcp import FastMCP
from tools.session_tools import SessionTools
from tools.script import Script
from tools.site_info import SiteInfo
from tools.screenshot import Screenshot

# Force rebuild trigger for dependency update

mcp = FastMCP(name="imweb-mcp-server")

# 세션 도구를 먼저 초기화
session_tools = SessionTools(mcp)

# 다른 도구들에 세션 참조 전달
SiteInfo(mcp, session_tools)
Screenshot(mcp, session_tools)

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8001,
        path="/",
        log_level="debug",
    )