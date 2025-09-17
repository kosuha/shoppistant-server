"""
Paddle Webhook Router

Accepts Paddle Billing webhook events and acknowledges with 200 OK.
Signature verification and business logic will be added next.
"""
import logging
from fastapi import APIRouter, Request, Header

from core.responses import success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks", "paddle"])


@router.get("/paddle")
async def paddle_webhook_get():
    """Simple liveness check endpoint for webhook target."""
    return success_response(data={"ok": True}, message="paddle webhook alive")


@router.post("/paddle")
async def paddle_webhook(
    request: Request,
    paddle_signature: str | None = Header(default=None, alias="Paddle-Signature"),
):
    """
    Receive Paddle webhooks. At this stage we just log and ACK.

    Later: verify signature using Paddle's public key and dispatch events
    (e.g., membership activation, credits top-up).
    """
    raw = await request.body()
    try:
        # Keep concise logs to avoid leaking secrets in production
        logger.info(
            "[PADDLE] webhook received: len=%s, has_signature=%s",
            len(raw),
            bool(paddle_signature),
        )
    except Exception:
        # Logging shouldn't break the webhook
        pass

    # TODO: verify signature (Paddle-Signature) against configured public key
    # TODO: parse JSON and dispatch by event type

    return success_response(data={"received": True}, message="paddle webhook accepted")

