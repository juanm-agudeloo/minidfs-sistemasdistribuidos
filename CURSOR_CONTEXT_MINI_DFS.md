# CONTEXTO COMPLETO – PROYECTO MINI-DFS
## Para Cursor AI — Leer antes de generar cualquier código

---

## 1. CONTEXTO ACADÉMICO

- **Universidad:** Universidad Pontificia Bolivariana (UPB), Medellín
- **Curso:** Arquitecturas de Nube y Sistemas Distribuidos
- **Docente:** Álvaro Ospina Sanjuan
- **Proyecto vale:** 20% de la nota final
- **Fecha de entrega:** 24 de mayo de 2026 (GMT-5)
- **Modalidad:** Grupal (todos los integrantes deben participar con commits en el repositorio)

---

## 2. QUÉ HAY QUE CONSTRUIR

Un **Sistema de Archivos Distribuidos por Bloques (Mini-DFS)** minimalista, inspirado en HDFS/GFS, con las siguientes características:

- Archivos se dividen en **bloques de 64 MB** (configurable).
- Los bloques se distribuyen entre múltiples **DataNodes**.
- Cada bloque se **replica en mínimo 2 DataNodes distintos** en todo momento.
- Un **NameNode central** gestiona todos los metadatos **y actúa como único punto de entrada** para el cliente (incluida la transferencia de bloques).
- Un **Cliente CLI** permite operar el sistema.
- El sistema corre sobre **Internet real** (AWS Academy EC2 + Docker).
- Semántica **WORM** (Write-Once-Read-Many): no hay actualización parcial de archivos.

---

## 3. ARQUITECTURA DEL SISTEMA

```
┌─────────────────────────────────────────────────────────────────┐
│                     INTERNET / CLIENTE CLI                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ IP Pública (puerto 8000)
                            │ Metadatos + Transferencia de bloques (proxy)
              ┌─────────────▼──────────────┐
              │         NameNode           │  ← IP Pública expuesta
              │   (Maestro + API Gateway)  │    Solo nodo accesible
              └──┬───────────┬─────────────┘    desde Internet
                 │           │   IP Privada VPC (10.0.2.x)
                 │ HB/mgmt   │   Pipeline de replicación
        ┌────────▼───┐  ┌────▼───────┐  ┌────────────┐
        │ DataNode1  │  │ DataNode2  │  │ DataNode3  │
        │ 10.0.2.10  │  │ 10.0.2.11  │  │ 10.0.2.12  │
        │ (privado)  │  │ (privado)  │  │ (privado)  │
        └────────────┘  └────────────┘  └────────────┘
             Solo accesibles dentro de la VPC (sin IP pública)
```

### 3.1 NameNode
- Servidor central de metadatos y **único punto de entrada público**.
- Mantiene el **árbol de directorios y archivos** (namespace).
- Tabla principal: `archivo → [bloque_0, bloque_1, ...] → [DataNode_A, DataNode_B]`
- Gestiona el registro y monitoreo de DataNodes via **heartbeats** usando **IPs privadas** de la VPC.
- Detecta nodos caídos e inicia **re-replicación automática** comunicándose con DataNodes por IP privada.
- **Proxy de bloques**: recibe datos de bloques del cliente y los reenvía a los DataNodes internamente; también recupera bloques desde DataNodes y los entrega al cliente. El cliente NUNCA habla directamente con un DataNode.
- Persiste metadatos en base de datos (SQLite en desarrollo, PostgreSQL en producción).

### 3.2 DataNode
- Almacena bloques como archivos binarios locales nombrados por `block_id`.
- Expone API REST para recibir y enviar bloques — **solo accesible desde dentro de la VPC** (sin IP pública).
- Envía **heartbeat cada 3 segundos** al NameNode usando la **IP privada del NameNode**.
- Implementa el **pipeline de replicación**: al recibir un bloque, lo reenvía al siguiente DataNode en la cadena si se le indica (comunicación DataNode↔DataNode por IP privada).

### 3.3 Cliente
- CLI en Python.
- Se autentica con user/password → recibe JWT token.
- Cada usuario gestiona **solo sus propios archivos**.
- Para `put`: fragmenta el archivo localmente → pide asignación al NameNode → transfiere bloques **al NameNode** (que los proxea internamente a los DataNodes).
- Para `get`: pide lista de bloques al NameNode → descarga bloques **desde el NameNode** (que los recupera internamente desde los DataNodes) → reensambla el archivo.
- El cliente **nunca necesita conocer las IPs de los DataNodes**.

### 3.4 Topología de Red VPC (AWS)

```
VPC: 10.0.0.0/16
│
├── Subred pública  10.0.1.0/24   (us-east-1a)
│     └── NameNode   — IP privada: 10.0.1.x  |  IP pública: EIP
│
└── Subred privada  10.0.2.0/24   (us-east-1a)
      ├── DataNode0  — IP privada: 10.0.2.10  (sin IP pública)
      ├── DataNode1  — IP privada: 10.0.2.11  (sin IP pública)
      └── DataNode2  — IP privada: 10.0.2.12  (sin IP pública)

Internet Gateway → Subred pública → NameNode
NAT Gateway      → Subred privada → DataNodes pueden hacer egress
                                     (para clonar repo, descargar Docker, etc.)
```

