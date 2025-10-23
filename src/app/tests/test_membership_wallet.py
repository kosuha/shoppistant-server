from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import membership_router
from app import main as main_module


class StubMembershipService:
    """테스트 시나리오별로 멤버십 상태를 제어하기 위한 스텁."""

    def __init__(self, level: int, is_expired: bool):
        self._level = level
        self._is_expired = is_expired
        self.calls: List[str] = []

    async def get_user_membership(self, user_id: str) -> Dict[str, Any]:
        self.calls.append(user_id)
        return {
            "membership_level": self._level,
            "is_expired": self._is_expired,
        }


class StubDbHelper:
    """wallet 충전 동작을 기록하기 위한 스텁."""

    def __init__(self):
        self.credit_calls: List[Tuple[str, float, Optional[Dict[str, Any]], Optional[str]]] = []

    async def credit_wallet(
        self,
        user_id: str,
        amount: float,
        metadata: Optional[Dict[str, Any]] = None,
        source_event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.credit_calls.append((user_id, amount, metadata, source_event_id))
        return {"id": "tx-test", "amount": amount}

    async def get_user_wallet(self, user_id: str) -> Dict[str, Any]:
        """충전 후 잔액 확인을 위한 간단한 응답."""
        credited = sum(call[1] for call in self.credit_calls if call[0] == user_id)
        return {"balance_usd": credited, "total_spent_usd": 0}


@pytest.fixture
def test_client(monkeypatch) -> TestClient:
    """membership 라우터만 포함한 경량 FastAPI 앱 생성."""

    app = FastAPI()
    fake_user = SimpleNamespace(id="user-test")

    async def override_get_current_user():
        return fake_user

    app.include_router(membership_router.router)
    app.dependency_overrides[membership_router.get_current_user] = override_get_current_user

    return TestClient(app)


def test_wallet_credit_requires_active_membership(test_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    membership_service = StubMembershipService(level=0, is_expired=True)
    membership_router.set_dependencies(None, membership_service)

    db_helper = StubDbHelper()
    monkeypatch.setattr(main_module, "db_helper", db_helper, raising=False)

    response = test_client.post(
        "/api/v1/membership/wallet/credit",
        params={"amount_usd": 5},
        headers={"Authorization": "Bearer test-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "error"
    assert payload["error_code"] == "MEMBERSHIP_REQUIRED"
    assert not db_helper.credit_calls


def test_wallet_credit_succeeds_for_active_membership(test_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    membership_service = StubMembershipService(level=1, is_expired=False)
    membership_router.set_dependencies(None, membership_service)

    db_helper = StubDbHelper()
    monkeypatch.setattr(main_module, "db_helper", db_helper, raising=False)

    response = test_client.post(
        "/api/v1/membership/wallet/credit",
        params={"amount_usd": 12.5},
        headers={"Authorization": "Bearer test-token"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "success"
    assert payload["data"]["wallet"]["balance_usd"] == pytest.approx(12.5)
    assert len(db_helper.credit_calls) == 1
    user_id, amount, metadata, source_event_id = db_helper.credit_calls[0]
    assert user_id == "user-test"
    assert amount == pytest.approx(12.5)
    assert metadata is None or "provider" not in metadata  # membership_router는 테스트 엔드포인트로 메타데이터 미전달
    assert source_event_id is None
