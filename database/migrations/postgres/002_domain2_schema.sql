-- 002_domain2_schema.sql
-- Covers Licitações, Workflows, Segmentação e Jobs

CREATE TABLE orgaos (
    id SERIAL PRIMARY KEY,
    cnpj TEXT UNIQUE NOT NULL,
    nome TEXT,
    municipio TEXT,
    municipio_ibge TEXT,
    uf TEXT,
    esfera TEXT,
    poder TEXT,
    capag_nota TEXT,
    capag_fonte TEXT,
    capag_atualizada_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_orgaos_cnpj ON orgaos(cnpj);
CREATE INDEX idx_orgaos_capag ON orgaos(capag_nota);

CREATE TABLE segments (
  id TEXT PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  priority INTEGER DEFAULT 0,
  match_mode TEXT CHECK (match_mode IN ('ANY','ALL')),
  min_hits INTEGER NOT NULL DEFAULT 1,
  organization_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_segments_organization_id ON segments(organization_id);

CREATE TABLE segment_terms (
  id TEXT PRIMARY KEY,
  segment_id TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
  term TEXT NOT NULL,
  term_type TEXT CHECK (term_type IN ('include','exclude','required')) NOT NULL,
  group_id TEXT,
  organization_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_segment_terms_segment_id ON segment_terms(segment_id);

CREATE TABLE contratacoes (
    pncp_id TEXT PRIMARY KEY,
    
    orgao_cnpj TEXT,
    ano TEXT,
    sequencial TEXT,
    
    orgao_nome TEXT,
    modalidade_codigo INTEGER,
    modalidade_nome TEXT,
    numero TEXT,
    objeto TEXT,
    situacao_codigo INTEGER,
    situacao_nome TEXT,
    
    data_publicacao TIMESTAMPTZ,
    data_abertura TIMESTAMPTZ,
    data_encerramento TIMESTAMPTZ,
    
    uf TEXT,
    municipio TEXT,
    
    valor_estimado_centavos BIGINT,
    
    url_pncp_detalhe TEXT,
    
    payload_publicacao_hash TEXT,
    payload_publicacao_json JSONB,
    
    payload_detalhe_hash TEXT,     
    payload_detalhe_json JSONB,     
    
    first_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, 
    
    enrichment_status TEXT DEFAULT 'PENDING' CHECK(enrichment_status IN ('PENDING','COMPLETED','ERROR','RETRY')),
    enrichment_attempts INTEGER DEFAULT 0,
    last_enrichment_attempt TIMESTAMPTZ,
    last_error TEXT,
    
    is_valid BOOLEAN DEFAULT TRUE,
    url_pncp_status_code INTEGER,
    url_pncp_checked_at TIMESTAMPTZ,
    url_pncp_source TEXT,
    url_pncp_error TEXT,
    segmento_principal TEXT,
    segmentos_json JSONB,
    segmento_updated_at TIMESTAMPTZ,
    deadline_at TIMESTAMPTZ,
    deadline_source TEXT,
    deadline_checked_at TIMESTAMPTZ,
    deadline_raw TEXT,
    deadline_kind TEXT,
    deadline_reason TEXT,
    orgao_id INTEGER REFERENCES orgaos(id),
    itens_count INTEGER DEFAULT 0,
    itens_preview_json JSONB,
    itens_updated_at TIMESTAMPTZ,
    itens_status TEXT NOT NULL DEFAULT 'NOT_FETCHED' CHECK(itens_status IN ('NOT_FETCHED', 'FETCHING', 'COMPLETED', 'FAILED_TEMP', 'FAILED_AUTH', 'NOT_AVAILABLE', 'FAILED')),
    itens_last_error TEXT,
    itens_attempts INTEGER NOT NULL DEFAULT 0,
    itens_next_retry_at TIMESTAMPTZ,
    itens_last_fetch_at TIMESTAMPTZ,
    itens_lock_owner TEXT,
    itens_lock_until TIMESTAMPTZ,
    arquivos_status TEXT DEFAULT 'NOT_FETCHED' CHECK(arquivos_status IN ('NOT_FETCHED', 'FETCHING', 'COMPLETED', 'FAILED_TEMP', 'FAILED_AUTH', 'NOT_AVAILABLE', 'FAILED')),
    arquivos_count INTEGER DEFAULT 0,
    arquivos_updated_at TIMESTAMPTZ,
    arquivos_last_error TEXT,
    arquivos_preview_json JSONB,
    arquivos_attempts INTEGER DEFAULT 0,
    arquivos_next_retry_at TIMESTAMPTZ,
    arquivos_last_fetch_at TIMESTAMPTZ,
    arquivos_lock_owner TEXT,
    arquivos_lock_until TIMESTAMPTZ,
    segment_id TEXT REFERENCES segments(id) ON DELETE SET NULL,
    organization_id TEXT REFERENCES organizations(id) ON DELETE CASCADE
);

CREATE INDEX idx_contrat_uf ON contratacoes(uf);
CREATE INDEX idx_contrat_modalidade ON contratacoes(modalidade_codigo);
CREATE INDEX idx_contrat_enrichment ON contratacoes(enrichment_status);
CREATE INDEX idx_contrat_valid ON contratacoes(is_valid);
CREATE INDEX idx_contratacoes_created_at ON contratacoes(first_seen_at);
CREATE INDEX idx_contratacoes_valor_global ON contratacoes(valor_estimado_centavos);
CREATE INDEX idx_contratacoes_prazo_final ON contratacoes(deadline_at);
CREATE INDEX idx_contratacoes_segmento ON contratacoes(segmento_principal);
CREATE INDEX idx_contratacoes_orgao_id ON contratacoes(orgao_id);
CREATE INDEX idx_contratacoes_itens_status ON contratacoes(itens_status);
CREATE INDEX idx_contratacoes_itens_next_retry_at ON contratacoes(itens_next_retry_at);
CREATE INDEX idx_contratacoes_segment_id ON contratacoes(segment_id);
CREATE INDEX idx_contratacoes_organization_id ON contratacoes(organization_id);

CREATE TABLE contratacao_itens (
    id SERIAL PRIMARY KEY,
    pncp_id TEXT NOT NULL REFERENCES contratacoes(pncp_id) ON DELETE CASCADE,
    item_id TEXT, 
    item_hash TEXT NOT NULL, 
    
    numero_item INTEGER,
    descricao TEXT,
    quantidade NUMERIC,
    unidade TEXT,
    valor_unitario_centavos BIGINT,
    valor_total_centavos BIGINT,
    
    payload_json JSONB, 
    first_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    segmento_codigo TEXT,
    segmento_nome TEXT,
    segment_id TEXT REFERENCES segments(id) ON DELETE SET NULL,
    segment_score REAL,
    segment_evidence TEXT
);
CREATE UNIQUE INDEX idx_item_unique ON contratacao_itens(pncp_id, item_hash);

CREATE TABLE contratacao_partes (
    id SERIAL PRIMARY KEY,
    pncp_id TEXT NOT NULL REFERENCES contratacoes(pncp_id) ON DELETE CASCADE,
    papel TEXT NOT NULL, 
    cnpj TEXT,
    nome TEXT
);
CREATE UNIQUE INDEX idx_parte_unique ON contratacao_partes(pncp_id, papel, cnpj);

CREATE TABLE licitacao_arquivos (
    id SERIAL PRIMARY KEY,
    pncp_id TEXT NOT NULL REFERENCES contratacoes(pncp_id) ON DELETE CASCADE,
    doc_seq INTEGER NOT NULL,
    titulo TEXT,
    tipo_documento_id INTEGER,
    tipo_documento_nome TEXT,
    url TEXT,
    raw_json JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pncp_id, doc_seq)
);
CREATE INDEX idx_arq_pncp_id ON licitacao_arquivos(pncp_id);
CREATE INDEX idx_arq_pncp_id_doc_seq ON licitacao_arquivos(pncp_id, doc_seq);

CREATE TABLE licitacao_workflow (
    pncp_id TEXT NOT NULL REFERENCES contratacoes(pncp_id) ON DELETE CASCADE,
    organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('ACTIVE', 'IGNORED')),
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (pncp_id, organization_id)
);
CREATE INDEX idx_workflow_org ON licitacao_workflow(organization_id);
CREATE INDEX idx_workflow_status ON licitacao_workflow(status);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  status TEXT CHECK (status IN ('pending','running','done','error')) DEFAULT 'pending',
  processed INTEGER DEFAULT 0,
  errors INTEGER DEFAULT 0,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  organization_id TEXT REFERENCES organizations(id) ON DELETE CASCADE
);
CREATE INDEX idx_jobs_organization_id ON jobs(organization_id);