**Reglas de tráfico:**
| Origen | Destino | Puerto | Via |
|---|---|---|---|
| Cliente (Internet) | NameNode | 8000 | IP pública / EIP |
| NameNode | DataNode | 8001–8003 | IP privada VPC |
| DataNode | NameNode | 8000 | IP privada VPC |
| DataNode | DataNode | 8001–8003 | IP privada VPC (pipeline) |
| Admin | NameNode | 22 | IP pública (SSH) |
| Admin | DataNode | 22 | Via NameNode como bastión (opcional) |

---

## 4. OPERACIONES REQUERIDAS

| Comando | Descripción |
|---|---|
| `put <archivo>` | Sube un archivo al DFS (fragmenta + distribuye + replica) |
| `get <archivo>` | Descarga y reconstruye un archivo del DFS |
| `ls [ruta]` | Lista contenido de un directorio |
| `mkdir <ruta>` | Crea directorio en el namespace |
| `rm <archivo>` | Elimina archivo y sus bloques |
| `rmdir <ruta>` | Elimina directorio vacío |

---

## 5. APIS REST DEFINIDAS

### NameNode (puerto 8000) — único endpoint público

| Método | Endpoint | Auth | Descripción |
|---|---|---|---|
| POST | `/auth/login` | No | Login → JWT token |
| POST | `/files/put` | JWT | Solicita asignación de bloques para nuevo archivo |
| GET | `/files/get/{path}` | JWT | Retorna lista ordenada de block_ids (sin IPs de DataNodes) |
| GET | `/files/ls/{path}` | JWT | Lista directorio |
| POST | `/files/mkdir` | JWT | Crea directorio |
| DELETE | `/files/rm/{path}` | JWT | Elimina archivo |
| DELETE | `/files/rmdir/{path}` | JWT | Elimina directorio |
| POST | `/blocks/{block_id}` | JWT | **PROXY PUT**: recibe bloque del cliente y lo distribuye a DataNodes |
| GET | `/blocks/{block_id}` | JWT | **PROXY GET**: recupera bloque desde un DataNode y lo entrega al cliente |
| POST | `/nodes/register` | No | DataNode se registra (solo desde dentro de la VPC) |
| POST | `/nodes/heartbeat` | Token | DataNode envía heartbeat + block report (solo desde VPC) |

> **Nota:** Las IPs privadas de los DataNodes **nunca se exponen** al cliente. Los endpoints `/blocks/{block_id}` del NameNode actúan como API Gateway transparente.

### DataNode (puerto configurable, default 8001) — solo acceso interno VPC

| Método | Endpoint | Descripción |
|---|---|---|
| POST | `/blocks/{block_id}` | Recibe y almacena un bloque (stream binario). Query param `next_node` para pipeline |
| GET | `/blocks/{block_id}` | Retorna bloque como stream binario |
| DELETE | `/blocks/{block_id}` | Elimina bloque local |
| GET | `/blocks` | Lista block_ids almacenados |
| GET | `/health` | Estado del nodo: espacio libre, bloques totales, uptime |

---

## 6. FLUJO PUT (paso a paso)

1. Cliente → NameNode `POST /auth/login` → recibe JWT
2. Cliente → NameNode `POST /files/put` con nombre y tamaño → recibe lista `[{block_id}, ...]` (sin IPs)
3. Para cada bloque:
   - Cliente → NameNode: `POST /blocks/{block_id}` con datos binarios (stream)
   - NameNode (internamente, usando IPs privadas) → DN_primary: `POST /blocks/{block_id}?next_node=DN_replica_private_ip` con datos
   - DN_primary almacena localmente y reenvía a DN_replica por IP privada (pipeline)
   - NameNode confirma éxito al cliente
4. Cliente → NameNode: confirmación de escritura completa
5. NameNode persiste metadatos definitivos

## 6.1 FLUJO GET (paso a paso)

1. Cliente → NameNode: `GET /files/get/{path}` con JWT → recibe lista ordenada de `[{block_id, index}, ...]` (sin IPs)
2. Para cada bloque en orden:
   - Cliente → NameNode: `GET /blocks/{block_id}`
   - NameNode (internamente) → DN_A private IP: `GET /blocks/{block_id}` → datos binarios
   - Si DN_A falla, NameNode intenta DN_B (failover interno, transparente al cliente)
   - NameNode retransmite los datos al cliente
3. Cliente escribe bloques en orden al archivo destino local

---

## 7. ALGORITMOS CLAVE

### Particionamiento (cliente)
```
bloques = ceil(tamaño_archivo / BLOCK_SIZE)
block_id = uuid4()  # único por bloque
último bloque puede ser menor a BLOCK_SIZE
```

### Selección de DataNodes (NameNode)
```
1. Filtrar DataNodes activos (heartbeat < HEARTBEAT_TIMEOUT)
2. Filtrar con espacio libre >= BLOCK_SIZE
3. Ordenar por carga (menor número de bloques primero)
4. Seleccionar los primeros REPLICATION_FACTOR nodos
   → Internamente se usa la IP privada de cada DataNode para comunicación
```

### Re-replicación por fallo (NameNode - background)
```
Si heartbeat de DN no llega en HEARTBEAT_TIMEOUT:
  - Marcar DN como DEAD
  - Identificar bloques que tenían réplica en ese DN
  - Para cada bloque con réplicas_activas < REPLICATION_FACTOR:
    - Ordenar a un DN activo (vía IP privada) que lo copie a otro DN disponible (vía IP privada)
    - Actualizar tabla de metadatos
```

---

## 8. CONFIGURACIÓN (variables de entorno)

