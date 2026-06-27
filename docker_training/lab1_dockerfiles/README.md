# Lab 1: Building Docker Images

## Overview

In this lab, you will containerize a two-service application:

- **Server** — A Flask API that collects temperature and humidity sensor readings and stores them to a file
- **Client** — A Python script that simulates sensors sending data, then prints statistics from the server

By the end of this lab you will be able to:

- Write a `Dockerfile` from scratch
- Build and run Docker images
- Understand and fix Docker layer caching
- Use `.dockerignore` to keep images lean
- Secure your container with a non-root user
- Add a `HEALTHCHECK` instruction
- _(Bonus)_ Use multi-stage builds

---

## Application Overview

### Server (`server/server.py`)

A Flask REST API with four endpoints:

| Method | Path        | Description                                     |
| ------ | ----------- | ----------------------------------------------- |
| `GET`  | `/health`   | Health check — returns status and reading count |
| `GET`  | `/readings` | List all stored sensor readings                 |
| `POST` | `/readings` | Submit a new reading                            |
| `GET`  | `/stats`    | Min / max / avg for temperature and humidity    |

The server stores all data in a local file (`data.json`), configurable via the `DATA_FILE` environment variable.

**Example — submit a reading:**

```bash
curl -X POST http://localhost:5000/readings \
  -H "Content-Type: application/json" \
  -d '{"sensor_id": "sensor-A", "temperature": 22.5, "humidity": 65.0}'
```

**Example — get stats:**

```bash
curl http://localhost:5000/stats
```

---

### Client (`client/client.py`)

A one-shot Python script that:

1. Sends `NUM_READINGS` random readings to the server
2. Fetches and prints stats after all readings are submitted

**Configuration via environment variables:**

| Variable       | Default                 | Description                   |
| -------------- | ----------------------- | ----------------------------- |
| `SERVER_URL`   | `http://localhost:5000` | Base URL of the sensor server |
| `NUM_READINGS` | `5`                     | How many readings to send     |

---

## Step 1: Read the Code First

> **Do not skip this step.** Understanding what the app does is part of the lab.

Open `server/server.py` and answer these questions before writing any Dockerfiles:

- What port does the server listen on?
- What file does the server write data to?
- What happens if the `data.json` file doesn't exist yet?
- What validation does the server do on incoming requests?

Open `client/client.py` and answer:

- How does the client know where the server is?
- What happens if the server is not running when the client starts?
- What does the client print after sending all readings?

---

## Part 1: Write Basic Dockerfiles

### Step 2: Dockerfile for the Server

Create `server/Dockerfile`. Requirements:

- Use `python:3.11-slim` as the base image
- Set `/app` as the working directory
- Copy and install dependencies from `requirements.txt`
- Copy the application code
- Expose the correct port
- Set the startup command

**Build and test:**

```bash
# Build the image
docker build -t sensor-server ./server

# Run the server (detached)
docker run -d -p 5000:5000 --name my-server sensor-server

# Test it
curl http://localhost:5000/health
curl http://localhost:5000/stats

# Submit a reading
curl -X POST http://localhost:5000/readings \
  -H "Content-Type: application/json" \
  -d '{"sensor_id": "sensor-A", "temperature": 22.5, "humidity": 65.0}'

# Confirm it was stored
curl http://localhost:5000/stats

# Clean up
docker stop my-server && docker rm my-server
```

> **Solution:** `server/Dockerfile.sol`

---

### Step 3: Dockerfile for the Client

Create `client/Dockerfile`. Similar to the server, but:

- No port needs to be exposed
- The startup command runs `client.py`

**Build:**

```bash
docker build -t sensor-client ./client
```

> **Note:** Getting the client and server containers to talk requires Docker networking, which is covered in **Lab 2**. For now, just verify the image builds successfully.
> If you want to test end-to-end now, see the tip below.

<details>
<summary>💡 Tip: Test the client against the server right now (optional)</summary>

On **Docker Desktop** (Mac/Windows):

```bash
docker run --rm \
  -e SERVER_URL=http://host.docker.internal:5000 \
  sensor-client
```

On **Linux**:

```bash
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -e SERVER_URL=http://host.docker.internal:5000 \
  sensor-client
```

