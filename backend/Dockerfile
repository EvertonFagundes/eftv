# Dockerfile - Backend container
FROM python:3.12-slim

# Instala dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Define diretório de trabalho
WORKDIR /app

# Copia requirements e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código da aplicação
COPY . .

# Copia entrypoint e dá permissão de execução (ainda como root)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Usuário não-root para segurança
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expõe porta
EXPOSE 8000

# Comando de inicialização (Render/Heroku injetam PORT; local usa 8000)
ENTRYPOINT ["/app/entrypoint.sh"]