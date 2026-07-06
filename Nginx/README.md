# Nginx Load Balancing Lab

## Objective

Learn how Nginx acts as a load balancer, distributing incoming requests across multiple backend containers using the Round Robin algorithm.

## What You'll See

When you refresh the page multiple times, you'll see different container hostnames. This demonstrates that Nginx is distributing requests across 3 Flask containers.

## Prerequisites

- Docker installed
- Docker Compose installed

## Architecture

```
Browser / curl
      ↓
  Nginx (Port 80)
      ↓
  Load Balancer (Round Robin)
      ↓
  ┌──────┬──────┬──────┐
  │ App1 │ App2 │ App3 │
  │:7000 │:7000 │:7000 │
  └──────┴──────┴──────┘
```

- **Nginx** is the single entry point (reverse proxy)
- **3 Flask containers** run the actual application
- Nginx distributes requests evenly using Round Robin

---

## Lab Steps

### Step 1: Start the Application

```bash
docker compose up --build --scale app=3
```

> **Why `--scale app=3`?**
> The `deploy: replicas` key in `docker-compose.yml` only works in Docker Swarm mode.
> For regular Compose, `--scale` is how you spin up multiple instances of a service.

**What happens:**
- Builds the Flask application image
- Starts 3 instances of the Flask app, each with a unique hostname
- Starts Nginx as a reverse proxy/load balancer
- Nginx listens on port 80 and forwards requests to the Flask containers

**Expected output:**
```
Container nginx-app-1  Started
Container nginx-app-2  Started
Container nginx-app-3  Started
Container nginx-nginx-1  Started
```

---

### Step 2: Test the Load Balancer

Open your browser and navigate to `http://localhost`. Refresh the page several times.

**What you should see rotate:**
```
Hello! I am Container ID: nginx-app-1
Hello! I am Container ID: nginx-app-2
Hello! I am Container ID: nginx-app-3
Hello! I am Container ID: nginx-app-1   ← starts over
```

**Or use the terminal:**

On **Linux/Mac**:
```bash
for i in {1..9}; do
  echo "Request $i: $(curl -s http://localhost)"
done
```

On **Windows (PowerShell)**:
```powershell
1..9 | ForEach-Object { "Request $_`: $(Invoke-WebRequest -Uri http://localhost -UseBasicParsing).Content" }
```

**Expected output:**
```
Request 1: Hello! I am Container ID: nginx-app-1
Request 2: Hello! I am Container ID: nginx-app-2
Request 3: Hello! I am Container ID: nginx-app-3
Request 4: Hello! I am Container ID: nginx-app-1
...
```

---

### Step 3: Understand Why This Works

#### Why does the container name change?

Nginx uses **Round Robin** by default — requests are distributed to each backend in turn:

1. Request 1 → App 1
2. Request 2 → App 2
3. Request 3 → App 3
4. Request 4 → App 1 ← cycle repeats

This ensures:
- **Even load distribution** — no single container is overwhelmed
- **High availability** — if one container fails, Nginx routes around it
- **Scalability** — add more containers with `--scale app=5` and Nginx picks them up automatically

#### How does Nginx know about all 3 containers?

In `nginx.conf`:
```nginx
upstream my_app {
    server app:7000;
}
```

`app` is the Docker Compose service name. Docker's built-in DNS resolves `app` to **all running containers** with that service name. Nginx gets the full list and round-robins across them.

#### docker-compose.yml explained

```yaml
services:
  app:
    build: .          # Build our Flask image

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"       # Nginx is the only service exposed to the host
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf  # Inject our config
    depends_on:
      - app           # Start app containers before Nginx
```

Notice only **Nginx** has a port mapping. The Flask containers are internal — not directly reachable from outside the Docker network.

---

### Step 4: Simulate a Container Failure

With the stack running, open a new terminal and stop one of the app containers:

```bash
docker stop nginx-app-2
```

Send a few requests:

```bash
# Linux/Mac
for i in {1..6}; do curl -s http://localhost; echo; done

# PowerShell
1..6 | ForEach-Object { (Invoke-WebRequest -Uri http://localhost -UseBasicParsing).Content }
```

**What do you observe?** Nginx stops routing to `nginx-app-2` and distributes requests across the remaining two containers. This is the **high availability** benefit of a load balancer.

Bring it back:
```bash
docker start nginx-app-2
```

---

## Cleanup

```bash
# Stop and remove containers and network
docker compose down

# Also remove the built image
docker compose down --rmi local
```

## Key Takeaways

1. **Load Balancing**: Distributes traffic across multiple servers/containers
2. **Round Robin**: Simple algorithm that cycles through servers in order
3. **High Availability**: If one container fails, others continue serving
4. **Scalability**: Easy to add more replicas to handle more traffic
5. **Reverse Proxy**: Nginx sits in front of your application, handling routing

## Next Steps

- Experiment with different load balancing algorithms (ip_hash, least_conn)
- Add health checks to remove unhealthy containers
- Scale up to 5 or 10 replicas and observe the distribution
- Learn about sticky sessions (session affinity)