```env
# ── Parámetros DFS ─────────────────────────────────────────────
BLOCK_SIZE=67108864          # 64 MB en bytes
REPLICATION_FACTOR=2
HEARTBEAT_INTERVAL=3         # segundos entre heartbeats del DataNode
HEARTBEAT_TIMEOUT=10         # segundos sin heartbeat para declarar DN muerto

# ── NameNode ────────────────────────────────────────────────────
NAMENODE_PUBLIC_HOST=<EIP>   # IP pública / EIP — solo para el cliente
NAMENODE_PRIVATE_HOST=10.0.1.x  # IP privada VPC — usada por DataNodes para HB
NAMENODE_PORT=8000

# ── DataNode ────────────────────────────────────────────────────
# NAMENODE_HOST debe ser SIEMPRE la IP privada del NameNode (dentro de la VPC)
NAMENODE_HOST=10.0.1.x       # ← IP PRIVADA del NameNode (inyectada por Terraform)
DATANODE_PORT=8001
DATANODE_PRIVATE_IP=10.0.2.x # IP privada del DataNode actual (auto-detectada o inyectada)
DATA_DIR=./blocks            # directorio donde el DataNode guarda bloques

# ── Base de datos ───────────────────────────────────────────────
DB_URL=sqlite:///./namenode.db

# ── Seguridad ───────────────────────────────────────────────────
JWT_SECRET=change_me_in_production
JWT_EXPIRE_HOURS=24
```

> **Importante:** Los DataNodes nunca usan `NAMENODE_PUBLIC_HOST`. Siempre usan `NAMENODE_HOST` (IP privada). Solo el cliente CLI usa la IP pública del NameNode.

---

## 9. STACK TECNOLÓGICO

| Componente | Tecnología |
|---|---|
| API REST (NameNode y DataNode) | Python 3.11 + FastAPI + Uvicorn |
| Base de datos metadatos | SQLite (dev) / PostgreSQL (prod) |
| ORM | SQLAlchemy |
| Cliente HTTP inter-nodos | httpx (async) |
| CLI del cliente | Python + Click |
| Contenedores | Docker + Docker Compose |
| Infraestructura | AWS Academy EC2 + VPC |

---

## 10. ESTRUCTURA DE CARPETAS ESPERADA

```
mini-dfs/
├── namenode/
│   ├── Dockerfile
│   ├── main.py              # FastAPI app
│   ├── models.py            # SQLAlchemy models
│   ├── database.py          # DB init y sesión
│   ├── routes/
│   │   ├── auth.py
│   │   ├── files.py
│   │   ├── blocks.py        # ← NUEVO: proxy PUT/GET de bloques hacia DataNodes
│   │   └── nodes.py
│   ├── services/
│   │   ├── block_manager.py # lógica de asignación y replicación (usa IPs privadas)
│   │   ├── block_proxy.py   # ← NUEVO: lógica de proxy streaming hacia DataNodes
│   │   └── monitor.py       # heartbeat watcher + re-replicación (usa IPs privadas)
│   └── requirements.txt
│
├── datanode/
│   ├── Dockerfile
│   ├── main.py              # FastAPI app
│   ├── routes/
│   │   └── blocks.py
│   ├── services/
│   │   ├── storage.py       # leer/escribir bloques en disco
│   │   └── heartbeat.py     # tarea background: envía HB al NameNode por IP privada
│   └── requirements.txt
│
├── client/
│   ├── cli.py               # Click CLI: put, get, ls, mkdir, rm, rmdir
│   ├── dfs_client.py        # fragmentación, PUT/GET via NameNode (sin IPs DataNode)
│   └── requirements.txt
│
├── shared/
│   └── config.py            # variables de entorno compartidas
│
├── infra/                   # Terraform AWS
│   ├── main.tf
│   ├── variables.tf
│   ├── vpc.tf               # ← NUEVO: VPC, subnets, IGW, NAT, route tables
│   ├── security.tf
│   ├── ec2.tf
│   ├── outputs.tf
│   ├── userdata/
│   │   ├── namenode.sh
│   │   └── datanode.sh
│   └── terraform.tfvars.example
│
├── docker-compose.yml       # namenode + 3 datanodes en red interna bridge
└── README.md
```

---

## 11. DOCKER COMPOSE (estructura esperada)

```yaml
# 4 servicios: namenode, datanode1, datanode2, datanode3
# Red interna: dfs-net (bridge) — simula la VPC en local
# namenode: puerto 8000 expuesto al host; DataNodes solo en la red interna (sin ports: al host)
# datanodeN: accesibles solo dentro de dfs-net por nombre de servicio
# NAMENODE_HOST para los DataNodes = "namenode" (nombre DNS interno de Docker)
# Variables de entorno inyectadas por servicio
# datanode1/2/3 dependen de namenode (depends_on)

# En local (docker-compose) el proxy de bloques del NameNode usa el nombre DNS del servicio.
# En AWS el proxy usa la IP privada de la VPC.
```

---

## 12. DIVISIÓN EN 3 AVANCES (para trabajo grupal)

---

### AVANCE 1 — Infraestructura Base y NameNode
**Responsable sugerido:** Integrante A  
**Objetivo:** Tener el NameNode funcionando con registro de DataNodes, autenticación y namespace básico.

