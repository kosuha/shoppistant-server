"""PaddleBillingClient 단위 테스트"""
import asyncio
from typing import List

import httpx
import pytest

from services.paddle_billing_client import PaddleAPIError, PaddleBillingClient


class _DummyAsyncClient:
    """httpx.AsyncClient 대체용 간단한 더블"""

    def __init__(self, responses: List[httpx.Response]) -> None:
        self._responses = responses

    async def __aenter__(self) -> "_DummyAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def request(self, method: str, url: str, headers=None, json=None) -> httpx.Response:  # noqa: D401 - 테스트 더블
        try:
            return self._responses.pop(0)
        except IndexError as exc:  # pragma: no cover - 테스트 보조 코드
            raise AssertionError("예상보다 많은 요청이 발생했습니다") from exc


def _patch_async_client(monkeypatch, responses: List[httpx.Response]) -> None:
    """httpx.AsyncClient를 더블로 교체"""

    response_queue = list(responses)

    def _factory(*args, **kwargs):  # noqa: D401 - 테스트 헬퍼
        return _DummyAsyncClient(response_queue)

    monkeypatch.setattr("services.paddle_billing_client.httpx.AsyncClient", _factory)


def test_cancel_subscription_success(monkeypatch):
    """성공 응답을 반환하면 JSON을 그대로 전달한다"""

    response = httpx.Response(status_code=200, json={"status": "ok"})
    _patch_async_client(monkeypatch, [response])

    async def _run():
        client = PaddleBillingClient(api_key="test-key", base_url="https://example.com", backoff_factor=0)
        return await client.cancel_subscription("sub_123")

    result = asyncio.run(_run())
    assert result == {"status": "ok"}


def test_cancel_subscription_retry_then_success(monkeypatch):
    """재시도 가능 오류 뒤 성공하면 최종 성공 결과를 반환한다"""

    first = httpx.Response(status_code=500, json={"error": {"code": "server_error", "message": "boom"}})
    second = httpx.Response(status_code=200, json={"status": "ok"})

    responses = [first, second]

    def _factory(*args, **kwargs):
        return _DummyAsyncClient(responses)

    monkeypatch.setattr("services.paddle_billing_client.httpx.AsyncClient", _factory)

    async def _run():
        client = PaddleBillingClient(
            api_key="test-key",
            base_url="https://example.com",
            max_retries=1,
            backoff_factor=0,
        )
        return await client.cancel_subscription("sub_123")

    result = asyncio.run(_run())
    assert result == {"status": "ok"}


def test_error_mapping_subscription_not_found(monkeypatch):
    """구독을 찾지 못한 경우 매핑된 오류 메시지를 반환한다"""

    response = httpx.Response(
        status_code=404,
        json={"error": {"code": "subscription_not_found", "message": "not found"}},
    )

    def _factory(*args, **kwargs):
        return _DummyAsyncClient([response])

    monkeypatch.setattr("services.paddle_billing_client.httpx.AsyncClient", _factory)

    async def _run():
        client = PaddleBillingClient(api_key="test-key", base_url="https://example.com", backoff_factor=0)
        await client.cancel_subscription("sub_404")

    with pytest.raises(PaddleAPIError) as excinfo:
        asyncio.run(_run())

    error = excinfo.value
    assert error.status_code == 404
    assert error.code == "subscription_not_found"
    assert str(error) == "Paddle 구독 정보를 찾을 수 없습니다."


def test_missing_api_key_error():
    """API 키가 없으면 명확한 ValueError를 발생시킨다"""

    with pytest.raises(ValueError) as excinfo:
        PaddleBillingClient(api_key=" ")

    assert "Paddle 관리자 API 키" in str(excinfo.value)
