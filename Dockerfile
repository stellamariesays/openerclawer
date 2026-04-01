FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway.py memory.py ./
COPY workspace/ workspace/

# Config and memory are mounted at runtime, not baked in
VOLUME ["/app/config.json", "/app/memory"]

CMD ["python3", "gateway.py"]
