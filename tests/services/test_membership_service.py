"""MembershipService sync_paddle_subscription 테스트"""
import pytest

from services.membership_service import MembershipService


class DummyDbHelper:
    def __init__(self, membership=None):
        self.membership = membership
        self.updated_subscription_id = None
        self.created_records = []
        self.logged_events = []

    async def get_user_membership(self, user_id):  # noqa: D401 - 테스트 스텁
        return self.membership

    async def update_membership_subscription_id(self, user_id, subscription_id):
        self.updated_subscription_id = subscription_id
        if self.membership is not None:
            self.membership = {**self.membership, "paddle_subscription_id": subscription_id}
        return True

    async def create_user_membership(
        self,
        user_id,
        membership_level=0,
        expires_at=None,
        next_billing_at=None,
        cancel_at_period_end=False,
        cancel_requested_at=None,
        paddle_subscription_id=None,
    ):
        record = {
            "user_id": user_id,
            "membership_level": membership_level,
            "expires_at": expires_at,
            "next_billing_at": next_billing_at,
            "cancel_at_period_end": cancel_at_period_end,
            "cancel_requested_at": cancel_requested_at,
            "paddle_subscription_id": paddle_subscription_id,
        }
        self.created_records.append(record)
        self.membership = record
        return record

    async def log_system_event(self, user_id=None, event_type="info", event_data=None, ip_address=None, user_agent=None):
        self.logged_events.append(
            {
                "user_id": user_id,
                "event_type": event_type,
                "event_data": event_data or {},
            }
        )
        return True


@pytest.mark.asyncio
async def test_sync_subscription_noop_when_same_id():
    helper = DummyDbHelper(
        membership={
            "user_id": "user-1",
            "membership_level": 1,
            "paddle_subscription_id": "sub_same",
        }
    )
    service = MembershipService(helper)

    result = await service.sync_paddle_subscription("user-1", "sub_same", metadata={"product": "membership"})

    assert result["status"] == "unchanged"
    assert helper.updated_subscription_id is None
    assert not helper.created_records
    assert helper.logged_events[-1]["event_type"] == "membership_subscription_sync"


@pytest.mark.asyncio
async def test_sync_subscription_updates_existing_record():
    helper = DummyDbHelper(
        membership={
            "user_id": "user-2",
            "membership_level": 1,
            "paddle_subscription_id": "sub_old",
        }
    )
    service = MembershipService(helper)

    result = await service.sync_paddle_subscription("user-2", "sub_new", metadata={"product": "membership"})

    assert result["status"] == "updated"
    assert helper.updated_subscription_id == "sub_new"
    assert not helper.created_records
    assert helper.membership["paddle_subscription_id"] == "sub_new"


@pytest.mark.asyncio
async def test_sync_subscription_creates_membership_when_missing():
    helper = DummyDbHelper(membership=None)
    service = MembershipService(helper)

    result = await service.sync_paddle_subscription("user-3", "sub_created", metadata={"product": "membership"})

    assert result["status"] == "created"
    assert helper.created_records
    assert helper.created_records[0]["paddle_subscription_id"] == "sub_created"
