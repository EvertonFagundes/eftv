# services/email_service.py - Envio de emails (verificacao, boas-vindas, etc.)
import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)

_FROM_PATTERN = re.compile(r"^\s*(?P<name>[^<]*?)\s*<(?P<email>[^>]+)>\s*$")

PROVIDERS = ("auto", "brevo", "resend", "dev")


def parse_email_from(value: str) -> tuple[str, str]:
    """Separa ``"Nome <email>"`` em ``(nome, email)``.

    Se nao houver nome, usa o proprio endereco nos dois campos.
    """
    match = _FROM_PATTERN.match(value)
    if match:
        email = match.group("email").strip()
        name = match.group("name").strip().strip('"') or email
        return name, email
    address = value.strip()
    return address, address


class EmailService:
    """
    Servico de envio de emails.

    Provedores suportados, escolhidos por ``EMAIL_PROVIDER``:

    - ``brevo``: API HTTPS do Brevo (funciona no Render free, que bloqueia SMTP);
    - ``resend``: alternativa;
    - ``auto`` (padrao): Brevo se houver ``BREVO_API_KEY``, senao Resend,
      senao modo desenvolvimento;
    - ``dev``: nao envia; registra o conteudo no log para testes.

    Sem nenhum provedor configurado o cadastro continua funcionando e o link
    aparece no log. Em producao, configure ``BREVO_API_KEY``.
    """

    def __init__(self) -> None:
        self.brevo_api_key = settings.BREVO_API_KEY
        self.resend_api_key = settings.RESEND_API_KEY
        self.provider = self._resolve_provider(settings.EMAIL_PROVIDER)
        self.from_email = settings.EMAIL_FROM
        self.frontend_url = settings.FRONTEND_URL

    def _resolve_provider(self, configured: str) -> str:
        configured = (configured or "auto").strip().lower()
        if configured not in PROVIDERS:
            logger.warning("EMAIL_PROVIDER desconhecido (%s); usando auto", configured)
            configured = "auto"

        if configured != "auto":
            return configured
        if self.brevo_api_key:
            return "brevo"
        if self.resend_api_key:
            return "resend"
        return "dev"

    async def send_verification_email(
        self,
        to_email: str,
        token: str,
        full_name: str | None = None,
    ) -> bool:
        """
        Envia email de verificacao de conta com link contendo o token.

        Retorna True se enviado com sucesso (ou simulado em dev sem chave).
        """
        if "localhost" in self.frontend_url and not settings.DEBUG:
            # Em producao o destinatario nao consegue abrir localhost.
            logger.error(
                "FRONTEND_URL aponta para localhost (%s); o link de verificacao "
                "nao funciona fora da maquina local",
                self.frontend_url,
            )

        verification_url = f"{self.frontend_url.rstrip('/')}/verify-email.html?token={token}"

        subject = "Confirme seu email - EFTV"
        html_body = self._verification_html(full_name, token, verification_url)
        text_body = (
            f"Olá{', ' + full_name if full_name else ''}!\n"
            f"Confirme seu email no EFTV acessando:\n{verification_url}\n"
            f"O codigo expira em {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} horas.\n"
            f"Se voce nao solicitou este email, ignore esta mensagem."
        )

        return await self._send(to_email, subject, text_body, html_body)

    async def send_password_reset_email(
        self,
        to_email: str,
        code: str,
        full_name: str | None = None,
    ) -> bool:
        """Envia o codigo de recuperacao de senha (valido por 30 minutos)."""

        subject = "Codigo para redefinir sua senha - EFTV"
        text_body = (
            f"Ola{', ' + full_name if full_name else ''}!\n"
            f"Seu codigo para redefinir a senha do EFTV e: {code}\n"
            "Ele expira em 30 minutos.\n"
            "Se voce nao pediu para redefinir a senha, ignore este email."
        )
        html_body = (
            f"<p>Ola{', ' + full_name if full_name else ''}!</p>"
            "<p>Seu codigo para redefinir a senha do EFTV e:</p>"
            f"<p style=\"font-size:28px;font-weight:bold;letter-spacing:6px\">{code}</p>"
            "<p>Ele expira em 30 minutos.</p>"
            "<p>Se voce nao pediu para redefinir a senha, ignore este email.</p>"
        )
        return await self._send(to_email, subject, text_body, html_body)

    async def send_welcome_email(
        self,
        to_email: str,
        full_name: str | None = None,
    ) -> bool:
        """Envia email de boas-vindas apos verificacao bem-sucedida."""
        subject = "Bem-vindo ao EFTV - 7 dias grátis ativados"
        text_body = (
            f"Olá{', ' + full_name if full_name else ''}!\n"
            f"Seu email foi confirmado e seus 7 dias gratis foram ativados.\n"
            f"Aproveite o EFTV!\n"
        )
        html_body = f"<p>Olá{', ' + full_name if full_name else ''}!</p><p>Seu email foi confirmado e seus <strong>7 dias gratis</strong> foram ativados. Aproveite o EFTV!</p>"
        return await self._send(to_email, subject, text_body, html_body)

    async def _send(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        """Envia pelo provedor configurado; em dev apenas registra no log."""
        if self.provider == "brevo":
            if not self.brevo_api_key:
                logger.error(
                    "EMAIL_PROVIDER=brevo sem BREVO_API_KEY; email para %s nao enviado",
                    to_email,
                )
                return False
            if self.brevo_api_key.startswith("xsmtpsib-"):
                # Chave SMTP nao serve na API v3, e o Render free bloqueia SMTP.
                logger.error(
                    "BREVO_API_KEY e uma chave SMTP (xsmtpsib-...). Crie uma API key "
                    "v3 em SMTP & API > API Keys (xkeysib-...); email para %s nao enviado",
                    to_email,
                )
                return False
            return await self._send_via_brevo(to_email, subject, text_body, html_body)

        if self.provider == "resend":
            if not self.resend_api_key:
                logger.error(
                    "EMAIL_PROVIDER=resend sem RESEND_API_KEY; email para %s nao enviado",
                    to_email,
                )
                return False
            return await self._send_via_resend(to_email, subject, text_body, html_body)

        # Sem provedor configurado (desenvolvimento): registra o email no log
        # e segue o fluxo, para dar para testar o cadastro sem enviar nada.
        logger.info("Email (modo dev) para %s: %s | %s", to_email, subject, text_body)
        return True

    def _brevo_payload(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> dict[str, object]:
        sender_name, sender_email = parse_email_from(self.from_email)
        payload: dict[str, object] = {
            "sender": {"name": sender_name, "email": sender_email},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": text_body,
        }
        if html_body:
            payload["htmlContent"] = html_body
        return payload

    async def _send_via_brevo(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        """Envia email pela API HTTPS do Brevo (porta 443)."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": self.brevo_api_key or "",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=self._brevo_payload(to_email, subject, text_body, html_body),
                )
        except Exception:
            # Em falha de rede/provedor, nao bloqueia o fluxo de registro;
            # o token ainda esta valido e pode ser reenviado.
            logger.exception("Falha ao enviar email via Brevo")
            return False

        if response.status_code not in (200, 201, 202):
            logger.error(
                "Brevo recusou email: HTTP %s | %s",
                response.status_code,
                response.text[:300],
            )
            return False
        return True

    async def _send_via_resend(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str | None = None,
    ) -> bool:
        """Envia email usando a API do Resend."""
        try:
            import httpx

            payload = {
                "from": self.from_email,
                "to": [to_email],
                "subject": subject,
                "text": text_body,
            }
            if html_body:
                payload["html"] = html_body

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {self.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except Exception:
            logger.exception("Falha ao enviar email via Resend")
            return False

        if response.status_code not in (200, 201, 202):
            logger.error(
                "Resend recusou email: HTTP %s | %s",
                response.status_code,
                response.text[:300],
            )
            return False
        return True

    @staticmethod
    def _verification_html(
        full_name: str | None,
        token: str,
        verification_url: str,
    ) -> str:
        name = f", {full_name}" if full_name else ""
        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #e50914;">Confirme seu email - EFTV</h2>
            <p>Olá{name},</p>
            <p>Obrigado por se cadastrar no EFTV! Para completar seu cadastro e ativar seus
            <strong>7 dias gratis</strong>, confirme seu email clicando no botao abaixo:</p>
            <p style="text-align: center; margin: 30px 0;">
                <a href="{verification_url}"
                   style="background-color: #e50914; color: white; padding: 12px 24px;
                          text-decoration: none; border-radius: 6px; font-weight: bold;">
                    Confirmar email
                </a>
            </p>
            <p>Ou copie e cole este link no navegador:<br>
            <code>{verification_url}</code></p>
            <p>Este link expira em {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} horas.</p>
            <p>Se voce nao solicitou este cadastro, ignore este email.</p>
            <hr>
            <p style="font-size: 12px; color: #666;">EFTV - Plataforma de Streaming</p>
        </body>
        </html>
        """
