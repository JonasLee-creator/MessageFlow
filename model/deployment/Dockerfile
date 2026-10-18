FROM python:3.11-slim
WORKDIR /app/model
COPY model/deployment/requirements.txt /tmp/model-requirements.txt
RUN pip install --no-cache-dir -r /tmp/model-requirements.txt
COPY model/evaluation ./evaluation
COPY model/src ./src
COPY model/config ./config
COPY model/deployment ./deployment
ENV PYTHONPATH=/app/model:/app/model/src PYTHONDONTWRITEBYTECODE=1
EXPOSE 8088
CMD ["python", "-m", "deployment.server", "--host", "0.0.0.0", "--port", "8088"]