**Entregables del avance:**
- [ ] `shared/config.py` con todas las variables de entorno (incluyendo `NAMENODE_PRIVATE_HOST`)
- [ ] `namenode/database.py` + `namenode/models.py` (tablas: User, File, Block, DataNode — el campo `address` del DataNode almacena su IP privada)
- [ ] `namenode/routes/auth.py` → `POST /auth/login` con JWT
- [ ] `namenode/routes/nodes.py` → `POST /nodes/register` y `POST /nodes/heartbeat`
- [ ] `namenode/services/monitor.py` → tarea background que detecta DataNodes caídos
- [ ] `namenode/Dockerfile` + entrada en `docker-compose.yml`
- [ ] Tests básicos: registrar 3 DataNodes (con IPs privadas simuladas), enviar heartbeats, verificar que uno se marca DEAD

**Lo que NO incluye este avance:** lógica de bloques, CLI, DataNode real.

**Criterio de éxito:**  
`docker-compose up namenode` → NameNode corre en puerto 8000, acepta registros de DataNodes ficticios vía curl, autentica usuarios, detecta y loguea DataNodes muertos.

---

### AVANCE 2 — DataNode y Transferencia de Bloques
**Responsable sugerido:** Integrante B  
**Objetivo:** DataNodes funcionando con almacenamiento real de bloques, pipeline de replicación, y proxy de bloques en el NameNode.

**Entregables del avance:**
- [ ] `datanode/routes/blocks.py` → `POST /blocks/{id}`, `GET /blocks/{id}`, `DELETE /blocks/{id}`, `GET /blocks`, `GET /health`
- [ ] `datanode/services/storage.py` → leer/escribir/listar/borrar bloques en disco como archivos binarios
- [ ] `datanode/services/heartbeat.py` → tarea background que envía heartbeat al NameNode usando `NAMENODE_HOST` (IP privada)
- [ ] Pipeline de replicación: al recibir un bloque con `next_node` (IP privada del siguiente DN), reenviarlo
- [ ] `namenode/routes/blocks.py` → `POST /blocks/{block_id}` y `GET /blocks/{block_id}` (proxy hacia DataNodes por IP privada)
- [ ] `namenode/services/block_proxy.py` → lógica de streaming proxy con failover entre réplicas
- [ ] `namenode/routes/files.py` → `POST /files/put` (asigna DataNodes con el algoritmo de selección) y `namenode/services/block_manager.py`
- [ ] `datanode/Dockerfile` + 3 servicios datanode en `docker-compose.yml` (sin `ports:` expuestos al host)
- [ ] Tests: subir un bloque de prueba via NameNode proxy → verificar que aparece en 2 DataNodes

**Lo que NO incluye este avance:** CLI completa, comando get, reconstrucción de archivos.

**Criterio de éxito:**  
`docker-compose up` → 3 DataNodes se registran en NameNode, se puede hacer `POST /blocks/{id}` al NameNode y los bloques quedan replicados en 2 DataNodes (verificable con `GET /blocks` en cada DataNode desde dentro de la red).

---

### AVANCE 3 — CLI del Cliente, GET, Tolerancia a Fallos y Pruebas Finales
**Responsable sugerido:** Integrante C  
**Objetivo:** Sistema completo end-to-end con CLI funcional y tolerancia a caída de un DataNode.

**Entregables del avance:**
- [ ] `namenode/routes/files.py` → completar `GET /files/get/{path}`, `GET /files/ls/{path}`, `POST /files/mkdir`, `DELETE /files/rm/{path}`, `DELETE /files/rmdir/{path}`
- [ ] `client/dfs_client.py` → lógica de fragmentación, PUT de bloques via NameNode, GET con reensamble (failover es transparente porque lo maneja el NameNode)
- [ ] `client/cli.py` → comandos Click: `put`, `get`, `ls`, `mkdir`, `rm`, `rmdir` con autenticación
- [ ] Re-replicación automática: cuando un DataNode cae, el monitor del NameNode copia los bloques huérfanos a otro DataNode activo (comunicación por IPs privadas)
- [ ] `README.md` completo con instrucciones de despliegue local y en AWS (incluyendo nota sobre VPC)
- [ ] Prueba final documentada: subir archivo de 200+ MB → verificar distribución → bajar un DataNode → verificar que el archivo sigue disponible → verificar re-replicación

**Criterio de éxito:**  
`python client/cli.py put archivo_grande.bin /user/archivo_grande.bin` funciona end-to-end **apuntando solo al NameNode**, el archivo se recupera íntegro con `get`, y si se baja un DataNode el sistema sigue operativo.

---

## 13. NOTAS IMPORTANTES PARA CURSOR

1. **Cada avance debe ser un Pull Request separado** para evidenciar participación individual (requerimiento del profesor).
2. **Usar ramas:** `avance-1-namenode`, `avance-2-datanode`, `avance-3-cliente`.
3. **Todos los endpoints deben validar el JWT** excepto `/auth/login` y `/nodes/register`.
4. **El NameNode sí actúa como proxy de datos de bloques** hacia los DataNodes. El cliente solo habla con el NameNode. Los DataNodes son completamente privados (sin IP pública en AWS).
5. **Logging obligatorio** en todos los componentes: registrar cada operación relevante con timestamp.
6. **Manejo de errores:** si un DataNode no responde durante un proxy PUT o GET, el NameNode selecciona otra réplica disponible (failover interno, transparente al cliente).
7. **El tamaño de bloque debe leerse de la variable de entorno** `BLOCK_SIZE`, nunca hardcodeado.
8. **Para el pipeline de replicación:** el NameNode envía el bloque al DN_primary con el query param `next_node=<IP_privada_DN_replica>`; DN_primary replica a DN_replica usando esa IP privada, sin intervención del cliente.
9. **La base de datos del NameNode debe persistir** entre reinicios del contenedor (volumen Docker).
10. **Los bloques de los DataNodes deben persistir** entre reinicios (volumen Docker por DataNode).
11. **Separación pública/privada de IPs:**
    - `NAMENODE_HOST` en DataNodes = **siempre IP privada** del NameNode (inyectada por Terraform o nombre DNS en Docker).
    - La tabla `DataNode` en la BD almacena la **IP privada** de cada nodo.
    - El cliente CLI usa la **IP pública** (o EIP) del NameNode en su config (`~/.dfs_config`).
    - **Nunca** retornar IPs de DataNodes al cliente en ningún endpoint.

