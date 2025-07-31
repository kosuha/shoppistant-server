import requests
from datetime import datetime
from typing import Dict, Any

class SessionTools:
    def __init__(self, mcp):
        self.mcp = mcp
        self._session_tokens = {}
        self._register_tools()
    
    def _register_tools(self):
        self.mcp.tool(self.set_session_token)
        self.mcp.tool(self.site_info)
    
    def get_session_data(self, session_id: str):
        """Helper function to get session data"""
        return self._session_tokens.get(session_id)
    
    async def set_session_token(self, session_id: str, user_id: str, site: dict) -> str:
        """
        Set selected site information in the session. (OAuth token removed)
        
        Args:
            session_id: Session ID
            user_id: User ID
            site: Site information dictionary {"site_name": "...", "site_code": "...", "domain": "..."}
        """
        print("##### CALL TOOL: set_session_token")

        # Check domain information
        if "domain" not in site:
            return f"Site {site.get('site_name', 'Unknown')} has no domain information."

        self._session_tokens[session_id] = {
            "user_id": user_id,
            "site": site,  # Single site information
            "created_at": datetime.now().isoformat()
        }
        return f"Site '{site.get('site_name', site.get('site_code'))}' set for session {session_id}"

    async def site_info(self, session_id: str) -> Dict[str, Any]:
        """
        Get selected site information from the current thread.
        
        Args:
            session_id: Session ID
        """
        print("##### CALL TOOL: site_info")
        try:
            session_data = self.get_session_data(session_id)
            
            if not session_data:
                return {"error": "Session does not exist."}
            
            site = session_data.get("site")
            
            if not site:
                return {"error": "No site information found in session."}

            # Return single site information
            site_info = {
                "site_name": site.get("site_name", "Unknown"),
                "site_code": site.get("site_code", ""),
                "domain": site.get("domain", "")
            }

            return {"site": site_info}
            
        except Exception as e:
            return {"error": str(e)}