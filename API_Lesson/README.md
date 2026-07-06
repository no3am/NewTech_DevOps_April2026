# Pokedex API - REST API Lab Exercise

Welcome to the Pokedex API lab! This exercise will teach you the fundamentals of building REST APIs using Python and FastAPI.

## 📚 Learning Objectives

By the end of this lab, you will understand:
- How to create REST API endpoints using FastAPI
- What decorators are and how they work (`@app.get`, `@app.post`, etc.)
- How Pydantic models validate and structure data
- How to test APIs using Swagger UI (interactive documentation)

## 🎯 Project Overview

You'll build a simple **Pokedex API** that allows you to:
- **GET** all Pokemon (list them)
- **GET** a specific Pokemon by ID (view details)
- **POST** a new Pokemon (add to collection)
- **DELETE** a Pokemon by ID (remove from collection)

The data is stored in memory (a Python dictionary), so it will reset when you restart the server. This is perfect for learning - no database setup required!

---

## 🚀 Getting Started

### Step 1: Install Dependencies

First, make sure you have Python 3.7+ installed. Then install the required packages:

```bash
pip install -r requirements.txt
```

This will install:
- **FastAPI**: The web framework for building APIs
- **Uvicorn**: The ASGI server that runs your FastAPI application

### Step 2: Run the Application

Start the FastAPI server:

```bash
uvicorn main:app --reload
```

**What does this command do?**
- `uvicorn`: The server that runs your FastAPI app
- `main:app`: Tells uvicorn to look for the `app` object in `main.py`
- `--reload`: Automatically restarts the server when you make code changes (great for development!)

You should see output like:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Step 3: Open the Interactive API Documentation

FastAPI automatically generates interactive API documentation! Open your web browser and visit:

**http://127.0.0.1:8000/docs**

This is the **Swagger UI** - a visual interface where you can:
- See all available endpoints
- Test each endpoint directly in your browser
- See example requests and responses
- Understand what data each endpoint expects

**Try it out:**
1. Click on `POST /pokemon` to expand it
2. Click "Try it out"
3. Fill in the example JSON (or modify it):
   ```json
   {
     "name": "Pikachu",
     "type": "Electric",
     "power_level": 85
   }
   ```
4. Click "Execute"
5. You should see the response with your newly created Pokemon (including its ID)!

### Alternative Documentation

FastAPI also provides ReDoc documentation at:
**http://127.0.0.1:8000/redoc**

This is a cleaner, more readable format, but Swagger UI is better for testing.

---

## 📖 Understanding the Code

### Decorators Explained

In `main.py`, you'll see lines like:
```python
@app.get("/pokemon")
def list_pokemon():
    ...
```

The `@app.get("/pokemon")` is a **decorator**. It's Python's way of saying:
> "When someone makes a GET request to `/pokemon`, run the `list_pokemon()` function"

**Common HTTP Methods:**
- `GET`: Retrieve data (read-only, safe operation)
- `POST`: Create new data
- `PUT`: Replace entire resource
- `PATCH`: Partially update a resource
- `DELETE`: Remove data

### Pydantic Models Explained

Pydantic models (like `PokemonCreate` and `PokemonResponse`) define the structure of your data:

```python
class PokemonCreate(BaseModel):
    name: str
    type: str
    power_level: int
```

**What Pydantic does:**
1. **Validates** incoming data - ensures `name` is a string, `power_level` is an integer
2. **Rejects invalid data** - if someone sends `power_level: "eighty"` (a string), FastAPI returns an error
3. **Auto-generates documentation** - Swagger UI shows exactly what data is expected
4. **Type safety** - your IDE can help catch errors before runtime

---

## 🧪 Testing the API

### Using Swagger UI (Recommended for Beginners)

1. Go to **http://127.0.0.1:8000/docs**
2. Try each endpoint:
   - **POST /pokemon**: Add a few Pokemon
   - **GET /pokemon**: See all Pokemon you've added
   - **GET /pokemon/{id}**: Get a specific Pokemon (use ID 1, 2, etc.)
   - **DELETE /pokemon/{id}**: Remove a Pokemon

### Using curl (Command Line)

If you prefer the command line:

```bash
# Add a Pokemon
curl -X POST "http://127.0.0.1:8000/pokemon" \
     -H "Content-Type: application/json" \
     -d '{"name": "Charizard", "type": "Fire", "power_level": 95}'

# List all Pokemon
curl http://127.0.0.1:8000/pokemon

# Get a specific Pokemon (replace 1 with actual ID)
curl http://127.0.0.1:8000/pokemon/1

# Delete a Pokemon (replace 1 with actual ID)
curl -X DELETE http://127.0.0.1:8000/pokemon/1
```

---

## 🎓 Challenge: Add an Update Endpoint

Your task is to add a **PATCH** endpoint that allows updating a Pokemon's power level.

### Requirements:
1. Create a new route: `PATCH /pokemon/{pokemon_id}`
2. Create a Pydantic model for the update request (only `power_level` should be required)
3. The endpoint should:
   - Find the Pokemon by ID
   - Update only the `power_level` field
   - Return the updated Pokemon
   - Return 404 if Pokemon not found

### Hints:
- Look at the existing `DELETE` endpoint for how to handle path parameters
- Create a new Pydantic model like `PokemonUpdate` with an optional `power_level` field
- Use `pokemon_db[pokemon_id]["power_level"] = new_value` to update the dictionary
- Remember to use `@app.patch()` decorator

### Example Request:
```json
PATCH /pokemon/1
{
  "power_level": 100
}
```

### Testing:
Once you've added the endpoint, it should appear in Swagger UI at `/docs`. Test it there!

---

## 📝 Key Concepts Recap

1. **Decorators** (`@app.get`, `@app.post`, etc.):
   - Tell FastAPI which HTTP method and URL path to handle
   - Automatically register routes and generate documentation

2. **Pydantic Models**:
   - Define data structure and validation rules
   - Ensure type safety and data integrity
   - Auto-generate API documentation

3. **HTTP Methods**:
   - GET: Read data
   - POST: Create data
   - PATCH: Partially update data
   - DELETE: Remove data

4. **Swagger UI** (`/docs`):
   - Interactive API documentation
   - Test endpoints without writing code
   - See request/response examples

---

## 🐛 Troubleshooting

**Port already in use?**
- Another process might be using port 8000
- Change the port: `uvicorn main:app --reload --port 8001`

**Module not found?**
- Make sure you're in the correct directory
- Verify `requirements.txt` is installed: `pip list`

**Changes not reflecting?**
- Make sure you used `--reload` flag
- Check the terminal for error messages
- Restart the server manually (Ctrl+C, then run again)

---

## 🎉 Next Steps

Once you've completed the challenge:
1. Try adding more fields to Pokemon (e.g., `height`, `weight`, `abilities`)
2. Add validation (e.g., Pokemon name must be at least 3 characters)
3. Add filtering to `GET /pokemon` (e.g., filter by type)
4. Learn about databases and replace the in-memory dictionary with SQLite or PostgreSQL

Happy coding! 🚀