---

## 14. CRITERIOS DE EVALUACIÓN (para tenerlos en cuenta)

| Criterio | Peso |
|---|---|
| Diseño arquitectónico y documentación | 20% |
| Gestión de bloques y metadatos | 20% |
| Implementación funcional CLI/API | 20% |
| Comunicación entre nodos | 15% |
| Resultados en entorno distribuido (≥3 nodos) | 15% |
| Video e informe final | 10% |

**Penalidades:**
- Sin video con todos los integrantes → máximo 80%
- Sin evidencia de gestión de tareas grupal → máximo 70%
- Sin autoevaluación → máximo 90%
- Sin pre-informe individual → el trabajo grupal no se recibe

---

---

## 15. INFRAESTRUCTURA CON TERRAFORM — AWS ACADEMY

### 15.1 Restricciones importantes de AWS Academy

AWS Academy NO es una cuenta AWS normal. Antes de escribir cualquier Terraform, tener en cuenta:

| Restricción | Detalle |
|---|---|
| **Credenciales temporales** | `AWS_SESSION_TOKEN` expira cada ~4 horas. Hay que renovarlas desde el Learner Lab antes de cada `terraform apply` |
| **Sin crear usuarios IAM** | No se pueden crear IAM users, roles nuevos ni políticas personalizadas |
| **Rol fijo** | Solo existe el rol `LabRole`. Usarlo para cualquier recurso que requiera `iam_instance_profile` |
| **Región fija** | Solo `us-east-1` está habilitada en la mayoría de labs |
| **Sin Route53** | No se puede gestionar DNS |
| **Sin ACM** | No se pueden crear certificados SSL |
| **Key pair** | Crear el key pair manualmente en la consola AWS y referenciar su nombre en Terraform (no crearlo con Terraform) |
| **Límite de instancias** | Generalmente máximo 5–10 instancias t2.micro simultáneas |
| **VPC default** | Se puede usar la VPC por defecto, pero se recomienda crear una dedicada para aislar el tráfico |

---

### 15.2 Configurar credenciales antes de cada sesión

En AWS Academy → Learner Lab → **AWS Details** → copiar las tres variables y pegarlas en la terminal:

```bash
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."
export AWS_DEFAULT_REGION="us-east-1"
```

O guardarlas en `~/.aws/credentials` bajo el perfil `[academy]`:

```ini
[academy]
aws_access_key_id     = ASIA...
aws_secret_access_key = ...
aws_session_token     = ...
region                = us-east-1
```

Luego usar `terraform apply -var="aws_profile=academy"` o `AWS_PROFILE=academy terraform apply`.

> ⚠️ **Nunca** hacer commit de credenciales. Añadir `.env`, `*.tfvars` y `~/.aws/` al `.gitignore`.

---

### 15.3 Estructura de archivos Terraform

```
infra/
├── main.tf          # provider + backend
├── variables.tf     # todas las variables
├── vpc.tf           # ← NUEVO: VPC, subnets, IGW, NAT Gateway, route tables
├── outputs.tf       # IP pública del NameNode + IPs privadas de DataNodes
├── security.tf      # Security Groups (NameNode público, DataNodes solo VPC)
├── ec2.tf           # instancias NameNode (subred pública) y DataNodes (subred privada)
├── userdata/
│   ├── namenode.sh  # script de arranque del NameNode
│   └── datanode.sh  # script de arranque de los DataNodes (usa IP privada del NameNode)
└── terraform.tfvars.example   # ejemplo sin credenciales reales
```

---

### 15.4 `main.tf` — Provider y backend

```hcl
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend local (S3 no siempre está disponible en Academy)
  # backend "s3" {
  #   bucket = "mini-dfs-tfstate-TUNOMBRE"
  #   key    = "terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
  # Las credenciales se toman de las variables de entorno:
  # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN
}
```

---

### 15.5 `variables.tf`

```hcl
variable "aws_region" {
  description = "Región AWS (Academy solo permite us-east-1)"
  type        = string
  default     = "us-east-1"
}

variable "key_pair_name" {
  description = "Nombre del key pair creado manualmente en la consola AWS"
  type        = string
}

variable "instance_type" {
  description = "Tipo de instancia EC2"
  type        = string
  default     = "t2.micro"
}

variable "ami_id" {
  description = "AMI Ubuntu 22.04 en us-east-1"
  type        = string
  default     = "ami-0c7217cdde317cfec"  # Ubuntu 22.04 LTS us-east-1 (verificar vigencia)
}

variable "block_size" {
  description = "Tamaño de bloque DFS en bytes (default 64MB)"
  type        = number
  default     = 67108864
}

variable "replication_factor" {
  description = "Factor de replicación mínimo"
  type        = number
  default     = 2
}

variable "datanode_count" {
  description = "Número de DataNodes a crear (mínimo 2, recomendado 3)"
  type        = number
  default     = 3
}

variable "jwt_secret" {
  description = "Secreto para firmar JWT tokens"
  type        = string
  sensitive   = true
}

variable "vpc_cidr" {
  description = "Bloque CIDR para la VPC dedicada del Mini-DFS"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR de la subred pública (NameNode)"
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR de la subred privada (DataNodes)"
  type        = string
  default     = "10.0.2.0/24"
}
```

