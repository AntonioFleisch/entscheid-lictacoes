import psycopg
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from auth_deps import get_db, require_system_admin

router = APIRouter()


class UserUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    is_system_admin: Optional[bool] = None


@router.get("")
async def list_users(current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("""
        SELECT u.id, u.email, u.is_active, u.is_system_admin, u.created_at, u.last_login_at,
               w.id as personal_workspace_id,
               (SELECT COUNT(*) FROM organization_memberships m WHERE m.user_id = u.id AND m.is_active = TRUE) as membership_count
        FROM users u
        LEFT JOIN workspaces w ON w.owner_user_id = u.id AND w.type = 'personal'
        ORDER BY u.created_at DESC
    """)
    users = [dict(row) for row in c.fetchall()]
    return {"status": "success", "users": users}


@router.get("/{user_id}")
async def get_user(user_id: str, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("SELECT id, email, is_active, is_system_admin, is_email_verified, created_at, updated_at, last_login_at FROM users WHERE id = %s", (user_id,))
    user = c.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    # Get personal workspace
    c.execute("SELECT id, slug, name FROM workspaces WHERE owner_user_id = %s AND type = 'personal'", (user_id,))
    personal_ws = c.fetchone()
    
    # Get org memberships
    c.execute("""
        SELECT m.id as membership_id, m.organization_id, o.name as organization_name, o.slug as organization_slug, 
               m.role, m.is_active, m.created_at, w.id as workspace_id
        FROM organization_memberships m
        JOIN organizations o ON o.id = m.organization_id
        LEFT JOIN workspaces w ON w.organization_id = o.id AND w.type = 'organization'
        WHERE m.user_id = %s
        ORDER BY m.created_at ASC
    """, (user_id,))
    memberships = [dict(row) for row in c.fetchall()]
    
    return {
        "status": "success",
        "user": dict(user),
        "personal_workspace": dict(personal_ws) if personal_ws else None,
        "memberships": memberships
    }


@router.patch("/{user_id}")
async def update_user(user_id: str, req: UserUpdateRequest, current_admin: dict = Depends(require_system_admin), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = c.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    
    # Prevent self-demotion from system admin
    if user_id == current_admin["id"] and req.is_system_admin is False:
        raise HTTPException(status_code=400, detail="Você não pode remover seus próprios privilégios de administrador.")
    
    now = datetime.utcnow().isoformat()
    
    if req.is_active is not None:
        c.execute("UPDATE users SET is_active = %s, updated_at = %s WHERE id = %s", (req.is_active, now, user_id))
        
    if req.is_system_admin is not None:
        c.execute("UPDATE users SET is_system_admin = %s, updated_at = %s WHERE id = %s", (req.is_system_admin, now, user_id))
    
    db.commit()
    
    c.execute("SELECT id, email, is_active, is_system_admin, created_at, updated_at FROM users WHERE id = %s", (user_id,))
    updated = c.fetchone()
    return {"status": "success", "user": dict(updated)}
