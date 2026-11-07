# routes/auth.py - Rotas de autenticação
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.device import SubscriptionDevice
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.auth import (
    EmailVerificationResponse,
    MessageResponse,
    RefreshTokenRequest,
    ResendVerificationRequest,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
    VerifyEmailRequest,
)
from app.security.dependencies import get_current_user, rate_limit_dependency
from app.services.auth_service import (
    create_token_pair,
    decode_token,
    get_token_type,
    hash_password,
    is_token_expired,
    verify_password,
)
from app.services.email_service import EmailService

router = APIRouter(prefix="/auth", tags=["Autenticação"])

email_service = EmailService()


async def _get_or_create_default_plan(db: AsyncSession) -> Plan:
    """Garante que exista um plano default gratuito (trial de 7 dias)."""
    plan_result = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order.asc())  # noqa: E712
    )
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        plan = Plan(
            name="Dono do App",
            description="Plano default para o proprietario da instância EFTV",
            price_cents=0,
            currency="BRL",
            interval="month",
            max_simultaneous_streams=5,
            max_devices=10,
            features={"hd": True, "full_hd": True, "4k": False},
            sort_order=0,
        )
        db.add(plan)
        await db.flush()
    return plan


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserRegister,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Registra novo usuário.

    A conta e criada com email_verified=False. Um token de verificacao e
    enviado por email. Somente apos verificar o email o trial gratuito de
    7 dias e ativado.
    """
    # Rate limiting por IP para evitar cadastros em massa
    await rate_limit_dependency(request)

    # Verifica se email já existe
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já cadastrado",
        )

    # Verifica se já existe algum admin no banco; se não, este usuário vira admin
    admin_result = await db.execute(select(User).where(User.is_admin == True))  # noqa: E712
    existing_admin = admin_result.scalar_one_or_none()
    is_first_user = existing_admin is None

    # Cria usuário (sem subscription ainda - so apos verificar email)
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        is_admin=is_first_user,
        email_verified=False,
    )
    db.add(user)
    await db.flush()  # Para obter o ID

    # Gera token de verificacao de email (valido por 24h)
    verification_token = user.generate_email_verification_token()

    # Envia email de verificacao (nao bloqueia o cadastro se falhar)
    try:
        await email_service.send_verification_email(
            to_email=data.email,
            token=verification_token,
            full_name=data.full_name,
        )
    except Exception:
        # Falha ao enviar email nao deve impedir o cadastro
        pass

    await db.commit()
    await db.refresh(user)

    # Gera tokens de acesso (login automatico apos cadastro)
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


@router.post("/verify-email", response_model=EmailVerificationResponse)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Verifica o email do usuário usando o token enviado por email.

    Apos a verificacao bem-sucedida, ativa o trial gratuito de 7 dias
    (status='trial') se o usuario ainda nao tiver uma assinatura ativa.
    """
    result = await db.execute(
        select(User).where(User.email_verification_token == data.token)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de verificacao invalido",
        )

    if not user.is_email_verification_token_valid(data.token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token de verificacao expirado ou invalido",
        )

    if user.email_verified:
        # Ja verificado - retorna sucesso idempotente
        return EmailVerificationResponse(
            message="Email ja verificado anteriormente",
            email_verified=True,
        )

    # Marca email como verificado e limpa o token
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_expires_at = None

    # Verifica se ja existe uma subscription ativa/trial para este usuario
    existing_sub_result = await db.execute(
        select(Subscription).where(Subscription.user_id == user.id).order_by(
            Subscription.created_at.desc()
        )
    )
    existing_sub = existing_sub_result.scalar_one_or_none()

    if not existing_sub or existing_sub.status not in ["active", "trial"]:
        # Ativa trial gratuito de 7 dias
        plan = await _get_or_create_default_plan(db)
        now = datetime.now(UTC)
        trial_end = now + timedelta(days=settings.FREE_TRIAL_DAYS)
        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status="trial",
            current_period_start=now,
            current_period_end=trial_end,
            trial_end=trial_end,
            auto_renew=False,
        )
        db.add(subscription)

    await db.commit()
    await db.refresh(user)

    # Envia email de boas-vindas (nao bloqueia se falhar)
    try:
        await email_service.send_welcome_email(
            to_email=user.email,
            full_name=user.full_name,
        )
    except Exception:
        pass

    return EmailVerificationResponse(
        message="Email verificado com sucesso. Seus 7 dias gratis foram ativados!",
        email_verified=True,
    )


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(
    data: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Reenvia o email de verificacao para um usuário nao verificado.
    """
    await rate_limit_dependency(request)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user:
        # Retorna sucesso generico para nao revelar se o email existe
        return MessageResponse(
            message="Se o email estiver cadastrado e nao verificado, um novo link sera enviado."
        )

    if user.email_verified:
        return MessageResponse(message="Este email ja esta verificado.")

    # Gera novo token de verificacao
    verification_token = user.generate_email_verification_token()

    # Envia email
    try:
        await email_service.send_verification_email(
            to_email=user.email,
            token=verification_token,
            full_name=user.full_name,
        )
    except Exception:
        pass

    await db.commit()

    return MessageResponse(
        message="Se o email estiver cadastrado e nao verificado, um novo link sera enviado."
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
    data: RefreshTokenRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    """
    Renova access token usando o refresh token.

    Aceita o token no corpo JSON (app Android) ou no cookie HttpOnly (web).
    """

    refresh_token = (data.refresh_token if data else None) or request.cookies.get("refresh_token")
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
