# routes/auth.py - Rotas de autenticação
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
    RefreshTokenRequest,
    MessageResponse,
)
from app.security.dependencies import get_current_user, get_current_user_optional
from app.services.auth_service import (
    hash_password,
    verify_password,
    create_token_pair,
    decode_token,
    get_token_type,
    is_token_expired,
)

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra novo usuário.
    Se plan_id fornecido, cria assinatura pendente (checkout posterior).
    """
    # Verifica se email já existe
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já cadastrado",
        )

    # Cria usuário
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
    )
    db.add(user)
    await db.flush()  # Para obter o ID

    # Se plan_id fornecido, cria subscription pendente (integração Mercado Pago vem na Fase 2)
    if data.plan_id:
        from app.models.subscription import Subscription
        from app.models.plan import Plan

        plan_result = await db.execute(select(Plan).where(Plan.id == data.plan_id))
        plan = plan_result.scalar_one_or_none()
        if plan:
            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status="pending",
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc),
            )
            db.add(subscription)

    await db.commit()
    await db.refresh(user)

    # Gera tokens
    access_token, access_jti, refresh_token, refresh_jti = create_token_pair(str(user.id))

    # Cookie HttpOnly para refresh token
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth/refresh",
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=Token)
async def login(
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login com email e senha."""
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário desativado",
        )

    # Gera tokens
    access_token, access_jti, refresh_token, refresh_jti = create_token_pair(str(user.id))

    # Cookie HttpOnly para refresh token
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth/refresh",
    )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=Token)
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Renova access token usando refresh token do cookie HttpOnly.
    """
    from fastapi import Request

    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token não encontrado",
        )

    payload = decode_token(refresh_token)
    if not payload or get_token_type(payload) != "refresh" or is_token_expired(payload):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token inválido ou expirado",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token malformado",
        )

    # Verifica se usuário ainda existe e está ativo
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou desativado",
        )

    # Gera novo par de tokens (rotate refresh token)
    access_token, access_jti, new_refresh_token, new_refresh_jti = create_token_pair(str(user.id))

    # Atualiza cookie
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth/refresh",
    )

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    """Logout - remove cookie de refresh token."""
    response.delete_cookie(key="refresh_token", path="/auth/refresh")
    return MessageResponse(message="Logout realizado com sucesso")


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Retorna dados do usuário autenticado."""
    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Atualiza dados do usuário autenticado."""
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.phone is not None:
        user.phone = data.phone
    if data.password is not None:
        user.password_hash = hash_password(data.password)

    await db.commit()
    await db.refresh(user)
    return user