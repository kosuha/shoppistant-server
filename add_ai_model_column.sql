-- chat_messages 테이블에 AI 모델 정보 컬럼 추가

ALTER TABLE chat_messages 
ADD COLUMN IF NOT EXISTS ai_model VARCHAR(50) DEFAULT NULL;

-- 인덱스 추가 (모델별 분석을 위한 쿼리 최적화)
CREATE INDEX IF NOT EXISTS idx_chat_messages_ai_model ON chat_messages(ai_model);
CREATE INDEX IF NOT EXISTS idx_chat_messages_model_cost ON chat_messages(ai_model, cost_usd);

-- 코멘트 추가
COMMENT ON COLUMN chat_messages.ai_model IS '사용된 AI 모델명 (예: gemini-2.5-pro, gemini-2.5-flash)';