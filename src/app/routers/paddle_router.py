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
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Header, HTTPException

from core.responses import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks", "paddle"])


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

    # Parse JSON
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    # Extract fields
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

    if not items:
        # Some Paddle events wrap the transaction under "object" or similar
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

    # Only act on completed/paid events
    et = (event_type or "").lower()
    if not ("completed" in et or "paid" in et or "succeeded" in et):
        return success_response(data={"skipped": True}, message="event ignored")

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
        except Exception as e:  # pragma: no cover - diagnostic path
            logger.error("[PADDLE] service fallback acquisition failed: %s", e)

    if event_id and db_helper:
        already_processed = await db_helper.has_processed_webhook_event("paddle", event_id)
        if already_processed:
            logger.info("[PADDLE] duplicate event ignored: %s", event_id)
            return success_response(data={"duplicate": True}, message="event already processed")

    # Resolve env configuration
    price_membership = os.getenv("PADDLE_PRICE_ID_MEMBERSHIP", "")
    price_credits = os.getenv("PADDLE_PRICE_ID_CREDITS", "")
    try:
        credits_unit_price = Decimal(os.getenv("CREDITS_UNIT_PRICE_USD", "1.4"))
    except (InvalidOperation, TypeError):
        credits_unit_price = Decimal("0")

    # Dispatch items
    membership_count = 0
    credit_quantity = 0
    credit_amount_usd = Decimal("0")
    credit_amount_inferred = False
    credit_currency_mismatch = False

    for it in items:
        # Try multiple shapes for price id
        price_id = _get(it, "price", "id") or it.get("price_id") or it.get("priceId")
        qty_raw = it.get("quantity") or 1
        try:
            qty = max(0, int(qty_raw))
        except (TypeError, ValueError):
            qty = 0

        if price_membership and price_id == price_membership:
            membership_count += qty
            continue

        if price_credits and price_id == price_credits:
            credit_quantity += qty

            item_currency = (
                _get(it, "price", "currency_code")
                or _get(it, "price", "currency")
                or currency
                or "USD"
            )
            item_currency = item_currency.upper()

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
                else:
                    credit_currency_mismatch = True
                    logger.error(
                        "[PADDLE] unsupported currency for credits: %s (event %s)",
                        item_currency,
                        event_id,
                    )

            if amount_dec is None and qty > 0:
                if credits_unit_price > 0:
                    amount_dec = (credits_unit_price * Decimal(qty)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    credit_amount_inferred = True
                else:
                    amount_dec = Decimal("0")

            if amount_dec is not None:
                credit_amount_usd += amount_dec

    if credit_amount_inferred:
        logger.warning(
            "[PADDLE] credit amount inferred from unit price configuration for event %s",
            event_id,
        )

    if credit_currency_mismatch:
        logger.error(
            "[PADDLE] credit processing blocked due to unsupported currency (event %s)",
            event_id,
        )

    # Prepare results structure and log item mapping summary
    results: Dict[str, Any] = {}

    logger.info(
        "[PADDLE] mapped items summary: membership_count=%s credit_quantity=%s custom_keys=%s price_ids=%s",
        membership_count,
        credit_quantity,
        sorted(custom.keys()),
        [
            _get(it, "price", "id") or it.get("price_id") or it.get("priceId")
            for it in items
        ],
    )

    # No mapped items, just ACK (and record event for idempotency)
    if membership_count == 0 and credit_quantity == 0:
        logger.info("[PADDLE] interim results payload: %s", results)
        if event_id and db_helper:
            await db_helper.record_webhook_event(
                "paddle",
                event_id,
                "acknowledged",
                {"reason": "no mapped items"},
            )
        return success_response(data={"ok": True}, message="no mapped items; acknowledged")

    # Identify user
    user_id = uid
    if not user_id and email:
        # Optional: resolve user by email via Supabase admin (skipped here)
        logger.warning("[PADDLE] uid missing; email resolution not implemented")

    results: Dict[str, Any] = {}
    # Membership activation/extension: assume 30 days per unit
    if membership_count > 0 and membership_service and user_id:
        try:
            res = await membership_service.upgrade_membership(
                user_id=user_id,
                target_level=1,
                duration_days=30 * membership_count,
                next_billing_at=next_billing_at,
            )
            res_data = res if isinstance(res, dict) else {}
            results["membership"] = {
                "success": bool(res_data),
                "data": res_data,
            }
        except Exception as e:
            logger.error(f"[PADDLE] membership update failed: {e}")
            results["membership"] = {"success": False}
    elif membership_count > 0 and not user_id:
        results["membership"] = {"success": False, "reason": "missing_user"}
    elif membership_count > 0 and not membership_service:
        results["membership"] = {"success": False, "reason": "service_unavailable"}

    # Credits top-up: credit wallet with USD equivalent
    if credit_quantity > 0:
        credit_result: Dict[str, Any] = {
            "quantity": credit_quantity,
            "amount_usd": float(credit_amount_usd) if credit_amount_usd else 0,
            "inferred": credit_amount_inferred,
            "success": False,
        }

        if credit_currency_mismatch:
            credit_result["error"] = "unsupported_currency"
        elif not user_id:
            credit_result["error"] = "missing_user"
        elif not db_helper:
            credit_result["error"] = "service_unavailable"
        else:
            try:
                amount_usd_float = float(credit_amount_usd)
                credit_metadata = {
                    "provider": "paddle",
                    "event_id": event_id,
                    "transaction_id": transaction_id,
                    "quantity": credit_quantity,
                    "amount_usd": amount_usd_float,
                    "inferred": credit_amount_inferred,
                }
                tx = await db_helper.credit_wallet(  # type: ignore
                    user_id,
                    amount_usd_float,
                    metadata=credit_metadata,
                    source_event_id=event_id,
                )
                credit_result["success"] = bool(tx)
                credit_result["transaction_recorded"] = bool(tx)
            except Exception as e:
                logger.error(f"[PADDLE] wallet credit failed: {e}")
                credit_result["error"] = "credit_failed"

        results["credits"] = credit_result

    logger.info("[PADDLE] interim results payload: %s", results)

    if event_id and db_helper:
        await db_helper.record_webhook_event(
            "paddle",
            event_id,
            "processed",
            {
                "transaction_id": transaction_id,
                "membership_units": membership_count,
                "credit_quantity": credit_quantity,
                "next_billing_at": next_billing_at.isoformat() if next_billing_at else None,
                "results": results,
            },
        )

    return success_response(data={"processed": results}, message="paddle webhook processed")
