# Docker Compose Lab 2: The Easy Way

This lab takes the exact same two-container application from Lab 1 and replaces the manual shell script with a single `docker-compose.yml` file.

---

## Step 1: Run the Manual Script First

Before looking at Compose, run Lab 1 the old way so you feel the pain:

```bash
cd ../docker_compose_lab1
bash manual_deploy.sh
```

It works — but look at what it took: manual network creation, a fragile `sleep 5`, 30+ lines of flags repeated across every `docker run` call.

Now clean it up:
```bash
docker stop flask-app postgres-db
docker rm flask-app postgres-db
docker network rm class-net
```

---

## Step 2: Read the Compose File as a Translation

Open `manual_deploy.sh` and `docker-compose.yml` side by side. Every line in the script has a direct equivalent in the compose file:

| `manual_deploy.sh` | `docker-compose.yml` |
|--------------------|----------------------|
| `docker network create class-net` | `networks: app-network:` |
| `docker run --name flask-app` | `services: web:` |
| `docker build -t flask-app .` | `build: .` |
| `-p 8000:7000` | `ports: - "8000:7000"` |
| `-e DB_HOST=postgres-db` | `environment: - DB_HOST=db` |
| `--network class-net` | `networks: - app-network` |
| `sleep 5` | `depends_on: - db` |
| `postgres:15` (no Dockerfile) | `image: postgres:15` |
| *(data lost on stop)* | `volumes: postgres-data:` |

### Key concepts to understand:

**What is a "service"?**
A service is everything you'd pass to one `docker run` command. The service name (`web`, `db`) replaces `--name` and also becomes the container's DNS hostname on the network.

**`build` vs `image`**
- `build: .` → run `docker build` in this directory (used for your own app)
- `image: postgres:15` → pull this directly from Docker Hub (used for public images)

**Service names as DNS**
In the script, `DB_HOST=postgres-db` had to exactly match `--name postgres-db`. In Compose, `DB_HOST=db` works because Compose automatically registers every service name as a DNS entry. No more hunting for IP addresses.

**`depends_on`**
Better than `sleep 5` — Compose waits for the `db` container to *start* before launching `web`. However it doesn't wait for Postgres to be *ready to accept connections*. You'll fix this properly in Lab 3 with `condition: service_healthy`.

**Volumes and networks at the bottom**
The top-level `volumes:` and `networks:` sections are declarations. Compose provisions them automatically on `up` and prefixes them with the project name (e.g., `docker_compose_lab2_postgres-data`).

---

## Step 3: Run It

```bash
# From the docker_compose_lab2/ directory:
docker compose up -d
```

That's it. One command replaced the entire script.

```bash
# Check everything is running
docker compose ps

# Access the app
curl http://localhost:8000
# Expected: Connected to DB!

# Follow logs
docker compose logs -f
```

---

## Step 4: Verify the Concepts

**Check DNS resolution is working:**
```bash
# Open a shell inside the web container
docker compose exec web sh

# Resolve the db service name — should return an IP
python3 -c "import socket; print(socket.gethostbyname('db'))"
exit
```

**Check the volume persists data:**
```bash
# Tear down containers (NOT volumes)
docker compose down

# Bring them back up
docker compose up -d

# Data is still there
curl http://localhost:8000
```

**Check what happens without the volume:**
```bash
docker compose down -v   # removes volumes too
docker compose up -d
curl http://localhost:8000
# Still works — but any data written to the DB is gone
```

---

## Step 5: Teardown

```bash
# Stop and remove containers + network (keep volume)
docker compose down

# Stop and remove everything including volume
docker compose down -v
```

---

## Key Commands

```bash
docker compose up -d          # Start stack detached
docker compose up -d --build  # Rebuild images then start
docker compose down           # Stop and remove containers/networks
docker compose down -v        # Also remove volumes
docker compose ps             # Show service status
docker compose logs -f        # Follow all logs
docker compose exec <svc> sh  # Shell into a running service
```

---

## Check Your Understanding

**Q: In the manual script we ran `docker network create class-net`. Where did that go?**
Compose creates networks declared in `networks:` automatically on `up`. You never run `docker network create` manually.

**Q: The script used `--name postgres-db` and then `DB_HOST=postgres-db`. In Compose, the service is named `db` and `DB_HOST=db`. Why does that work?**
Compose registers each service name as a DNS hostname on the shared network. Any container on the same network can reach `db` by name — no IP needed.

**Q: `depends_on: - db` replaced `sleep 5`. Is it better?**
Slightly — it waits for the container to start rather than guessing with a timer. But it still doesn't guarantee Postgres is ready to accept connections. Lab 3 shows the proper fix.
