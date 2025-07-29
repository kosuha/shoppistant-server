"""
이미지 데이터 검증 유틸리티
"""
import base64
import logging
from typing import List, Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)

class ImageValidator:
    """이미지 데이터 검증을 위한 클래스"""
    
    # 허용된 이미지 타입
    ALLOWED_MIME_TYPES = [
        'image/jpeg',
        'image/jpg', 
        'image/png',
        'image/gif',
        'image/webp'
    ]
    
    # 크기 제한 (바이트)
    MAX_SINGLE_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
    MAX_TOTAL_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_IMAGE_COUNT = 3  # 최대 이미지 개수
    
    @classmethod
    def validate_image_data(cls, image_data: Optional[List[str]]) -> bool:
        """
        이미지 데이터 배열을 검증합니다.
        
        Args:
            image_data: 이미지 데이터 배열 (Base64 형식)
            
        Returns:
            bool: 검증 통과 여부
            
        Raises:
            HTTPException: 검증 실패 시
        """
        if not image_data:
            return True  # 이미지가 없으면 OK
        
        # 배열 형태로 정규화
        images = image_data if isinstance(image_data, list) else [image_data]
        
        # 이미지 개수 제한
        if len(images) > cls.MAX_IMAGE_COUNT:
            raise HTTPException(
                status_code=400, 
                detail=f"이미지는 최대 {cls.MAX_IMAGE_COUNT}개까지 첨부할 수 있습니다."
            )
        
        total_size = 0
        
        for i, img_data in enumerate(images):
            try:
                # Base64 형식 검증
                if not isinstance(img_data, str) or not img_data.startswith('data:image/'):
                    raise HTTPException(
                        status_code=400,
                        detail=f"이미지 {i+1}번: 올바른 Base64 이미지 형식이 아닙니다."
                    )
                
                # MIME 타입 추출 및 검증
                try:
                    header, base64_data = img_data.split(',', 1)
                    mime_type = header.split(':')[1].split(';')[0]
                except (ValueError, IndexError):
                    raise HTTPException(
                        status_code=400,
                        detail=f"이미지 {i+1}번: 데이터 형식이 올바르지 않습니다."
                    )
                
                if mime_type not in cls.ALLOWED_MIME_TYPES:
                    raise HTTPException(
                        status_code=415,
                        detail=f"이미지 {i+1}번: 지원하지 않는 이미지 형식입니다. (지원: JPEG, PNG, GIF, WebP)"
                    )
                
                # Base64 디코딩 및 크기 검증
                try:
                    image_bytes = base64.b64decode(base64_data)
                    image_size = len(image_bytes)
                except Exception:
                    raise HTTPException(
                        status_code=400,
                        detail=f"이미지 {i+1}번: Base64 디코딩에 실패했습니다."
                    )
                
                # 단일 이미지 크기 제한
                if image_size > cls.MAX_SINGLE_IMAGE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"이미지 {i+1}번: 파일 크기가 너무 큽니다. (최대: 5MB)"
                    )
                
                total_size += image_size
                
                # 기본적인 이미지 헤더 검증 (선택적)
                cls._validate_image_header(image_bytes, mime_type, i+1)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"이미지 {i+1} 검증 중 예상치 못한 오류: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"이미지 {i+1}번: 검증 중 오류가 발생했습니다."
                )
        
        # 총 크기 검증
        if total_size > cls.MAX_TOTAL_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"전체 이미지 크기가 너무 큽니다. (최대: 10MB, 현재: {total_size // (1024*1024)}MB)"
            )
        
        logger.info(f"이미지 검증 완료: {len(images)}개, 총 {total_size // 1024}KB")
        return True
    
    @classmethod
    def _validate_image_header(cls, image_bytes: bytes, mime_type: str, image_num: int) -> None:
        """
        이미지 헤더를 검증합니다.
        
        Args:
            image_bytes: 이미지 바이트 데이터
            mime_type: MIME 타입
            image_num: 이미지 번호 (에러 메시지용)
        """
        if len(image_bytes) < 8:
            raise HTTPException(
                status_code=400,
                detail=f"이미지 {image_num}번: 이미지 파일이 손상되었습니다."
            )
        
        # JPEG 시그니처 검증
        if mime_type in ['image/jpeg', 'image/jpg']:
            if not (image_bytes.startswith(b'\xff\xd8') and image_bytes.endswith(b'\xff\xd9')):
                raise HTTPException(
                    status_code=400,
                    detail=f"이미지 {image_num}번: JPEG 파일이 손상되었습니다."
                )
        
        # PNG 시그니처 검증
        elif mime_type == 'image/png':
            if not image_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
                raise HTTPException(
                    status_code=400,
                    detail=f"이미지 {image_num}번: PNG 파일이 손상되었습니다."
                )
        
        # GIF 시그니처 검증
        elif mime_type == 'image/gif':
            if not (image_bytes.startswith(b'GIF87a') or image_bytes.startswith(b'GIF89a')):
                raise HTTPException(
                    status_code=400,
                    detail=f"이미지 {image_num}번: GIF 파일이 손상되었습니다."
                )
        
        # WebP 시그니처 검증
        elif mime_type == 'image/webp':
            if not (image_bytes.startswith(b'RIFF') and b'WEBP' in image_bytes[:12]):
                raise HTTPException(
                    status_code=400,
                    detail=f"이미지 {image_num}번: WebP 파일이 손상되었습니다."
                )