FROM python:3.11-slim

WORKDIR /app

COPY namenode/requirements.txt ./namenode/requirements.txt
RUN pip install --no-cache-dir -r namenode/requirements.txt

COPY shared/ ./shared/
COPY namenode/ ./namenode/

ENV PYTHONPATH=/app
ENV DB_URL=sqlite:////data/namenode.db
ENV NAMENODE_PRIVATE_HOST=namenode

EXPOSE 8000

CMD ["uvicorn", "namenode.main:app", "--host", "0.0.0.0", "--port", "8000"]
