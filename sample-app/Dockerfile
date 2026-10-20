FROM python:3.11-slim

# Create non-root app user
RUN useradd -m -u 1000 appuser

WORKDIR /app

COPY app.py /app/app.py

USER appuser

EXPOSE 8080

CMD ["python", "app.py"]