-- System tables
CREATE TABLE job_locks (
    job_name TEXT PRIMARY KEY,
    locked_by TEXT,
    locked_at TIMESTAMPTZ,
    locked_until TIMESTAMPTZ
);

CREATE TABLE staging_publicacao (
    id SERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    modalidade_code INTEGER,
    pncp_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    status TEXT DEFAULT 'NEW' CHECK(status IN ('NEW','PROCESSED','ERROR')),
    error TEXT
);
CREATE INDEX idx_staging_pub_pncp ON staging_publicacao(pncp_id);
CREATE INDEX idx_staging_pub_status ON staging_publicacao(status);

CREATE TABLE staging_detalhe (
    id SERIAL PRIMARY KEY,
    fetched_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    pncp_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    status TEXT DEFAULT 'NEW' CHECK(status IN ('NEW','PROCESSED','ERROR')),
    error TEXT
);
CREATE INDEX idx_staging_det_pncp ON staging_detalhe(pncp_id);

CREATE TABLE pncp_request_log (
    id SERIAL PRIMARY KEY,
    pncp_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ingest_runs (
    run_id TEXT PRIMARY KEY,
    window_start TIMESTAMPTZ, 
    window_end TIMESTAMPTZ,   
    params JSONB,       
    status TEXT CHECK(status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ingest_cursors (
    run_id TEXT PRIMARY KEY REFERENCES ingest_runs(run_id) ON DELETE CASCADE,
    cursor_state JSONB, 
    page_num INTEGER,
    last_success_at TIMESTAMPTZ
);
