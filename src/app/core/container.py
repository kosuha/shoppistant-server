"""의존성 주입 컨테이너"""
from typing import Any, Dict, Type, TypeVar, Union, get_args, get_origin
from types import UnionType
import inspect


_OPTIONAL_UNRESOLVED = object()

T = TypeVar('T')

class DIContainer:
    """간단한 의존성 주입 컨테이너"""
    
    def __init__(self):
        self._services: Dict[Type, Any] = {}
        self._singletons: Dict[Type, Any] = {}
        self._factories: Dict[Type, Any] = {}
        
    def register_singleton(self, interface: Type[T], implementation: T) -> None:
        """싱글톤 인스턴스 등록"""
        self._singletons[interface] = implementation
        
    def register_transient(self, interface: Type[T], factory_func) -> None:
        """팩토리 함수 등록 (매번 새 인스턴스 생성)"""
        self._factories[interface] = factory_func
        
    def register_service(self, interface: Type[T], service_class: Type[T]) -> None:
        """서비스 클래스 등록 (의존성 자동 해결)"""
        self._services[interface] = service_class
        
    def get(self, interface: Type[T]) -> T:
        """서비스 인스턴스 조회"""
        # 1. 싱글톤 확인
        if interface in self._singletons:
            return self._singletons[interface]
            
        # 2. 팩토리 함수 확인
        if interface in self._factories:
            return self._factories[interface]()
            
        # 3. 서비스 클래스 확인 (의존성 자동 해결 + 싱글톤 캐싱)
        if interface in self._services:
            # 이미 생성된 인스턴스가 있는지 확인 (자동 싱글톤)
            if interface not in self._singletons:
                service_class = self._services[interface]
                instance = self._create_instance(service_class)
                self._singletons[interface] = instance
            return self._singletons[interface]
            
        interface_name = getattr(interface, "__name__", repr(interface))
        raise ValueError(f"Service {interface_name} not registered")
    
    def clear_cache(self) -> None:
        """캐시된 싱글톤 인스턴스 정리 (테스트용)"""
        cached_services = [k for k in self._singletons.keys() if k in self._services]
        for service_type in cached_services:
            del self._singletons[service_type]
        
    def _create_instance(self, service_class: Type[T]) -> T:
        """의존성을 자동으로 해결하여 인스턴스 생성"""
        constructor = service_class.__init__
        sig = inspect.signature(constructor)
        
        kwargs = {}
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            param_type = param.annotation
            if param_type != inspect.Parameter.empty:
                try:
                    if self._is_union_type(param_type):
                        resolved = self._resolve_union_dependency(param_type)
                        kwargs[param_name] = None if resolved is _OPTIONAL_UNRESOLVED else resolved
                    else:
                        kwargs[param_name] = self.get(param_type)
                except ValueError:
                    if param.default != inspect.Parameter.empty:
                        kwargs[param_name] = param.default
                    else:
                        raise ValueError(f"Cannot resolve dependency {param_type} for {service_class.__name__}")

        return service_class(**kwargs)

    @staticmethod
    def _is_union_type(annotation: Any) -> bool:
        origin = get_origin(annotation)
        if origin in (Union, UnionType):
            return True
        if origin is None and isinstance(annotation, UnionType):  # pragma: no cover - 방어적 처리
            return True
        return False

    def _resolve_union_dependency(self, annotation: Any) -> Any:
        args = get_args(annotation)
        if not args:
            raise ValueError(f"Cannot resolve union dependency for {annotation}")

        non_none_args = [arg for arg in args if arg is not type(None)]

        # Optional[T] 형태: T만 시도, 실패하면 None 허용
        if len(non_none_args) == 1 and len(non_none_args) != len(args):
            actual_type = non_none_args[0]
            try:
                return self.get(actual_type)
            except ValueError:
                return _OPTIONAL_UNRESOLVED

        # 일반 Union: 첫 번째로 해결 가능한 타입을 선택
        for candidate in non_none_args or args:
            try:
                return self.get(candidate)
            except ValueError:
                continue

        raise ValueError(f"Cannot resolve union dependency for {annotation}")

# 전역 컨테이너 인스턴스
container = DIContainer()
