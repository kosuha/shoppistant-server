"""
Paddle Webhook Router

Handles Paddle Billing webhook events:
- optional signature verification using webhook secret (Billing, HMAC-SHA256)
- membership activation/extension
- wallet credit top-up for AI credits
- idempotency tracking via system_logs to avoid duplicate processing
"""
import json
import os
import logging
import hmac
import hashlib
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Header, HTTPException

from core.responses import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks", "paddle"])


HandlerResult = Tuple[Optional[str], Dict[str, Any]]
HandlerFunc = Callable[["PaddleHandlerContext"], Awaitable[HandlerResult]]


@dataclass(slots=True)
class PaddleHandlerContext:
    event_type: str
    event_type_normalized: str
    payload: Dict[str, Any]
    data: Dict[str, Any]
    membership_service: Any
    db_helper: Any
    uid: Optional[str]
    email: Optional[str]
    transaction_id: Optional[str]
    subscription_id: Optional[str]
    event_id: Optional[str]
    membership_count: int
    credit_quantity: int
    credit_amount_usd: Decimal
    credit_units_total: Decimal
    credit_amount_inferred: bool
    credit_currency_mismatch: bool
    credit_currency_codes: List[str]
    next_billing_at: Optional[datetime]
    credits_pack_size: Decimal

def _verify_signature(raw: bytes, signature: Optional[str]) -> bool:
    """Verify Paddle-Signature if configured (Billing HMAC-SHA256)."""

    strict = os.getenv("PADDLE_WEBHOOK_STRICT_VERIFY", "true").lower() == "true"
    secret = os.getenv("PADDLE_WEBHOOK_SECRET", "").strip()

    if not secret:
        if strict:
            logger.warning("[PADDLE] strict verify enabled but no webhook secret configured")
            return False
        return True

    if not signature:
        logger.warning("[PADDLE] missing Paddle-Signature header")
        return not strict

    try:
        parts: Dict[str, str] = {}
        for chunk in signature.split(";"):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            k, v = chunk.split("=", 1)
            parts[k.strip()] = v.strip()

        ts = parts.get("ts")
        provided = parts.get("h1") or parts.get("sig") or parts.get("signature")
        if not ts or not provided:
            logger.warning("[PADDLE] signature header missing ts/h1 component")
            return not strict

        # Compute expected signature: HMAC_SHA256(secret, f"{ts}:{raw}")
        payload = ts.encode("utf-8") + b":" + raw
        expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

        if hmac.compare_digest(expected, provided):
            return True

        logger.error("[PADDLE] signature mismatch")
        return False if strict else True
    except Exception as e:
        logger.error(f"[PADDLE] signature verification error: {e}")
        return False if strict else True


