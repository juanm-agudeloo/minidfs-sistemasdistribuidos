Estado actual: Avance 2 ✅
DataNode real con almacenamiento de bloques en disco, pipeline de replicación, 
proxy de bloques en el NameNode y namespace de archivos.

Componentes incluidos
ComponenteDescripciónshared/config.pyVariables de entorno del sistemanamenode/API FastAPI (puerto 8000) — único punto de entrada públiconamenode/routes/files.pyNamespace: put,
get, ls, mkdir, rmnamenode/routes/blocks.pyProxy PUT/GET de bloques hacia DataNodes (cliente nunca ve IPs privadas)namenode/services/block_manager.pyAlgoritmo de asignación y
selección de DataNodesnamenode/services/block_proxy.pyStreaming proxy con failover entre réplicasdatanode/API FastAPI por cada nodo de almacenamientodatanode/services/storage.
pyLeer/escribir/listar/borrar bloques en discodatanode/services/heartbeat.pyTarea background: registro y heartbeat al NameNode por IP privadadocker-compose.ymlNameNode + 3 DataNodes en red interna
dfs-nettests/Pruebas de registro, heartbeat y detección DEAD (Avance 1)

Arquitectura
Cliente CLI
    │
    │ HTTP (puerto 8000)
    ▼
 NameNode  ◄──── único punto público
    │
    │ IP privada (dfs-net / VPC)
    ├──► DataNode1
    ├──► DataNode2
    └──► DataNode3
El cliente nunca conoce las IPs de los DataNodes. Todo pasa por el NameNode.

Arranque local
bashdocker compose up --build

NameNode API: http://localhost:8000/docs
Usuario demo: demo / demo123
Los 3 DataNodes se registran automáticamente en el NameNode al arrancar.


Probar con curl
bash# 1. Login → obtener JWT
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Verificar DataNodes registrados
curl -s http://localhost:8000/nodes/ | python -m json.tool

# 3. Crear directorio
curl -s -X POST http://localhost:8000/files/mkdir \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path":"/test"}'

# 4. Registrar archivo y obtener block_ids
RESP=$(curl -s -X POST http://localhost:8000/files/put \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"path":"/test/archivo.bin","size_bytes":1048576}')
echo $RESP

BLOCK_ID=$(echo $RESP | python -c "import sys,json; print(json.load(sys.stdin)['blocks'][0]['block_id'])")

# 5. Subir bloque de prueba (1 MB)
dd if=/dev/urandom of=/tmp/test_block.bin bs=1M count=1
curl -s -X POST "http://localhost:8000/blocks/$BLOCK_ID" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @/tmp/test_block.bin

# 6. Verificar replicación en 2 DataNodes
docker exec mini-dfs-datanode1 ls //data/blocks/
docker exec mini-dfs-datanode2 ls //data/blocks/
docker exec mini-dfs-datanode3 ls //data/blocks/

# 7. Descargar bloque de vuelta (via proxy NameNode)
curl -s "http://localhost:8000/blocks/$BLOCK_ID" \
  -H "Authorization: Bearer $TOKEN" \
  --output /tmp/bloque_descargado.bin

Nota Windows (Git Bash): usar //data/blocks/ en lugar de /data/blocks/ para evitar conversión de rutas.


Tests (Avance 1)
bashpip install -r namenode/requirements.txt -r tests/requirements.txt
pytest tests/ -v

Próximos avances

Avance 3: CLI completa (put, get, ls, mkdir, rm, rmdir), re-replicación automática cuando cae un DataNode, prueba end-to-end con archivo de 200+ MB.


Ramas
RamaContenidoavance-1-namenodeNameNode base: auth, heartbeats, monitoravance-2-datanodeDataNode, proxy de bloques, replicación, namespaceavance-3-clienteCLI completa, re-replicación, pruebas finales
