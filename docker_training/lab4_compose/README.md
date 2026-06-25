# Lab 4: Docker Compose

## Overview

Across Labs 1–3, every time you ran a container you typed something like this:

```bash
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  -v sensor-data-vol:/data \
  -e DATA_FILE=/data/data.json \
  sensor-server
```

That's one service. A real application might have five. Docker Compose lets you define your entire stack in a single `docker-compose.yml` file and manage it with one command.

By the end of this lab you will be able to:
- Write a `docker-compose.yml` from scratch
- Manage a multi-container stack with Compose commands
- Use `depends_on` with health check conditions
- Run one-off containers with `docker compose run`
- Use override files for dev vs prod configurations
- Understand service profiles for optional containers

**Prerequisites:** Images from Lab 1. Compose is included with Docker Desktop. Verify:
```bash
docker compose version
```

---

## Anatomy of a `docker-compose.yml`

```yaml
services:           # The containers you want to run
  my-service:
    image: ...      # Use a pre-built image, OR
    build: ...      # Build from a Dockerfile
    ports: ...      # Port mappings (-p)
    volumes: ...    # Volume mounts (-v)
    environment: ...# Environment variables (-e)
    networks: ...   # Which networks to join
    depends_on: ... # Start order and health conditions
    restart: ...    # Restart policy

volumes:            # Declare named volumes
  my-volume:

networks:           # Declare custom networks
  my-network:
```

Compose automatically creates the declared volumes and networks when you run `docker compose up`. It also prefixes all resource names with your project name (the directory name by default) to avoid clashes.

---

## Part 1: Start Simple — Server Only

### Step 1: Create `docker-compose.yml`

Create `lab4_compose/docker-compose.yml` and add just the server service:

```yaml
services:

  sensor-server:
    build:
      context: ../lab1_dockerfiles/server
      dockerfile: Dockerfile.sol
    ports:
      - "5000:5000"
    volumes:
      - sensor-data:/data
    environment:
      - DATA_FILE=/data/data.json

volumes:
  sensor-data:
```

### Step 2: Build and start

```bash
# From the lab4_compose/ directory:

# Build the image(s)
docker compose build

# Start the stack (foreground — shows logs)
docker compose up

# Or start detached
docker compose up -d
```

Test it:
```bash
curl http://localhost:5000/health
curl http://localhost:5000/stats
```

### Step 3: Explore what Compose created

```bash
# See running services
docker compose ps

# Check logs
docker compose logs
docker compose logs sensor-server   # specific service
docker compose logs -f sensor-server  # follow

# List volumes and networks Compose created
docker volume ls
docker network ls
```

Notice Compose prefixed everything with the project name (e.g., `lab4_compose_sensor-data`, `lab4_compose_sensor-net`). This keeps stacks isolated from each other.

---

## Part 2: Add a Network

Right now Compose created a default network automatically. Make it explicit:

```yaml
services:

  sensor-server:
    build:
      context: ../lab1_dockerfiles/server
      dockerfile: Dockerfile.sol
    ports:
      - "5000:5000"
    volumes:
      - sensor-data:/data
    environment:
      - DATA_FILE=/data/data.json
    networks:
      - sensor-net

volumes:
  sensor-data:

networks:
  sensor-net:
    driver: bridge
```

Restart the stack to apply the change:
```bash
docker compose up -d
```

Compose detects the change and recreates only what changed.

---

## Part 3: Add a Health Check and Restart Policy

```yaml
services:

  sensor-server:
    build:
      context: ../lab1_dockerfiles/server
      dockerfile: Dockerfile.sol
    ports:
      - "5000:5000"
    volumes:
      - sensor-data:/data
    environment:
      - DATA_FILE=/data/data.json
    networks:
      - sensor-net
    healthcheck:
      test: ["CMD", "python3", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"]
      interval: 30s
      timeout: 5s
      start_period: 5s
      retries: 3
    restart: unless-stopped

volumes:
  sensor-data:

networks:
  sensor-net:
    driver: bridge
```

**`restart` policies:**

| Policy | Behaviour |
|--------|-----------|
| `no` | Never restart (default) |
| `always` | Always restart, even on clean exit |
| `on-failure` | Restart only on non-zero exit code |
| `unless-stopped` | Restart always, except when manually stopped |

Check the health status after ~30 seconds:
```bash
docker compose ps
# HEALTH column should show "healthy"
```

---

## Part 4: Run the Client with `docker compose run`

The client is a one-shot container — it sends readings and exits. The right tool for this in Compose is `docker compose run`, not adding it as a permanent service.

First, build the client image:
```bash
docker compose build   # if you add the build block below
```

Add the client to your compose file but **do not** give it ports or restart — it will be invoked on demand:

