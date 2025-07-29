-- 일일 요청 수 추적을 위한 테이블 생성
CREATE TABLE IF NOT EXISTS daily_request_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    request_date DATE NOT NULL DEFAULT CURRENT_DATE,
    request_count INTEGER NOT NULL DEFAULT 1,
    endpoint VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 사용자별 일일 요청 수 제약 (하나의 날짜당 하나의 레코드)
    UNIQUE(user_id, request_date)
);

-- 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_daily_request_logs_user_date ON daily_request_logs(user_id, request_date);
CREATE INDEX IF NOT EXISTS idx_daily_request_logs_date ON daily_request_logs(request_date);

-- RLS 정책 설정
ALTER TABLE daily_request_logs ENABLE ROW LEVEL SECURITY;

-- 사용자는 자신의 로그만 조회 가능
CREATE POLICY "Users can view own request logs" ON daily_request_logs
    FOR SELECT USING (auth.uid() = user_id);

-- 시스템에서만 로그 삽입/업데이트 가능 (서버 사이드에서만)
CREATE POLICY "System can insert request logs" ON daily_request_logs
    FOR INSERT WITH CHECK (true);

CREATE POLICY "System can update request logs" ON daily_request_logs
    FOR UPDATE USING (true);