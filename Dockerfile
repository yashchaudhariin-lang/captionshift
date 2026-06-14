FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    g++ \
    gcc \
    build-essential \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY index.html .
COPY fonts/ ./fonts/

EXPOSE 7860

CMD ["python", "app.py"]
