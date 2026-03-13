import psycopg
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.api.deps import get_db, require_system_admin
import re

router = APIRouter()

def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    return re.sub(r'^-+|-+$', '', text)

class OrgCreateRequest(BaseModel):
    name: str
    slug: Optional[str] = None

class OrgUpdateRequest(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    is_active: Optional[bool] = None

@router.get("")
async def list_orgs(current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("""
        SELECT o.id, o.name, o.slug, o.is_active, o.created_at, o.updated_at,
               w.id as workspace_id,
               (SELECT COUNT(*) FROM organization_memberships m WHERE m.organization_id = o.id AND m.is_active = TRUE) as member_count
        FROM organizations o
        LEFT JOIN workspaces w ON w.organization_id = o.id AND w.type = 'organization'
        WHERE o.is_active = TRUE
        ORDER BY o.name ASC
    """)
    orgs = c.fetchall()
    return {"status": "success", "organizations": [dict(org) for org in orgs]}

@router.post("")
async def create_org(req: OrgCreateRequest, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    
    slug = slugify(req.slug or req.name)
    if not slug:
        raise HTTPException(status_code=400, detail="Nome inválido para gerar slug.")
        
    c.execute("SELECT id FROM organizations WHERE slug = %s", (slug,))
    if c.fetchone():
        raise HTTPException(status_code=400, detail=f"Slug '{slug}' já está em uso.")
    
    # Also check workspace slug uniqueness
    c.execute("SELECT id FROM workspaces WHERE slug = %s", (slug,))
    if c.fetchone():
        raise HTTPException(status_code=400, detail=f"Slug '{slug}' já está em uso por um workspace.")
        
    org_id = str(uuid.uuid4())
    workspace_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    try:
        # Create org
        c.execute("""
            INSERT INTO organizations (id, name, slug, is_active, created_by_user_id, created_at, updated_at)
            VALUES (%s, %s, %s, TRUE, %s, %s, %s)
        """, (org_id, req.name, slug, current_admin["id"], now, now))
        
        # Create org workspace atomically
        c.execute("""
            INSERT INTO workspaces (id, type, name, slug, organization_id, is_active, created_at, updated_at)
            VALUES (%s, 'organization', %s, %s, %s, TRUE, %s, %s)
        """, (workspace_id, req.name, slug, org_id, now, now))
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
        
    c.execute("""
        SELECT o.id, o.name, o.slug, o.is_active, o.created_at, o.updated_at, w.id as workspace_id
        FROM organizations o
        LEFT JOIN workspaces w ON w.organization_id = o.id AND w.type = 'organization'
        WHERE o.id = %s
    """, (org_id,))
    org = c.fetchone()
    return {"status": "success", "organization": dict(org)}

@router.get("/{org_id}")
async def get_org(org_id: str, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("""
        SELECT o.id, o.name, o.slug, o.is_active, o.created_at, o.updated_at, o.created_by_user_id, w.id as workspace_id
        FROM organizations o
        LEFT JOIN workspaces w ON w.organization_id = o.id AND w.type = 'organization'
        WHERE o.id = %s
    """, (org_id,))
    org = c.fetchone()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {"status": "success", "organization": dict(org)}

@router.patch("/{org_id}")
async def update_org(org_id: str, req: OrgUpdateRequest, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("SELECT * FROM organizations WHERE id = %s", (org_id,))
    org = c.fetchone()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
        
    new_name = req.name if req.name is not None else org['name']
    new_slug = org['slug']
    if req.slug is not None:
        new_slug = slugify(req.slug)
        if new_slug != org['slug']:
            c.execute("SELECT id FROM organizations WHERE slug = %s AND id != %s", (new_slug, org_id))
            if c.fetchone():
                raise HTTPException(status_code=400, detail=f"Slug '{new_slug}' já está em uso.")
                
    new_is_active = req.is_active if req.is_active is not None else org['is_active']
    now = datetime.utcnow().isoformat()
    
    c.execute("""
        UPDATE organizations 
        SET name = %s, slug = %s, is_active = %s, updated_at = %s
        WHERE id = %s
    """, (new_name, new_slug, bool(new_is_active), now, org_id))
    
    # Cascade deactivation to workspace
    if req.is_active is not None:
        c.execute("""
            UPDATE workspaces SET is_active = %s, updated_at = %s
            WHERE organization_id = %s AND type = 'organization'
        """, (bool(new_is_active), now, org_id))
    
    # Update workspace name/slug if changed
    if req.name is not None or req.slug is not None:
        c.execute("""
            UPDATE workspaces SET name = %s, slug = %s, updated_at = %s
            WHERE organization_id = %s AND type = 'organization'
        """, (new_name, new_slug, now, org_id))
    
    db.commit()
    
    c.execute("SELECT id, name, slug, is_active, created_at, updated_at FROM organizations WHERE id = %s", (org_id,))
    updated_org = c.fetchone()
    return {"status": "success", "organization": dict(updated_org)}

class SetManagerRequest(BaseModel):
    email: str

@router.post("/{org_id}/set-manager")
async def set_manager(org_id: str, req: SetManagerRequest, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("SELECT id FROM organizations WHERE id = %s AND is_active = TRUE", (org_id,))
    if not c.fetchone():
        raise HTTPException(status_code=404, detail="Organização não encontrada.")

    email_lower = req.email.strip().lower()
    c.execute("SELECT id, email FROM users WHERE email = %s AND is_active = TRUE", (email_lower,))
    target_user = c.fetchone()
    if not target_user:
        raise HTTPException(status_code=404, detail=f"Usuário '{email_lower}' não encontrado.")

    c.execute(
        "SELECT id, role, is_active FROM organization_memberships WHERE user_id = %s AND organization_id = %s",
        (target_user["id"], org_id)
    )
    existing = c.fetchone()
    now = datetime.utcnow().isoformat()

    if existing:
        c.execute(
            "UPDATE organization_memberships SET role = 'GERENTE', is_active = TRUE, updated_at = %s WHERE id = %s",
            (now, existing["id"])
        )
    else:
        membership_id = str(uuid.uuid4())
        c.execute("""
            INSERT INTO organization_memberships (id, user_id, organization_id, role, created_at, updated_at, is_active, invited_by_user_id)
            VALUES (%s, %s, %s, 'GERENTE', %s, %s, TRUE, %s)
        """, (membership_id, target_user["id"], org_id, now, now, current_admin["id"]))

    db.commit()
    return {"status": "success", "message": f"Usuário '{email_lower}' agora é GERENTE desta organização."}


@router.get("/{org_id}/members")
async def list_org_members_admin(org_id: str, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("""
        SELECT m.id, m.user_id, u.email, m.role, m.created_at, m.is_active
        FROM organization_memberships m
        JOIN users u ON u.id = m.user_id
        WHERE m.organization_id = %s AND m.is_active = TRUE
        ORDER BY m.created_at ASC
    """, (org_id,))
    members = []
    for row in c.fetchall():
        members.append({
            "id": row["id"],
            "user_id": row["user_id"],
            "email": row["email"],
            "name": row["email"],
            "role": row["role"],
            "created_at": row["created_at"]
        })
    return {"status": "success", "members": members}


@router.delete("/{org_id}")
async def delete_org(org_id: str, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("SELECT * FROM organizations WHERE id = %s", (org_id,))
    org = c.fetchone()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
        
    now = datetime.utcnow().isoformat()
    
    try:
        # Soft delete org
        c.execute("UPDATE organizations SET is_active = FALSE, updated_at = %s WHERE id = %s", (now, org_id))
        
        # Cascade: deactivate workspace
        c.execute("UPDATE workspaces SET is_active = FALSE, updated_at = %s WHERE organization_id = %s AND type = 'organization'", (now, org_id))
        
        # Cascade: deactivate memberships
        c.execute("UPDATE organization_memberships SET is_active = FALSE, updated_at = %s WHERE organization_id = %s", (now, org_id))
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"status": "success", "message": "Organization deactivated successfully"}
