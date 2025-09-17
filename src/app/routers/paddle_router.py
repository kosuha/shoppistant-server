"""
Paddle Webhook Router

Handles Paddle Billing webhook events:
- optional signature verification using public key
- membership activation/extension
- wallet credit top-up for AI credits
"""
import json
import os
import base64
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request, Header, HTTPException

from core.responses import success_response, error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks", "paddle"])


def _verify_signature(raw: bytes, signature: Optional[str]) -> bool:
    """Verify Paddle-Signature if configured.

    If PADDLE_WEBHOOK_PUBLIC_KEY is not set, returns True (non-strict).
    If PADDLE_WEBHOOK_STRICT_VERIFY=true, failures return False.
    """
    strict = os.getenv("PADDLE_WEBHOOK_STRICT_VERIFY", "false").lower() == "true"
    public_key = os.getenv("PADDLE_WEBHOOK_PUBLIC_KEY", "").strip()
    if not public_key:
        if strict:
            logger.warning("[PADDLE] strict verify enabled but no public key configured")
            return False
        return True
    if not signature:
        logger.warning("[PADDLE] missing Paddle-Signature header")
        return not strict

    try:
        # Best-effort RSA-SHA256 verification (depends on cryptography library)
        from cryptography.hazmat.primitives import serialization, hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        pub = serialization.load_pem_public_key(public_key.encode("utf-8"))
        sig = base64.b64decode(signature)
        pub.verify(sig, raw, padding.PKCS1v15(), hashes.SHA256())
        return True
    except ImportError:
        logger.warning("[PADDLE] cryptography not installed; skipping signature verification")
        return not strict
    except Exception as e:
        logger.error(f"[PADDLE] signature verification failed: {e}")
        return False if strict else True


def _get(d: Dict, *keys: str, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


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
    custom = _get(data, "custom_data") or _get(data, "customData") or {}
    uid = custom.get("uid") or custom.get("user_id") or custom.get("userId")
    email = _get(data, "customer", "email") or _get(data, "customer_email")
    items: List[Dict[str, Any]] = data.get("items") or []

    if not items:
        # Some Paddle events wrap the transaction under "object" or similar
        items = _get(data, "object", "items", default=[]) or _get(payload, "object", "items", default=[])

    logger.info("[PADDLE] event=%s uid=%s email=%s items=%s", event_type, uid, bool(email), len(items))

    # Only act on completed/paid events
    et = (event_type or "").lower()
    if not ("completed" in et or "paid" in et or "succeeded" in et):
        return success_response(data={"skipped": True}, message="event ignored")

    # Resolve env configuration
    price_membership = os.getenv("PADDLE_PRICE_ID_MEMBERSHIP", "")
    price_credits = os.getenv("PADDLE_PRICE_ID_CREDITS", "")
    credits_unit_price = float(os.getenv("CREDITS_UNIT_PRICE_USD", "1.4"))

    # Dispatch items
    membership_count = 0
    credits_units = 0

    for it in items:
        # Try multiple shapes for price id
        price_id = _get(it, "price", "id") or it.get("price_id") or it.get("priceId")
        qty = int(it.get("quantity") or 1)
        if price_membership and price_id == price_membership:
            membership_count += qty
        elif price_credits and price_id == price_credits:
            credits_units += max(0, qty)

    # No mapped items, just ACK
    if membership_count == 0 and credits_units == 0:
        return success_response(data={"ok": True}, message="no mapped items; acknowledged")

    # Execute business actions
    try:
        from app.main import membership_service, db_helper  # type: ignore
    except Exception:
        membership_service = None
        db_helper = None

    # Identify user
    user_id = uid
    if not user_id and email:
        # Optional: resolve user by email via Supabase admin (skipped here)
        logger.warning("[PADDLE] uid missing; email resolution not implemented")

    results = {}
    # Membership activation/extension: assume 30 days per unit
    if membership_count > 0 and membership_service and user_id:
        try:
            res = await membership_service.upgrade_membership(
                user_id=user_id,
                target_level=1,
                duration_days=30 * membership_count,
            )
            results["membership"] = res or True
        except Exception as e:
            logger.error(f"[PADDLE] membership update failed: {e}")
            results["membership"] = False

    # Credits top-up: credit wallet with USD equivalent
    if credits_units > 0 and db_helper and user_id:
        try:
            amount_usd = credits_units * credits_unit_price
            tx = await db_helper.credit_wallet(user_id, amount_usd)  # type: ignore
            results["credits_usd"] = amount_usd
            results["tx"] = bool(tx)
        except Exception as e:
            logger.error(f"[PADDLE] wallet credit failed: {e}")
            results["credits_usd"] = 0
            results["tx"] = False

    return success_response(data={"processed": results}, message="paddle webhook processed")
