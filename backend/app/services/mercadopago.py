# services/mercadopago.py - Integração Mercado Pago
import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import httpx
from sqlalchemy import func, select

from app.config import settings
from app.models.payment import Payment
from app.models.plan import Plan
from app.models.subscription import Subscription
from app.models.user import User

MERCADOPAGO_BASE_URL = "https://api.mercadopago.com"
if settings.MERCADOPAGO_SANDBOX:
    MERCADOPAGO_BASE_URL = (
        "https://api.mercadopago.com"  # Sandbox usa mesma URL, headers diferentes
    )

logger = logging.getLogger(__name__)

# Estados da preapproval no Mercado Pago que liberam o acesso.
_ACTIVE_PREAPPROVAL_STATUSES = {"authorized"}

# Janela aceita entre o ts assinado e agora (anti-replay do webhook).
WEBHOOK_TOLERANCE_SECONDS = 600

# Cache da identidade da conta coletora (evita consultar o Mercado Pago a
# cada abertura de tela). Conta de teste nao consegue cobrar cliente real.
_account_cache: dict = {"at": 0.0, "data": None}


async def get_account_info(force: bool = False) -> dict | None:
    """Diz se a conta que recebe os pagamentos e de teste.

    Conta de teste so aceita pagador de teste ("Both payer and collector must
    be real or test users"). O resultado fica em cache por 10 minutos.
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        return None

    now = time.monotonic()
    if (
        not force
        and _account_cache["data"] is not None
        and now - _account_cache["at"] < 600
    ):
        return _account_cache["data"]

    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            response = await client.get(
                f"{MERCADOPAGO_BASE_URL}/users/me",
                headers=_get_headers(),
            )
        if response.status_code >= 400:
            return None
        data = response.json()
    except Exception:  # noqa: BLE001
        return None

    email = str(data.get("email") or "")
    nickname = str(data.get("nickname") or "")
    info = {
        "id": data.get("id"),
        "is_test_user": "test_user" in (data.get("tags") or [])
        or email.endswith("@testuser.com")
        or nickname.startswith("TESTUSER"),
        "site_id": data.get("site_id"),
        "country_id": data.get("country_id"),
    }
    _account_cache.update(at=now, data=info)
    return info


def validate_webhook_signature(headers, data_id: str | None) -> bool:
    """Valida o header ``x-signature`` enviado pelo Mercado Pago.

    O Mercado Pago assina ``id:<data.id>;request-id:<x-request-id>;ts:<ts>;``
    com HMAC-SHA256 usando o segredo configurado no painel.

    Em producao o segredo e obrigatorio: sem ele o webhook e recusado (antes
    era aceito, e qualquer um podia forcar chamadas/reenvios). Em
    desenvolvimento a validacao continua opcional para facilitar testes.
    """
    secret = settings.MERCADOPAGO_WEBHOOK_SECRET
    if not secret:
        if settings.ENVIRONMENT == "production":
            logger.error(
                "MERCADOPAGO_WEBHOOK_SECRET nao configurado: webhook recusado em producao"
            )
            return False
        logger.warning(
            "MERCADOPAGO_WEBHOOK_SECRET nao configurado: webhook aceito sem validar assinatura"
        )
        return True

    signature = headers.get("x-signature")
    if not signature:
        return False

    parts = {}
    for chunk in signature.split(","):
        key, _, value = chunk.partition("=")
        parts[key.strip()] = value.strip()

    ts = parts.get("ts")
    received = parts.get("v1")
    if not ts or not received:
        return False

    # Rejeita replay de um webhook antigo (a assinatura continua valida, mas a
    # notificacao ja foi processada). O Mercado Pago reenvia assinado de novo.
    try:
        if abs(time.time() - float(ts)) > WEBHOOK_TOLERANCE_SECONDS:
            logger.warning("Webhook do Mercado Pago com timestamp fora da janela: %s", ts)
            return False
    except (TypeError, ValueError):
        return False

    request_id = headers.get("x-request-id")
    # O template do Mercado Pago omite as partes ausentes, mas sempre termina
    # cada chave com ";". Assim: "id:...;request-id:...;ts:...;".
    manifest_parts = []
    if data_id:
        manifest_parts.append(f"id:{data_id}")
    if request_id:
        manifest_parts.append(f"request-id:{request_id}")
    manifest_parts.append(f"ts:{ts}")
    manifest = ";".join(manifest_parts) + ";"

    expected = hmac.new(
        secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, received)


def _get_headers(idempotency_key: str | None = None) -> dict:
    headers = {
        "Authorization": f"Bearer {settings.MERCADOPAGO_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["X-Idempotency-Key"] = idempotency_key
    return headers


async def _plan_belongs_to_account(plan_id: str) -> bool:
    """Confere se o plano salvo ainda pertence a conta coletora atual.

    Quando o token muda (teste -> producao), o plano antigo continua gravado
    no banco mas pertence a outro coletor. Reaproveitar esse id geraria um
    link de assinatura invalido para o cliente.
    """
    account = await get_account_info()
    if account is None or not account.get("id"):
        # Sem como comparar: mantem o plano em vez de recriar a cada checkout.
        return True

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{MERCADOPAGO_BASE_URL}/preapproval_plan/{plan_id}",
                headers=_get_headers(),
            )
    except Exception:  # noqa: BLE001
        return True

    if response.status_code >= 400:
        return False

    try:
        collector_id = response.json().get("collector_id")
    except ValueError:
        return True

    return str(collector_id) == str(account["id"])


async def get_or_create_subscription_plan(db, plan: Plan) -> str:
    """Devolve o id do plano de assinatura no Mercado Pago, criando se preciso.

    O fluxo por plano (``preapproval_plan``) gera um link de checkout onde o
    proprio Mercado Pago coleta o cartao do cliente. E o caminho recomendado
    quando o app nao tokeniza cartao e evita a exigencia de ``payer_email``
    conhecido na criacao da assinatura.
    """
    existing = getattr(plan, "mercadopago_plan_id", None)
    if existing and await _plan_belongs_to_account(str(existing)):
        return str(existing)
    if existing:
        logger.warning(
            "Plano MP %s nao pertence a conta atual; criando um novo", existing
        )
        plan.mercadopago_plan_id = None

    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado")

    payload = {
        "reason": f"EFTV - {plan.name}",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": round(plan.price_cents / 100, 2),
            "currency_id": plan.currency or "BRL",
        },
        "back_url": f"{settings.FRONTEND_URL.rstrip('/')}/checkout.html?app=1",
        "payment_methods_allowed": {"payment_types": [{"id": "credit_card"}]},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MERCADOPAGO_BASE_URL}/preapproval_plan",
            json=payload,
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Erro ao criar plano MP: {response.status_code} - {response.text}"
        )

    data = response.json()
    plan.mercadopago_plan_id = data.get("id")
    await db.flush()
    logger.info("Plano de assinatura criado no Mercado Pago: %s", plan.mercadopago_plan_id)
    return str(plan.mercadopago_plan_id)


async def create_checkout_preference(
    user: User,
    plan: Plan,
    payer_email: str,
    payer_name: str | None = None,
    payer_phone: str | None = None,
    payer_cpf: str | None = None,
    back_urls: dict | None = None,
    db=None,
) -> dict:
    """
    Cria a assinatura no Mercado Pago e devolve o link de checkout.

    Primeiro tenta a preapproval direta (identifica o usuario por
    ``external_reference``). Se o Mercado Pago recusar, cai no fluxo por
    plano, que gera um link de assinatura reutilizavel.
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN não configurado")

    # O endpoint /preapproval aceita apenas os campos da assinatura. Campos do
    # Checkout Pro (back_urls, auto_return, notification_url, payer) nao
    # existem aqui: o webhook e configurado no painel da aplicacao no Mercado
    # Pago e o retorno e uma unica back_url.
    frontend = settings.FRONTEND_URL.rstrip("/")
    back_url = f"{frontend}/checkout.html"
    if back_urls:
        back_url = back_urls.get("success", back_url)

    preapproval_data = {
        "reason": f"EFTV - {plan.name}",
        "external_reference": str(user.id),
        "payer_email": payer_email,
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": round(plan.price_cents / 100, 2),
            "currency_id": plan.currency or "BRL",
        },
        "back_url": back_url,
        # Em Assinaturas o painel nao oferece a secao Webhooks: a notificacao
        # e registrada na criacao da assinatura. source_news=webhooks evita
        # que o Mercado Pago use o formato IPN antigo.
        "notification_url": (
            f"{settings.API_BASE_URL.rstrip('/')}"
            "/subscriptions/webhook/mercadopago?source_news=webhooks"
        ),
        # Sem cartao tokenizado no app: o cliente escolhe o meio de pagamento
        # no checkout do Mercado Pago. O acesso so e liberado pelo webhook.
        "status": "pending",
    }

    async def post_preapproval(payload: dict) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(
                f"{MERCADOPAGO_BASE_URL}/preapproval",
                json=payload,
                headers=_get_headers(),
            )

    response = await post_preapproval(preapproval_data)

    # O Mercado Pago devolve "User bad request" quando o ``payer_email`` nao
    # pertence a uma conta Mercado Pago (comum em cliente que ainda nao tem
    # conta). Sem o campo, o proprio checkout pede o e-mail do pagador.
    if response.status_code >= 400 and preapproval_data.get("payer_email"):
        fallback = {k: v for k, v in preapproval_data.items() if k != "payer_email"}
        retry = await post_preapproval(fallback)
        if retry.status_code < 400:
            logger.info("Preapproval criada sem payer_email; o checkout pede o e-mail")
            data = dict(retry.json())
            data["preapproval_id"] = data.get("id")
            data["mode"] = "preapproval"
            return data
        logger.warning(
            "Tentativa sem payer_email tambem falhou: %s - %s",
            retry.status_code,
            retry.text,
        )

    if response.status_code < 400:
        data = dict(response.json())
        data["preapproval_id"] = data.get("id")
        data["mode"] = "preapproval"
        return data

    logger.warning(
        "Mercado Pago recusou a preapproval direta (%s - %s); usando plano",
        response.status_code,
        response.text,
    )

    # Fallback: link de assinatura do plano. O pagador e identificado pelo
    # ``external_reference`` anexado ao init_point (e, se o Mercado Pago nao
    # repassar, pelo e-mail do pagador no webhook).
    if db is None:
        raise RuntimeError(
            f"Erro ao criar assinatura MP: {response.status_code} - {response.text}"
        )

    try:
        plan_id = await get_or_create_subscription_plan(db, plan)
    except RuntimeError as exc:
        raise RuntimeError(
            f"Erro ao criar assinatura MP: {response.status_code} - {response.text}. "
            f"{exc}"
        ) from exc

    init_point = (
        "https://www.mercadopago.com.br/subscriptions/checkout"
        f"?preapproval_plan_id={plan_id}"
        f"&external_reference={user.id}"
    )
    return {
        "id": plan_id,
        "preapproval_id": None,
        "init_point": init_point,
        "sandbox_init_point": None,
        "mode": "plan",
    }


