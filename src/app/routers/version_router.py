from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sites", tags=["versions"])  # final path: /api/v1/sites/{site_code}/versions
security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)


def _get_admin_client():
    from main import supabase_admin
    if not supabase_admin:
        raise RuntimeError("Supabase admin client is not configured")
    return supabase_admin


# 기존 권한 체크는 site_code만 검사해서 도메인으로 호출 시 403이 발생할 수 있었다.
# 식별자(사이트코드 또는 도메인)를 받아 사용자 소유의 사이트를 해석하여 정규화된 site_code를 반환한다.

def _resolve_user_site(client, user_id: str, identifier: str) -> Dict[str, Any]:
    """identifier가 site_code 또는 primary_domain일 수 있으므로 둘 다 매칭해 사이트 행을 반환"""
    # Supabase-Py v2: or_ 사용
    res = client.table("user_sites").select("*") \
        .eq("user_id", user_id) \
        .or_(f"site_code.eq.{identifier},primary_domain.eq.{identifier}") \
        .limit(1).execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="해당 사이트에 대한 권한이 없습니다.")
    return res.data[0]


@router.get("/{site_code}/versions")
async def list_versions(site_code: str, user=Depends(get_current_user)):
    """지정 사이트의 모든 버전 목록 (created_at ASC)
    site_code에는 실제 site_code 또는 도메인(primary_domain) 둘 다 허용
    """
    client = _get_admin_client()
    try:
        site = _resolve_user_site(client, user.id, site_code)
        canonical_code = site.get("site_code")
        result = client.table("site_script_versions").select("*") \
            .eq("user_id", user.id) \
            .eq("site_code", canonical_code) \
            .order("created_at", desc=False) \
            .execute()

        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result.data or []
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"버전 목록 조회 실패: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.get("/{site_code}/versions/head")
async def get_head(site_code: str, user=Depends(get_current_user)):
    """최신 버전 1건 반환 (없으면 null)
    site_code에는 실제 site_code 또는 도메인(primary_domain) 둘 다 허용
    """
    client = _get_admin_client()
    try:
        site = _resolve_user_site(client, user.id, site_code)
        canonical_code = site.get("site_code")
        result = client.table("site_script_versions").select("*") \
            .eq("user_id", user.id) \
            .eq("site_code", canonical_code) \
            .order("created_at", desc=True).limit(1) \
            .execute()

        head = result.data[0] if result.data else None
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": head
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HEAD 버전 조회 실패: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@router.post("/{site_code}/versions")
async def create_version(site_code: str, request: Request, user=Depends(get_current_user)):
    """스냅샷/패치 저장 API
    요청 바디 예시:
    - snapshot: { "type":"snapshot", "js_code":"...", "css_code":"...", "patch_count_from_snapshot":0, "message_id":"...", "change_summary":"..." }
    - patch:    { "type":"patch",    "js_patch":"...",  "css_patch":"...",  "patch_count_from_snapshot":3, "message_id":"...", "change_summary":"..." }
    site_code에는 실제 site_code 또는 도메인(primary_domain) 둘 다 허용
    """
    client = _get_admin_client()
    try:
        site = _resolve_user_site(client, user.id, site_code)
        canonical_code = site.get("site_code")
        body = await request.json()

        vtype: str = (body.get("type") or "").lower()
        if vtype not in ("snapshot", "patch"):
            raise HTTPException(status_code=400, detail="type은 'snapshot' 또는 'patch'여야 합니다.")

        # 클라이언트 호환: js_code/css_code 또는 javascript/css 둘 다 허용
        javascript: Optional[str] = body.get("javascript") or body.get("js_code")
        css: Optional[str] = body.get("css") or body.get("css_code")
        js_patch: Optional[str] = body.get("js_patch")
        css_patch: Optional[str] = body.get("css_patch")
        patch_count: int = int(body.get("patch_count_from_snapshot") or 0)

        # 유효성
        if vtype == "snapshot":
            if (javascript is None and css is None) or (js_patch is not None or css_patch is not None):
                raise HTTPException(status_code=400, detail="snapshot은 javascript/css 중 하나 이상이 필요하고, 패치 필드는 없어야 합니다.")
        else:
            if (js_patch is None and css_patch is None) or (javascript is not None or css is not None):
                raise HTTPException(status_code=400, detail="patch는 js_patch/css_patch 중 하나 이상이 필요하고, 코드 필드는 없어야 합니다.")

        # parent_id는 최신 버전을 참조(패치일 때)
        parent_id: Optional[str] = None
        if vtype == "patch":
            head_res = client.table("site_script_versions").select("id") \
                .eq("user_id", user.id).eq("site_code", canonical_code) \
                .order("created_at", desc=True).limit(1).execute()
            parent_id = head_res.data[0]["id"] if head_res.data else None

        metadata: Dict[str, Any] = body.get("metadata") or {}
        # message_id, change_summary를 metadata로 수용
        if "message_id" in body and body.get("message_id") is not None:
            metadata.setdefault("message_id", body.get("message_id"))
        if "change_summary" in body and body.get("change_summary") is not None:
            metadata.setdefault("change_summary", body.get("change_summary"))

        row = {
            "user_id": user.id,
            "site_code": canonical_code,
            "type": vtype,
            "javascript": javascript,
            "css": css,
            "js_patch": js_patch,
            "css_patch": css_patch,
            "patch_count_from_snapshot": patch_count,
            "parent_id": parent_id,
            "metadata": metadata or None,
            # is_release는 기본값 false
        }

        insert_res = client.table("site_script_versions").insert(row).execute()
        created = insert_res.data[0] if insert_res.data else None
        if not created:
            raise HTTPException(status_code=500, detail="버전 생성 실패")

        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": created
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"버전 생성 실패: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
