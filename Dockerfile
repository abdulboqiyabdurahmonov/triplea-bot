# 1) Берём официальный образ с Python 3.11
FROM python:3.11-slim

# 2) Рабочая папка внутри контейнера
WORKDIR /app

# 3) Копируем всё из репо в контейнер
COPY . /app

# 4) Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# 5) Открываем порт 8000 (Render проксирует его на $PORT)
EXPOSE 8000

# 6) Команда старта сервера
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
