-- 003_workspaces.sql
-- Replaces organization-default architecture with workspace-based model.
-- Transactional: entire migration runs in a single transaction.

BEGIN;

-- ============================================================================
-- STEP 1: Create workspaces table
-- ============================================================================
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL CHECK (type IN ('personal', 'organization')),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    owner_user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
    organization_id TEXT REFERENCES organizations(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_workspace_owner CHECK (
        (type = 'personal' AND owner_user_id IS NOT NULL AND organization_id IS NULL)
        OR
        (type = 'organization' AND organization_id IS NOT NULL AND owner_user_id IS NULL)
    )
);

-- Uniqueness: 1 personal workspace per user, 1 org workspace per org
CREATE UNIQUE INDEX idx_ws_personal_unique ON workspaces(owner_user_id) WHERE type = 'personal';
CREATE UNIQUE INDEX idx_ws_org_unique ON workspaces(organization_id) WHERE type = 'organization';
CREATE INDEX idx_ws_type ON workspaces(type);
CREATE INDEX idx_ws_slug ON workspaces(slug);

-- ============================================================================
-- STEP 2: Add created_by_user_id to organizations (if not exists)
-- ============================================================================
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS created_by_user_id TEXT REFERENCES users(id);

-- ============================================================================
-- STEP 3: Rename user_memberships → organization_memberships + normalize roles
-- ============================================================================
ALTER TABLE user_memberships RENAME TO organization_memberships;

-- Normalize roles: OWNER and ADMIN become GERENTE
UPDATE organization_memberships SET role = 'GERENTE' WHERE role IN ('OWNER', 'ADMIN');

-- Ensure UNIQUE(user_id, organization_id) — drop dupes first if any
DELETE FROM organization_memberships a
USING organization_memberships b
WHERE a.id > b.id
  AND a.user_id = b.user_id
  AND a.organization_id = b.organization_id;

-- Add unique constraint
ALTER TABLE organization_memberships
    ADD CONSTRAINT uq_org_membership_user_org UNIQUE (user_id, organization_id);

-- ============================================================================
-- STEP 4: Detect default orgs (created automatically at registration)
-- ============================================================================
CREATE TEMP TABLE default_org_ids AS
SELECT o.id AS org_id, m.user_id
FROM organizations o
JOIN organization_memberships m ON m.organization_id = o.id AND m.role = 'GERENTE'
WHERE o.name = 'Default Org'
GROUP BY o.id, m.user_id
HAVING COUNT(*) = 1;

-- ============================================================================
-- STEP 5: Create 1 personal workspace per user
-- ============================================================================
INSERT INTO workspaces (id, type, name, slug, owner_user_id, created_at, updated_at)
SELECT gen_random_uuid()::text, 'personal', 'Meu Espaço', 'personal-' || u.id, u.id, NOW(), NOW()
FROM users u;

-- ============================================================================
-- STEP 6: Create org workspaces for REAL orgs only
-- ============================================================================
INSERT INTO workspaces (id, type, name, slug, organization_id, created_at, updated_at)
SELECT gen_random_uuid()::text, 'organization', o.name, o.slug, o.id, NOW(), NOW()
FROM organizations o
WHERE o.id NOT IN (SELECT org_id FROM default_org_ids)
  AND o.is_active = TRUE;

-- ============================================================================
-- STEP 7: Add workspace_id to product tables (nullable first)
-- ============================================================================
ALTER TABLE contratacoes ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id);
ALTER TABLE segments ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id);
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id);

-- licitacao_workflow: drop old PK, add workspace_id
ALTER TABLE licitacao_workflow DROP CONSTRAINT IF EXISTS licitacao_workflow_pkey;
ALTER TABLE licitacao_workflow ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id);

-- ============================================================================
-- STEP 8: Backfill workspace_id from default orgs → personal workspace
-- ============================================================================

-- contratacoes: default org data → personal workspace
UPDATE contratacoes c SET workspace_id = w.id
FROM default_org_ids d
JOIN workspaces w ON w.owner_user_id = d.user_id AND w.type = 'personal'
WHERE c.organization_id = d.org_id AND c.workspace_id IS NULL;

-- contratacoes: real org data → org workspace
UPDATE contratacoes c SET workspace_id = w.id
FROM workspaces w
WHERE w.organization_id = c.organization_id AND w.type = 'organization'
  AND c.workspace_id IS NULL AND c.organization_id IS NOT NULL;

-- contratacoes: orphan data (no org) → NULL workspace (handled below)
-- For records with NULL organization_id, assign to the first system admin's personal workspace
-- or leave NULL and let the sanity audit catch them.

-- segments: default org → personal workspace
UPDATE segments s SET workspace_id = w.id
FROM default_org_ids d
JOIN workspaces w ON w.owner_user_id = d.user_id AND w.type = 'personal'
WHERE s.organization_id = d.org_id AND s.workspace_id IS NULL;

