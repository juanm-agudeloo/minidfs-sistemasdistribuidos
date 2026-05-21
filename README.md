# Mini-DFS — Sistema de Archivos Distribuido por Bloques

Sistema de archivos distribuido minimalista inspirado en HDFS/GFS. Los archivos se
fragmentan en bloques, se distribuyen entre varios DataNodes y se replican en como
mínimo 2 nodos. Un **NameNode** central es el **único punto de entrada público** y
actúa como proxy de bloques: el cliente nunca conoce ni contacta las IPs de los
DataNodes.

**Estado actual: Avance 3 ✅** — sistema completo end-to-end: CLI del cliente,
`put`/`get` con fragmentación y reensamble, namespace completo y re-replicación
automática ante caída de un DataNode.

---

## Arquitectura

```
Cliente CLI
    │  HTTP (puerto 8000) — metadatos + transferencia de bloques (proxy)
    ▼
 NameNode   ◄──── único punto público
    │  IP privada (dfs-net / VPC)
    ├──► DataNode1
    ├──► DataNode2
    └──► DataNode3
```

El cliente solo habla con el NameNode. Los DataNodes son privados (sin IP pública en
AWS, sin `ports:` expuestos en Docker). Semántica **WORM** (Write-Once-Read-Many).

### Componentes

| Componente | Descripción |
|---|---|
| `shared/config.py` | Variables de entorno del sistema |
| `namenode/` | API FastAPI (puerto 8000), único punto público |
| `namenode/routes/auth.py` | Login → JWT |
| `namenode/routes/nodes.py` | Registro y heartbeats de DataNodes |
| `namenode/routes/files.py` | Namespace: put, get, ls, mkdir, rm, rmdir |
| `namenode/routes/blocks.py` | Proxy PUT/GET de bloques hacia DataNodes |
| `namenode/services/block_manager.py` | Asignación y selección de DataNodes |
| `namenode/services/block_proxy.py` | Streaming proxy con failover entre réplicas |
| `namenode/services/monitor.py` | Detección de nodos DEAD + **re-replicación automática** |
| `datanode/` | API FastAPI por cada nodo de almacenamiento |
| `datanode/services/storage.py` | Leer/escribir/listar/borrar bloques en disco |
| `datanode/services/heartbeat.py` | Registro y heartbeat al NameNode por IP privada |
| `client/dfs_client.py` | Fragmentación, PUT/GET vía NameNode |
| `client/cli.py` | CLI Click: put, get, ls, mkdir, rm, rmdir |
| `docker-compose.yml` | NameNode + 3 DataNodes en red interna `dfs-net` |
| `tests/` | Pruebas de heartbeat/DEAD (Avance 1), namespace y re-replicación (Avance 3) |

---

## Arranque local

```bash
docker compose up --build
```

- NameNode API: http://localhost:8000/docs
- Usuario demo: `demo` / `demo123`
- Los 3 DataNodes se registran automáticamente en el NameNode al arrancar.

---

## Uso de la CLI

La CLI apunta **solo al NameNode**. Tras el login, la URL y el token JWT se guardan
en `~/.dfs_config`.

```bash
pip install -r client/requirements.txt

# 1. Login (guarda token en ~/.dfs_config)
python client/cli.py --url http://localhost:8000 login -u demo -p demo123

# 2. Crear directorio
python client/cli.py mkdir /datos

# 3. Subir un archivo (fragmenta + distribuye + replica)
python client/cli.py put pelicula.bin /datos/pelicula.bin

# 4. Listar
python client/cli.py ls /datos

# 5. Descargar y reconstruir
python client/cli.py get /datos/pelicula.bin ./descarga.bin

# 6. Borrar archivo (y sus bloques en los DataNodes)
python client/cli.py rm /datos/pelicula.bin

# 7. Borrar directorio vacío
python client/cli.py rmdir /datos
```

