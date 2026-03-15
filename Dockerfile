FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY .env.example ./.env.example

WORKDIR /app/backend

EXPOSE 8000

CMD ["python", "start.py"]
