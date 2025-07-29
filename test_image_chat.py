#!/usr/bin/env python3
"""
이미지 첨부 채팅 기능 테스트 스크립트
"""
import requests
import base64
import json

# 테스트용 작은 이미지 생성 (1x1 픽셀 PNG)
def create_test_image_base64():
    """1x1 픽셀 PNG 이미지를 Base64로 생성"""
    # 1x1 픽셀 검은색 PNG 이미지 (최소한의 유효한 PNG)
    png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82'
    base64_data = base64.b64encode(png_data).decode('utf-8')
    return f"data:image/png;base64,{base64_data}"

def test_image_validation():
    """이미지 검증 로직 테스트"""
    from src.app.utils.image_validator import ImageValidator
    
    print("=== 이미지 검증 테스트 ===")
    
    # 테스트 1: 빈 배열
    try:
        ImageValidator.validate_image_data([])
        print("✅ 빈 배열 테스트 통과")
    except Exception as e:
        print(f"❌ 빈 배열 테스트 실패: {e}")
    
    # 테스트 2: None
    try:
        ImageValidator.validate_image_data(None)
        print("✅ None 테스트 통과")
    except Exception as e:
        print(f"❌ None 테스트 실패: {e}")
    
    # 테스트 3: 유효한 이미지
    try:
        test_image = create_test_image_base64()
        ImageValidator.validate_image_data([test_image])
        print("✅ 유효한 이미지 테스트 통과")
    except Exception as e:
        print(f"❌ 유효한 이미지 테스트 실패: {e}")
    
    # 테스트 4: 잘못된 형식
    try:
        ImageValidator.validate_image_data(["invalid_data"])
        print("❌ 잘못된 형식 테스트 실패 - 예외가 발생해야 함")
    except Exception as e:
        print(f"✅ 잘못된 형식 테스트 통과: {e}")
    
    # 테스트 5: 너무 많은 이미지
    try:
        test_image = create_test_image_base64()
        ImageValidator.validate_image_data([test_image] * 5)  # 5개 (최대 3개 초과)
        print("❌ 이미지 개수 초과 테스트 실패 - 예외가 발생해야 함")
    except Exception as e:
        print(f"✅ 이미지 개수 초과 테스트 통과: {e}")

def test_api_request():
    """API 요청 테스트 (실제 서버가 실행 중일 때)"""
    print("\n=== API 요청 테스트 ===")
    
    # 테스트용 이미지 생성
    test_image = create_test_image_base64()
    
    # 테스트용 요청 데이터
    test_data = {
        "thread_id": "test-thread-id",
        "site_code": "test-site",
        "message": "이미지를 첨부해서 보냅니다.",
        "image_data": [test_image]
    }
    
    print("테스트 요청 데이터:")
    print(f"- 메시지: {test_data['message']}")
    print(f"- 이미지 개수: {len(test_data['image_data'])}")
    print(f"- 이미지 크기: {len(test_data['image_data'][0])} 문자")
    
    # 실제 API 호출을 위해서는 서버가 실행되어야 하고 인증 토큰이 필요합니다
    print("\n실제 API 테스트를 위해서는:")
    print("1. 서버가 실행되어야 합니다")
    print("2. 유효한 인증 토큰이 필요합니다")
    print("3. 유효한 thread_id가 필요합니다")

if __name__ == "__main__":
    print("이미지 첨부 채팅 기능 테스트")
    print("=" * 50)
    
    # 검증 로직 테스트
    test_image_validation()
    
    # API 요청 테스트 (데모용)
    test_api_request()
    
    print("\n테스트 완료!")