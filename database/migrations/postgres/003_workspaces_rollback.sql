-- 003_workspaces_rollback.sql
-- MANUAL SAFETY NET. Never auto-executed.
-- Run only if you need to reverse the 003_workspaces migration.

BEGIN;

-- Drop new tables
DROP TABLE IF EXISTS migration_audit CASCADE;
DROP TABLE IF EXISTS workflows CASCADE;

-- Remove workspace_id from product tables
ALTER TABLE licitacao_workflow DROP CONSTRAINT IF EXISTS licitacao_workflow_pkey;
ALTER TABLE licitacao_workflow DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE licitacao_workflow ADD PRIMARY KEY (pncp_id, organization_id);

ALTER TABLE contratacoes DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE segments DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE segment_terms DROP COLUMN IF EXISTS workspace_id;
ALTER TABLE jobs DROP COLUMN IF EXISTS workspace_id;

-- Rename back
ALTER TABLE organization_memberships RENAME TO user_memberships;

-- Restore roles
UPDATE user_memberships SET role = 'OWNER' WHERE role = 'GERENTE';

-- Re-activate default orgs
UPDATE organizations SET is_active = TRUE WHERE name = 'Default Org';
UPDATE user_memberships SET is_active = TRUE
WHERE organization_id IN (SELECT id FROM organizations WHERE name = 'Default Org');

-- Drop constraint
ALTER TABLE user_memberships DROP CONSTRAINT IF EXISTS uq_org_membership_user_org;

-- Drop workspaces
DROP TABLE IF EXISTS workspaces CASCADE;

-- Drop added column
ALTER TABLE organizations DROP COLUMN IF EXISTS created_by_user_id;

COMMIT;
