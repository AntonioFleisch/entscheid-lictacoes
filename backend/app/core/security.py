import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext

AUTH_JWT_SECRET = os.getenv("AUTH_JWT_SECRET", "super-secret-key")
AUTH_ACCESS_TOKEN_MINUTES = int(os.getenv("AUTH_ACCESS_TOKEN_MINUTES", "30"))
AUTH_ISSUER = os.getenv("AUTH_ISSUER", "entscheid")
AUTH_AUDIENCE = os.getenv("AUTH_AUDIENCE", "entscheid-web")
AUTH_PEPPER = os.getenv("AUTH_PEPPER", "")

ALGORITHM = "HS256"

# Password hashing context using argon2
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    peppered_password = password + AUTH_PEPPER
    return pwd_context.hash(peppered_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    peppered_password = plain_password + AUTH_PEPPER
    return pwd_context.verify(peppered_password, hashed_password)

def validate_password_policy(password: str) -> bool:
    """
    Validates minimum password policy:
    >= 10 characters
    at least 1 letter and 1 number
    """
    if len(password) < 10:
        return False
    if not any(char.isalpha() for char in password):
        return False
    if not any(char.isdigit() for char in password):
        return False
    return True

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=AUTH_ACCESS_TOKEN_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iss": AUTH_ISSUER,
        "aud": AUTH_AUDIENCE
    })
    encoded_jwt = jwt.encode(to_encode, AUTH_JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, 
            AUTH_JWT_SECRET, 
            algorithms=[ALGORITHM], 
            issuer=AUTH_ISSUER,
            audience=AUTH_AUDIENCE
        )
        return payload
    except JWTError:
        return None