async def get_preapproval(preapproval_id: str) -> dict:
    """Busca detalhes de uma preapproval (assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/preapproval/{preapproval_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao buscar preapproval: {response.status_code} - {response.text}")

    return cast(dict, response.json())


async def cancel_preapproval(preapproval_id: str) -> dict:
    """Cancela uma preapproval (assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            f"{MERCADOPAGO_BASE_URL}/preapproval/{preapproval_id}",
            json={"status": "cancelled"},
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Erro ao cancelar preapproval: {response.status_code} - {response.text}"
        )

    return cast(dict, response.json())


async def get_payment(payment_id: str) -> dict:
    """Busca detalhes de um pagamento."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/v1/payments/{payment_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(f"Erro ao buscar pagamento: {response.status_code} - {response.text}")

    return cast(dict, response.json())


async def get_authorized_payment(authorized_payment_id: str) -> dict:
    """Busca um pagamento autorizado (cobranca recorrente da assinatura)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/authorized_payments/{authorized_payment_id}",
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Erro ao buscar pagamento autorizado: {response.status_code} - {response.text}"
        )

    return cast(dict, response.json())


async def search_authorized_payments(preapproval_id: str) -> list[dict]:
    """Busca as cobrancas recorrentes de uma assinatura no Mercado Pago.

    Caminho de fallback quando o webhook nao chega (fluxo por plano nao
    recebe ``notification_url``): a conciliacao busca as faturas aqui.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/authorized_payments/search",
            params={"preapproval_id": preapproval_id, "limit": 10},
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Erro ao buscar cobrancas da assinatura: {response.status_code} - {response.text}"
        )

    return cast(list, response.json().get("results") or [])


def _parse_datetime(value: str | None) -> datetime | None:
    """Converte as datas ISO do Mercado Pago em ``datetime`` com timezone."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _next_period_end(start: datetime | None, auto_recurring: dict) -> datetime:
    """Calcula o fim do periodo quando o Mercado Pago nao informa a data.

    Base: ``start`` (ou agora) mais a frequencia da assinatura. Mensal vira
    31 dias e anual 366, com uma folga para nao expirar na virada do mes.
    """
    base = start or datetime.now(UTC)
    try:
        frequency = int(auto_recurring.get("frequency") or 1)
    except (TypeError, ValueError):
        frequency = 1
    frequency_type = str(auto_recurring.get("frequency_type") or "months")

    if frequency_type == "days":
        return base + timedelta(days=frequency)
    if frequency_type == "years":
        return base + timedelta(days=366 * frequency)
    # months (padrao das assinaturas)
    return base + timedelta(days=31 * frequency)