-- segments: real org → org workspace
UPDATE segments s SET workspace_id = w.id
FROM workspaces w
WHERE w.organization_id = s.organization_id AND w.type = 'organization'
  AND s.workspace_id IS NULL AND s.organization_id IS NOT NULL;

-- segment_terms: inherit workspace from parent segment
ALTER TABLE segment_terms ADD COLUMN IF NOT EXISTS workspace_id TEXT REFERENCES workspaces(id);
UPDATE segment_terms st SET workspace_id = s.workspace_id
FROM segments s WHERE st.segment_id = s.id AND st.workspace_id IS NULL;

-- jobs: default org → personal workspace
UPDATE jobs j SET workspace_id = w.id
FROM default_org_ids d
JOIN workspaces w ON w.owner_user_id = d.user_id AND w.type = 'personal'
WHERE j.organization_id = d.org_id AND j.workspace_id IS NULL;

-- jobs: real org → org workspace
UPDATE jobs j SET workspace_id = w.id
FROM workspaces w
WHERE w.organization_id = j.organization_id AND w.type = 'organization'
  AND j.workspace_id IS NULL AND j.organization_id IS NOT NULL;

-- licitacao_workflow: default org → personal workspace
UPDATE licitacao_workflow lw SET workspace_id = w.id
FROM default_org_ids d
JOIN workspaces w ON w.owner_user_id = d.user_id AND w.type = 'personal'
WHERE lw.organization_id = d.org_id AND lw.workspace_id IS NULL;

-- licitacao_workflow: real org → org workspace
UPDATE licitacao_workflow lw SET workspace_id = w.id
FROM workspaces w
WHERE w.organization_id = lw.organization_id AND w.type = 'organization'
  AND lw.workspace_id IS NULL AND lw.organization_id IS NOT NULL;

-- ============================================================================
-- STEP 9: Set NOT NULL where appropriate + new PKs/indexes
-- ============================================================================

-- Delete orphans that couldn't be mapped (safety)
DELETE FROM licitacao_workflow WHERE workspace_id IS NULL;

-- Re-create PK for licitacao_workflow
ALTER TABLE licitacao_workflow ADD PRIMARY KEY (pncp_id, workspace_id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_contratacoes_workspace_id ON contratacoes(workspace_id);
CREATE INDEX IF NOT EXISTS idx_segments_workspace_id ON segments(workspace_id);
CREATE INDEX IF NOT EXISTS idx_jobs_workspace_id ON jobs(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workflow_workspace ON licitacao_workflow(workspace_id);

-- ============================================================================
-- STEP 10: Deactivate default orgs and their memberships
-- ============================================================================
UPDATE organizations SET is_active = FALSE, updated_at = NOW()
WHERE id IN (SELECT org_id FROM default_org_ids);

UPDATE organization_memberships SET is_active = FALSE, updated_at = NOW()
WHERE organization_id IN (SELECT org_id FROM default_org_ids);

-- ============================================================================
-- STEP 11: Create workflows base table
-- ============================================================================
CREATE TABLE IF NOT EXISTS workflows (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    config_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_workflows_workspace_id ON workflows(workspace_id);

-- ============================================================================
-- STEP 12: Post-migration sanity audit
-- ============================================================================
CREATE TABLE IF NOT EXISTS migration_audit (
    id SERIAL PRIMARY KEY,
    check_name TEXT NOT NULL,
    result_count INTEGER,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO migration_audit (check_name, result_count, details)
SELECT 'users_without_personal_ws', COUNT(*),
  CASE WHEN COUNT(*) > 0 THEN jsonb_agg(u.id) ELSE '[]'::jsonb END
FROM users u
LEFT JOIN workspaces w ON w.owner_user_id = u.id AND w.type = 'personal'
WHERE w.id IS NULL;

INSERT INTO migration_audit (check_name, result_count, details)
SELECT 'active_orgs_without_workspace', COUNT(*),
  CASE WHEN COUNT(*) > 0 THEN jsonb_agg(o.id) ELSE '[]'::jsonb END
FROM organizations o
LEFT JOIN workspaces w ON w.organization_id = o.id AND w.type = 'organization'
WHERE o.is_active = TRUE AND w.id IS NULL
  AND o.id NOT IN (SELECT org_id FROM default_org_ids);

INSERT INTO migration_audit (check_name, result_count, details)
SELECT 'contratacoes_without_workspace', COUNT(*), NULL
FROM contratacoes WHERE workspace_id IS NULL;

INSERT INTO migration_audit (check_name, result_count, details)
SELECT 'orphan_memberships', COUNT(*), NULL
FROM organization_memberships om
LEFT JOIN organizations o ON o.id = om.organization_id
WHERE o.id IS NULL OR o.is_active = FALSE;

-- Cleanup temp table
DROP TABLE IF EXISTS default_org_ids;

COMMIT;
