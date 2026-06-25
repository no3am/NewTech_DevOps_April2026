# Lab 2: Docker Networking

## Overview

In Lab 1, the client couldn't reach the server without the `host.docker.internal` workaround. In this lab you'll understand why, and fix it properly using Docker networks.

By the end of this lab you will be able to:
- Explain how the default `bridge` network works and its limitations
- Create a custom bridge network with automatic container DNS
- Connect containers so they communicate by name
- Understand the difference between internal networking and port publishing
- Inspect and debug container networks

**Prerequisites:** Images from Lab 1 must be built.
```bash
docker build -t sensor-server ./lab1/server
docker build -t sensor-client ./lab1/client
```

---

## Background: How Docker Networking Works

When Docker starts, it creates three default networks:

```bash
docker network ls
```

```
NETWORK ID     NAME      DRIVER    SCOPE
...            bridge    bridge    local   ← default for all containers
...            host      host      local
...            none      null      local
```

Every container you run without `--network` is automatically attached to the **default bridge network**. The problem: the default bridge does **not support DNS resolution by container name**. Containers can only find each other by IP address — and IPs change every time a container restarts.

Custom bridge networks solve this. They have a built-in DNS server that resolves container names automatically.

---

## Part 1: The Problem — Default Bridge Network

### Step 1: Run both containers on the default network

```bash
# Start the server (no --network flag = default bridge)
docker run -d --name my-server -p 5000:5000 sensor-server

# Try to run the client pointing at the server by name
docker run --rm -e SERVER_URL=http://my-server:5000 sensor-client
```

**What do you see?** The client fails with a connection error — `my-server` cannot be resolved by name on the default bridge.

### Step 2: Find the server's IP and try again

```bash
# Get the server container's IP address
docker inspect my-server --format='{{.NetworkSettings.IPAddress}}'
# Example output: 172.17.0.2

# Run the client using the IP directly
docker run --rm -e SERVER_URL=http://172.17.0.2:5000 sensor-client
```

**What do you see?** It works — but this is fragile. Restart the server and the IP may change:

```bash
docker stop my-server && docker rm my-server
docker run -d --name my-server sensor-server

docker inspect my-server --format='{{.NetworkSettings.IPAddress}}'
# IP may be different now
```

**Conclusion:** IP-based discovery doesn't work in real systems. We need DNS.

### Cleanup
```bash
docker stop my-server && docker rm my-server
```

---

## Part 2: The Fix — Custom Bridge Network

### Step 3: Create a custom network

```bash
docker network create sensor-net
```

Inspect it:
```bash
docker network inspect sensor-net
```

Notice the `"Containers"` section is empty. Notice the `"Driver": "bridge"` — same technology as the default, but with DNS enabled.

### Step 4: Run both containers on the custom network

```bash
# Start the server on sensor-net
docker run -d \
  --name my-server \
  --network sensor-net \
  sensor-server

# Run the client on the same network, pointing at server by NAME
docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  sensor-client
```

**What do you see?** The client successfully sends readings and prints stats. The name `my-server` resolved because both containers are on the same custom network.

### Step 5: Inspect the network

```bash
docker network inspect sensor-net
```

Now look at the `"Containers"` section — you'll see `my-server` listed with its IP and MAC address.

### Cleanup
```bash
docker stop my-server && docker rm my-server
```

---

## Part 3: Port Publishing vs Internal Networking

There is an important distinction between **internal networking** and **port publishing**.

### Step 6: Run the server WITHOUT publishing ports

```bash
# No -p flag — port 5000 is NOT published to the host
docker run -d \
  --name my-server \
  --network sensor-net \
  sensor-server
```

**Test 1 — from host machine:**
```bash
curl http://localhost:5000/health
# Connection refused — port is not published to the host
```

**Test 2 — from another container on the same network:**
```bash
docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  sensor-client
# Works! Internal networking doesn't need -p
```

### Step 7: Add port publishing

```bash
docker stop my-server && docker rm my-server

# Now publish port 5000 to the host
docker run -d \
  --name my-server \
  --network sensor-net \
  -p 5000:5000 \
  sensor-server
```

**Test again from host:**
```bash
curl http://localhost:5000/health
# Now works
```

### Key Takeaway

| Scenario | Needs `-p`? |
|----------|------------|
| Container → container (same network) | No |
| Host machine → container | Yes |
| Browser / external traffic → container | Yes |

**Rule of thumb:** Only publish ports that external users or services need to access directly. Internal services should stay internal.

### Cleanup
```bash
docker stop my-server && docker rm my-server
```

---

## Part 4: Connecting a Running Container to a Network

You don't always need to specify `--network` at startup. You can connect a running container to a network after the fact.

```bash
# Start server on the default network (no --network)
docker run -d --name my-server sensor-server

# Start client on sensor-net — it can't reach my-server yet
docker run -d --name my-client \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  sensor-client

# Connect my-server to sensor-net as well
docker network connect sensor-net my-server

# Now run the client again
docker run --rm \
  --network sensor-net \
  -e SERVER_URL=http://my-server:5000 \
  sensor-client
```

Useful when you can't restart a running container.

### Cleanup
```bash
docker stop my-server my-client
docker rm my-server my-client
docker network rm sensor-net
```

---

## Part 5: Debugging Inside a Container

When networking isn't working, it helps to debug from *inside* the container.

```bash
# Create the network and start the server
docker network create sensor-net
docker run -d --name my-server --network sensor-net sensor-server

# Open a shell inside a temporary container on the same network
docker run --rm -it --network sensor-net python:3.11-slim bash

# From inside the container, test connectivity:
# Note: curl is not installed on slim images — use Python instead
python3 -c "import urllib.request; print(urllib.request.urlopen('http://my-server:5000/health').read().decode())"
python3 -c "import urllib.request; print(urllib.request.urlopen('http://my-server:5000/stats').read().decode())"

# Or install curl on the fly (lost when container exits)
apt-get update && apt-get install -y curl
curl http://my-server:5000/health
exit
```

You can also exec into a running container:
```bash
docker exec -it my-server sh
# Now you're inside the server container
# Check what's listening:
ss -tlnp
exit
```

### Cleanup
```bash
docker stop my-server && docker rm my-server
docker network rm sensor-net
```

---

## Bonus: `--network host`

```bash
docker run --rm --network host sensor-server
```

With `--network host`, the container shares the host's network stack directly — no isolation. Port 5000 is immediately accessible on the host without `-p`.

**Why this is a bad idea:**
- Removes network isolation entirely
- Container can access (and bind to) any port on the host
- A bug or vulnerability in the container can affect the host's network
- Does **not work** on Docker Desktop (Mac/Windows) — host network is the Linux VM, not your machine
- Avoid in production; use custom networks instead

---

## Summary: Networks Cheat Sheet

```bash
# List networks
docker network ls

# Create a custom bridge network
docker network create <name>

# Run a container on a specific network
docker run --network <name> ...

# Connect a running container to a network
docker network connect <network> <container>

# Disconnect a container from a network
docker network disconnect <network> <container>

# Inspect a network (see connected containers, subnet, etc.)
docker network inspect <name>

# Remove a network (all containers must be disconnected first)
docker network rm <name>
```

---

## What's Next?

Right now you're managing networks and volumes with long `docker run` commands. Imagine doing this for 5 services.

In **Lab 3**, you'll learn Docker volumes — how to persist data so it survives container restarts. Then in **Lab 4**, Docker Compose will replace all these manual commands with a single declarative file.
