# Lab 3: Docker Volumes

## Overview

In Lab 2, you connected the client and server containers. But there's still a problem: every time the server container is removed, all collected sensor readings are lost. The container filesystem is ephemeral — it lives and dies with the container.

In this lab you'll fix that using Docker volumes.

By the end of this lab you will be able to:
- Explain why container data is lost by default
- Use **bind mounts** to share a host directory with a container
- Use **named volumes** for portable, Docker-managed storage
- Choose the right storage type for different use cases
- Inspect and manage volumes

**Prerequisites:** Images from Lab 1 must be built, and `sensor-net` from Lab 2 should be re-created if needed.
```bash
docker build -t sensor-server ./lab1/server
docker build -t sensor-client ./lab1/client
docker network create sensor-net
```

---

## Background: The Container Filesystem

Every container gets its own isolated writable layer on top of its image. When the container is removed, that layer is deleted. Files written inside the container — logs, databases, uploaded files — are gone.

This is by design. Containers are meant to be stateless and replaceable. **Volumes** are the mechanism for anything that needs to outlive a container.

Also notice this in `server/server.py`:

```python
DATA_FILE = os.environ.get("DATA_FILE", "data.json")
```

The server already supports configuring the data file path via an environment variable. You'll use this in every exercise below to redirect data to a mounted location.

---

## Part 1: Proving the Problem

### Step 1: Run the server and send some readings

```bash
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  sensor-server

docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  -e NUM_READINGS=10 \
  sensor-client
```

Confirm the data is there:
```bash
curl http://localhost:5000/stats
```

### Step 2: Stop and REMOVE the container

```bash
docker stop my-server && docker rm my-server
```

### Step 3: Start a fresh container and check the data

```bash
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  sensor-server

curl http://localhost:5000/stats
```

**What do you see?** All 10 readings are gone. The new container started with a fresh, empty filesystem.

### Cleanup
```bash
docker stop my-server && docker rm my-server
```

---

## Part 2: Bind Mounts

A **bind mount** maps a directory (or file) on your host machine into the container. Data written there is actually written to your host — it persists independently of the container.

```
Host: ./sensor-data/   <──────────────>  Container: /data/
```

### Step 4: Create a host directory and run the server with a bind mount

```bash
# Create the directory on your host
mkdir sensor-data

# Run server, mounting ./sensor-data into /data inside the container
# Use DATA_FILE env var to tell the server to write there
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  -v ./sensor-data:/data \
  -e DATA_FILE=/data/data.json \
  sensor-server
```

### Step 5: Send readings and observe them on the host

```bash
docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  -e NUM_READINGS=5 \
  sensor-client

# Look at the file on your HOST machine
cat ./sensor-data/data.json
```

The file is sitting right there on your machine — not hidden inside the container.

### Step 6: Prove data survives container removal

```bash
docker stop my-server && docker rm my-server

# data.json still exists on the host
cat ./sensor-data/data.json

# Start a new container pointing at the same data
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  -v ./sensor-data:/data \
  -e DATA_FILE=/data/data.json \
  sensor-server

curl http://localhost:5000/stats
```

**The readings are still there.** The new container picked up where the old one left off.

### Step 7: Live edits (bind mount superpower)

Because the file is on your host, you can edit it directly and the container sees the change immediately:

```bash
# Edit data.json on your host (add a fake reading, change a value, etc.)
# Then check the server reflects the change
curl http://localhost:5000/readings
```

> This is why bind mounts are popular in **local development** — you can hot-reload config files or inject test data without rebuilding the image.

### Cleanup
```bash
docker stop my-server && docker rm my-server
```

---

## Part 3: Named Volumes

Bind mounts depend on a specific path on your host machine. This makes them less portable — on a different machine or in CI, the path may not exist.

**Named volumes** are managed entirely by Docker. You don't specify a host path; Docker stores the data in its own managed location. The volume can be referenced by name from any container.

### Step 8: Create a named volume

```bash
docker volume create sensor-data-vol
```

List all volumes:
```bash
docker volume ls
```

Inspect it:
```bash
docker volume inspect sensor-data-vol
```

Look at the `"Mountpoint"` field — Docker chose a path on the host. You don't need to know or manage that path.

### Step 9: Run the server using the named volume

