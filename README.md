# Mini-DFS — Sistema de Archivos Distribuido por Bloques

Proyecto académico UPB — Arquitecturas de Nube y Sistemas Distribuidos.

## Estado actual: Avance 1 ✅

Infraestructura base del **NameNode**: autenticación JWT, registro de DataNodes, heartbeats y monitor que marca nodos caídos como `DEAD`.

### Componentes incluidos

| Componente | Descripción |
|---|---|
| `shared/config.py` | Variables de entorno del sistema |
| `namenode/` | API FastAPI (puerto 8000) |
| `docker-compose.yml` | Solo NameNode (Avance 2 añadirá DataNodes) |
| `tests/` | Pruebas de registro, heartbeat y detección DEAD |

### Arranque local

```bash
docker compose up --build namenode
```

API: http://localhost:8000/docs

Usuario demo: `demo` / `demo123`

### Probar con curl

```bash
# Login
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}'

# Registrar DataNode ficticio (IP privada simulada)
curl -s -X POST http://localhost:8000/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"node_id":"datanode-0","address":"10.0.2.10","port":8001,"free_space_bytes":10000000000}'

# Heartbeat (usar node_token de la respuesta anterior)
curl -s -X POST http://localhost:8000/nodes/heartbeat \
  -H "Authorization: Bearer <node_token>" \
  -H "Content-Type: application/json" \
  -d '{"free_space_bytes":9000000000,"blocks_count":0,"block_ids":[]}'

# Listar DataNodes
curl -s http://localhost:8000/nodes/
```

### Tests

```bash
pip install -r namenode/requirements.txt -r tests/requirements.txt
pytest tests/ -v
```

### Próximos avances

- **Avance 2:** DataNode real, proxy de bloques, pipeline de replicación
- **Avance 3:** CLI completa (`put`, `get`, `ls`, …), re-replicación automática

### Rama sugerida

`avance-1-namenode`
