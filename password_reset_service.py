import os
import psycopg
import secrets
import hashlib
from datetime import datetime, timedelta
import uuid

PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))
AUTH_PEPPER = os.getenv("AUTH_PEPPER", "")

def hash_reset_token(token_plain: str) -> str:
    """Creates a SHA-256 hash of the token."""
    text = token_plain + AUTH_PEPPER
    return hashlib.sha256(text.encode()).hexdigest()

def create_reset_token(db: psycopg.Connection, user_id: str, ip_address: str = None, user_agent: str = None) -> str:
    """Generates a secure reset token, saves its hash, and returns the plain token."""
    token_plain = secrets.token_urlsafe(48)
    token_hash = hash_reset_token(token_plain)
    
    expires_at = (datetime.utcnow() + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES)).isoformat()
    now_iso = datetime.utcnow().isoformat()
    
    token_id = str(uuid.uuid4())
    
    db.execute("""
        INSERT INTO password_reset_tokens (id, user_id, token_hash, created_at, expires_at, ip_address, user_agent)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (token_id, user_id, token_hash, now_iso, expires_at, ip_address, user_agent))
    
    db.commit()
    return token_plain

def validate_reset_token(db: psycopg.Connection, token_plain: str) -> dict:
    """Validates if a plain token corresponds to an active, unused token hash in DB."""
    token_hash = hash_reset_token(token_plain)
    
    now_iso = datetime.utcnow().isoformat()
    cur = db.execute("""
        SELECT * FROM password_reset_tokens 
        WHERE token_hash = %s AND consumed_at IS NULL AND expires_at > %s
    """, (token_hash, now_iso))
    
    row = cur.fetchone()
    if row:
        return row
    return None

def consume_reset_token(db: psycopg.Connection, token_plain: str) -> str:
    """Marks the token as used, revokes all active refresh tokens for the user, and returns user_id."""
    token_hash = hash_reset_token(token_plain)
    now_iso = datetime.utcnow().isoformat()
    
    cur = db.execute("SELECT user_id FROM password_reset_tokens WHERE token_hash = %s", (token_hash,))
    row = cur.fetchone()
    if not row:
        return None
        
    user_id = row['user_id']
    
    # Mark as used
    db.execute("UPDATE password_reset_tokens SET consumed_at = %s WHERE token_hash = %s", (now_iso, token_hash))
    
    # Revoke all refresh tokens for global logout on all devices
    db.execute("UPDATE refresh_tokens SET revoked_at = %s WHERE user_id = %s AND revoked_at IS NULL", (now_iso, user_id))
    
    db.commit()
    return user_id
