-- Add status field to chat_messages table
-- 메시지 상태 필드 추가: 'pending' | 'in_progress' | 'completed' | 'error'

ALTER TABLE public.chat_messages 
ADD COLUMN status text DEFAULT 'completed' 
CHECK (status = ANY (ARRAY['pending'::text, 'in_progress'::text, 'completed'::text, 'error'::text]));

-- 기존 메시지들의 기본 상태를 'completed'로 설정
UPDATE public.chat_messages 
SET status = 'completed' 
WHERE status IS NULL;

-- 인덱스 추가 (상태별 조회 성능 향상)
CREATE INDEX IF NOT EXISTS idx_chat_messages_status ON public.chat_messages(status);
CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_status ON public.chat_messages(thread_id, status);

COMMENT ON COLUMN public.chat_messages.status IS '메시지 처리 상태: pending(대기중), in_progress(처리중), completed(완료), error(오류)';