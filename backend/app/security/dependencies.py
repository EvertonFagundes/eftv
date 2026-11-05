# security/dependencies.py - Dependencies de autenticação e autorização
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.services.auth_service import decode_token, get_token_type, is_token_expired
from app.services.devices import InvalidDeviceError, normalize_device_id

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Dependency para obter usuário autenticado via access token.
    Raises 401 se token inválido, expirado ou usuário não encontrado.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if get_token_type(payload) != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tipo de token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if is_token_expired(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token malformado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado",
        )

    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """
    Dependency opcional - retorna usuário se token válido, None caso contrário.
    Útil para endpoints públicos que personalizam resposta se logado.
    """
    if not credentials:
        return None

    payload = decode_token(credentials.credentials)
    if not payload or get_token_type(payload) != "access" or is_token_expired(payload):
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        return None

    return user


async def get_current_active_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Subscription:
    """
    Dependency para obter assinatura ativa do usuário logado.
    Raises 403 se não tem assinatura ativa.
    """
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .where(Subscription.status.in_(["active", "trial"]))
        .order_by(Subscription.created_at.desc())
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nenhuma assinatura ativa encontrada",
        )

    if not subscription.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura expirada ou cancelada",
        )

    return subscription


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Dependency que exige usuário admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return user


async def get_device_id(
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
) -> str:
    """
    Identificador estavel do aparelho, gerado pelo app na primeira execucao.
    Nao e dado de hardware: e um UUID aleatorio por instalacao.
    """
    try:
        return normalize_device_id(x_device_id)
    except InvalidDeviceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "device_id_missing", "message": str(exc)},
        ) from exc


async def get_device_fingerprint(request: Request) -> str:
    """Gera fingerprint simples do device baseado em IP + User-Agent."""
    ip = request.client.host if request.client else "unknown"
    ua = request.headers.get("user-agent", "unknown")
    import hashlib

    raw = f"{ip}:{ua}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class RateLimiter:
    """Rate limiter simples em memória (para dev). Em produção usar Redis."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        import time

        now = time.time()
        if key not in self.requests:
            self.requests[key] = []

        # Limpa requests antigos
        self.requests[key] = [ts for ts in self.requests[key] if now - ts < self.window_seconds]

        if len(self.requests[key]) >= self.max_requests:
            return False

        self.requests[key].append(now)
        return True


# Instância global para dev (em produção usar Redis)
rate_limiter = RateLimiter(
    max_requests=settings.RATE_LIMIT_REQUESTS,
    window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
)


async def rate_limit_dependency(request: Request) -> None:
    """Dependency para rate limiting por IP."""
    ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"ratelimit:{ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas requisições. Tente novamente mais tarde.",
        )
