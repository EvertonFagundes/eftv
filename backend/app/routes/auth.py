# routes/auth.py - Rotas de autenticação
import contextlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.subscription import Subscription
from app.models.user import User
from app.schemas.auth import (
    EmailVerificationResponse,
    ForgotPasswordRequest,
    MessageResponse,
    RefreshTokenRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    Token,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
    VerifyEmailRequest,
)
from app.security.dependencies import (
    check_login_failures,
    get_current_user,
    record_login_success,
)
from app.services import device_login, rate_limit, sessions, trials
from app.services.auth_service import (
    create_token_pair,
    decode_token,
    dummy_password_hash,
    get_token_type,
    hash_password,
    is_token_expired,
    verify_and_update_password,
    verify_password,
)
from app.services.devices import InvalidDeviceError, normalize_device_id
from app.services.email_service import EmailService
from app.services.plans import get_or_create_plan

router = APIRouter(prefix="/auth", tags=["Autenticação"])

email_service = EmailService()


def _refresh_expiry() -> datetime:
    """Quando o refresh token expira (mesma regra do JWT)."""
    return datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)


def _optional_device_id(raw: str | None) -> str | None:
    """Aceita o header de aparelho sem obrigar (web nao manda)."""
    try:
        return normalize_device_id(raw)
    except InvalidDeviceError:
        return None


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Cookie HttpOnly usado pelo site; o app Android usa o corpo JSON."""
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/auth/refresh",
    )


async def _issue_tokens(
    db: AsyncSession,
    user_id,
    device_id: str | None = None,
    *,
    commit: bool = True,
) -> tuple[str, str]:
    """Cria o par de tokens e registra o refresh (para poder revogar)."""
    access_token, _access_jti, refresh_token, refresh_jti = create_token_pair(str(user_id))
    await sessions.register(
        db,
        user_id=user_id,
        jti=refresh_jti,
        expires_at=_refresh_expiry(),
        device_id=device_id,
        commit=False,
    )
    if commit:
        await db.commit()
    return access_token, refresh_token


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
    # Limite por CONTA (e-mail), nao por IP: atras do proxy do Render todos
    # os clientes aparecem com o mesmo IP, entao um balde por IP bloquearia
    # a base inteira.
    await rate_limit.hit(
        db,
        key=rate_limit.scoped_key("register", data.email),
        limit=settings.RATE_LIMIT_REGISTER_PER_HOUR,
        window_seconds=3600,
        detail="Muitas tentativas de cadastro para este email. Tente mais tarde.",
    )

    # Verifica se email já existe
    result = await db.execute(select(User).where(User.email == data.email))
    existing = result.scalar_one_or_none()

    if existing is not None and existing.email_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email já cadastrado",
        )

    if existing is not None:
        # Conta criada e nunca confirmada (dono do e-mail nunca terminou o
        # cadastro, ou alguem "reservou" o endereco). Como a posse do e-mail
        # ainda vai ser provada pela verificacao, o cadastro novo assume a
        # conta em vez de vazar pagamento/futuro trial para quem reservou.
        existing.password_hash = hash_password(data.password)
        existing.full_name = data.full_name or existing.full_name
        existing.phone = data.phone or existing.phone
        user = existing
    else:
        # Somente a primeira conta de uma instalacao vazia vira admin. Antes
        # bastava nao existir admin: se o ultimo admin fosse removido, o
        # proximo cadastro (de qualquer pessoa) assumia o painel.
        users_result = await db.execute(select(func.count(User.id)))
        is_first_user = int(users_result.scalar_one() or 0) == 0

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
    with contextlib.suppress(Exception):
        await email_service.send_verification_email(
            to_email=data.email,
            token=verification_token,
            full_name=data.full_name,
        )

    await db.commit()
    await db.refresh(user)

    # Gera tokens de acesso (login automatico apos cadastro)
    access_token, refresh_token = await _issue_tokens(db, user.id)

    _set_refresh_cookie(response, refresh_token)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/verify-email", response_model=EmailVerificationResponse)
async def verify_email(
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
):
    """
    Verifica o email do usuário usando o token enviado por email.

    Apos a verificacao bem-sucedida, ativa o trial gratuito de 7 dias
    (status='trial') se o usuario ainda nao tiver uma assinatura ativa e se
    o aparelho (quando informado) ainda nao tiver consumido o teste.
    """
    result = await db.execute(select(User).where(User.email_verification_token == data.token))
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
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    )
    existing_subs = existing_sub_result.scalars().all()
    has_trial_or_active = any(sub.status in ("active", "trial") for sub in existing_subs)

    device_id = _optional_device_id(x_device_id)
    trial_activated = False

    if not has_trial_or_active:
        # Teste por APARELHO: o mesmo celular nao ganha outro trial so por
        # criar outra conta. Quando o app nao manda o header (confirmacao
        # pelo navegador), o bloqueio acontece no /player/playlist.
        blocked = device_id is not None and await trials.device_already_used(db, device_id, user.id)
        if blocked:
            trial_activated = False
        else:
            plan = await get_or_create_plan(db)
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
            await db.flush()
            if device_id is not None:
                await trials.claim(
                    db,
                    device_id=device_id,
                    user_id=user.id,
                    subscription_id=subscription.id,
                    commit=False,
                )
            trial_activated = True

    await db.commit()
    await db.refresh(user)

    # Envia email de boas-vindas (nao bloqueia se falhar)
    with contextlib.suppress(Exception):
        await email_service.send_welcome_email(
            to_email=user.email,
            full_name=user.full_name,
        )

    if trial_activated:
        message = "Email verificado com sucesso. Seus 7 dias gratis foram ativados!"
    elif has_trial_or_active:
        message = "Email verificado com sucesso."
    else:
        message = (
            "Email verificado. Este aparelho ja usou o teste gratis: "
            "assine para continuar assistindo."
        )

    return EmailVerificationResponse(
        message=message,
        email_verified=True,
        trial_activated=trial_activated,
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
    await rate_limit.hit(
        db,
        key=rate_limit.scoped_key("verify-email", data.email),
        limit=settings.RATE_LIMIT_EMAIL_PER_HOUR,
        window_seconds=3600,
        detail="Muitos reenvios para este email. Tente novamente mais tarde.",
    )

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
    with contextlib.suppress(Exception):
        await email_service.send_verification_email(
            to_email=user.email,
            token=verification_token,
            full_name=user.full_name,
        )

    await db.commit()

    return MessageResponse(
        message="Se o email estiver cadastrado e nao verificado, um novo link sera enviado."
    )


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Envia um codigo de recuperacao de senha para o email informado.

    Responde sempre com a mesma mensagem para nao revelar quais emails
    estao cadastrados.
    """
    await rate_limit.hit(
        db,
        key=rate_limit.scoped_key("forgot-password", data.email),
        limit=settings.RATE_LIMIT_EMAIL_PER_HOUR,
        window_seconds=3600,
        detail="Muitos pedidos de recuperacao para este email. Tente mais tarde.",
    )

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is not None:
        code = user.generate_password_reset_code()
        await db.commit()
        # Nao bloqueia a resposta se o provedor de email falhar.
        with contextlib.suppress(Exception):
            await email_service.send_password_reset_email(
                to_email=user.email,
                code=code,
                full_name=user.full_name,
            )

    return MessageResponse(
        message="Se este email estiver cadastrado, enviaremos um codigo de recuperacao."
    )


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Troca a senha usando o codigo recebido por email."""
    # Codigo de 6 digitos so e seguro com limite por conta: 1 milhao de
    # combinacoes com 5 tentativas a cada 15 minutos nao e viavel.
    await rate_limit.hit(
        db,
        key=rate_limit.scoped_key("reset-password", data.email),
        limit=settings.RATE_LIMIT_PASSWORD_RESET_ATTEMPTS,
        window_seconds=settings.RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS,
        detail=("Muitas tentativas de codigo para esta conta. " "Peca um novo codigo mais tarde."),
    )

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_password_reset_code_valid(data.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Codigo invalido ou expirado. Pedir um novo codigo.",
        )

    user.password_hash = hash_password(data.new_password)
    user.password_reset_token = None
    user.password_reset_expires_at = None
    # Nao reativa conta desativada: recuperar a senha nao pode desfazer um
    # bloqueio feito pelo suporte. E derruba as sessoes antigas, senao um
    # aparelho ja logado continua renovando o acesso com a senha trocada.
    await sessions.revoke_all(db, user.id, commit=False)
    await db.commit()

    return MessageResponse(message="Senha alterada com sucesso. Entre com a nova senha.")


@router.post("/login", response_model=Token)
async def login(
    data: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
    x_device_id: str | None = Header(default=None, alias="X-Device-Id"),
):
    """Login com email e senha."""
    # Conta as tentativas POR CONTA antes de validar: sem isso a senha podia
    # ser martelada sem parar. Limite por IP nao serve aqui porque atras do
    # proxy do Render todos os clientes vem do mesmo IP.
    await check_login_failures(db, data.email)

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user is None:
        # Mesmo custo de bcrypt de uma conta real, para o tempo de resposta
        # nao denunciar quais e-mails existem.
        verify_password(data.password, dummy_password_hash())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )

    valid, new_hash = verify_and_update_password(data.password, user.password_hash)
    if not valid:
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

    # Hash legado (bcrypt puro): migra para bcrypt_sha256. O commit acontece
    # junto com o registro do refresh token em _issue_tokens.
    if new_hash:
        user.password_hash = new_hash

    # Senha certa: zera o contador de tentativas da conta.
    await record_login_success(db, data.email)

    # Gera tokens (e registra o refresh para poder revogar depois)
    access_token, refresh_token = await _issue_tokens(db, user.id, _optional_device_id(x_device_id))

    _set_refresh_cookie(response, refresh_token)

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
    O token apresentado e revogado na rotacao: um refresh copiado deixa de
    funcionar assim que o dono renova a sessao.
    """

    refresh = (data.refresh_token if data else None) or request.cookies.get("refresh_token")
    if not refresh:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token não encontrado",
        )

    payload = decode_token(refresh)
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

    try:
        user_uuid = UUID(str(user_id))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token malformado",
        ) from None

    jti = payload.get("jti")
    stored = await sessions.get(db, jti) if isinstance(jti, str) and jti else None

    # Token registrado e revogado/expirado: sessao encerrada (logout, troca de
    # aparelho ou revogacao pelo suporte).
    if stored is not None and (
        str(stored.user_id) != str(user_id) or not sessions.is_usable(stored)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessao encerrada. Entre novamente.",
        )

    # Verifica se usuário ainda existe e está ativo
    result = await db.execute(select(User).where(User.id == user_uuid))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado ou desativado",
        )

    if stored is None and isinstance(jti, str) and jti:
        # Token emitido antes deste controle existir: aceita uma vez e passa a
        # registrar, para nao derrubar quem ja estava logado.
        expires_at = datetime.fromtimestamp(float(payload.get("exp", 0)), UTC)
        await sessions.register(
            db,
            user_id=user.id,
            jti=jti,
            expires_at=expires_at,
            commit=False,
        )
    elif stored is not None:
        # Rotacao: o token usado nao serve mais.
        stored.revoked_at = datetime.now(UTC)

    # Gera novo par de tokens
    access_token, new_refresh_token = await _issue_tokens(
        db, user.id, stored.device_id if stored is not None else None
    )

    _set_refresh_cookie(response, new_refresh_token)

    return Token(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    data: RefreshTokenRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Logout - revoga o refresh token e remove o cookie.

    Antes so apagava o cookie: quem tinha copiado o token continuava
    renovando a sessao. Agora o jti vai para a lista de revogados.
    """
    token = (data.refresh_token if data else None) or request.cookies.get("refresh_token")
    if token:
        payload = decode_token(token)
        jti = payload.get("jti") if payload else None
        if isinstance(jti, str) and jti:
            await sessions.revoke(db, jti)

    response.delete_cookie(key="refresh_token", path="/auth/refresh")
    return MessageResponse(message="Logout realizado com sucesso")


# ----------------------------------------------------------------------
# Login na TV por codigo ("entrar pelo celular")
#
# O controle remoto nao tem teclado. Em vez de digitar e-mail e senha na TV,
# ela mostra um codigo curto e o assinante confirma no celular, onde ja esta
# logado. O mesmo vale para a assinatura (ver /subscriptions/checkout).
# ----------------------------------------------------------------------


class DeviceCodeRequest(BaseModel):
    device_name: str | None = None


class DeviceCodeResponse(BaseModel):
    code: str
    expires_in: int
    poll_in: int


class DeviceCodePollRequest(BaseModel):
    code: str


class DeviceCodePollResponse(BaseModel):
    status: str
    access_token: str | None = None
    refresh_token: str | None = None
    email: str | None = None
    expires_in: int | None = None


class DeviceCodeApproveRequest(BaseModel):
    code: str


@router.post("/device-code", response_model=DeviceCodeResponse)
async def create_device_code(
    payload: DeviceCodeRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
):
    """A TV pede um codigo para exibir na tela."""
    entry = await device_login.create_code(db, payload.device_name if payload else None)
    return DeviceCodeResponse(
        code=device_login.format_code(entry.code),
        expires_in=settings.DEVICE_CODE_TTL_MINUTES * 60,
        poll_in=3,
    )


@router.post("/device-code/poll", response_model=DeviceCodePollResponse)
async def poll_device_code(
    payload: DeviceCodePollRequest,
    db: AsyncSession = Depends(get_db),
):
    """A TV pergunta se ja foi autorizada. Os tokens saem uma unica vez."""
    state, entry = await device_login.poll_code(db, payload.code)
    if state != "approved" or entry is None:
        return DeviceCodePollResponse(status=state)
    return DeviceCodePollResponse(
        status="approved",
        access_token=entry.access_token,
        refresh_token=entry.refresh_token,
        email=entry.email,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/device-code/approve", response_model=MessageResponse)
async def approve_device_code(
    payload: DeviceCodeApproveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """O celular (conta ja logada) autoriza a TV digitando o codigo."""
    try:
        await device_login.approve_code(db, code=payload.code, user_id=user.id, email=user.email)
    except ValueError as exc:
        if str(exc) == "expired":
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Codigo expirado. Gere outro na TV.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Codigo invalido. Confira os caracteres na TV.",
        ) from exc

    return MessageResponse(message="TV autorizada. Ela entra sozinha em instantes.")


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
    """Atualiza dados do usuário autenticado.

    Trocar a senha exige a senha atual: um access token roubado (15 min) nao
    pode virar troca de senha definitiva. Depois da troca, todas as sessoes
    sao revogadas.
    """
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.phone is not None:
        user.phone = data.phone
    if data.password is not None:
        if not data.current_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe a senha atual para trocar a senha.",
            )
        valid, _ = verify_and_update_password(data.current_password, user.password_hash)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Senha atual incorreta.",
            )
        user.password_hash = hash_password(data.password)
        await sessions.revoke_all(db, user.id, commit=False)

    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me/export")
async def export_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exporta os dados da conta (LGPD / Play Store).

    Devolve o cadastro, as assinaturas e as cobrancas em JSON. Nao inclui
    senha, tokens nem dados do cartao (o app nunca os recebeu).
    """
    from app.models.payment import Payment

    subs_result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at)
    )
    payments_result = await db.execute(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at)
    )

    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "email_verified": user.email_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "subscriptions": [
            {
                "id": str(sub.id),
                "status": sub.status,
                "current_period_start": (
                    sub.current_period_start.isoformat() if sub.current_period_start else None
                ),
                "current_period_end": (
                    sub.current_period_end.isoformat() if sub.current_period_end else None
                ),
                "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
                "auto_renew": sub.auto_renew,
            }
            for sub in subs_result.scalars().all()
        ],
        "payments": [
            {
                "id": str(payment.id),
                "amount_cents": payment.amount_cents,
                "currency": payment.currency,
                "status": payment.status,
                "payment_method": payment.payment_method,
                "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
                "created_at": payment.created_at.isoformat() if payment.created_at else None,
            }
            for payment in payments_result.scalars().all()
        ],
    }