En AWS se usa la IP pública del NameNode: `--url http://<EIP_namenode>:8000`.

---

## Probar con curl

```bash
# 1. Login → obtener JWT
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Verificar DataNodes registrados
curl -s http://localhost:8000/nodes/ | python -m json.tool

# 3. Registrar archivo y obtener block_ids
RESP=$(curl -s -X POST http://localhost:8000/files/put \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"path":"/test/archivo.bin","size_bytes":1048576}')
BLOCK_ID=$(echo $RESP | python -c "import sys,json; print(json.load(sys.stdin)['blocks'][0]['block_id'])")

# 4. Subir bloque (via proxy del NameNode)
dd if=/dev/urandom of=/tmp/test_block.bin bs=1M count=1
curl -s -X POST "http://localhost:8000/blocks/$BLOCK_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" --data-binary @/tmp/test_block.bin

# 5. Verificar replicación en los DataNodes
docker exec mini-dfs-datanode1 ls //data/blocks/
docker exec mini-dfs-datanode2 ls //data/blocks/

# 6. Descargar el bloque de vuelta (via proxy del NameNode)
curl -s "http://localhost:8000/blocks/$BLOCK_ID" \
  -H "Authorization: Bearer $TOKEN" --output /tmp/bloque_descargado.bin
```

> Nota Windows (Git Bash): usar `//data/blocks/` en lugar de `/data/blocks/`.

---

## Tolerancia a fallos: re-replicación automática

El monitor del NameNode (`services/monitor.py`) corre en background y cada 2 s:

1. Marca como **DEAD** los DataNodes sin heartbeat por más de `HEARTBEAT_TIMEOUT`.
2. Para cada bloque cuyas réplicas **activas** sean menos que `REPLICATION_FACTOR`,
   copia el bloque desde una réplica viva a otro DataNode activo (comunicación por IP
   privada) y actualiza los metadatos.

Cuando un DataNode caído vuelve y envía heartbeat, se reactiva automáticamente.

---

## Tests

```bash
pip install -r namenode/requirements.txt -r tests/requirements.txt
pytest tests/ -v
```

- `test_avance1_namenode.py` — registro, heartbeat y detección DEAD.
- `test_avance3.py` — namespace (mkdir/ls/rmdir/rm) y re-replicación automática.

---

## Prueba final end-to-end (archivo grande)

```bash
# Crear un archivo de 200 MB
dd if=/dev/urandom of=grande.bin bs=1M count=200

python client/cli.py --url http://localhost:8000 login -u demo -p demo123
python client/cli.py mkdir /grande
python client/cli.py put grande.bin /grande/grande.bin     # ~4 bloques de 64 MB

# Bajar un DataNode y verificar que el archivo sigue disponible
docker stop mini-dfs-datanode1
sleep 12   # > HEARTBEAT_TIMEOUT: el monitor lo marca DEAD y re-replica

python client/cli.py get /grande/grande.bin ./recuperado.bin
# Verificar integridad
diff grande.bin recuperado.bin && echo "OK: archivo íntegro tras caída de DataNode"
```

---

## Despliegue en AWS Academy

La infraestructura (VPC con subred pública para el NameNode y subred privada para los
DataNodes, NAT Gateway, Security Groups, EC2 + userdata con Docker) está documentada
en `CURSOR_CONTEXT_MINI_DFS.md` (sección 15), lista para llevar a `infra/*.tf` con
Terraform. Puntos clave de AWS Academy: credenciales temporales (renovar cada ~4 h),
rol fijo `LabRole`, región `us-east-1`, `terraform destroy` al terminar.

---

## Ramas

| Rama | Contenido |
|---|---|
| `avance-1-namenode` | NameNode base: auth, heartbeats, monitor |
| `avance-2-datanode` | DataNode, proxy de bloques, replicación, namespace |
| `avance-3-cliente` | CLI completa, GET, re-replicación, pruebas finales |
