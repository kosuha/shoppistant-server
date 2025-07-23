"""
리팩토링 테스트 스크립트
"""
import asyncio
import sys
import os

# 프로젝트 루트 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), 'src', 'app'))

async def test_dependency_injection():
    """의존성 주입 컨테이너 테스트"""
    print("=== 의존성 주입 테스트 ===")
    
    try:
        from core.container import container
        from core.interfaces import IAuthService, IScriptService
        from tests.mocks import configure_test_dependencies
        
        # 테스트 환경 설정
        configure_test_dependencies()
        
        # 서비스 조회 테스트
        auth_service = container.get(IAuthService)
        script_service = container.get(IScriptService)
        
        print(f"✅ AuthService 인스턴스: {type(auth_service).__name__}")
        print(f"✅ ScriptService 인스턴스: {type(script_service).__name__}")
        
        # 싱글톤 테스트
        auth_service2 = container.get(IAuthService)
        assert auth_service is auth_service2, "싱글톤 패턴이 작동하지 않음"
        print("✅ 싱글톤 패턴 동작 확인")
        
        return True
        
    except Exception as e:
        print(f"❌ 의존성 주입 테스트 실패: {e}")
        return False

async def test_service_operations():
    """서비스 작업 테스트"""
    print("\n=== 서비스 작업 테스트 ===")
    
    try:
        from core.interfaces import IScriptService
        from tests.mocks import configure_test_dependencies
        
        # 테스트 환경 설정
        container = configure_test_dependencies()
        script_service = container.get(IScriptService)
        
        # Mock 스크립트 조회 테스트
        result = await script_service.get_site_scripts("test-user", "test-site")
        print(f"✅ 스크립트 조회 결과: {result}")
        
        # Mock 스크립트 배포 테스트
        result = await script_service.deploy_site_scripts(
            "test-user", 
            "test-site", 
            {"script": "console.log('test');"}
        )
        print(f"✅ 스크립트 배포 결과: {result}")
        
        return True
        
    except Exception as e:
        print(f"❌ 서비스 작업 테스트 실패: {e}")
        return False

async def test_config_validation():
    """설정 검증 테스트"""
    print("\n=== 설정 검증 테스트 ===")
    
    try:
        # 환경변수 모의 설정
        os.environ.update({
            'SUPABASE_URL': 'http://test.supabase.co',
            'SUPABASE_ANON_KEY': 'test-anon-key',
            'GEMINI_API_KEY': 'test-gemini-key',
            'IMWEB_CLIENT_ID': 'test-client-id',
            'IMWEB_CLIENT_SECRET': 'test-client-secret',
            'IMWEB_REDIRECT_URI': 'http://localhost:3000/callback'
        })
        
        from core.config import Settings
        settings = Settings()
        
        print(f"✅ Supabase URL: {settings.SUPABASE_URL}")
        print(f"✅ Debug 모드: {settings.DEBUG}")
        print(f"✅ 로그 레벨: {settings.LOG_LEVEL}")
        
        return True
        
    except Exception as e:
        print(f"❌ 설정 검증 테스트 실패: {e}")
        return False

async def main():
    """메인 테스트 실행"""
    print("🚀 리팩토링 테스트 시작\n")
    
    tests = [
        test_config_validation,
        test_dependency_injection,
        test_service_operations
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ 테스트 실행 중 오류: {e}")
            results.append(False)
    
    print(f"\n📊 테스트 결과: {sum(results)}/{len(results)} 성공")
    
    if all(results):
        print("🎉 모든 테스트 통과! 리팩토링이 성공적으로 완료되었습니다.")
    else:
        print("⚠️  일부 테스트 실패. 코드를 검토해주세요.")

if __name__ == "__main__":
    asyncio.run(main())
