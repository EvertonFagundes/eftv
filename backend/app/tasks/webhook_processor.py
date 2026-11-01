# tasks/webhook_processor.py - Processa webhooks assíncronos


async def process_pending_webhooks(limit: int = 100) -> int:
    """
    Processa webhooks pendentes salvos no banco.
    Útil para retry de webhooks que falharam.
    Returns: número de webhooks processados.
    """
    # TODO: Implementar tabela de webhook_queue para retry
    # Por enquanto apenas placeholder
    return 0


async def save_webhook_for_retry(payload: dict, error: str | None = None) -> None:
    """
    Salva webhook para processamento posterior (retry).
    """
    # TODO: Implementar tabela webhook_queue
    pass
