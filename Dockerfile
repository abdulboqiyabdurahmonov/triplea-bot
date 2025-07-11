# Базовый образ
FROM python:3.11-slim

# Рабочая директория внутри контейнера
WORKDIR /app

# Скопировать только зависимости сначала (для кэширования)
COPY requirements.txt .

# Установить зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Скопировать весь код приложения
COPY . .

# Открыть порт (тот же, что и WEBAPP_PORT)
EXPOSE 8443

# Команда запуска: uvicorn не нужен, т.к. мы используем aiogram.start_webhook
CMD ["python", "main.py"]
