from fastmcp import FastMCP
from tools.session_tools import SessionTools
from tools.site_info import SiteInfo
from tools.member_info import MemberInfo
from tools.community import Community
from tools.promotion import Promotion
from tools.product import Product

mcp = FastMCP(name="imweb-mcp-server")

# 세션 도구를 먼저 초기화
session_tools = SessionTools(mcp)

# 다른 도구들에 세션 참조 전달
SiteInfo(mcp, session_tools)
MemberInfo(mcp, session_tools)
Community(mcp, session_tools)
Promotion(mcp, session_tools)
Product(mcp, session_tools)

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8001,
        path="/",
        log_level="debug",
    )