async def _find_subscription(
    db,
    preapproval_id: str | None,
    external_reference: str | None = None,
    payer_email: str | None = None,
) -> Subscription | None:
    """Localiza a assinatura pelo id da preapproval, usuario ou e-mail."""
    if preapproval_id:
        result = await db.execute(
            select(Subscription).where(Subscription.mercadopago_subscription_id == preapproval_id)
        )
        subscription = result.scalar_one_or_none()
        if subscription is not None:
            return cast(Subscription | None, subscription)

    if external_reference:
        try:
            user_id = UUID(str(external_reference))
        except ValueError:
            user_id = None
        if user_id is not None:
            result = await db.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id)
                .order_by(Subscription.created_at.desc())
            )
            subscription = result.scalars().first()
            if subscription is not None:
                if preapproval_id:
                    subscription.mercadopago_subscription_id = preapproval_id
                return cast(Subscription | None, subscription)

    # Fluxo por plano: o Mercado Pago pode nao repassar o external_reference,
    # entao o e-mail do pagador e a unica ligacao com a conta do app.
    if payer_email:
        from app.models.user import User

        user_result = await db.execute(
            select(User).where(func.lower(User.email) == payer_email.lower())
        )
        user = user_result.scalar_one_or_none()
        # So casa com conta CONFIRMADA: cadastrar o e-mail de outra pessoa
        # (conta nao verificada) nao pode capturar o pagamento dela.
        if user is not None and user.email_verified:
            result = await db.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .order_by(Subscription.created_at.desc())
            )
            subscription = result.scalars().first()
            if subscription is not None:
                if preapproval_id:
                    subscription.mercadopago_subscription_id = preapproval_id
                return cast(Subscription | None, subscription)

    return None


