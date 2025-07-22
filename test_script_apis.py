#!/usr/bin/env python3
"""
스크립트 관리 API의 기본 테스트
새로 구현된 기능들의 동작을 확인합니다.
"""
import asyncio
import json
import sys
import os

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from app.schemas import (
    ScriptValidationResult, 
    ScriptValidationError, 
    AIScriptResponse,
    ScriptUpdate,
    CurrentScripts
)
from app.main import validate_script_content, detect_script_related_request, parse_metadata_scripts

def test_script_validation():
    """스크립트 검증 기능 테스트"""
    print("=== 스크립트 검증 테스트 ===")
    
    # 1. 정상적인 스크립트
    valid_script = "<script>console.log('Hello World');</script>"
    result = validate_script_content(valid_script)
    assert result.is_valid == True
    assert len(result.errors) == 0
    print("✅ 정상 스크립트 검증 통과")
    
    # 2. 너무 큰 스크립트 (100KB 초과)
    large_script = "<script>" + "x" * (100 * 1024 + 1) + "</script>"
    result = validate_script_content(large_script)
    assert result.is_valid == False
    assert len(result.errors) > 0
    print("✅ 큰 스크립트 검증 실패 (예상됨)")
    
    # 3. 위험한 패턴 포함
    dangerous_script = "<script>document.write('dangerous');</script>"
    result = validate_script_content(dangerous_script)
    assert result.is_valid == True  # 경고만 발생
    assert len(result.warnings) > 0
    print("✅ 위험한 패턴 경고 발생")
    
    print("스크립트 검증 테스트 완료\n")

def test_script_detection():
    """스크립트 관련 요청 감지 테스트"""
    print("=== 스크립트 요청 감지 테스트 ===")
    
    # 1. 스크립트 관련 키워드
    script_messages = [
        "헤더에 구글 애널리틱스 스크립트를 추가해줘",
        "Add Google Analytics tracking code",
        "JavaScript 코드를 삽입하고 싶어",
        "채팅 위젯을 추가해주세요"
    ]
    
    for msg in script_messages:
        result = detect_script_related_request(msg)
        assert result == True
        print(f"✅ 스크립트 요청 감지: '{msg[:20]}...'")
    
    # 2. 일반적인 메시지
    normal_messages = [
        "안녕하세요",
        "상품 정보를 확인하고 싶어요", 
        "주문 상태는 어떻게 확인하나요?"
    ]
    
    for msg in normal_messages:
        result = detect_script_related_request(msg)
        assert result == False
        print(f"✅ 일반 요청 감지: '{msg}'")
    
    print("스크립트 요청 감지 테스트 완료\n")

def test_metadata_parsing():
    """메타데이터 파싱 테스트"""
    print("=== 메타데이터 파싱 테스트 ===")
    
    # 1. 정상적인 메타데이터
    metadata_json = json.dumps({
        "current_scripts": {
            "header": "<script>console.log('header');</script>",
            "body": "",
            "footer": "<script>console.log('footer');</script>"
        }
    }, ensure_ascii=False)
    
    result = parse_metadata_scripts(metadata_json)
    assert result['header'] == "<script>console.log('header');</script>"
    assert result['body'] == ""
    assert result['footer'] == "<script>console.log('footer');</script>"
    print("✅ 정상 메타데이터 파싱 성공")
    
    # 2. 빈 메타데이터
    result = parse_metadata_scripts("")
    assert result == {}
    print("✅ 빈 메타데이터 처리")
    
    # 3. 잘못된 JSON
    result = parse_metadata_scripts("invalid json")
    assert result == {}
    print("✅ 잘못된 JSON 처리")
    
    print("메타데이터 파싱 테스트 완료\n")

def test_pydantic_schemas():
    """Pydantic 스키마 테스트"""
    print("=== Pydantic 스키마 테스트 ===")
    
    # 1. ScriptUpdate 스키마
    script_update = ScriptUpdate(
        header=None,
        body=None,
        footer=None,
        explanation="테스트 설명",
        requires_deployment=True,
        action_type="create"
    )
    assert script_update.explanation == "테스트 설명"
    assert script_update.requires_deployment == True
    print("✅ ScriptUpdate 스키마 생성 성공")
    
    # 2. AIScriptResponse 스키마  
    ai_response = AIScriptResponse(
        message="스크립트를 생성했습니다.",
        script_updates=script_update,
        requires_user_confirmation=False
    )
    assert ai_response.message == "스크립트를 생성했습니다."
    print("✅ AIScriptResponse 스키마 생성 성공")
    
    # 3. CurrentScripts 스키마
    current_scripts = CurrentScripts(
        header="<script>test</script>",
        body=None,
        footer=""
    )
    assert current_scripts.header == "<script>test</script>"
    assert current_scripts.body == None
    print("✅ CurrentScripts 스키마 생성 성공")
    
    print("Pydantic 스키마 테스트 완료\n")

def test_json_schema_generation():
    """JSON 스키마 생성 테스트 (Gemini 구조화된 출력용)"""
    print("=== JSON 스키마 생성 테스트 ===")
    
    # AIScriptResponse의 JSON 스키마 생성
    schema = AIScriptResponse.model_json_schema()
    
    # 필수 필드 확인
    assert 'message' in schema['properties']
    assert 'script_updates' in schema['properties']
    assert 'requires_user_confirmation' in schema['properties']
    
    print("✅ AIScriptResponse JSON 스키마 생성 성공")
    print(f"생성된 스키마 키들: {list(schema['properties'].keys())}")
    
    print("JSON 스키마 생성 테스트 완료\n")

def main():
    """모든 테스트 실행"""
    print("🚀 스크립트 관리 API 기본 테스트 시작\n")
    
    try:
        test_script_validation()
        test_script_detection()
        test_metadata_parsing()
        test_pydantic_schemas()
        test_json_schema_generation()
        
        print("✅ 모든 테스트 통과!")
        print("\n🎉 구현된 기능들이 정상적으로 동작합니다.")
        print("\n다음 단계:")
        print("1. 서버를 시작하여 실제 API 테스트")
        print("2. 프론트엔드와 연동 테스트")
        print("3. 실제 아임웹 사이트와 연동 테스트")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()