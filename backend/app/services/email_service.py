# services/email_service.py - Envio de emails (verificacao, boas-vindas, etc.)
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """
    Servico de envio de emails.

    Em producao usa Resend (RESEND_API_KEY). Em desenvolvimento, se nao houver
    chave configurada, apenas imprime o conteúdo no log (ou grava em arquivo)
    para permitir testes sem configurar um provedor de email real.
    """

    def __init__(self) -> None:
        self.api_key = settings.RESEND_API_KEY
        self.from_email = settings.EMAIL_FROM
        self.frontend_url = settings.FRONTEND_URL

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
        verification_url = f"{self.frontend_url}/verify-email?token={token}"

        subject = "Confirme seu email - EFTV"
        html_body = self._verification_html(full_name, token, verification_url)
        text_body = (
            f"Olá{', ' + full_name if full_name else ''}!\n"
            f"Confirme seu email no EFTV acessando:\n{verification_url}\n"
            f"O codigo expira em {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} horas.\n"
            f"Se voce nao solicitou este email, ignore esta mensagem."
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
        """
        Envia email real via Resend se houver API key; caso contrario, apenas
        registra no log (modo desenvolvimento).
        """
        if self.api_key:
            return await self._send_via_resend(to_email, subject, text_body, html_body)

        # Sem provedor configurado (desenvolvimento): registra o email no log
        # e segue o fluxo, para dar para testar o cadastro sem enviar nada.
        logger.info("Email (modo dev) para %s: %s | %s", to_email, subject, text_body)
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
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                return response.status_code in (200, 201, 202)
        except Exception:
            # Em falha de rede/provedor, nao bloqueia o fluxo de registro;
            # o token ainda esta valido e pode ser reenviado.
            return False

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
