import psycopg
import uuid
import os
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.core.security import hash_password, verify_password, validate_password_policy, create_access_token
from app.api.deps import get_db, get_current_user
import secrets
from app.services.auth.password_reset import create_reset_token, validate_reset_token, consume_reset_token
from app.services.email.service import send_email

router = APIRouter()

AUTH_ALLOW_REGISTER = os.getenv("AUTH_ALLOW_REGISTER", "true").lower() == "true"
AUTH_REFRESH_TOKEN_DAYS = int(os.getenv("AUTH_REFRESH_TOKEN_DAYS", "14"))
AUTH_ACCESS_TOKEN_MINUTES = int(os.getenv("AUTH_ACCESS_TOKEN_MINUTES", "30"))

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

# Helper for rate limit
def check_rate_limit(db: psycopg.Connection, email: str, ip_address: str):
    c = db.cursor()
    c.execute("""
        SELECT COUNT(*) as cnt FROM auth_events 
        WHERE event_type = 'LOGIN_FAIL' 
          AND created_at >= %s
          AND (email = %s OR ip_address = %s)
    """, (datetime.utcnow() - timedelta(minutes=10), email, ip_address))
    
    count = c.fetchone()["cnt"]
    if count >= 5:
        return False
    return True

def log_auth_event(db: psycopg.Connection, user_id: Optional[str], email: Optional[str], event_type: str, request: Request, meta: Optional[dict] = None):
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", None)
    c = db.cursor()
    c.execute("""
        INSERT INTO auth_events (id, user_id, email, event_type, created_at, ip_address, user_agent, meta_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (str(uuid.uuid4()), user_id, email, event_type, datetime.utcnow(), ip_address, user_agent, json.dumps(meta) if meta else None))
    db.commit()

@router.post("/register")
async def register(req: RegisterRequest, db: psycopg.Connection = Depends(get_db)):
    try:
        if not AUTH_ALLOW_REGISTER:
            raise HTTPException(status_code=403, detail="Registration is disabled")
            
        if not validate_password_policy(req.password):
            raise HTTPException(status_code=400, detail="Password must be at least 10 characters and contain at least 1 letter and 1 number.")
            
        email_lower = req.email.lower()
        c = db.cursor()
        
        # Check if user exists
        c.execute("SELECT id FROM users WHERE email = %s", (email_lower,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="User already exists")
            
        user_id = str(uuid.uuid4())
        workspace_id = str(uuid.uuid4())
        
        pwd_hash = hash_password(req.password)
        now = datetime.utcnow()
        
        try:
            # Create user
            c.execute("""
                INSERT INTO users (id, email, password_hash, is_active, is_email_verified, created_at, updated_at)
                VALUES (%s, %s, %s, TRUE, FALSE, %s, %s)
            """, (user_id, email_lower, pwd_hash, now, now))
            
            # Create personal workspace (NO default org)
            ws_slug = f"personal-{user_id}"
            c.execute("""
                INSERT INTO workspaces (id, type, name, slug, owner_user_id, created_at, updated_at)
                VALUES (%s, 'personal', 'Meu Espaço', %s, %s, %s, %s)
            """, (workspace_id, ws_slug, user_id, now, now))
            
            db.commit()
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to create user: {str(e)}")
            
        return {"status": "success", "message": "User registered successfully."}
    except HTTPException:
        raise
    except Exception as exc:
        import traceback
        with open("err.txt", "w") as f:
            f.write(traceback.format_exc())
            f.write(str(exc))
        raise HTTPException(status_code=500, detail=f"CRITICAL: {str(exc)}")

@router.post("/login")
async def login(req: LoginRequest, response: Response, request: Request, db: psycopg.Connection = Depends(get_db)):
    email_lower = req.email.lower()
    ip_address = request.client.host if request.client else ""
    
    if not check_rate_limit(db, email_lower, ip_address):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Please try again later.")
        
    c = db.cursor()
    c.execute("SELECT * FROM users WHERE email = %s", (email_lower,))
    user = c.fetchone()
    
    if not user or not verify_password(req.password, user["password_hash"]):
        log_auth_event(db, user["id"] if user else None, email_lower, "LOGIN_FAIL", request)
        raise HTTPException(status_code=401, detail="Invalid credentials")
        
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User account is inactive")
        
    # Check for ROOT_ADMIN_EMAIL
    root_admin_email = os.getenv("ROOT_ADMIN_EMAIL", "").lower()
    if root_admin_email and email_lower == root_admin_email and not user.get("is_system_admin"):
        c.execute("UPDATE users SET is_system_admin = TRUE WHERE id = %s", (user["id"],))
        db.commit()
        c.execute("SELECT * FROM users WHERE email = %s", (email_lower,))
        user = c.fetchone()

    # Create tokens — NO org in JWT 
    access_token = create_access_token({"sub": user["id"], "email": email_lower})
    refresh_random = secrets.token_urlsafe(32)
    refresh_token = f"{user['id']}:{refresh_random}"
    refresh_hash = hash_password(refresh_token)
    
    now = datetime.utcnow()
    expires_at = now + timedelta(days=AUTH_REFRESH_TOKEN_DAYS)
    
    try:
        c.execute("""
            INSERT INTO refresh_tokens (id, user_id, token_hash, created_at, expires_at, revoked_at, user_agent, ip_address)
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s)
        """, (str(uuid.uuid4()), user["id"], refresh_hash, now.isoformat(), expires_at.isoformat(), 
              request.headers.get("user-agent"), ip_address))
              
        c.execute("UPDATE users SET last_login_at = %s WHERE id = %s", (now.isoformat(), user["id"]))
        log_auth_event(db, user["id"], email_lower, "LOGIN_SUCCESS", request)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create session")

    # Set Refresh Token Cookie
    secure_cookie = os.getenv("ENV", "production") == "production"
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
        max_age=AUTH_REFRESH_TOKEN_DAYS * 24 * 60 * 60
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/refresh")
async def refresh(request: Request, response: Response, db: psycopg.Connection = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token provided")
        
    c = db.cursor()
    
    parts = refresh_token.split(":")
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="Invalid refresh token format")
        
    user_id_str = parts[0]
    
    c.execute("SELECT * FROM refresh_tokens WHERE user_id = %s AND revoked_at IS NULL AND expires_at > %s", (user_id_str, datetime.utcnow().isoformat()))
    valid_tokens = c.fetchall()
    
    matched_token = None
    for rt in valid_tokens:
        if verify_password(refresh_token, rt["token_hash"]):
            matched_token = rt
            break
            
    if not matched_token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        
    # Get user
    c.execute("SELECT * FROM users WHERE id = %s", (user_id_str,))
    user = c.fetchone()
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=403, detail="User inactive")

    # Rotate refresh token
    new_refresh_random = secrets.token_urlsafe(32)
    new_refresh_token = f"{user['id']}:{new_refresh_random}"
    new_refresh_hash = hash_password(new_refresh_token)
    now = datetime.utcnow()
    expires_at = now + timedelta(days=AUTH_REFRESH_TOKEN_DAYS)
    
    try:
        c.execute("UPDATE refresh_tokens SET revoked_at = %s WHERE id = %s", (now.isoformat(), matched_token["id"]))
        c.execute("""
            INSERT INTO refresh_tokens (id, user_id, token_hash, created_at, expires_at, revoked_at, user_agent, ip_address)
            VALUES (%s, %s, %s, %s, %s, NULL, %s, %s)
        """, (str(uuid.uuid4()), user["id"], new_refresh_hash, now.isoformat(), expires_at.isoformat(), 
              request.headers.get("user-agent"), request.client.host if request.client else ""))
        log_auth_event(db, user["id"], user["email"], "REFRESH", request)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not rotate refresh token")

    # NO org in JWT
    access_token = create_access_token({"sub": user["id"], "email": user["email"]})
    
    secure_cookie = os.getenv("ENV", "production") == "production"
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
        max_age=AUTH_REFRESH_TOKEN_DAYS * 24 * 60 * 60
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
async def logout(request: Request, response: Response, db: psycopg.Connection = Depends(get_db)):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        parts = refresh_token.split(":")
        if len(parts) == 2:
            user_id_str = parts[0]
            c = db.cursor()
            c.execute("SELECT * FROM refresh_tokens WHERE user_id = %s AND revoked_at IS NULL", (user_id_str,))
            valid_tokens = c.fetchall()
            for rt in valid_tokens:
                if verify_password(refresh_token, rt["token_hash"]):
                    c.execute("UPDATE refresh_tokens SET revoked_at = %s WHERE id = %s", (datetime.utcnow().isoformat(), rt["id"]))
                    log_auth_event(db, user_id_str, None, "LOGOUT", request)
                    db.commit()
                    break
                    
    response.delete_cookie("refresh_token", path="/")
    return {"status": "success"}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user), db: psycopg.Connection = Depends(get_db)):
    c = db.cursor()
    
    # 1. Get personal workspace
    c.execute(
        "SELECT id, slug, name FROM workspaces WHERE owner_user_id = %s AND type = 'personal' LIMIT 1",
        (current_user["id"],)
    )
    personal_ws = c.fetchone()
    
    # 2. Get org workspaces accessible to this user
    org_workspaces = []
    
    if current_user.get("is_system_admin"):
        # System admin sees all active org workspaces
        c.execute("""
            SELECT w.id as workspace_id, w.organization_id, o.name as organization_name, o.slug as organization_slug
            FROM workspaces w
            JOIN organizations o ON o.id = w.organization_id
            WHERE w.type = 'organization' AND w.is_active = TRUE AND o.is_active = TRUE
            ORDER BY o.name ASC
        """)
        for r in c.fetchall():
            org_workspaces.append({
                "workspace_id": r["workspace_id"],
                "organization_id": r["organization_id"],
                "organization_name": r["organization_name"],
                "organization_slug": r["organization_slug"],
                "role": "ADMIN_GLOBAL"
            })
    else:
        # Normal user: only orgs they belong to
        c.execute("""
            SELECT w.id as workspace_id, w.organization_id, o.name as organization_name, o.slug as organization_slug, m.role
            FROM organization_memberships m
            JOIN organizations o ON o.id = m.organization_id
            JOIN workspaces w ON w.organization_id = o.id AND w.type = 'organization'
            WHERE m.user_id = %s AND m.is_active = TRUE AND o.is_active = TRUE AND w.is_active = TRUE
            ORDER BY o.name ASC
        """, (current_user["id"],))
        for r in c.fetchall():
            org_workspaces.append({
                "workspace_id": r["workspace_id"],
                "organization_id": r["organization_id"],
                "organization_name": r["organization_name"],
                "organization_slug": r["organization_slug"],
                "role": r["role"]
            })
    
    return {
        "user": {
            "id": current_user["id"],
            "email": current_user["email"],
            "is_system_admin": bool(current_user.get("is_system_admin"))
        },
        "personal_workspace": {
            "id": personal_ws["id"] if personal_ws else None,
            "slug": personal_ws["slug"] if personal_ws else None,
            "name": personal_ws["name"] if personal_ws else None,
        } if personal_ws else None,
        "organization_workspaces": org_workspaces
    }

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request, db: psycopg.Connection = Depends(get_db)):
    email_lower = req.email.lower()
    ip_address = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")
    
    c = db.cursor()
    c.execute("""
        SELECT COUNT(*) as cnt FROM auth_events 
        WHERE event_type = 'PASSWORD_RESET_REQUEST' 
          AND created_at >= %s
          AND (email = %s OR ip_address = %s)
    """, (datetime.utcnow() - timedelta(minutes=5), email_lower, ip_address))
    
    count = c.fetchone()["cnt"]
    if count >= 3:
        raise HTTPException(status_code=429, detail="Too many reset requests.")
        
    log_auth_event(db, None, email_lower, "PASSWORD_RESET_REQUEST", request)
    
    c.execute("SELECT id FROM users WHERE email = %s AND is_active = TRUE", (email_lower,))
    user = c.fetchone()
    
    if user:
        token = create_reset_token(db, user['id'], ip_address, user_agent)
        
        app_url = os.getenv("APP_PUBLIC_URL", "http://localhost:3000").rstrip('/')
        reset_link = f"{app_url}/reset-password?token={token}"
        
        html = f"<p>Você solicitou a redefinição de senha.</p><p>Acesse o link abaixo para criar uma nova senha:</p><p><a href='{reset_link}'>{reset_link}</a></p><p>Se não foi você, ignore este email.</p>"
        text = f"Você solicitou a redefinição de senha.\n\nAcesse o link abaixo para criar uma nova senha:\n{reset_link}\n\nSe não foi você, ignore este email."
        
        send_email(email_lower, "Redefinição de Senha - PNCP Monitor", html, text)
        
    return Response(status_code=202)

@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, request: Request, db: psycopg.Connection = Depends(get_db)):
    if not validate_password_policy(req.new_password):
        raise HTTPException(status_code=400, detail="A senha deve ter pelo menos 10 caracteres, 1 letra e 1 número.")
        
    token_data = validate_reset_token(db, req.token)
    if not token_data:
        log_auth_event(db, None, None, "PASSWORD_RESET_FAIL", request, {"reason": "invalid_or_expired_token"})
        raise HTTPException(status_code=400, detail="Token inválido ou expirado.")
        
    user_id = token_data['user_id']
    
    new_hash = hash_password(req.new_password)
    try:
        c = db.cursor()
        c.execute("UPDATE users SET password_hash = %s, updated_at = %s WHERE id = %s", (new_hash, datetime.utcnow().isoformat(), user_id))
        
        consume_reset_token(db, req.token)
        
        c.execute("SELECT email FROM users WHERE id = %s", (user_id,))
        row = c.fetchone()
        email = row['email'] if row else None
        
        log_auth_event(db, user_id, email, "PASSWORD_RESET_SUCCESS", request)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao redefinir a senha.")
        
    return {"status": "success", "message": "Senha atualizada com sucesso."}
