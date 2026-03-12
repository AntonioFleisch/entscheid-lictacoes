import psycopg
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
import auth_security
from database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_token_from_header_or_cookie(request: Request, token: str = Depends(oauth2_scheme)) -> Optional[str]:
    if token:
        return token
    return None


async def get_current_user(token: str = Depends(get_token_from_header_or_cookie), db: psycopg.Connection = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail={"code": "NOT_AUTHENTICATED", "message": "Could not validate credentials"},
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    payload = auth_security.decode_access_token(token)
    if payload is None:
        raise credentials_exception

    user_id: str = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    c = db.cursor()
    c.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = c.fetchone()
    if user is None:
        raise credentials_exception

    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User is inactive")

    return user


async def get_current_workspace(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: psycopg.Connection = Depends(get_db)
):
    """
    Resolves the active workspace from X-Workspace-Id header.
    Fallback: if no header provided, auto-selects the user's personal workspace.

    Returns a dict with workspace info + access context.
    """
    ws_id = request.headers.get("X-Workspace-Id") or request.headers.get("X-Org-Id")
    c = db.cursor()

    if not ws_id:
        # Fallback: personal workspace
        c.execute(
            "SELECT * FROM workspaces WHERE owner_user_id = %s AND type = 'personal' LIMIT 1",
            (current_user["id"],)
        )
        ws = c.fetchone()
        if not ws:
            raise HTTPException(status_code=500, detail="Workspace pessoal não encontrado. Contate o administrador.")
        return {
            "workspace": ws,
            "workspace_id": ws["id"],
            "workspace_type": ws["type"],
            "role": None,  # Personal workspace has no org role
            "user": current_user
        }

    # Explicit workspace requested (support both direct ID and legacy Organization ID)
    c.execute(
        "SELECT * FROM workspaces WHERE (id = %s OR organization_id = %s) AND is_active = TRUE",
        (ws_id, ws_id)
    )
    ws = c.fetchone()
    if not ws:
        # Diagnostic log
        import logging
        logger = logging.getLogger("auth_logger")
        logger.warning(f"Workspace not found for ID: {ws_id}")
        raise HTTPException(status_code=404, detail="Workspace não encontrado ou inativo.")

    # Authorization check
    if ws["type"] == "personal":
        if ws["owner_user_id"] != current_user["id"] and not current_user.get("is_system_admin"):
            raise HTTPException(status_code=403, detail="Você não tem acesso a este workspace.")
        return {
            "workspace": ws,
            "workspace_id": ws["id"],
            "workspace_type": "personal",
            "role": None,
            "user": current_user
        }

    elif ws["type"] == "organization":
        # System admin always has access
        if current_user.get("is_system_admin"):
            return {
                "workspace": ws,
                "workspace_id": ws["id"],
                "workspace_type": "organization",
                "organization_id": ws["organization_id"],
                "role": "ADMIN_GLOBAL",
                "user": current_user
            }

        # Check org membership
        c.execute(
            "SELECT role FROM organization_memberships WHERE user_id = %s AND organization_id = %s AND is_active = TRUE",
            (current_user["id"], ws["organization_id"])
        )
        membership = c.fetchone()
        if not membership:
            raise HTTPException(status_code=403, detail="Você não tem acesso a esta organização.")

        return {
            "workspace": ws,
            "workspace_id": ws["id"],
            "workspace_type": "organization",
            "organization_id": ws["organization_id"],
            "role": membership["role"],
            "user": current_user
        }

    raise HTTPException(status_code=500, detail="Tipo de workspace desconhecido.")


async def require_system_admin(current_user: dict = Depends(get_current_user)):
    """Requires the user to be a global system administrator."""
    if not current_user.get("is_system_admin"):
        raise HTTPException(status_code=403, detail="Acesso negado: requer privilégios de administrador do sistema.")
    return current_user


def require_org_roles(allowed_roles: list[str]):
    """
    Dependency factory: checks that the current workspace is organizational
    and the user has one of the allowed roles (GERENTE, USUARIO).
    System admins always pass.
    """
    async def checker(ws_context: dict = Depends(get_current_workspace)):
        user = ws_context["user"]
        if user.get("is_system_admin"):
            return ws_context

        if ws_context["workspace_type"] != "organization":
            raise HTTPException(status_code=400, detail="Esta ação requer um workspace organizacional.")

        if ws_context.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Permissão insuficiente nesta organização.")

        return ws_context
    return checker


async def require_workspace_access(ws_context: dict = Depends(get_current_workspace)):
    """
    Lightweight dependency: just ensures the user has access to the workspace.
    Already validated by get_current_workspace, so this is essentially a pass-through
    that makes intent explicit in route definitions.
    """
    return ws_context
