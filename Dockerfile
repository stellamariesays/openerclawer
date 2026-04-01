FROM python:3.12-slim

# Node.js 22 for pi coding agent
RUN apt-get update && apt-get install -y curl &&     curl -fsSL https://deb.nodesource.com/setup_22.x | bash - &&     apt-get install -y nodejs &&     apt-get clean && rm -rf /var/lib/apt/lists/*

# Install pi
RUN npm install -g @mariozechner/pi-coding-agent

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway.py memory.py ./
COPY workspace/ workspace/

VOLUME ["/app/config.json", "/app/memory"]

CMD ["python3", "gateway.py"]
