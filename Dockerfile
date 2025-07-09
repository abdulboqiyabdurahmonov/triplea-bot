# 1) Берём официальный образ Python 3.11
FROM python:3.11-slim

# 2) Рабочая папка
WORKDIR /app

# 3) Копируем код
COPY . /app

# 4) Ставим зависимости
RUN pip install --no-cache-dir -r requirements.txt

# 5) Запуск polling-бота
CMD ["python", "main.py"]

