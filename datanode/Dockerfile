FROM python:3.11-slim
WORKDIR /app
COPY datanode/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ /app/shared/
COPY datanode/ /app/datanode/
ENV PYTHONPATH=/app
CMD ["uvicorn", "datanode.main:app", "--host", "0.0.0.0", "--port", "8001"]