---

### 15.6 `vpc.tf` — VPC, Subnets, Gateways y Rutas *(archivo nuevo)*

```hcl
# ── VPC dedicada ──────────────────────────────────────────────────────────────
resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true   # necesario para que EC2 resuelva nombres internos

  tags = { Name = "mini-dfs-vpc" }
}

# ── Subred pública (NameNode) ─────────────────────────────────────────────────
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = false  # EIP se asigna explícitamente al NameNode

  tags = { Name = "mini-dfs-public-subnet" }
}

# ── Subred privada (DataNodes) ────────────────────────────────────────────────
resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = var.private_subnet_cidr
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = false  # DataNodes NUNCA reciben IP pública

  tags = { Name = "mini-dfs-private-subnet" }
}

# ── Internet Gateway (subred pública → Internet) ──────────────────────────────
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "mini-dfs-igw" }
}

# ── EIP para NAT Gateway ──────────────────────────────────────────────────────
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "mini-dfs-nat-eip" }
}

# ── NAT Gateway (subred privada → Internet para egress, ej. git clone) ────────
resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public.id   # NAT siempre va en la subred pública

  tags = { Name = "mini-dfs-nat-gw" }
  depends_on = [aws_internet_gateway.igw]
}

# ── Tabla de rutas: subred pública ───────────────────────────────────────────
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = { Name = "mini-dfs-public-rt" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Tabla de rutas: subred privada ───────────────────────────────────────────
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id   # egress via NAT, sin IP pública
  }

  tags = { Name = "mini-dfs-private-rt" }
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}
```

---

### 15.7 `security.tf` — Security Groups

```hcl
# ── NameNode SG — único nodo con acceso público ───────────────────────────────
resource "aws_security_group" "namenode_sg" {
  name        = "mini-dfs-namenode-sg"
  description = "NameNode: API publica para clientes + acceso interno VPC"
  vpc_id      = aws_vpc.main.id

  # API REST del NameNode — acceso desde cualquier IP (cliente externo)
  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "NameNode API — acceso publico para clientes"
  }

  # SSH para administración
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH admin"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Egress libre (NameNode necesita llegar a DataNodes y a Internet)"
  }

  tags = { Name = "mini-dfs-namenode-sg" }
}

# ── DataNode SG — solo tráfico interno VPC ────────────────────────────────────
resource "aws_security_group" "datanode_sg" {
  name        = "mini-dfs-datanode-sg"
  description = "DataNodes: acceso SOLO desde dentro de la VPC (sin IP publica)"
  vpc_id      = aws_vpc.main.id

  # API REST del DataNode — SOLO desde el CIDR de la VPC (NameNode y otros DataNodes)
  ingress {
    from_port   = 8001
    to_port     = 8010        # rango para múltiples DataNodes en mismo SG
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "DataNode API — solo trafico interno VPC"
  }

  # Alternativamente, restringir al SG del NameNode para mayor precisión:
  ingress {
    from_port                = 8001
    to_port                  = 8010
    protocol                 = "tcp"
    source_security_group_id = aws_security_group.namenode_sg.id
    description              = "DataNode API — desde NameNode SG"
  }

  # DataNode ↔ DataNode para pipeline de replicación (dentro de la subred privada)
  ingress {
    from_port   = 8001
    to_port     = 8010
    protocol    = "tcp"
    self        = true
    description = "DataNode pipeline replicacion entre pares"
  }

  # SSH solo desde dentro de la VPC (ej. via NameNode como bastión)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "SSH solo desde VPC (via bastión)"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Egress libre (para HB al NameNode, replicacion, git clone via NAT)"
  }

  tags = { Name = "mini-dfs-datanode-sg" }
}
```

> **Nota sobre las dos reglas `ingress 8001-8010` del DataNode SG:** La primera permite cualquier origen dentro del CIDR VPC; la segunda refina el acceso al SG del NameNode. En la práctica, la regla `self = true` cubre la replicación DataNode↔DataNode. Puedes elegir solo el par `vpc_cidr` + `self` si quieres simplificar.

---

### 15.8 `ec2.tf` — Instancias

