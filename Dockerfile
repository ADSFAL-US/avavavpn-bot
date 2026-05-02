FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot files
COPY *.py .

# Create data directory
RUN mkdir -p /app/data

# Run bot
CMD ["python", "bot.py"]
