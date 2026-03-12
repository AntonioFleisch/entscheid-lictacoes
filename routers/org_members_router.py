import psycopg
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, EmailStr
from typing import Optional

from auth_deps import get_db, get_current_user

router = APIRouter()


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: Optional[str] = "USUARIO"


class UpdateMemberRoleRequest(BaseModel):
    role: str


# --- Helper: verify caller has manager-level access to this org ---
def _get_org_membership(org_id: str, current_user: dict, db: psycopg.Connection) -> dict:
    """Verify the caller has GERENTE access to the given org."""
    c = db.cursor()

    # System admin always has access
    if current_user.get("is_system_admin"):
        c.execute("SELECT id FROM organizations WHERE id = %s AND is_active = TRUE", (org_id,))
        if not c.fetchone():
            raise HTTPException(status_code=404, detail="Organização não encontrada.")
        return {"user_id": current_user["id"], "organization_id": org_id, "role": "ADMIN_GLOBAL", "is_active": True}

    # Check real membership
    c.execute(
        "SELECT * FROM organization_memberships WHERE user_id = %s AND organization_id = %s AND is_active = TRUE",
        (current_user["id"], org_id)
    )
    membership = c.fetchone()
    if not membership:
        raise HTTPException(status_code=403, detail="Você não tem acesso a esta organização.")
    if membership["role"] not in ("GERENTE",):
        raise HTTPException(status_code=403, detail="Permissão insuficiente. Apenas gerentes podem gerenciar membros.")

    return membership


@router.get("")
async def list_members(
    org_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: psycopg.Connection = Depends(get_db)
):
    _get_org_membership(org_id, current_user, db)
    c = db.cursor()
    c.execute("""
        SELECT m.id, m.user_id, u.email, m.role, m.created_at, m.is_active, m.invited_by_user_id
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
            "created_at": row["created_at"],
            "invited_by_user_id": row["invited_by_user_id"]
        })
    return {"status": "success", "members": members}


@router.post("")
async def add_member(
    req: AddMemberRequest,
    org_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: psycopg.Connection = Depends(get_db)
):
    caller_membership = _get_org_membership(org_id, current_user, db)
    c = db.cursor()

    # GERENTE can add both GERENTE and USUARIO; system admin always can
    allowed_roles = ["USUARIO", "GERENTE"]
    
    target_role = req.role.upper() if req.role else "USUARIO"
    if target_role not in allowed_roles:
        raise HTTPException(status_code=403, detail=f"Papel '{target_role}' inválido. Use GERENTE ou USUARIO.")

    # Find target user by email
    email_lower = req.email.lower()
    c.execute("SELECT id, email FROM users WHERE email = %s AND is_active = TRUE", (email_lower,))
    target_user = c.fetchone()
    if not target_user:
        raise HTTPException(status_code=404, detail=f"Usuário '{email_lower}' não encontrado no sistema.")

    # Check if already a member
    c.execute(
        "SELECT id, is_active FROM organization_memberships WHERE user_id = %s AND organization_id = %s",
        (target_user["id"], org_id)
    )
    existing = c.fetchone()
    if existing:
        if existing["is_active"]:
            raise HTTPException(status_code=400, detail="Este usuário já é membro desta organização.")
        else:
            # Reactivate
            now = datetime.utcnow().isoformat()
            c.execute(
                "UPDATE organization_memberships SET is_active = TRUE, role = %s, invited_by_user_id = %s, updated_at = %s WHERE id = %s",
                (target_role, current_user["id"], now, existing["id"])
            )
            db.commit()
            return {"status": "success", "message": f"Membro '{email_lower}' reativado com papel '{target_role}'."}

    # Create new membership
    membership_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    c.execute("""
        INSERT INTO organization_memberships (id, user_id, organization_id, role, created_at, updated_at, is_active, invited_by_user_id)
        VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
    """, (membership_id, target_user["id"], org_id, target_role, now, now, current_user["id"]))
    db.commit()

    return {
        "status": "success",
        "message": f"Membro '{email_lower}' adicionado com papel '{target_role}'.",
        "member": {
            "id": membership_id,
            "user_id": target_user["id"],
            "email": target_user["email"],
            "name": target_user["email"],
            "role": target_role,
            "created_at": now
        }
    }


@router.delete("/{membership_id}")
async def remove_member(
    membership_id: str,
    org_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: psycopg.Connection = Depends(get_db)
):
    caller_membership = _get_org_membership(org_id, current_user, db)
    c = db.cursor()

    # Find the membership to remove
    c.execute(
        "SELECT * FROM organization_memberships WHERE id = %s AND organization_id = %s AND is_active = TRUE",
        (membership_id, org_id)
    )
    target = c.fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="Membro não encontrado.")

    # Cannot remove yourself
    if target["user_id"] == current_user["id"]:
        raise HTTPException(status_code=400, detail="Você não pode remover a si mesmo da organização.")

    # GERENTE can only remove USUARIO
    if caller_membership["role"] == "GERENTE" and target["role"] not in ("USUARIO",):
        raise HTTPException(status_code=403, detail="Gerentes só podem remover membros com papel 'USUARIO'.")

    # Soft delete
    c.execute("UPDATE organization_memberships SET is_active = FALSE, updated_at = %s WHERE id = %s", (datetime.utcnow().isoformat(), membership_id))
    db.commit()

    return {"status": "success", "message": "Membro removido da organização."}