@router.delete("/me", response_model=MessageResponse)
async def delete_me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Exclui a conta do app (LGPD / exigencia da Play Store).

    Anonimiza o cadastro, encerra as sessoes e corta a cobranca recorrente.
    O historico de pagamentos fica sem dado pessoal (o e-mail vira um
    identificador interno), que e o minimo exigido para obrigacao fiscal.
    """
    from app.services.devices import revoke_all_devices
    from app.services.mercadopago import cancel_preapproval

    # Excluir o unico admin deixaria o painel sem dono e abriria caminho para
    # o proximo usuario reivindicar a propriedade. Transfira antes.
    if user.is_admin:
        admins_result = await db.execute(
            select(func.count(User.id)).where(User.is_admin.is_(True), User.is_active.is_(True))
        )
        if int(admins_result.scalar_one() or 0) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Nao e possivel excluir o ultimo administrador. "
                    "Promova outro usuario antes de excluir esta conta."
                ),
            )

    subs_result = await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    subscriptions = list(subs_result.scalars().all())

    for sub in subscriptions:
        sub.cancel_at_period_end = True
        sub.auto_renew = False
        sub.status = "cancelled" if sub.status != "expired" else sub.status
        sub.cancelled_at = sub.cancelled_at or datetime.now(UTC)

    # Corta a recorrencia no Mercado Pago (best-effort: o cadastro sai de
    # qualquer forma e a falha fica no log para o suporte).
    for sub in subscriptions:
        if sub.mercadopago_subscription_id:
            with contextlib.suppress(Exception):
                await cancel_preapproval(str(sub.mercadopago_subscription_id))

    with contextlib.suppress(Exception):
        await revoke_all_devices(db, [sub.id for sub in subscriptions])

    # Derruba todas as sessoes emitidas (refresh registrados).
    await sessions.revoke_all(db, user.id)

    # Anonimiza: o e-mail e unico, entao usa um identificador interno.
    user.email = f"deleted-{user.id}@deleted.eftv.invalid"
    user.full_name = None
    user.phone = None
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.email_verified = False
    user.is_active = False
    user.is_admin = False
    user.email_verification_token = None
    user.password_reset_token = None

    # Nao apaga as linhas de pagamento: guarda o valor/status sem dado pessoal.
    await db.commit()

    return MessageResponse(message="Conta excluida. Voce foi desconectado de todos os aparelhos.")
