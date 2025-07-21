import requests
from .session_tools import SessionTools
from enum import Enum
from typing import List

class StatusType(Enum):
    COMPLETE = "complete"
    WAIT = "wait"

class RangeType(Enum):
    GTE = "GTE"
    LTE = "LTE" 
    BETWEEN = "BETWEEN"

class ReviewLevelType(Enum):
    WORST = "1"
    NORMAL = "2"
    BEST = "3"

class ReviewRatingType(Enum):
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"

class BoolType(Enum):
    Y = "Y"
    N = "N"

class Community:
    def __init__(self, mcp, session_tools: SessionTools = None):
        self.mcp = mcp
        self.session_tools = session_tools
        self._register_tools()
    
    def get_session_data(self, session_id: str):
        """세션 데이터를 가져오는 헬퍼 함수"""
        if self.session_tools:
            return self.session_tools.get_session_data(session_id)
        return None
    
    def _get_site_and_token(self, session_id: str, site_code: str = None, site_name: str = None):
        """사이트 정보와 토큰을 가져오는 공통 헬퍼 함수"""
        session_data = self.get_session_data(session_id)
        
        if not session_data:
            return None, {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        if not sites:
            return None, {"error": "세션에 사이트 정보가 없습니다."}
        
        target_site = None
        if site_code:
            target_site = next((site for site in sites if site["site_code"] == site_code), None)
            if not target_site:
                return None, {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
        elif site_name:
            target_site = next((site for site in sites if site["site_name"] == site_name), None)
            if not target_site:
                return None, {"error": f"사이트 이름 '{site_name}'을 찾을 수 없습니다."}
        else:
            target_site = sites[0]
        
        return target_site, None
    
    def _register_tools(self):
        self.mcp.tool(self.get_community_qna_list)
        self.mcp.tool(self.post_community_qna)
        self.mcp.tool(self.get_community_qna_answer)
        self.mcp.tool(self.get_community_qna)
        self.mcp.tool(self.get_community_review_list)
        self.mcp.tool(self.get_community_review_answer)
        self.mcp.tool(self.get_community_review)
        self.mcp.tool(self.put_community_review)
    
    async def get_community_qna_list(
        self, 
        session_id: str, 
        page: int,
        limit: int = 10,
        prod_code: str = None,
        status: StatusType = None,
        qna_create_time_type: RangeType = None,
        qna_create_time: List[str] = None,
        site_name: str = None, 
        site_code: str = None
    ):
        """
        Q&A 목록을 조회합니다.
        Q&A 정보를 제공할때는 반드시 Q&A 관리 URL을 링크로 제공해야합니다.
        
        Q&A 목록이 포함하는 정보:
            qnaNo: Q&A 번호
            prodNo: 상품 번호
            memberUid: 회원 ID
            nick: 회원 닉네임
            subject: Q&A 제목
            body: Q&A 내용
            status: Q&A 상태 (complete: 완료, wait: 대기)
            url: Q&A 관리 URL
            wtime: Q&A 등록 시간
            utime: Q&A 수정 시간

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, min:1, max: 100)
            prod_code: 상품 코드 (없으면 전체 상품 조회)
            status: Q&A 상태 (COMPLETE: 완료, WAIT: 대기, 없으면 전체 조회)
            qna_create_time_type: Q&A 등록 시간 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정, 없으면 전체 조회)
            qna_create_time: Q&A 등록 시간 검색 범위 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜, 없으면 전체 조회)
                - GTE/LTE: ['2021-01-01T00:00:00.000Z']
                - BETWEEN: ['2021-01-01T00:00:00.000Z', '2021-01-31T23:59:59.000Z']
        """
        print("##### CALL TOOL: get_community_qna_list")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "page": page,
                "limit": limit
            }
            if prod_code:
                params["prodCode"] = prod_code
            if status:
                params["status"] = status.value
            if qna_create_time_type and qna_create_time:
                params["qnaCreateTimeType"] = qna_create_time_type.value
                params["qnaCreateTime[]"] = qna_create_time
            
            response = requests.get("https://openapi.imweb.me/community/qna",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params=params
            )

            if response.status_code != 200:
                print(f"회원 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 목록 조회 실패: {response.status_code}"}
            
            data = response.json().get("data", {})
            qna_list = data.get('list', [])
            for qna in qna_list:
                qna['url'] = f"https://{target_site['primary_domain']}/admin/shopping/answers#admin_qna_detail!/{qna['qnaNo']}"

            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    # Q&A에 답변을 등록해야하는데 API에 아직 답변완료 처리기능이 없어서 답변을 직접 등록하도록 유도합니다.
    async def post_community_qna(
        self, 
        session_id: str, 
        qna_no: int,
        site_name: str = None, 
        site_code: str = None
    ):
        """
        Q&A에 대한 답변 등록 링크를 제공합니다.
        Q&A에 답변을 등록해야하는데 API에 아직 답변완료 처리기능이 없어서 URL을 제공하여 답변을 직접 등록하도록 유도합니다.
        
        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            qna_no: 답변할 Q&A 번호
        """
        print("##### CALL TOOL: post_community_qna")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            # access_token = target_site["access_token"]
            primary_domain = target_site.get("primary_domain")

            # json_data = {
            #     "qnaNo": qna_no,
            #     "reply": reply,
            #     "memberUid": member_uid
            # }
            
            # response = requests.post("https://openapi.imweb.me/community/qna",
            #     headers={
            #         "Content-Type": "application/json",
            #         "Authorization": f"Bearer {access_token}",
            #     },
            #     json=json_data
            # )

            url = f"https://{primary_domain}/admin/shopping/answers#admin_qna_detail!/{qna_no}"
            return {
                "message": "답변을 등록하려면 답변 등록 페이지로 이동하세요.",
                "direct_link": f"[답변 등록 페이지]({url})",
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_community_qna_answer(
        self, 
        session_id: str, 
        qna_no_list: List[int],
        site_name: str = None, 
        site_code: str = None
    ):
        """
        Q&A 답글 목록 조회
        Q&A 번호를 이용해 해당 Q&A글에 달린 답글 목록을 조회합니다.
        답글의 Q&A 번호를 파라미터로 요청할 시 답글의 답글목록도 조회할 수 있습니다.
        
        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            qna_no_list: 답글을 조회할 Q&A 번호 목록(최소 1개, 최대 10개)
        """
        print("##### CALL TOOL: get_community_qna_answer")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "qnaNoList[]": qna_no_list
            }
            
            response = requests.get(
                "https://openapi.imweb.me/community/qna-answer",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params=params
            )

            if response.status_code != 200:
                print(f"회원 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_community_qna(
        self, 
        session_id: str, 
        qna_no: int,
        site_name: str = None, 
        site_code: str = None
    ):
        """
        Q&A 조회
        조회할 Q&A 번호를 이용해 해당 Q&A글을 조회합니다.
        
        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            qna_no: 조회할 Q&A 번호
        """
        print("##### CALL TOOL: get_community_qna")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            response = requests.get(
                f"https://openapi.imweb.me/community/qna/{qna_no}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                }
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return {"error": f"실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_community_review_list(
        self, 
        session_id: str, 
        page: int,
        limit: int = 10,
        prod_no: int = None,
        level: ReviewLevelType = None,
        rating: ReviewRatingType = None,
        is_photo: BoolType = None,
        review_create_time_type: RangeType = None,
        review_create_time: List[str] = None,
        site_name: str = None, 
        site_code: str = None
    ):
        """
        구매평 목록 조회
        
        Args:
            session_id: 세션 ID
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, min: 1, max: 100)
            prod_no: 상품 번호 (없으면 전체 상품 조회)
            level: 구매평 레벨 (WORST: 최악, NORMAL: 보통, BEST: 최고, 없으면 전체 조회)
            rating: 구매평 평점 (ONE: 1점, TWO: 2점, THREE: 3점, FOUR: 4점, FIVE: 5점, 없으면 전체 조회)
            is_photo: 구매평 사진 여부 (Y: 있음, N: 없음, 없으면 전체 조회)
            review_create_time_type: 구매평 등록 시간 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정, 없으면 전체 조회)
            review_create_time: 구매평 등록 시간 검색 범위 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜, 없으면 전체 조회)
                - GTE/LTE: ['2021-01-01T00:00:00.000Z']
                - BETWEEN: ['2021-01-01T00:00:00.000Z', '2021-01-31T23:59:59.000Z']
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_community_review_list")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "page": page,
                "limit": limit
            }
            if prod_no:
                params["prodNo"] = prod_no
            if level:
                params["level"] = level.value
            if rating:
                params["rating"] = rating.value
            if is_photo:
                params["isPhoto"] = is_photo.value
            if review_create_time_type and review_create_time:
                params["reviewCreateTimeType"] = review_create_time_type.value
                params["reviewCreateTime[]"] = review_create_time
            
            response = requests.get(
                f"https://openapi.imweb.me/community/review",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params=params
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return {"error": f"실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_community_review_answer(
        self, 
        session_id: str, 
        review_no_list: List[int],
        site_name: str = None, 
        site_code: str = None
    ):
        """
        구매평 답글 목록 조회
        구매평 번호를 이용해 해당 구매평에 달린 답글 목록을 조회합니다.
        답글의 구매평 번호를 파라미터로 요청할 시 답글의 답글 목록도 조회할 수 있습니다.
        
        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            reivew_no_list: 답글을 조회할 Q&A 번호 목록(최소 1개, 최대 10개)
        """
        print("##### CALL TOOL: get_community_review_answer")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "reviewNoList[]": review_no_list
            }
            
            response = requests.get(
                "https://openapi.imweb.me/community/review-answer",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params=params
            )

            if response.status_code != 200:
                print(f"회원 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_community_review(
        self, 
        session_id: str, 
        review_no: int,
        site_name: str = None, 
        site_code: str = None
    ):
        """
        구매평 조회
        조회할 구매평 번호를 이용해 해당 구매평을 조회합니다.
        
        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            review_no: 조회할 구매평 번호
        """
        print("##### CALL TOOL: get_community_review")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            response = requests.get(
                f"https://openapi.imweb.me/community/review/{review_no}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                }
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return {"error": f"실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def put_community_review(
        self, 
        session_id: str, 
        review_no: int,
        body: str,
        rating: int = None,
        site_name: str = None, 
        site_code: int = None
    ):
        """
        구매평 수정
        구매평 번호와 내용을 이용해 해당 구매평을 수정합니다.
        
        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            review_no: 조회할 구매평 번호
            body: 수정할 구매평 내용 (없으면 수정하지 않음)
            rating: 수정할 구매평 평점 (1~5 사이의 정수, 없으면 수정하지 않음)
        """
        print("##### CALL TOOL: get_community_review")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            json_data = {}
            if body:
                json_data["body"] = body
            if 0 < rating < 6:
                json_data["rating"] = rating
            
            response = requests.put(
                f"https://openapi.imweb.me/community/review/{review_no}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                json=json_data
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return {"error": f"실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