def _get(d: Dict, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _to_decimal(value: Any) -> Optional[Decimal]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _extract_amount(value: Any) -> Any:
    if isinstance(value, dict):
        if 'amount' in value:
            return value['amount']
        if 'value' in value:
            return value['value']
    return value


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            if raw.endswith('Z'):
                raw = raw[:-1] + '+00:00'
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None
    return None


async def _handle_transaction_payment(ctx: PaddleHandlerContext) -> HandlerResult:
    results: Dict[str, Any] = {}
    membership_count = ctx.membership_count
    credit_quantity = ctx.credit_quantity
    credit_amount_usd = ctx.credit_amount_usd
    credit_units_total = ctx.credit_units_total

    if membership_count == 0 and credit_quantity == 0:
        results.setdefault("info", "no mapped items")

    if membership_count > 0:
        if not ctx.uid:
            results["membership"] = {"success": False, "reason": "missing_user"}
        elif not ctx.membership_service:
            results["membership"] = {"success": False, "reason": "service_unavailable"}
        else:
            try:
                res = await ctx.membership_service.upgrade_membership(  # type: ignore[attr-defined]
                    user_id=ctx.uid,
                    target_level=1,
                    duration_days=30 * membership_count,
                    next_billing_at=ctx.next_billing_at,
                    paddle_subscription_id=ctx.subscription_id,
                )
                res_data = res if isinstance(res, dict) else {}
                resubscribe_detected = bool(res_data.get("resubscribe_detected"))
                if resubscribe_detected:
                    previous_subscription_id = res_data.pop("previous_subscription_id", None)
                    previous_subscription_status = res_data.pop("previous_subscription_status", None)
                    cancel_flags_cleared = res_data.pop("cancel_flags_cleared", None)
                    status_check_correlation_id = res_data.pop("status_check_correlation_id", None)
                    res_data.pop("resubscribe_detected", None)

                results["membership"] = {
                    "success": bool(res_data),
                    "data": res_data,
                }
                if resubscribe_detected:
                    results["membership"]["resubscribe_detected"] = True
                    resubscribe_info = {}
                    if previous_subscription_id:
                        resubscribe_info["previous_subscription_id"] = previous_subscription_id
                    if previous_subscription_status:
                        resubscribe_info["previous_subscription_status"] = previous_subscription_status
                    if cancel_flags_cleared is not None:
                        resubscribe_info["cancel_flags_cleared"] = cancel_flags_cleared
                    if status_check_correlation_id:
                        resubscribe_info["status_check_correlation_id"] = status_check_correlation_id
                    if resubscribe_info:
                        resubscribe_info["subscription_id"] = ctx.subscription_id
                        results["membership"]["resubscribe"] = resubscribe_info
                if not res_data:
                    results["membership"]["error"] = "membership_update_failed"
            except Exception as e:
                logger.error(f"[PADDLE] membership update failed: {e}")
                results["membership"] = {"success": False, "error": "membership_update_failed"}

    if credit_quantity > 0:
        credit_result: Dict[str, Any] = {
            "credit_units": float(credit_units_total) if credit_units_total else 0,
            "credit_packs": credit_quantity,
            "amount_usd": float(credit_amount_usd) if credit_amount_usd else 0,
            "inferred": ctx.credit_amount_inferred,
            "currencies": sorted(ctx.credit_currency_codes) if ctx.credit_currency_codes else [],
            "success": False,
        }

        if ctx.credit_currency_mismatch:
            credit_result["error"] = "unsupported_currency"
        elif not ctx.uid:
            credit_result["error"] = "missing_user"
        elif not ctx.membership_service:
            credit_result["error"] = "service_unavailable"
        elif not ctx.db_helper:
            credit_result["error"] = "service_unavailable"
        else:
            membership_data: Optional[Dict[str, Any]] = None
            try:
                membership_data = await ctx.membership_service.get_user_membership(ctx.uid)  # type: ignore[attr-defined]
            except Exception as membership_err:
                logger.error("[PADDLE] membership lookup failed for credits: %s", membership_err)

            membership_level = 0
            membership_active = False
            if isinstance(membership_data, dict):
                raw_level = membership_data.get("membership_level", 0)
                try:
                    membership_level = int(raw_level)
                except (TypeError, ValueError):
                    membership_level = 0
                is_expired = membership_data.get("is_expired")
                membership_active = membership_level > 0 and is_expired is False

            if not membership_active:
                credit_result["error"] = "membership_required"
                logger.warning(
                    "[PADDLE] credit purchase blocked - membership inactive (event %s, uid=%s, level=%s)",
                    ctx.event_id,
                    ctx.uid,
                    membership_level,
                )
            else:
                try:
                    credit_metadata = {
                        "provider": "paddle",
                        "event_id": ctx.event_id,
                        "transaction_id": ctx.transaction_id,
                        "quantity": credit_quantity,
                        "pack_size": float(ctx.credits_pack_size) if ctx.credits_pack_size else None,
                        "credits_granted": float(credit_units_total) if credit_units_total else 0,
                        "amount_usd": float(credit_amount_usd) if credit_amount_usd else 0,
                        "inferred": ctx.credit_amount_inferred,
                        "currencies": sorted(ctx.credit_currency_codes) if ctx.credit_currency_codes else None,
                    }
                    tx = await ctx.db_helper.credit_wallet(  # type: ignore
                        ctx.uid,
                        float(credit_units_total) if credit_units_total else float(credit_quantity),
                        metadata=credit_metadata,
                        source_event_id=ctx.event_id,
                    )
                    credit_result["success"] = bool(tx)
                    credit_result["transaction_recorded"] = bool(tx)
                except Exception as e:
                    logger.error(f"[PADDLE] wallet credit failed: {e}")
                    credit_result["error"] = "credit_failed"

        results["credits"] = credit_result

    return "payment", results


async def _handle_transaction_state_change(ctx: PaddleHandlerContext) -> HandlerResult:
    event_lower = ctx.event_type_normalized
    is_refund = any(keyword in event_lower for keyword in TRANSACTION_REFUND_KEYWORDS)

    if not is_refund:
        return "transaction_state", {"info": "transaction event ignored"}

    results: Dict[str, Any] = {}

    if ctx.membership_count > 0:
        if not ctx.uid:
            results["membership_refund"] = {"success": False, "reason": "missing_user"}
        elif not ctx.membership_service:
            results["membership_refund"] = {"success": False, "reason": "service_unavailable"}
        else:
            try:
                res = await ctx.membership_service.force_downgrade_to_free(ctx.uid)  # type: ignore[attr-defined]
                success = bool(res)
                results["membership_refund"] = {
                    "success": success,
                    "data": res if success else None,
                }
                if not success:
                    results["membership_refund"]["error"] = "downgrade_failed"
            except Exception as e:
                logger.error(f"[PADDLE] membership refund handling failed: {e}")
                results["membership_refund"] = {"success": False, "error": "internal_error"}

    if ctx.credit_quantity > 0:
        credit_result: Dict[str, Any] = {
            "credit_units": float(ctx.credit_units_total) if ctx.credit_units_total else 0,
            "credit_packs": ctx.credit_quantity,
            "amount_usd": float(ctx.credit_amount_usd) if ctx.credit_amount_usd else 0,
            "inferred": ctx.credit_amount_inferred,
            "currencies": sorted(ctx.credit_currency_codes) if ctx.credit_currency_codes else [],
            "success": False,
        }

        if ctx.credit_currency_mismatch:
            credit_result["error"] = "unsupported_currency"
        elif not ctx.uid:
            credit_result["error"] = "missing_user"
        elif not ctx.db_helper:
            credit_result["error"] = "service_unavailable"
        else:
            try:
                debit_metadata = {
                    "provider": "paddle",
                    "event_id": ctx.event_id,
                    "transaction_id": ctx.transaction_id,
                    "quantity": ctx.credit_quantity,
                    "amount_usd": float(ctx.credit_amount_usd) if ctx.credit_amount_usd else 0,
                    "credits_reversed": float(ctx.credit_units_total) if ctx.credit_units_total else 0,
                    "inferred": ctx.credit_amount_inferred,
                    "currencies": sorted(ctx.credit_currency_codes) if ctx.credit_currency_codes else None,
                }
                tx = await ctx.db_helper.debit_wallet(  # type: ignore
                    ctx.uid,
                    float(ctx.credit_units_total) if ctx.credit_units_total else float(ctx.credit_quantity),
                    metadata=debit_metadata,
                    source_event_id=ctx.event_id,
                )
                credit_result["success"] = bool(tx)
                credit_result["transaction_recorded"] = bool(tx)
            except Exception as e:
                logger.error(f"[PADDLE] wallet debit failed: {e}")
                credit_result["error"] = "debit_failed"

        results["credits_refund"] = credit_result

    return "refund", results


async def _handle_subscription_status_change(ctx: PaddleHandlerContext) -> HandlerResult:
    results: Dict[str, Any] = {}
    subscription_status = (
        _get(ctx.data, "subscription", "status")
        or ctx.data.get("status")
        or ""
    ).lower()

    event_lower = ctx.event_type_normalized
    is_cancel_event = (
        "cancel" in event_lower
        or "cancellation" in event_lower
        or ("subscription.updated" in event_lower and subscription_status in SUBSCRIPTION_CANCEL_STATES)
        or subscription_status in SUBSCRIPTION_CANCEL_STATES
    )

    if not is_cancel_event:
        results["info"] = "subscription event ignored"
        return "subscription", results

    cancel_effective_raw = (
        _get(ctx.data, "cancellation_effective_date")
        or _get(ctx.data, "effective_date")
        or _get(ctx.data, "effective_at")
        or _get(ctx.data, "subscription", "cancellation_effective_date")
        or _get(ctx.data, "subscription", "cancelled_at")
        or _get(ctx.data, "subscription", "ended_at")
    )
    cancel_effective_at = _parse_datetime(cancel_effective_raw)
    now_utc = datetime.now(timezone.utc)

    if not ctx.uid:
        results["cancellation"] = {"success": False, "reason": "missing_user"}
    elif not ctx.membership_service:
        results["cancellation"] = {"success": False, "reason": "service_unavailable"}
    else:
        try:
            if cancel_effective_at and cancel_effective_at <= now_utc:
                res = await ctx.membership_service.force_downgrade_to_free(ctx.uid)  # type: ignore[attr-defined]
                success = bool(res)
                action = "downgraded"
            else:
                res = await ctx.membership_service.cancel_membership(ctx.uid, trigger_source="webhook")  # type: ignore[attr-defined]
                success = bool(res)
                action = "scheduled"
            results["cancellation"] = {
                "success": success,
                "action": action,
                "effective_at": cancel_effective_at.isoformat() if cancel_effective_at else None,
                "data": res if success else None,
            }
            if not success:
                results["cancellation"]["error"] = "membership_not_found"
        except ValueError as e:
            results["cancellation"] = {"success": False, "error": str(e), "action": "not_applicable"}
        except Exception as e:
            logger.error(f"[PADDLE] cancellation handling failed: {e}")
            results["cancellation"] = {"success": False, "error": "internal_error"}

    return "cancellation", results


async def _handle_payment_method_event(ctx: PaddleHandlerContext) -> HandlerResult:
    logger.info("[PADDLE] payment method event received: %s", ctx.event_type)
    return "payment_method", {
        "payment_method": {
            "success": True,
            "info": "payment method event ignored",
            "event_type": ctx.event_type,
        }
    }


async def _handle_unhandled_event(_: PaddleHandlerContext) -> HandlerResult:
    return None, {}


TRANSACTION_PAYMENT_EVENTS = {
    "transaction.completed",
}

TRANSACTION_STATE_EVENTS = {
    "transaction.refunded",
    "transaction.payment_refunded",
    "transaction.chargeback_created",
    "transaction.chargeback_warning",
    "transaction.chargeback_warning_reversed",
    "transaction.payment_failed",
}

SUBSCRIPTION_EVENTS = {
    "subscription.cancelled",
    "subscription.canceled",
    "subscription.updated",
    "subscription.paused",
    "subscription.resumed",
}

PAYMENT_METHOD_EVENTS = {
    "payment_method.created",
    "payment_method.updated",
    "payment_method.expired",
    "payment_method.disabled",
}

HANDLER_MAP: Dict[str, HandlerFunc] = {
    **{name: _handle_transaction_payment for name in TRANSACTION_PAYMENT_EVENTS},
    **{name: _handle_transaction_state_change for name in TRANSACTION_STATE_EVENTS},
    **{name: _handle_subscription_status_change for name in SUBSCRIPTION_EVENTS},
    **{name: _handle_payment_method_event for name in PAYMENT_METHOD_EVENTS},
}

TRANSACTION_REFUND_KEYWORDS = (
    "refund",
    "chargeback",
    "warning",
    "reverse",
)

SUBSCRIPTION_CANCEL_STATES = {"canceled", "cancelled", "inactive", "past_due", "paused"}


def _resolve_handler(event_type_normalized: str) -> HandlerFunc:
    if not event_type_normalized:
        return _handle_unhandled_event

    handler = HANDLER_MAP.get(event_type_normalized)
    if handler:
        return handler

    if event_type_normalized.startswith("transaction."):
        if event_type_normalized == "transaction.completed":
            return _handle_transaction_payment
        return _handle_transaction_state_change

    if event_type_normalized.startswith("subscription."):
        return _handle_subscription_status_change

    if event_type_normalized.startswith("payment_method."):
        return _handle_payment_method_event

    return _handle_unhandled_event


def _preview_event_category(
    handler: HandlerFunc,
    event_type_normalized: str,
    data: Dict[str, Any],
) -> Optional[str]:
    if handler is _handle_transaction_payment:
        return "payment"
    if handler is _handle_transaction_state_change:
        if any(keyword in event_type_normalized for keyword in TRANSACTION_REFUND_KEYWORDS):
            return "refund"
        return "transaction_state"
    if handler is _handle_subscription_status_change:
        subscription_status = (
            _get(data, "subscription", "status")
            or data.get("status")
            or ""
        ).lower()
        event_lower = event_type_normalized
        is_cancel_event = (
            "cancel" in event_lower
            or "cancellation" in event_lower
            or ("subscription.updated" in event_lower and subscription_status in SUBSCRIPTION_CANCEL_STATES)
            or subscription_status in SUBSCRIPTION_CANCEL_STATES
        )
        return "cancellation" if is_cancel_event else "subscription"
    if handler is _handle_payment_method_event:
        return "payment_method"
    return None


async def _get_services():
    """paddle 처리에 필요한 서비스 인스턴스를 반환"""
    try:
        from app.main import membership_service as membership_service  # type: ignore
        from app.main import db_helper as db_helper  # type: ignore
    except Exception:
        membership_service = None
        db_helper = None

    if membership_service is None or db_helper is None:
        try:
            from core.factory import ServiceFactory

            if membership_service is None:
                membership_service = ServiceFactory.get_membership_service()
            if db_helper is None:
                db_helper = ServiceFactory.get_db_helper()
        except Exception as e:  # pragma: no cover - 진단용 경로
            logger.error("[PADDLE] service fallback acquisition failed: %s", e)

    return membership_service, db_helper


async def process_paddle_payload(
    payload: Dict[str, Any],
    *,
    allow_duplicate: bool = False,
    replay_reason: str | None = None,
) -> Dict[str, Any]:
    """Paddle 웹훅 페이로드를 처리하고 결과와 로깅 상태를 반환"""

    event_type: str = payload.get("event_type") or payload.get("eventType") or ""
    data = payload.get("data") or payload
    custom_raw = _get(data, "custom_data") or _get(data, "customData") or {}
    custom: Dict[str, Any] = {}
    if isinstance(custom_raw, dict):
        custom = custom_raw
    elif isinstance(custom_raw, str):
        try:
            parsed = json.loads(custom_raw)
            if isinstance(parsed, dict):
                custom = parsed
            else:
                logger.warning("[PADDLE] custom_data parsed to non-dict type: %s", type(parsed))
        except json.JSONDecodeError:
            logger.warning("[PADDLE] failed to decode custom_data payload: %s", custom_raw)
    elif custom_raw:
        logger.warning("[PADDLE] unsupported custom_data type: %s", type(custom_raw))

    uid = custom.get("uid") or custom.get("user_id") or custom.get("userId")
    email = _get(data, "customer", "email") or _get(data, "customer_email")
    items: List[Dict[str, Any]] = data.get("items") or []
    event_id: Optional[str] = (
        payload.get("event_id")
        or payload.get("eventId")
        or payload.get("notification_id")
        or _get(payload, "meta", "event_id")
    )
    if not event_id:
        logger.warning("[PADDLE] webhook payload missing event_id; idempotency limited")
    transaction_id: Optional[str] = (
        _get(data, "id")
        or payload.get("id")
        or _get(payload, "object", "id")
    )
    currency: Optional[str] = (
        _get(data, "currency_code")
        or _get(data, "currency")
        or _get(data, "details", "currency")
        or _get(payload, "currency")
    )
    if currency:
        currency = currency.upper()

    next_billing_raw = (
        _get(data, "subscription", "next_billed_at")
        or _get(data, "subscription", "next_billing_at")
        or _get(data, "subscription", "next_billing_date")
        or _get(data, "subscription", "billing_period", "next_billed_at")
        or _get(data, "subscription", "billing_period", "next_billing_at")
        or _get(data, "billing_period", "next_billing_at")
        or _get(data, "billing_period", "next_payment_date")
        or _get(data, "next_payment", "date")
        or _get(data, "next_payment_date")
    )
    next_billing_at = _parse_datetime(next_billing_raw)

    subscription_id = (
        _get(data, "subscription_id")
        or _get(data, "subscription", "id")
        or _get(payload, "subscription", "id")
        or _get(data, "object", "subscription_id")
        or _get(payload, "object", "subscription_id")
    )

    if not items:
        items = _get(data, "object", "items", default=[]) or _get(payload, "object", "items", default=[])

    logger.info(
        "[PADDLE] event=%s uid=%s email=%s items=%s event_id=%s tx_id=%s",
        event_type,
        uid,
        bool(email),
        len(items),
        event_id,
        transaction_id,
    )

    event_type_normalized = (event_type or "").strip().lower()
    handler = _resolve_handler(event_type_normalized)

    if handler is _handle_unhandled_event:
        return {
            "processed": {},
            "event_id": event_id,
            "event_category": None,
            "status": "skipped",
            "duplicate": False,
            "skip": True,
            "user_id": uid,
            "user_email": email,
            "transaction_id": transaction_id,
            "log_recorded": False,
        }

    event_category_preview = _preview_event_category(handler, event_type_normalized, data)

    membership_service, db_helper = await _get_services()

    if event_id and db_helper and not allow_duplicate:
        already_processed = await db_helper.has_processed_webhook_event("paddle", event_id)
        if already_processed:
            logger.info("[PADDLE] duplicate event ignored: %s", event_id)
            return {
                "processed": {},
                "event_id": event_id,
                "event_category": event_category_preview,
                "status": "duplicate",
                "duplicate": True,
                "skip": False,
                "user_id": uid,
                "user_email": email,
                "transaction_id": transaction_id,
                "log_recorded": False,
            }

    price_membership = os.getenv("PADDLE_PRICE_ID_MEMBERSHIP", "")
    price_credits = os.getenv("PADDLE_PRICE_ID_CREDITS", "")
    try:
        credits_unit_price = Decimal(os.getenv("CREDITS_UNIT_PRICE_USD", "1.4"))
    except (InvalidOperation, TypeError):
        credits_unit_price = Decimal("0")
    try:
        credits_pack_size = Decimal(
            os.getenv("CREDITS_PACK_SIZE")
            or os.getenv("CREDITS_BUNDLE_SIZE")
            or "5"
        )
    except (InvalidOperation, TypeError):
        credits_pack_size = Decimal("0")

    def summarize_items(items_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        membership_total = 0
        credit_qty = 0
        credit_amount_total = Decimal("0")
        credit_units_total = Decimal("0")
        credit_amount_estimated = False
        credit_currency_mismatch_local = False
        credit_currency_codes_local: set[str] = set()
        price_ids_local: list[str] = []

        for it in items_list:
            price_id = _get(it, "price", "id") or it.get("price_id") or it.get("priceId")
            if price_id:
                price_ids_local.append(price_id)

            qty_raw = it.get("quantity") or 1
            try:
                qty = max(0, int(qty_raw))
            except (TypeError, ValueError):
                qty = 0

            if price_membership and price_id == price_membership:
                membership_total += qty
                continue

            if price_credits and price_id == price_credits:
                credit_qty += qty

                item_currency = (
                    _get(it, "price", "currency_code")
                    or _get(it, "price", "currency")
                    or currency
                    or "USD"
                )
                item_currency = item_currency.upper()
                credit_currency_codes_local.add(item_currency)

                totals = it.get("totals") or {}
                raw_total = (
                    _extract_amount(totals.get("total"))
                    or _extract_amount(totals.get("grand_total"))
                    or _extract_amount(totals.get("gross"))
                    or _extract_amount(totals.get("amount"))
                    or _extract_amount(it.get("totals"))
                    or _extract_amount(it.get("total"))
                )

                if raw_total is None:
                    unit_price_obj = _get(it, "price", "unit_price") or {}
                    raw_unit = _extract_amount(unit_price_obj)
                    if raw_unit is None:
                        raw_unit = _extract_amount(_get(it, "price", "unit_amount"))
                    unit_dec = _to_decimal(raw_unit)
                    if unit_dec is not None:
                        raw_total = unit_dec * qty

                amount_dec = None
                raw_total_dec = _to_decimal(raw_total)
                if raw_total_dec is not None:
                    if item_currency == "USD":
                        amount_dec = (raw_total_dec / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    elif credits_unit_price > 0 and qty > 0:
                        amount_dec = (credits_unit_price * Decimal(qty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        credit_amount_estimated = True
                        logger.info(
                            "[PADDLE] non-USD currency %s detected; inferred USD amount using configuration (event %s)",
                            item_currency,
                            event_id,
                        )
                    else:
                        credit_currency_mismatch_local = True
                        logger.error(
                            "[PADDLE] unsupported currency for credits: %s (event %s)",
                            item_currency,
                            event_id,
                        )

                if amount_dec is not None:
                    credit_amount_total += amount_dec

                if credits_pack_size > 0 and credit_qty > 0:
                    credit_units_total = Decimal(credit_qty) * credits_pack_size
                else:
                    credit_units_total += Decimal(credit_qty)

        return {
            "membership_count": membership_total,
            "credit_quantity": credit_qty,
            "credit_amount_usd": credit_amount_total,
            "credit_units": credit_units_total,
            "credit_amount_estimated": credit_amount_estimated,
            "credit_currency_mismatch": credit_currency_mismatch_local,
            "credit_currency_codes": sorted(credit_currency_codes_local),
            "price_ids": price_ids_local,
        }

    summary = summarize_items(items)
    membership_count = summary["membership_count"]
    credit_quantity = summary["credit_quantity"]
    credit_amount_usd = summary["credit_amount_usd"]
    credit_units_total = summary["credit_units"]
    credit_amount_inferred = summary["credit_amount_estimated"]
    credit_currency_mismatch = summary["credit_currency_mismatch"]
    credit_currency_codes = summary["credit_currency_codes"]

    logger.info(
        "[PADDLE] summary membership=%s credits=%s amount=%s price_ids=%s category=%s",
        membership_count,
        credit_quantity,
        credit_amount_usd,
        summary["price_ids"],
        event_category_preview,
    )
    context = PaddleHandlerContext(
        event_type=event_type,
        event_type_normalized=event_type_normalized,
        payload=payload,
        data=data,
        membership_service=membership_service,
        db_helper=db_helper,
        uid=uid,
        email=email,
        transaction_id=transaction_id,
        subscription_id=subscription_id,
        event_id=event_id,
        membership_count=membership_count,
        credit_quantity=credit_quantity,
        credit_amount_usd=credit_amount_usd,
        credit_units_total=credit_units_total,
        credit_amount_inferred=credit_amount_inferred,
        credit_currency_mismatch=credit_currency_mismatch,
        credit_currency_codes=credit_currency_codes,
        next_billing_at=next_billing_at,
        credits_pack_size=credits_pack_size,
    )

    event_category, handler_results = await handler(context)

    if event_category is None:
        return {
            "processed": {},
            "event_id": event_id,
            "event_category": None,
            "status": "skipped",
            "duplicate": False,
            "skip": True,
            "user_id": uid,
            "user_email": email,
            "transaction_id": transaction_id,
            "log_recorded": False,
        }

    results = handler_results or {}

    status_label = "replayed" if allow_duplicate else "processed"

    payload_data: Dict[str, Any] = {
        "transaction_id": transaction_id,
        "membership_units": membership_count,
        "credit_quantity": credit_quantity,
        "credit_amount_usd": float(credit_amount_usd) if isinstance(credit_amount_usd, Decimal) else credit_amount_usd,
        "credit_units": float(credit_units_total) if isinstance(credit_units_total, Decimal) else credit_units_total,
        "next_billing_at": next_billing_at.isoformat() if next_billing_at else None,
        "event_category": event_category,
        "results": results,
        "user_id": uid,
        "user_email": email,
        "raw_payload": payload,
        "currency": currency,
        "price_ids": summary["price_ids"],
        "subscription_id": subscription_id,
    }

    if replay_reason:
        payload_data["replay_reason"] = replay_reason

    log_recorded = False
    if event_id and db_helper:
        log_recorded = await db_helper.record_webhook_event(
            "paddle",
            event_id,
            status_label,
            payload_data,
        )

    return {
        "processed": results,
        "event_id": event_id,
        "event_category": event_category,
        "status": status_label,
        "duplicate": False,
        "skip": False,
        "user_id": uid,
        "user_email": email,
        "transaction_id": transaction_id,
        "log_recorded": log_recorded,
    }


@router.get("/paddle")
async def paddle_webhook_get():
    return success_response(data={"ok": True}, message="paddle webhook alive")


@router.post("/paddle")
async def paddle_webhook(
    request: Request,
    paddle_signature: str | None = Header(default=None, alias="Paddle-Signature"),
):
    raw = await request.body()
    logger.info(
        "[PADDLE] webhook received: len=%s, has_signature=%s",
        len(raw),
        bool(paddle_signature),
    )

    # Verify signature (best effort)
    if not _verify_signature(raw, paddle_signature):
        raise HTTPException(status_code=400, detail="invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    outcome = await process_paddle_payload(payload)

    if outcome.get("skip"):
        logger.info("[PADDLE] event ignored by category")
        return success_response(data={"skipped": True}, message="event ignored")

    if outcome.get("duplicate"):
        return success_response(data=outcome, message="event already processed")

    return success_response(data=outcome, message="paddle webhook processed")