```hcl
# ── EIP para el NameNode (IP pública fija entre sesiones) ─────────────────────
resource "aws_eip" "namenode_eip" {
  domain   = "vpc"
  instance = aws_instance.namenode.id
  tags     = { Name = "mini-dfs-namenode-eip" }
}

# ── NameNode — subred pública, con IP pública ─────────────────────────────────
resource "aws_instance" "namenode" {
  ami                    = var.ami_id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = aws_subnet.public.id        # ← subred PÚBLICA
  vpc_security_group_ids = [aws_security_group.namenode_sg.id]
  associate_public_ip_address = false                  # usamos EIP en su lugar

  iam_instance_profile = "LabInstanceProfile"

  user_data = templatefile("${path.module}/userdata/namenode.sh", {
    block_size         = var.block_size
    replication_factor = var.replication_factor
    jwt_secret         = var.jwt_secret
  })

  root_block_device {
    volume_size = 20   # GB
    volume_type = "gp2"
  }

  tags = { Name = "mini-dfs-namenode", Role = "namenode" }
}

# ── DataNodes — subred PRIVADA, sin IP pública ────────────────────────────────
resource "aws_instance" "datanode" {
  count = var.datanode_count

  ami                         = var.ami_id
  instance_type               = var.instance_type
  key_name                    = var.key_pair_name
  subnet_id                   = aws_subnet.private.id  # ← subred PRIVADA
  vpc_security_group_ids      = [aws_security_group.datanode_sg.id]
  associate_public_ip_address = false                  # ← SIN IP pública

  iam_instance_profile = "LabInstanceProfile"

  # NAMENODE_HOST = IP privada del NameNode (dentro de la VPC, sin pasar por Internet)
  user_data = templatefile("${path.module}/userdata/datanode.sh", {
    namenode_private_ip = aws_instance.namenode.private_ip   # ← IP PRIVADA
    namenode_port       = 8000
    datanode_port       = 8001 + count.index
    block_size          = var.block_size
    replication_factor  = var.replication_factor
    node_index          = count.index
  })

  root_block_device {
    volume_size = 30   # GB
    volume_type = "gp2"
  }

  tags = {
    Name  = "mini-dfs-datanode-${count.index}"
    Role  = "datanode"
    Index = tostring(count.index)
  }
}
```

---

### 15.9 `outputs.tf`

```hcl
# IP pública del NameNode — la única IP que necesita el cliente
output "namenode_public_ip" {
  description = "IP publica (EIP) del NameNode — usar en el cliente CLI"
  value       = aws_eip.namenode_eip.public_ip
}

output "namenode_api_url" {
  description = "URL base de la API del NameNode para el cliente"
  value       = "http://${aws_eip.namenode_eip.public_ip}:8000"
}

# IP privada del NameNode — usada internamente por los DataNodes
output "namenode_private_ip" {
  description = "IP privada del NameNode dentro de la VPC (usada por DataNodes para HB)"
  value       = aws_instance.namenode.private_ip
}

# IPs privadas de los DataNodes — NO exponer al cliente; solo para auditoría/debug
output "datanode_private_ips" {
  description = "IPs privadas de los DataNodes (solo accesibles dentro de la VPC)"
  value       = aws_instance.datanode[*].private_ip
}

output "ssh_namenode" {
  description = "Comando SSH para conectar al NameNode (punto de entrada publico)"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ubuntu@${aws_eip.namenode_eip.public_ip}"
}

output "ssh_datanode_via_bastion" {
  description = "Comando SSH a DataNodes usando el NameNode como bastión"
  value = [
    for i, dn in aws_instance.datanode :
    "ssh -J ubuntu@${aws_eip.namenode_eip.public_ip} ubuntu@${dn.private_ip}"
  ]
}
```

---

### 15.10 `userdata/namenode.sh` — Script de arranque

```bash
#!/bin/bash
set -e

# Variables inyectadas por Terraform templatefile
BLOCK_SIZE="${block_size}"
REPLICATION_FACTOR="${replication_factor}"
JWT_SECRET="${jwt_secret}"

# Actualizar sistema e instalar dependencias
apt-get update -y
apt-get install -y docker.io docker-compose git curl

# Habilitar Docker
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Clonar repositorio del proyecto
git clone https://github.com/TU_ORG/mini-dfs.git /opt/mini-dfs
cd /opt/mini-dfs

# Obtener la IP privada del NameNode desde el metadata de la instancia
NAMENODE_PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)

# Crear archivo .env para el NameNode
cat > namenode/.env <<EOF
BLOCK_SIZE=$BLOCK_SIZE
REPLICATION_FACTOR=$REPLICATION_FACTOR
JWT_SECRET=$JWT_SECRET
NAMENODE_PORT=8000
NAMENODE_PRIVATE_HOST=$NAMENODE_PRIVATE_IP
DB_URL=sqlite:////data/namenode.db
EOF

# Crear directorio de persistencia
mkdir -p /data/namenode

# Arrancar NameNode con Docker
docker build -t mini-dfs-namenode ./namenode
docker run -d \
  --name namenode \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /data/namenode:/data \
  --env-file namenode/.env \
  mini-dfs-namenode

echo "NameNode iniciado en puerto 8000"
echo "IP privada VPC: $NAMENODE_PRIVATE_IP"
```

---

### 15.11 `userdata/datanode.sh` — Script de arranque

