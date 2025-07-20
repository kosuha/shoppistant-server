_session_tokens = {}

def get_session_data(session_id: str):
    """세션 데이터를 가져오는 헬퍼 함수"""
    return _session_tokens.get(session_id)