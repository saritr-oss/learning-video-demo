FROM python:3.11-slim

WORKDIR /app

# Copy all application files
COPY . .

# Expose the port Cloud Run will use
EXPOSE 8080

# Run the server
CMD ["python3", "server.py"]
