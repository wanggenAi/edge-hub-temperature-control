# TDengine Local Deployment with Docker

## 1. Purpose

This document records a practical local deployment path for TDengine using
Docker so that:

- TDengine can be started consistently on a developer machine
- the Java `data-hub` can be switched from log mode to real database writes
- later project services can move toward a unified Docker-based deployment style

The current goal is local single-node deployment for development and integration
testing, not production clustering.

## 2. Recommended Local Approach

For local development, the recommended setup is:

1. install Docker Desktop
2. start Docker Desktop and verify the Docker CLI
3. start TDengine with the repository Compose file
4. verify CLI, REST, and Explorer access
5. switch `data-hub` to `tdengine-rest` mode

This keeps the workflow simple and close to the later full-project Docker setup.

## 3. Install Docker Desktop Locally

### 3.1 macOS

Recommended because the current development environment is already on macOS.

Steps:

1. Download Docker Desktop for Mac from the official Docker page.
2. Open the installer and drag Docker into `Applications`.
3. Start Docker Desktop.
4. Accept the initial permission prompts if macOS asks for them.
5. Wait until Docker Desktop shows that the engine is running.

Official reference:

- Docker Desktop for Mac permissions and installation notes:
  - https://docs.docker.com/desktop/setup/install/mac-permission-requirements/

### 3.2 Windows

If later you deploy on a Windows development machine, install Docker Desktop for
Windows and make sure WSL 2 is available.

Official reference:

- Docker Desktop for Windows:
  - https://docs.docker.com/installation/windows/

## 4. Verify Docker After Installation

Run:

```bash
docker version
docker info
docker compose version
```

Expected result:

- Docker client and server both report versions
- `docker compose version` returns normally

If this fails, check:

- whether Docker Desktop is fully started
- whether the Docker whale icon shows the engine is running

## 5. Start TDengine with Compose

The repository now includes:

- `docker-compose.tdengine.yml`

This file starts a single TDengine container with:

- REST API on `6041`
- native service ports
- Explorer on `6060`
- local persistent directories under `runtime/tdengine`

### 5.1 Start the container

From the repository root:

```bash
docker compose -f docker-compose.tdengine.yml up -d
```

### 5.2 Check container status

```bash
docker compose -f docker-compose.tdengine.yml ps
docker compose -f docker-compose.tdengine.yml logs --tail 100
```

Expected result:

- container `edgehub-tdengine` is `Up`
- no repeated startup failures appear in the logs

Practical note:

- the strongest success signal is `Up ... (healthy)`
- TDengine may print internal startup messages during initialization
- occasional HTTP `404` lines for `/metrics` do not block normal REST SQL usage

### 5.3 Stop the container later

```bash
docker compose -f docker-compose.tdengine.yml down
```

If you want to delete local TDengine data as well, remove these directories:

- `runtime/tdengine/data`
- `runtime/tdengine/log`

## 6. Verify TDengine Locally

### 6.1 Verify with CLI inside the container

```bash
docker exec -it edgehub-tdengine taos
```

Then run:

```sql
SHOW DATABASES;
quit;
```

Expected result:

- the TDengine CLI opens
- the database list is displayed

### 6.2 Verify the REST SQL endpoint

TDengine REST listens on:

- `http://127.0.0.1:6041/rest/sql`

Run:

```bash
curl -u root:taosdata \
  -H 'Content-Type: text/plain' \
  -d 'SHOW DATABASES;' \
  http://127.0.0.1:6041/rest/sql
```

Expected result:

- JSON response with `code: 0`

### 6.3 Verify the web Explorer

Open:

- `http://127.0.0.1:6060`

Default login:

- username: `root`
- password: `taosdata`

## 7. Switch data-hub to TDengine

Edit:

- `data-hub/config/application.properties`

Set:

```properties
datahub.storage.mode=tdengine-rest
datahub.storage.tdengine.url=http://127.0.0.1:6041
datahub.storage.tdengine.database=edgehub
datahub.storage.tdengine.username=root
datahub.storage.tdengine.password=taosdata
datahub.storage.tdengine.auto-create=true
```

Then start `data-hub`:

```bash
cd data-hub
./gradlew bootRun
```

Expected result:

- `data-hub` connects to MQTT
- `data-hub` logs that the TDengine REST writer is initialized
- telemetry writes are persisted into TDengine

Typical initialization log:

```text
tdengine rest writer initialized url=http://127.0.0.1:6041 database=edgehub autoCreate=true
```

## 8. Verify Writes from data-hub

After `data-hub` runs for a short time, enter the container:

```bash
docker exec -it edgehub-tdengine taos
```

Then run:

```sql
SHOW DATABASES;
USE edgehub;
SHOW STABLES;
SHOW TABLES;
SELECT COUNT(*) FROM edgehub.telemetry_edge_node_001;
SELECT * FROM edgehub.telemetry_edge_node_001 LIMIT 5;
```

Expected result:

- database `edgehub` exists
- supertables `telemetry`, `params_set`, and `params_ack` exist
- per-device subtables exist
- telemetry rows appear after MQTT traffic arrives

Practical note:

- the current Java writer creates per-device subtables with sanitized names
- for device `edge-node-001`, the telemetry subtable becomes
  `telemetry_edge_node_001`

One-shot verification command:

```bash
docker exec edgehub-tdengine taos -s "SHOW DATABASES; USE edgehub; SHOW STABLES; SHOW TABLES; SELECT COUNT(*) FROM edgehub.telemetry_edge_node_001;"
```

Typical success signal:

- `edgehub` appears in the database list
- `SELECT COUNT(*) FROM edgehub.telemetry_edge_node_001;` returns a positive count

## 9. Common Notes

### 9.1 Why Docker is a good fit here

- local deployment becomes repeatable
- later service composition is easier
- data directories stay isolated under the project root
- the project can later evolve toward a unified Compose-based stack

### 9.2 Ports used by the current local setup

- `6041`: TDengine REST
- `6060`: TDengine Explorer
- `6030`: native service port
- `6043-6060`: additional TDengine service ports

### 9.3 When to move beyond this setup

This local Docker deployment is enough for:

- development
- integration testing
- thesis demonstration

Later, if you need:

- multi-node TDengine
- stronger persistence guarantees
- resource isolation
- production hardening

then the deployment design should move beyond this single-node local Compose
baseline.

## 10. References

- TDengine Docker deployment:
  - https://docs.tdengine.com/get-started/deploy-in-docker/
- TDengine data model:
  - https://docs.tdengine.com/basic-features/data-model/
- Docker Desktop for Mac permissions:
  - https://docs.docker.com/desktop/setup/install/mac-permission-requirements/
- Docker Desktop for Windows:
  - https://docs.docker.com/installation/windows/
