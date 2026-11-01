# services/auth_service.py - Lógica de autenticação (hash, JWT, tokens)
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.BCRYPT_ROUNDS)


def hash_password(password: str) -> str:
    """Gera hash bcrypt da senha."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha contra hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: str, extra_claims: dict | None = None) -> tuple[str, str]:
    """
    Cria access token JWT.
    Returns: (token, jti)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = str(uuid4())

    claims = {
        "sub": user_id,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "access",
        "jti": jti,
    }
    if extra_claims:
        claims.update(extra_claims)

    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti


def create_refresh_token(user_id: str) -> tuple[str, str]:
    """
    Cria refresh token JWT.
    Returns: (token, jti)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid4())

    claims = {
        "sub": user_id,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "refresh",
        "jti": jti,
    }

    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti


def create_stream_token(
    user_id: str,
    channel_id: str,
    max_streams: int = 1,
    quality: str = "auto",
    extra_claims: dict | None = None,
) -> tuple[str, str, datetime]:
    """
    Cria token JWT de curta duração para autorização de stream no CDN.
    Returns: (token, jti, expires_at)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=settings.STREAM_TOKEN_TTL_SECONDS)
    jti = str(uuid4())

    claims = {
        "sub": user_id,
        "channel_id": channel_id,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "stream",
        "jti": jti,
        "iss": settings.STREAM_TOKEN_ISSUER,
        "max_streams": max_streams,
        "quality": quality,
    }
    if extra_claims:
        claims.update(extra_claims)

    token = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, jti, expire


def decode_token(token: str) -> dict | None:
    """Decodifica e valida token JWT. Retorna payload ou None se inválido."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None


def get_token_type(payload: dict) -> str | None:
    """Extrai tipo do token do payload."""
    return payload.get("type")


def is_token_expired(payload: dict) -> bool:
    """Verifica se token expirou baseado no claim exp."""
    exp = payload.get("exp")
    if not exp:
        return True
    return datetime.now(timezone.utc).timestamp() > exp


def create_token_pair(user_id: str) -> tuple[str, str, str, str]:
    """
    Cria par access + refresh tokens.
    Returns: (access_token, access_jti, refresh_token, refresh_jti)
    """
    access_token, access_jti = create_access_token(user_id)
    refresh_token, refresh_jti = create_refresh_token(user_id)
    return access_token, access_jti, refresh_token, refresh_jti