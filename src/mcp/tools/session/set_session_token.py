from datetime import datetime
from .helper import _session_tokens

async def set_session_token(session_id: str, user_id: str, sites: list) -> str:
    global _session_tokens
    _session_tokens[session_id] = {
        "user_id": user_id,
        "sites": sites,
        "created_at": datetime.now().isoformat()
    }
    return f"세션 {session_id}에 {len(sites)}개 사이트 토큰 설정됨"