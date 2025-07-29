-- chat_messages 테이블에 총 비용 컬럼 추가

ALTER TABLE chat_messages 
ADD COLUMN IF NOT EXISTS cost_usd DECIMAL(10, 6) DEFAULT 0;

-- 인덱스 추가 (비용 분석을 위한 쿼리 최적화)
CREATE INDEX IF NOT EXISTS idx_chat_messages_cost_usd ON chat_messages(cost_usd);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_cost ON chat_messages(user_id, cost_usd);

-- 코멘트 추가
COMMENT ON COLUMN chat_messages.cost_usd IS 'AI API 호출 총 비용 (USD)';