```bash
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  -v sensor-data-vol:/data \
  -e DATA_FILE=/data/data.json \
  sensor-server

docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  -e NUM_READINGS=8 \
  sensor-client

curl http://localhost:5000/stats
```

### Step 10: Prove it survives container removal

```bash
docker stop my-server && docker rm my-server

# Start a brand new container using the same volume
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  -v sensor-data-vol:/data \
  -e DATA_FILE=/data/data.json \
  sensor-server

curl http://localhost:5000/stats
```

All readings are still there — and you never had to worry about the host path.

### Step 11: Share a volume between containers

Named volumes can be mounted by multiple containers simultaneously. This is how a primary and a backup container can share the same data:

```bash
# Run a second server container pointing at the same volume (different port)
docker run -d \
  --name my-server-2 \
  --network sensor-net \
  -p 5001:5000 \
  -v sensor-data-vol:/data \
  -e DATA_FILE=/data/data.json \
  sensor-server

# Both servers see the same data
curl http://localhost:5000/stats
curl http://localhost:5001/stats
```

### Cleanup
```bash
docker stop my-server my-server-2
docker rm my-server my-server-2
```

---

## Part 4: Read-Only Mounts

You can mount a volume or directory as **read-only** by appending `:ro`. This is useful for injecting configuration files that the container should read but never modify.

```bash
# Mount sensor-data-vol as read-only
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  -v sensor-data-vol:/data:ro \
  -e DATA_FILE=/data/data.json \
  sensor-server

# Try to write a new reading — the server will fail to save it
docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  sensor-client
```

The POST request returns an error because the container cannot write to `/data`. The existing data is still readable:

```bash
curl http://localhost:5000/readings   # existing data visible
curl http://localhost:5000/stats      # existing stats visible
```

### Cleanup
```bash
docker stop my-server && docker rm my-server
```

---

## Part 5: Cleaning Up Volumes

Unlike containers and images, volumes are **not deleted** when you remove a container. This is intentional — Docker protects your data.

```bash
# Remove a specific volume (must not be in use by any container)
docker volume rm sensor-data-vol

# Remove ALL unused volumes (not attached to any container)
docker volume prune

# Remove a container AND its anonymous volumes in one step
docker rm -v <container-name>
```

> **Warning:** `docker volume prune` is permanent. Don't run it on a production machine unless you're certain.

---

## Bonus: tmpfs Mounts

A **tmpfs** mount stores data in the host's memory — it is never written to disk and is lost when the container stops. Useful for sensitive temporary data (tokens, session data, intermediate processing files) that must not be persisted.

```bash
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  --tmpfs /tmp \
  -e DATA_FILE=/tmp/data.json \
  sensor-server

docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  sensor-client

curl http://localhost:5000/stats   # Works while container runs

docker stop my-server && docker rm my-server
# Data is gone — never touched disk
```

---

## Bind Mount vs Named Volume — When to Use Each

| | Bind Mount | Named Volume |
|---|---|---|
| Host path | You specify (`./sensor-data`) | Docker manages |
| Portability | Host-dependent | Portable across machines |
| Best for | Local dev, injecting config files | Production data (databases, uploads) |
| Visibility | Directly in your filesystem | Via `docker volume inspect` |
| Works in CI? | Only if path exists on runner | Yes — volume is created on demand |

---

## Key Commands Reference

```bash
# Create a named volume
docker volume create <name>

# List all volumes
docker volume ls

# Inspect a volume (see mount path, metadata)
docker volume inspect <name>

# Mount a named volume
docker run -v <volume-name>:/container/path ...

# Bind mount a host directory
docker run -v ./host-dir:/container/path ...

# Read-only mount
docker run -v <name>:/container/path:ro ...

# In-memory mount
docker run --tmpfs /container/path ...

# Remove a volume
docker volume rm <name>

# Remove all unused volumes
docker volume prune
```

---

## What's Next?

Look at the `docker run` commands you've been writing across Labs 1, 2, and 3:

```bash
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  -v sensor-data-vol:/data \
  -e DATA_FILE=/data/data.json \
  sensor-server
```

Now imagine writing and maintaining this for 5 services. **Docker Compose** replaces all of this with a single declarative `docker-compose.yml` file — defining networks, volumes, environment variables, and port mappings all in one place.

That's **Lab 4**.
