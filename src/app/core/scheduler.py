"""
배경 작업 스케줄러
일일 요청 수 초기화 및 기타 정기 작업 관리
"""
import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

class BackgroundScheduler:
    def __init__(self, db_helper):
        self.db_helper = db_helper
        self.running = False
        self.tasks = []
    
    async def start(self):
        """스케줄러 시작"""
        if self.running:
            return
        
        self.running = True
        logger.info("백그라운드 스케줄러 시작")
        
        # 일일 정리 작업 (매일 자정)
        self.tasks.append(
            asyncio.create_task(self._daily_cleanup_scheduler())
        )
        
        # 만료된 멤버십 체크 (매시간)
        self.tasks.append(
            asyncio.create_task(self._hourly_membership_check())
        )
    
    async def stop(self):
        """스케줄러 중지"""
        if not self.running:
            return
        
        self.running = False
        logger.info("백그라운드 스케줄러 중지")
        
        # 모든 실행 중인 작업 취소
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # 작업이 완료될 때까지 대기
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        
        self.tasks.clear()
    
    async def _daily_cleanup_scheduler(self):
        """매일 자정에 정리 작업 실행"""
        while self.running:
            try:
                # 다음 자정까지의 시간 계산
                now = datetime.now()
                next_midnight = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                sleep_seconds = (next_midnight - now).total_seconds()
                
                logger.info(f"다음 정리 작업까지 {sleep_seconds:.0f}초 대기")
                await asyncio.sleep(sleep_seconds)
                
                if not self.running:
                    break
                
                # 정리 작업 실행
                await self._run_daily_cleanup()
                
            except asyncio.CancelledError:
                logger.info("일일 정리 스케줄러 취소됨")
                break
            except Exception as e:
                logger.error(f"일일 정리 스케줄러 오류: {e}")
                # 오류 발생 시 1시간 후 재시도
                await asyncio.sleep(3600)
    
    async def _hourly_membership_check(self):
        """매시간 만료된 멤버십 확인"""
        while self.running:
            try:
                await asyncio.sleep(3600)  # 1시간 대기
                
                if not self.running:
                    break
                
                # 만료된 멤버십 다운그레이드
                downgraded_count = await self.db_helper.batch_downgrade_expired_memberships()
                if downgraded_count > 0:
                    logger.info(f"만료된 멤버십 {downgraded_count}개 다운그레이드 완료")
                
            except asyncio.CancelledError:
                logger.info("멤버십 체크 스케줄러 취소됨")
                break
            except Exception as e:
                logger.error(f"멤버십 체크 스케줄러 오류: {e}")
    
    async def _run_daily_cleanup(self):
        """일일 정리 작업 실행"""
        try:
            logger.info("일일 정리 작업 시작")
            
            # 1. 오래된 요청 로그 정리 (30일 이상)
            deleted_logs = await self.db_helper.cleanup_old_request_logs(days_to_keep=30)
            logger.info(f"오래된 요청 로그 {deleted_logs}개 정리 완료")
            
            # 2. 만료된 멤버십 다운그레이드
            downgraded_count = await self.db_helper.batch_downgrade_expired_memberships()
            logger.info(f"만료된 멤버십 {downgraded_count}개 다운그레이드 완료")
            
            # 3. 시스템 이벤트 로그 기록
            await self.db_helper.log_system_event(
                event_type='daily_cleanup',
                event_data={
                    'timestamp': datetime.now().isoformat(),
                    'deleted_logs': deleted_logs,
                    'downgraded_memberships': downgraded_count
                }
            )
            
            logger.info("일일 정리 작업 완료")
            
        except Exception as e:
            logger.error(f"일일 정리 작업 실패: {e}")
    
    async def trigger_cleanup_now(self) -> dict:
        """즉시 정리 작업 실행 (관리자용)"""
        try:
            logger.info("수동 정리 작업 실행")
            await self._run_daily_cleanup()
            return {"success": True, "message": "정리 작업 완료"}
        except Exception as e:
            logger.error(f"수동 정리 작업 실패: {e}")
            return {"success": False, "error": str(e)}

# 전역 스케줄러 인스턴스
scheduler: Optional[BackgroundScheduler] = None

def get_scheduler() -> Optional[BackgroundScheduler]:
    """스케줄러 인스턴스 반환"""
    return scheduler

async def initialize_scheduler(db_helper):
    """스케줄러 초기화"""
    global scheduler
    if scheduler is None:
        scheduler = BackgroundScheduler(db_helper)
        await scheduler.start()
        logger.info("백그라운드 스케줄러 초기화 완료")

async def cleanup_scheduler():
    """스케줄러 정리"""
    global scheduler
    if scheduler:
        await scheduler.stop()
        scheduler = None
        logger.info("백그라운드 스케줄러 정리 완료")