```bash
#!/bin/bash
set -e

# Variables inyectadas por Terraform templatefile
# NOTA: namenode_private_ip es la IP PRIVADA del NameNode dentro de la VPC
NAMENODE_HOST="${namenode_private_ip}"   # ← IP privada, nunca la pública
NAMENODE_PORT="${namenode_port}"
DATANODE_PORT="${datanode_port}"
BLOCK_SIZE="${block_size}"
NODE_INDEX="${node_index}"

apt-get update -y
apt-get install -y docker.io git curl

systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Obtener la IP privada de este DataNode
DATANODE_PRIVATE_IP=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4)

git clone https://github.com/TU_ORG/mini-dfs.git /opt/mini-dfs
cd /opt/mini-dfs

cat > datanode/.env <<EOF
NAMENODE_HOST=$NAMENODE_HOST
NAMENODE_PORT=$NAMENODE_PORT
DATANODE_PORT=$DATANODE_PORT
DATANODE_PRIVATE_IP=$DATANODE_PRIVATE_IP
BLOCK_SIZE=$BLOCK_SIZE
DATA_DIR=/data/blocks
NODE_ID=datanode-$NODE_INDEX
EOF

mkdir -p /data/blocks

docker build -t mini-dfs-datanode ./datanode
docker run -d \
  --name datanode-$NODE_INDEX \
  --restart unless-stopped \
  -p $DATANODE_PORT:$DATANODE_PORT \
  -v /data/blocks:/data/blocks \
  --env-file datanode/.env \
  mini-dfs-datanode

echo "DataNode $NODE_INDEX iniciado en puerto $DATANODE_PORT"
echo "Conectando al NameNode en $NAMENODE_HOST:$NAMENODE_PORT (IP privada VPC)"
echo "IP privada de este DataNode: $DATANODE_PRIVATE_IP"
```

---

### 15.12 `terraform.tfvars.example`

```hcl
# Copiar a terraform.tfvars y completar — NUNCA hacer commit de terraform.tfvars
aws_region          = "us-east-1"
key_pair_name       = "mi-keypair-academy"   # nombre exacto del key pair en la consola AWS
instance_type       = "t2.micro"
datanode_count      = 3
block_size          = 67108864
replication_factor  = 2
jwt_secret          = "cambiar_por_secreto_seguro"
vpc_cidr            = "10.0.0.0/16"
public_subnet_cidr  = "10.0.1.0/24"
private_subnet_cidr = "10.0.2.0/24"
```

---

### 15.13 Comandos de despliegue

```bash
# 1. Instalar Terraform
curl -fsSL https://releases.hashicorp.com/terraform/1.7.5/terraform_1.7.5_linux_amd64.zip -o tf.zip
unzip tf.zip && sudo mv terraform /usr/local/bin/

# 2. Configurar credenciales AWS Academy (renovar cada ~4 horas)
export AWS_ACCESS_KEY_ID="ASIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_SESSION_TOKEN="..."

# 3. Copiar y editar variables
cp infra/terraform.tfvars.example infra/terraform.tfvars
# → editar infra/terraform.tfvars con key_pair_name y jwt_secret

# 4. Inicializar y desplegar
cd infra/
terraform init
terraform plan          # revisar antes de aplicar
terraform apply         # escribir "yes" para confirmar

# 5. Ver IPs de salida
terraform output
# → namenode_public_ip   = IP pública para el cliente
# → namenode_private_ip  = IP privada para los DataNodes (solo referencia)
# → datanode_private_ips = IPs privadas de DataNodes (solo dentro de VPC)

# 6. Verificar que el NameNode responde (esperar ~2 min para que el userdata termine)
curl http://$(terraform output -raw namenode_public_ip):8000/docs

# 7. Configurar el cliente CLI con la IP pública del NameNode
echo "NAMENODE_URL=http://$(terraform output -raw namenode_public_ip):8000" > ~/.dfs_config

# 8. Al terminar la sesión de trabajo — destruir para no gastar créditos
terraform destroy
```

---

### 15.14 Flujo de trabajo recomendado con AWS Academy

```
Inicio de sesión Academy
        ↓
Copiar credenciales temporales (AWS Details)
        ↓
export AWS_ACCESS_KEY_ID / SECRET / SESSION_TOKEN
        ↓
terraform apply   ←── si las credenciales expiran, renovar y volver a apply
        ↓
Verificar: curl http://<namenode_public_ip>:8000/health
           (DataNodes se habrán registrado automáticamente por IP privada)
        ↓
Desarrollar / probar con cliente apuntando solo a la IP pública del NameNode
        ↓
terraform destroy   ←── SIEMPRE destruir al terminar para no agotar créditos
```

> 💡 **Tip:** Las IPs públicas del NameNode son fijas gracias a la EIP (`aws_eip.namenode_eip`). Las IPs privadas de los DataNodes cambian entre `destroy` + `apply`, pero eso es transparente porque Terraform las inyecta automáticamente en el userdata de los DataNodes.

---

### 15.15 Verificar el aislamiento de red (checklist post-deploy)

```bash
# ✅ NameNode accesible desde Internet (cliente)
curl http://<namenode_public_ip>:8000/docs

# ✅ DataNodes NO accesibles desde Internet (deben dar timeout/conexión rechazada)
# Obtener una IP privada de DataNode del output de Terraform:
DN_PRIVATE=$(terraform output -json datanode_private_ips | jq -r '.[0]')
curl --connect-timeout 5 http://$DN_PRIVATE:8001/health
# → debe fallar (timeout) desde fuera de la VPC

# ✅ DataNodes accesibles desde el NameNode (dentro de la VPC)
ssh -i ~/.ssh/mi-keypair-academy.pem ubuntu@<namenode_public_ip> \
  "curl http://$DN_PRIVATE:8001/health"
# → debe responder con JSON de estado del DataNode

# ✅ Heartbeats llegando al NameNode
ssh -i ~/.ssh/mi-keypair-academy.pem ubuntu@<namenode_public_ip> \
  "docker logs namenode 2>&1 | grep heartbeat | tail -5"
```

---

*Documento generado como contexto para implementación asistida por IA. Proyecto académico UPB 2026.*  
*Última actualización: arquitectura VPC con IPs privadas para comunicación interna.*
