#!/usr/bin/env python3
"""
Two-stage AI response system test
"""

import asyncio
import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from google import genai
from app.services import AIService
from app.services.database_helper import DatabaseHelper

async def test_two_stage_ai():
    """두 단계 AI 시스템 테스트"""
    print("🧪 두 단계 AI 시스템 테스트 시작")
    
    # Mock objects for testing
    class MockMCPClient:
        def __init__(self):
            self.session = "mock_session"
    
    class MockGeminiClient:
        def __init__(self):
            self.aio = self
            self.models = self
        
        async def generate_content(self, model, contents, config):
            """Mock response for testing"""
            print(f"📞 Mock AI 호출: {model}")
            print(f"📝 프롬프트 길이: {len(contents)}자")
            print(f"⚙️ 설정: tools={hasattr(config, 'tools')}, thinking={hasattr(config, 'thinking_config')}")
            
            # Mock response object
            class MockResponse:
                def __init__(self, text):
                    self.text = text
                    self.candidates = []
            
            if hasattr(config, 'tools') and hasattr(config, 'thinking_config'):
                # This should not happen in the two-stage system
                return MockResponse("ERROR: tools and thinking_config used together")
            elif hasattr(config, 'tools'):
                # Stage 1: Tool usage
                return MockResponse("1단계: MCP 도구를 사용하여 아임웹 사이트 정보를 수집했습니다.")
            else:
                # Stage 2: Structured output
                mock_json = '''{"message": "2단계: 구조화된 출력으로 사용자 요청에 답변합니다.", "script_updates": {"action": "create", "script": "console.log('test');"}}'''
                return MockResponse(mock_json)
    
    # Test setup
    mock_gemini = MockGeminiClient()
    mock_mcp = MockMCPClient()
    mock_db = DatabaseHelper("mock_db_path")
    
    # Create AI service
    ai_service = AIService(mock_gemini, mock_mcp, mock_db)
    
    # Mock user data
    ai_service.db_helper.get_user_sites = lambda user_id, owner_id: [
        {"site_code": "test", "access_token": "encrypted_token", "site_name": "Test Site"}
    ]
    ai_service.db_helper._decrypt_token = lambda token: "decrypted_token"
    ai_service.mcp_client.call_tool = lambda tool, params: None
    
    # Test chat history
    chat_history = [
        {"message_type": "user", "message": "테스트 스크립트를 만들어주세요", "created_at": "2024-01-01"}
    ]
    
    try:
        print("\n🚀 두 단계 AI 응답 생성 테스트")
        response_text, metadata = await ai_service.generate_gemini_response(
            chat_history=chat_history,
            user_id="test_user",
            metadata='{"current_script": {}}'
        )
        
        print(f"✅ 응답 생성 성공!")
        print(f"📄 응답 텍스트: {response_text}")
        print(f"📊 메타데이터: {metadata}")
        
        if "1단계" in response_text and "2단계" in response_text:
            print("❌ 오류: 두 단계가 동시에 실행됨")
        elif "2단계" in response_text:
            print("✅ 성공: 두 단계 분리 작동 확인")
        else:
            print("⚠️  경고: 예상과 다른 응답")
            
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")

if __name__ == "__main__":
    asyncio.run(test_two_stage_ai())