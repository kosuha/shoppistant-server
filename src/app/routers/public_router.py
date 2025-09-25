"""Public endpoints for client-side configuration (no auth required)."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Optional
import os

from fastapi import APIRouter

from core.responses import success_response, error_response

router = APIRouter(prefix="/api/v1/public", tags=["public"])

_DECIMAL_ZERO = Decimal("0")
_TWO_DP = Decimal("0.01")


def _get_decimal(key: str, default: str) -> Decimal:
    raw = os.getenv(key, default)
    if raw is None:
        return Decimal(default)
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def _quantize_currency(value: Decimal, digits: Decimal = _TWO_DP) -> Decimal:
    if value <= _DECIMAL_ZERO:
        return _DECIMAL_ZERO
    return value.quantize(digits, rounding=ROUND_HALF_UP)


def _to_float(value: Decimal, digits: Decimal = _TWO_DP) -> float:
    return float(_quantize_currency(value, digits))


def _format_pricing_payload() -> Dict[str, Any]:
    membership_usd = _get_decimal("MEMBERSHIP_PRICE_USD", "5")
    membership_krw = _get_decimal("MEMBERSHIP_PRICE_KRW", "7000")

    credits_unit_usd = _get_decimal("CREDITS_UNIT_PRICE_USD", "1.4")
    credits_unit_krw = _get_decimal("CREDITS_UNIT_PRICE_KRW", "1960")
    bundle_size_raw = os.getenv("CREDITS_BUNDLE_SIZE", "5") or "5"
    try:
        bundle_size = max(1, int(bundle_size_raw))
    except ValueError:
        bundle_size = 5

    credits_bundle_usd = credits_unit_usd * Decimal(bundle_size)
    credits_bundle_krw = credits_unit_krw * Decimal(bundle_size)

    return {
        "membership": {
            "usd": _to_float(membership_usd),
            "krw": int(_quantize_currency(membership_krw, Decimal("1"))),
        },
        "credits": {
            "bundle_size": bundle_size,
            "usd_per_bundle": _to_float(credits_bundle_usd),
            "krw_per_bundle": int(_quantize_currency(credits_bundle_krw, Decimal("1"))),
            "usd_unit": _to_float(credits_unit_usd),
            "krw_unit": int(_quantize_currency(credits_unit_krw, Decimal("1"))),
        },
    }


@router.get("/pricing")
async def get_public_pricing():
    try:
        data = _format_pricing_payload()
        return success_response(data=data, message="Pricing loaded")
    except Exception as exc:  # pragma: no cover - defensive
        return error_response(message="Failed to load pricing", error_code="PRICING_FETCH_ERROR", data={"detail": str(exc)})
