FROM python:3.11-slim

ARG APP_GIT_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SMART_LIFE_BOT_BUILD_SHA=${APP_GIT_SHA}

WORKDIR /app

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

RUN mkdir -p /app/data && chown -R 10001:10001 /app

USER 10001:10001

CMD ["python", "-m", "smart_life_bot.bot.telegram_polling"]