This works by routing traffic through the host machine. In Lab 2 you'll do this properly with a Docker network.

</details>

> **Solution:** `client/Dockerfile.sol`

---

## Part 2: Optimize Your Dockerfiles

### The Layer Caching Problem

Run this experiment with the server:

```bash
# 1. Build the image (note which steps are cached)
docker build -t sensor-server ./server

# 2. Add a blank line or comment anywhere in server.py

# 3. Build again
docker build -t sensor-server ./server
```

**What did you observe?**

If your Dockerfile copies all files _before_ installing dependencies, every minor code change causes Docker to re-run `pip install` — even though `requirements.txt` didn't change. In a CI/CD pipeline this wastes minutes on every commit.

**The fix:** Copy `requirements.txt` and run `pip install` _before_ copying the application code.

```dockerfile
# GOOD — requirements are cached separately from code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
```

```dockerfile
# BAD — any code change busts the pip install cache
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
```

**Update both Dockerfiles** so the layer order is correct, then rebuild and observe the difference.

---

### Step 4: Add a `.dockerignore` File

Without a `.dockerignore`, Docker sends your entire directory to the build daemon on every build — including `venv/`, `.git/`, test data, and editor files.

Create `server/.dockerignore` and `client/.dockerignore`:

```
__pycache__/
*.pyc
*.pyo
venv/
.env
data.json
.git/
*.md
```

**Verify it works:**

```bash
# Check image size before and after
docker images sensor-server
```

---

### Step 5: Add a Non-Root User

By default, processes inside containers run as `root`. If an attacker escapes the container, they get root access to the host. Always run as a non-root user.

Add these lines to both Dockerfiles (after `pip install`, before copying app code):

```dockerfile
RUN useradd --no-create-home --shell /bin/false appuser  && chown -R appuser:appuser /app
USER appuser
```

**Verify:**

```bash
docker run --rm sensor-server whoami
# Should print: appuser
```

---

### Step 6: Add a `HEALTHCHECK` (Server only)

A `HEALTHCHECK` tells Docker how to determine if the container is healthy. If the check fails repeatedly, Docker marks the container as `unhealthy`.

> This is the Docker equivalent of **liveness probes** in Kubernetes — the concept maps directly.

Add to `server/Dockerfile`:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
```

**Verify:**

```bash
docker run -d -p 5000:5000 --name test-server sensor-server

# Wait ~10 seconds, then check health status
docker inspect test-server --format='{{.State.Health.Status}}'
# Expected: healthy

docker stop test-server && docker rm test-server
```

---

## Bonus: Multi-Stage Builds

Multi-stage builds let you use a heavier image at build time but ship only what's needed at runtime.

**Where they really shine:** compiled languages (Go, Rust, Java) — the build toolchain stays in stage 1, only the binary goes in stage 2.

**For Python**, the gain is more modest, but the pattern is worth knowing:

```dockerfile
# Stage 1: Install dependencies (can include build tools for C extensions)
FROM python:3.11 AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/deps -r requirements.txt

# Stage 2: Lean runtime image
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /deps /usr/local
COPY server.py .
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser
EXPOSE 5000
CMD ["python3", "server.py"]
```

**Compare sizes:**

```bash
docker build -t sensor-server-multi -f Dockerfile.multistage ./server
docker images | grep sensor-server
```

---

## Key Commands Reference

```bash
# Build an image
docker build -t <name> <context-path>

# Build using a non-default Dockerfile
docker build -t <name> -f Dockerfile.sol <context-path>

# Run a container
docker run -p <host-port>:<container-port> <image>

# Run detached with a name
docker run -d -p 5000:5000 --name my-server sensor-server

# Pass environment variables
docker run -e SERVER_URL=http://... sensor-client

# View logs
docker logs my-server

# Stop and remove
docker stop my-server && docker rm my-server

# Inspect image layers and sizes
docker history sensor-server
docker images sensor-server
```

---

## What's Next?

You now have two images that can each run independently. But the client still can't reliably find the server without `host.docker.internal` workarounds.

In **Lab 2**, you'll learn Docker networking — how to create a private network so containers can discover each other by name, just like services in a real application.