async def process_webhook(payload: dict, db, data_id: str | None = None) -> None:
    """
    Processa webhook do Mercado Pago.

    Os eventos reais de assinatura enviados pelo Mercado Pago sao:
    - ``subscription_preapproval``: criacao/atualizacao da assinatura;
    - ``subscription_authorized_payment``: cobranca recorrente aprovada ou
      rejeitada.
    """
    event_type = payload.get("type") or payload.get("topic")
    data = payload.get("data") or {}
    resource_id = data.get("id") or payload.get("id") or data_id

    if not resource_id:
        logger.warning("Webhook do Mercado Pago sem id de recurso: %s", payload)
        return

    resource_id = str(resource_id)

    if event_type in ("subscription_preapproval", "preapproval"):
        await _handle_preapproval(resource_id, db)
    elif event_type in ("subscription_authorized_payment", "authorized_payment"):
        await _handle_authorized_payment(resource_id, db)
    else:
        logger.info("Webhook do Mercado Pago ignorado: %s", event_type)


async def search_preapprovals(**params) -> list[dict]:
    """Consulta assinaturas no Mercado Pago (por referencia, e-mail ou status)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{MERCADOPAGO_BASE_URL}/preapproval/search",
            params={"limit": 10, **params},
            headers=_get_headers(),
        )

    if response.status_code >= 400:
        raise RuntimeError(
            f"Erro ao buscar assinaturas MP: {response.status_code} - {response.text}"
        )

    return list(response.json().get("results") or [])


async def find_preapproval_for_user(db, user_id: UUID) -> dict | None:
    """Acha a assinatura criada pelo link de plano de um usuario.

    O link de checkout do plano leva o ``external_reference`` do app. Se o
    Mercado Pago nao repassar esse campo, o e-mail do pagador e a segunda
    tentativa.
    """
    results = await search_preapprovals(external_reference=str(user_id))

    if not results:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is not None and user.email:
            results = await search_preapprovals(payer_email=user.email)

    if not results:
        return None

    # Prioriza a assinatura que libera acesso; senao a mais recente.
    ativas = [item for item in results if item.get("status") == "authorized"]
    escolhidas = ativas or results
    escolhidas.sort(key=lambda item: str(item.get("date_created") or ""), reverse=True)
    return dict(escolhidas[0])


async def sync_pending_subscriptions(limit: int = 25) -> None:
    """Conciliacao periodica das assinaturas pendentes.

    O webhook do Mercado Pago pode atrasar ou falhar. Aqui o backend consulta
    a fonte a cada poucos minutos e libera o acesso sozinho, sem depender de o
    cliente abrir a tela de assinatura.
    """
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        return

    from app.database import get_db_context

    recent = datetime.now(UTC) - timedelta(days=7)
    async with get_db_context() as db:
        result = await db.execute(
            select(Subscription.id)
            .where(Subscription.status == "pending")
            .where(Subscription.created_at >= recent)
            .order_by(Subscription.created_at.desc())
            .limit(limit)
        )
        pending_ids = [row[0] for row in result.all()]

    for subscription_id in pending_ids:
        try:
            await sync_preapproval(subscription_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "Falha ao conciliar a assinatura pendente %s",
                subscription_id,
                exc_info=True,
            )


async def sync_preapproval(subscription_id: UUID) -> bool:
    """Sincroniza uma assinatura pendente direto com o Mercado Pago.

    Usado pelo botao "Atualizar status" do app: se o webhook atrasar ou falhar,
    o cliente paga e continua bloqueado. Aqui o status e buscado na fonte.

    Roda em uma sessao propria para que uma falha de rede ou do Mercado Pago
    nao derrube (nem suje) a sessao do request que chamou.
    """
    from app.database import get_db_context

    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        return False

    async with get_db_context() as db:
        result = await db.execute(select(Subscription).where(Subscription.id == subscription_id))
        subscription = result.scalar_one_or_none()
        if subscription is None:
            return False

        try:
            if subscription.mercadopago_subscription_id:
                await _handle_preapproval(subscription.mercadopago_subscription_id, db)
            else:
                # Checkout por plano: a assinatura so existe no Mercado Pago
                # depois que o cliente paga. Procura pela referencia do app.
                preapproval = await find_preapproval_for_user(db, subscription.user_id)
                if preapproval is None:
                    return False
                await _handle_preapproval(str(preapproval["id"]), db)

            # Mesmo sem webhook, grava a cobranca aprovada: e ela que mostra
            # o cartao usado na tela de assinatura.
            if subscription.mercadopago_subscription_id:
                await sync_payments_for_subscription(
                    str(subscription.mercadopago_subscription_id), db
                )
            await db.commit()
            return True
        except Exception:
            logger.warning(
                "Nao foi possivel sincronizar a preapproval da assinatura %s",
                subscription_id,
                exc_info=True,
            )
            return False


async def _handle_preapproval(preapproval_id: str, db) -> None:
    """Sincroniza status e periodo da assinatura com a preapproval."""
    data = await get_preapproval(preapproval_id)
    subscription = await _find_subscription(
        db,
        preapproval_id,
        data.get("external_reference"),
        data.get("payer_email"),
    )

    if subscription is None:
        logger.warning("Preapproval %s sem assinatura correspondente", preapproval_id)
        return

    subscription.mercadopago_subscription_id = preapproval_id
    preapproval_status = data.get("status")

    if preapproval_status in _ACTIVE_PREAPPROVAL_STATUSES:
        subscription.status = "active"
        subscription.auto_renew = True
        subscription.cancelled_at = None
        subscription.cancel_at_period_end = False
    elif preapproval_status == "pending":
        # Nao rebaixa quem ja tem acesso (trial ou assinatura ativa).
        if subscription.status not in ("active", "trial"):
            subscription.status = "pending"
    elif preapproval_status == "paused":
        subscription.status = "past_due"
    elif preapproval_status == "cancelled":
        # Cancelada: corta a recorrencia, mas quem ja pagou o periodo
        # vigente mantem o acesso ate o fim dele (cancelamento "no fim do
        # ciclo"). Cortar na hora seria cobrar por tempo que o cliente nao usa.
        subscription.auto_renew = False
        subscription.cancel_at_period_end = True
        period_end = subscription.current_period_end
        if period_end is not None and period_end.tzinfo is None:
            period_end = period_end.replace(tzinfo=UTC)
        if period_end is None or period_end <= datetime.now(UTC):
            subscription.status = "cancelled"
            subscription.cancelled_at = datetime.now(UTC)

    start = _parse_datetime(data.get("date_created"))
    end = _parse_datetime(data.get("next_payment_date"))
    if start is not None:
        subscription.current_period_start = start
    if end is None and preapproval_status in _ACTIVE_PREAPPROVAL_STATUSES:
        # O fluxo por plano nem sempre devolve next_payment_date. Sem o fim do
        # periodo a assinatura ficaria "ativa" e mesmo assim bloquearia o
        # acesso, porque has_access compara com current_period_end.
        end = _next_period_end(start, data.get("auto_recurring") or {})
    if end is not None:
        subscription.current_period_end = end


async def _handle_authorized_payment(authorized_payment_id: str, db) -> None:
    """Registra a cobranca recorrente e atualiza o acesso do assinante."""
    data = await get_authorized_payment(authorized_payment_id)
    await _record_authorized_payment(data, db)


async def sync_payments_for_subscription(preapproval_id: str, db) -> int:
    """Grava as cobrancas aprovadas encontradas na busca, sem depender do webhook.

    Ignora faturas ainda agendadas (nao cobradas) para nao rebaixar uma
    assinatura que esta em dia. Retorna o numero de faturas registradas.
    """
    try:
        invoices = await search_authorized_payments(preapproval_id)
    except Exception:  # noqa: BLE001
        logger.warning(
            "Falha ao buscar cobrancas da assinatura %s", preapproval_id, exc_info=True
        )
        return 0

    recorded = 0
    for invoice in invoices:
        if invoice.get("status") not in ("processed", "approved"):
            continue
        try:
            if await _record_authorized_payment(invoice, db):
                recorded += 1
        except Exception:  # noqa: BLE001
            logger.warning(
                "Falha ao registrar a cobranca %s da assinatura %s",
                invoice.get("id"),
                preapproval_id,
                exc_info=True,
            )
    return recorded


async def _record_authorized_payment(data: dict, db) -> bool:
    """Grava uma cobranca recorrente a partir do payload ja buscado.

    Idempotente: o Mercado Pago reenvia o mesmo evento se nao receber 200,
    e a conciliacao roda a cada poucos minutos em paralelo ao webhook.
    Retorna ``True`` quando uma cobranca nova foi gravada.
    """
    preapproval_id = data.get("preapproval_id")
    subscription = await _find_subscription(db, preapproval_id, data.get("external_reference"))

    if subscription is None:
        logger.warning(
            "Pagamento autorizado %s sem assinatura correspondente", data.get("id")
        )
        return False

    payment_info = data.get("payment") or {}
    # A busca devolve o id da fatura; o webhook costuma trazer o id do
    # pagamento. Considera os dois para nao gravar a mesma cobranca duas vezes.
    candidates = [
        str(value)
        for value in (payment_info.get("id"), data.get("id"))
        if value is not None
    ]
    mp_payment_id = candidates[0]
    payment_status = data.get("status")

    existing = await db.execute(
        select(Payment).where(Payment.mercadopago_payment_id.in_(candidates))
    )
    if existing.scalar_one_or_none() is not None:
        return False

    approved = payment_status in ("processed", "approved")
    if approved:
        status_label = "approved"
    elif payment_status == "refunded":
        status_label = "refunded"
    else:
        status_label = "rejected"

    amount = data.get("transaction_amount")
    if amount is None:
        amount = payment_info.get("transaction_amount") or 0

    payment = Payment(
        user_id=subscription.user_id,
        subscription_id=subscription.id,
        plan_id=subscription.plan_id,
        mercadopago_payment_id=mp_payment_id,
        amount_cents=int(round(float(amount) * 100)),
        currency=data.get("currency_id", "BRL"),
        status=status_label,
        payment_method=payment_info.get("payment_method_id"),
        paid_at=datetime.now(UTC) if approved else None,
        metadata=data,
    )
    db.add(payment)

    if approved:
        now = datetime.now(UTC)
        subscription.status = "active"
        subscription.auto_renew = True
        subscription.current_period_start = now
        end = _parse_datetime(data.get("next_payment_date"))
        if end is None:
            end = _next_period_end(now, data.get("auto_recurring") or {})
        # Renovacao nunca encurta um periodo que ja estava pago.
        if subscription.current_period_end and subscription.current_period_end > end:
            end = subscription.current_period_end
        subscription.current_period_end = end
    elif status_label == "refunded":
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.now(UTC)
        subscription.auto_renew = False
    else:
        subscription.status = "past_due"
    return True
