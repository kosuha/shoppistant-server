-- site_scripts 테이블 생성
-- 아임웹 사이트별 스크립트를 데이터베이스에 저장하기 위한 테이블

CREATE TABLE IF NOT EXISTS site_scripts (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    site_code VARCHAR(255) NOT NULL,
    script_content TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    user_id UUID NOT NULL,
    
    -- 외래키 제약 조건
    CONSTRAINT fk_site_scripts_user_sites 
        FOREIGN KEY (user_id, site_code) 
        REFERENCES user_sites(user_id, site_code) 
        ON DELETE CASCADE,
    
    -- 인덱스를 위한 유니크 제약조건 (사이트별로 하나의 활성 스크립트만 존재)
    CONSTRAINT uk_site_scripts_active_per_site 
        UNIQUE (site_code, is_active) 
        DEFERRABLE INITIALLY DEFERRED
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_site_scripts_site_code ON site_scripts(site_code);
CREATE INDEX IF NOT EXISTS idx_site_scripts_user_id ON site_scripts(user_id);
CREATE INDEX IF NOT EXISTS idx_site_scripts_active ON site_scripts(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_site_scripts_created_at ON site_scripts(created_at DESC);

-- updated_at 자동 업데이트를 위한 트리거 함수
CREATE OR REPLACE FUNCTION update_site_scripts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 트리거 생성
DROP TRIGGER IF EXISTS trigger_site_scripts_updated_at ON site_scripts;
CREATE TRIGGER trigger_site_scripts_updated_at
    BEFORE UPDATE ON site_scripts
    FOR EACH ROW
    EXECUTE FUNCTION update_site_scripts_updated_at();

-- RLS (Row Level Security) 정책 설정
ALTER TABLE site_scripts ENABLE ROW LEVEL SECURITY;

-- 사용자는 자신의 스크립트만 조회/수정 가능
CREATE POLICY "Users can view their own site scripts"
    ON site_scripts FOR SELECT
    USING (auth.uid()::text = user_id::text);

CREATE POLICY "Users can insert their own site scripts"
    ON site_scripts FOR INSERT
    WITH CHECK (auth.uid()::text = user_id::text);

CREATE POLICY "Users can update their own site scripts"
    ON site_scripts FOR UPDATE
    USING (auth.uid()::text = user_id::text)
    WITH CHECK (auth.uid()::text = user_id::text);

CREATE POLICY "Users can delete their own site scripts"
    ON site_scripts FOR DELETE
    USING (auth.uid()::text = user_id::text);

-- Service role에 대한 모든 권한 부여
CREATE POLICY "Service role has full access to site scripts"
    ON site_scripts FOR ALL
    USING (current_setting('role') = 'service_role')
    WITH CHECK (current_setting('role') = 'service_role');

COMMENT ON TABLE site_scripts IS '아임웹 사이트별 스크립트 저장 테이블';
COMMENT ON COLUMN site_scripts.id IS '스크립트 고유 ID';
COMMENT ON COLUMN site_scripts.site_code IS '사이트 코드 (user_sites 테이블과 연결)';
COMMENT ON COLUMN site_scripts.script_content IS '스크립트 내용 (JavaScript 코드)';
COMMENT ON COLUMN site_scripts.version IS '스크립트 버전 (1부터 시작, 업데이트시 증가)';
COMMENT ON COLUMN site_scripts.is_active IS '활성 스크립트 여부 (사이트별로 하나만 true 가능)';
COMMENT ON COLUMN site_scripts.user_id IS '스크립트 소유자 ID';