"""Paddle Billing API 클라이언트"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx


logger = logging.getLogger(__name__)


class PaddleAPIError(RuntimeError):
    """Paddle Billing API 오류"""

    def __init__(
        self,
        message: str,
        status_code: int,
        payload: Optional[Dict[str, Any]] = None,
        *,
        code: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.code = code or self._extract_error_code()

    def _extract_error_code(self) -> Optional[str]:
        """응답 페이로드에서 오류 코드를 추출"""

        error = self.payload.get("error") if isinstance(self.payload, dict) else None
        if isinstance(error, dict):
            return error.get("code") or error.get("type")
        return None


class PaddleBillingClient:
    """Paddle Billing REST API 비동기 클라이언트"""

    ERROR_CODE_MESSAGES: Dict[str, str] = {
        "subscription_not_found": "Paddle 구독 정보를 찾을 수 없습니다.",
        "subscription_cancel_invalid_status": "현재 상태에서는 구독을 해지할 수 없습니다.",
        "subscription_not_active": "활성 상태가 아닌 구독입니다.",
        "resource_not_found": "요청한 Paddle 리소스를 찾을 수 없습니다.",
        "forbidden": "Paddle API 권한이 거부되었습니다.",
        "invalid_api_key": "Paddle API 키가 올바르지 않습니다.",
        "validation_error": "Paddle API 요청 파라미터를 검증하지 못했습니다.",
        "rate_limited": "Paddle API 호출이 너무 많습니다. 잠시 후 다시 시도하세요.",
    }

    STATUS_MESSAGES: Dict[int, str] = {
        400: "Paddle API 요청 파라미터가 올바르지 않습니다.",
        401: "Paddle API 인증에 실패했습니다.",
        403: "Paddle API 접근 권한이 없습니다.",
        404: "요청한 Paddle 리소스를 찾지 못했습니다.",
        409: "Paddle 리소스 상태 충돌이 발생했습니다.",
        429: "Paddle API 호출이 제한되었습니다. 잠시 후 다시 시도하세요.",
        500: "Paddle API 서버 오류가 발생했습니다.",
        503: "Paddle API 서비스가 일시적으로 불가합니다.",
    }

    RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.paddle.com",
        timeout: float = 15.0,
        *,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("Paddle 관리자 API 키가 설정되지 않았습니다.")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.backoff_factor = max(0.0, float(backoff_factor)) or 0.5

    async def _request(
        self,
        method: str,
        path: str,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.request(method, url, headers=headers, json=json)
            except httpx.RequestError as exc:
                logger.warning(
                    "[PADDLE] API request network error: %s %s attempt=%s error=%s",
                    method,
                    path,
                    attempt + 1,
                    exc,
                )

                if attempt == self.max_retries:
                    raise PaddleAPIError(
                        "Paddle API 네트워크 오류가 발생했습니다.",
                        status_code=0,
                        payload={"error": {"message": str(exc)}},
                        code="network_error",
                    ) from exc

                await self._sleep_backoff(attempt)
                continue

            if response.status_code >= 400:
                payload = self._safe_json(response)
                message, code = self._resolve_error_message(payload, response.status_code)

                error = PaddleAPIError(message, response.status_code, payload, code=code)

                if self._is_retryable_status(response.status_code) and attempt < self.max_retries:
                    logger.warning(
                        "[PADDLE] API request retry: %s %s status=%s code=%s attempt=%s",
                        method,
                        path,
                        response.status_code,
                        error.code,
                        attempt + 1,
                    )
                    await self._sleep_backoff(attempt)
                    continue

                logger.error(
                    "[PADDLE] API request failed: %s %s status=%s code=%s payload=%s",
                    method,
                    path,
                    response.status_code,
                    error.code,
                    payload,
                )
                raise error

            try:
                return response.json()
            except Exception as exc:  # pragma: no cover - 방어적 코드
                logger.error("[PADDLE] API 응답 파싱 실패: %s", exc)
                raise PaddleAPIError(
                    "Paddle API 응답을 파싱하지 못했습니다",
                    response.status_code,
                    payload={"error": {"message": str(exc)}},
                    code="parse_error",
                ) from exc

        # 이 지점에 도달했다면 모든 재시도가 실패한 것
        raise PaddleAPIError("Paddle API 요청이 반복적으로 실패했습니다.", status_code=0)

    async def cancel_subscription(
        self,
        subscription_id: str,
        effective_from: str = "next_billing_period",
    ) -> Dict[str, Any]:
        """구독 해지 요청"""

        payload = {"effective_from": effective_from}
        return await self._request(
            "POST",
            f"/subscriptions/{subscription_id}/cancel",
            json=payload,
        )

    async def resume_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """해지 예약된 구독을 복구"""

        return await self._request(
            "POST",
            f"/subscriptions/{subscription_id}/resume",
        )

    async def get_checkout(self, checkout_id: str) -> Dict[str, Any]:
        """Checkout 세부 정보를 조회"""

        return await self._request("GET", f"/checkouts/{checkout_id}")

    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """구독 세부 정보를 조회"""

        return await self._request("GET", f"/subscriptions/{subscription_id}")

    async def _sleep_backoff(self, attempt: int) -> None:
        """재시도 전 지수 백오프 딜레이"""

        delay = self.backoff_factor * (2**attempt)
        if delay > 0:
            await asyncio.sleep(delay)

    def _is_retryable_status(self, status_code: int) -> bool:
        """HTTP 상태 코드 기준 재시도 가능 여부"""

        return status_code in self.RETRYABLE_STATUS

    def _resolve_error_message(self, payload: Dict[str, Any], status_code: int) -> tuple[str, Optional[str]]:
        """Paddle 오류 응답을 기반으로 메시지와 코드 결정"""

        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            code = error.get("code") or error.get("type")
            if code and code in self.ERROR_CODE_MESSAGES:
                return self.ERROR_CODE_MESSAGES[code], code

            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message, code

        status_message = self.STATUS_MESSAGES.get(status_code)
        if status_message:
            return status_message, None

        return "Paddle API 요청에 실패했습니다", None

    @staticmethod
    def _safe_json(response: httpx.Response) -> Dict[str, Any]:
        """JSON 파싱 실패 시 안전하게 fallback"""

        try:
            payload = response.json()
            return payload if isinstance(payload, dict) else {"data": payload}
        except Exception:
            return {"error": {"message": response.text}}