```yaml
  sensor-client:
    build:
      context: ../lab1_dockerfiles/client
      dockerfile: Dockerfile.sol
    environment:
      - SERVER_URL=http://sensor-server:5000
      - NUM_READINGS=10
    networks:
      - sensor-net
```

Run it:
```bash
# Run the client once (exits when done)
docker compose run --rm sensor-client

# Override an environment variable for this run only
docker compose run --rm -e NUM_READINGS=20 sensor-client
```

`--rm` removes the container after it exits (otherwise Compose keeps it around).

Check stats after:
```bash
curl http://localhost:5000/stats
```

---

## Part 5: `depends_on` with Health Check Condition

The client fails if it starts before the server is ready. Add `depends_on` to enforce start order:

```yaml
  sensor-client:
    build:
      context: ../lab1_dockerfiles/client
      dockerfile: Dockerfile.sol
    environment:
      - SERVER_URL=http://sensor-server:5000
      - NUM_READINGS=10
    networks:
      - sensor-net
    depends_on:
      sensor-server:
        condition: service_healthy
```

Now when you run `docker compose run --rm sensor-client`, Compose waits until `sensor-server` reports `healthy` before starting the client.

**`depends_on` conditions:**

| Condition | Waits until... |
|-----------|----------------|
| `service_started` | Container has started (default) |
| `service_healthy` | Container passes its healthcheck |
| `service_completed_successfully` | Container exited with code 0 |

---

## Part 6: Profiles — Optional Services

If a service is defined in the compose file, `docker compose up` starts it. But the client should only run on demand, not automatically with the rest of the stack.

**Profiles** solve this. A service with a profile is excluded from the default `up` unless you activate the profile:

```yaml
  sensor-client:
    ...
    profiles:
      - client
```

```bash
# Start only the server (client profile not activated)
docker compose up -d

# Run the client by activating the profile
docker compose --profile client run --rm sensor-client
```

This keeps one-shot or optional services in the same file without them running by default.

---

## Part 7: Override Files — Dev vs Prod

Compose supports merging multiple files. The standard pattern:

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Production/base config |
| `docker-compose.override.yml` | Auto-merged dev overrides |

If a file named `docker-compose.override.yml` exists, Compose automatically merges it with `docker-compose.yml` when you run `docker compose up`. No extra flags needed.

For a non-default override file:
```bash
docker compose -f docker-compose.yml -f docker-compose.override.example.yml up -d
```

An example dev override (`docker-compose.override.example.yml`) is included in this lab. It:
- Bind mounts `server.py` so code changes are reflected without rebuilding
- Enables Flask debug mode
- Disables restart so crash messages are visible immediately

> **Tip:** Add `docker-compose.override.yml` to `.gitignore` so developer-specific settings don't leak into the repo. Commit `docker-compose.override.example.yml` as documentation.

---

## Part 8: Teardown

```bash
# Stop containers, keep volumes and networks
docker compose stop

# Stop and remove containers + networks (keeps volumes)
docker compose down

# Stop, remove containers + networks + volumes (destroys data!)
docker compose down -v

# Rebuild images and restart
docker compose up -d --build
```

---

## Bonus: Exec Into a Running Service

```bash
# Open a shell inside the running server container
docker compose exec sensor-server sh

# Run a one-off command inside a running service
docker compose exec sensor-server python3 -c "import os; print(os.environ)"
```

---

## Key Commands Reference

```bash
docker compose build              # Build all service images
docker compose up                 # Start stack (foreground)
docker compose up -d              # Start stack (detached)
docker compose up -d --build      # Rebuild then start
docker compose down               # Stop and remove containers/networks
docker compose down -v            # Also remove volumes
docker compose ps                 # Show service status
docker compose logs               # All service logs
docker compose logs -f <service>  # Follow logs for one service
docker compose run --rm <service> # Run a one-off container
docker compose exec <service> sh  # Shell into running container
docker compose stop               # Stop without removing
docker compose restart <service>  # Restart one service
docker compose --profile <name> up # Activate a profile
```

---

## Solution File

A complete `docker-compose.sol.yml` with all concepts applied is included in this directory. To run it directly:

```bash
docker compose -f docker-compose.sol.yml up -d
docker compose -f docker-compose.sol.yml --profile client run --rm sensor-client
docker compose -f docker-compose.sol.yml down -v
```

---

## What's Next?

You now have a fully declarative stack. One file. One command to start, one to stop, data persists, services find each other by name, and the server restarts automatically if it crashes.

The next step is **Kubernetes** — where the same ideas (services, volumes, networking, health checks) are applied across a *cluster* of machines, with scheduling, scaling, and self-healing built in.
