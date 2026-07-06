"""
Pokedex API - A simple REST API for managing Pokemon
This lab demonstrates the basics of FastAPI, including decorators and Pydantic models.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# Initialize the FastAPI application
# FastAPI is a modern web framework for building APIs with Python
app = FastAPI(
    title="Pokedex API",
    description="A simple API to manage Pokemon - Add, View, and Delete Pokemon",
    version="1.0.0"
)

# In-memory storage: A dictionary to store Pokemon data
# In a real application, you would use a database (like PostgreSQL, MongoDB, etc.)
# For this lab, we'll use a simple dictionary where:
#   - Key: Pokemon ID (integer)
#   - Value: Pokemon object (dictionary with name, type, power_level)
pokemon_db = {}
next_id = 1  # Counter to assign unique IDs to new Pokemon


# ============================================================================
# PYDANTIC MODELS - Data Validation
# ============================================================================
# Pydantic models are Python classes that define the structure and validation
# rules for your data. They ensure that incoming data matches the expected format.
#
# Benefits:
#   1. Automatic validation: FastAPI validates incoming JSON data against the model
#   2. Type safety: Ensures data types are correct (e.g., name must be a string)
#   3. Documentation: FastAPI automatically generates API docs from these models
#   4. IDE support: Your editor can autocomplete and check types
#
# When you send JSON data to the API, Pydantic will:
#   - Check that required fields are present
#   - Validate data types (string, int, etc.)
#   - Return clear error messages if validation fails
# ============================================================================

class PokemonCreate(BaseModel):
    """
    Model for creating a new Pokemon.
    This defines what data is required when adding a Pokemon via POST /pokemon
    """
    name: str = Field(..., description="The Pokemon's name", example="Pikachu")
    type: str = Field(..., description="The Pokemon's type (e.g., Electric, Fire)", example="Electric")
    power_level: int = Field(..., ge=1, le=100, description="Power level between 1 and 100", example=85)
    
    # Field(...) means the field is REQUIRED
    # ge=1 means "greater than or equal to 1"
    # le=100 means "less than or equal to 100"


class PokemonResponse(BaseModel):
    """
    Model for returning Pokemon data.
    This defines what data is sent back when retrieving a Pokemon.
    """
    id: int
    name: str
    type: str
    power_level: int
    created_at: str  # Timestamp when the Pokemon was added


# ============================================================================
# API ROUTES - Using Decorators
# ============================================================================
# Decorators in Python are functions that modify other functions.
# The syntax @app.get("/path") is a decorator that tells FastAPI:
#   "When someone makes a GET request to /path, run the function below"
#
# Common decorators in FastAPI:
#   @app.get()    - Handle GET requests (retrieve data)
#   @app.post()   - Handle POST requests (create new data)
#   @app.put()    - Handle PUT requests (replace entire resource)
#   @app.patch()  - Handle PATCH requests (partial update)
#   @app.delete() - Handle DELETE requests (remove data)
#
# The decorator automatically:
#   1. Registers the route with FastAPI
#   2. Validates request/response data using Pydantic models
#   3. Generates API documentation
#   4. Handles JSON serialization/deserialization
# ============================================================================


@app.get("/")
def read_root():
    """
    Root endpoint - Welcome message
    This is a simple GET endpoint that returns a welcome message.
    """
    return {
        "message": "Welcome to the Pokedex API!",
        "endpoints": {
            "GET /pokemon": "List all Pokemon",
            "GET /pokemon/{id}": "Get a specific Pokemon by ID",
            "POST /pokemon": "Add a new Pokemon",
            "DELETE /pokemon/{id}": "Delete a Pokemon by ID"
        },
        "docs": "Visit /docs for interactive API documentation"
    }


@app.get("/pokemon", response_model=List[PokemonResponse])
def list_pokemon():
    """
    GET /pokemon - List all Pokemon
    
    This endpoint returns a list of all Pokemon stored in the database.
    The @app.get() decorator tells FastAPI this handles GET requests.
    response_model=List[PokemonResponse] tells FastAPI what format to return.
    
    Returns:
        List of all Pokemon objects
    """
    # Convert dictionary values to a list
    # pokemon_db.values() gives us all Pokemon objects
    return list(pokemon_db.values())


@app.get("/pokemon/{pokemon_id}", response_model=PokemonResponse)
def get_pokemon(pokemon_id: int):
    """
    GET /pokemon/{id} - Get a specific Pokemon by ID
    
    Path parameters: Values in the URL path (like {pokemon_id})
    FastAPI automatically extracts {pokemon_id} from the URL and passes it to the function.
    
    Args:
        pokemon_id: The ID of the Pokemon to retrieve (from the URL path)
    
    Returns:
        Pokemon object if found
    
    Raises:
        HTTPException: 404 if Pokemon not found
    """
    # Check if the Pokemon exists in our database
    if pokemon_id not in pokemon_db:
        # HTTPException is FastAPI's way of returning error responses
        # status_code=404 means "Not Found"
        raise HTTPException(status_code=404, detail=f"Pokemon with ID {pokemon_id} not found")
    
    return pokemon_db[pokemon_id]


@app.post("/pokemon", response_model=PokemonResponse, status_code=201)
def create_pokemon(pokemon: PokemonCreate):
    """
    POST /pokemon - Add a new Pokemon
    
    Request body: The JSON data sent in the request body
    FastAPI automatically:
      1. Reads the JSON from the request body
      2. Validates it against the PokemonCreate model
      3. Converts it to a Python object
      4. Passes it to this function as the 'pokemon' parameter
    
    If validation fails (e.g., missing name, invalid power_level), FastAPI
    automatically returns a 422 error with details about what's wrong.
    
    Args:
        pokemon: PokemonCreate object containing name, type, and power_level
    
    Returns:
        The newly created Pokemon with its assigned ID
    """
    global next_id  # Use the global counter
    
    # Create a new Pokemon object with an assigned ID
    new_pokemon = {
        "id": next_id,
        "name": pokemon.name,
        "type": pokemon.type,
        "power_level": pokemon.power_level,
        "created_at": datetime.now().isoformat()  # Current timestamp
    }
    
    # Store it in our in-memory database
    pokemon_db[next_id] = new_pokemon
    
    # Increment the ID counter for the next Pokemon
    next_id += 1
    
    # Return the created Pokemon (status_code=201 means "Created")
    return new_pokemon


@app.delete("/pokemon/{pokemon_id}", status_code=204)
def delete_pokemon(pokemon_id: int):
    """
    DELETE /pokemon/{id} - Remove a Pokemon by ID
    
    DELETE requests are used to remove resources.
    status_code=204 means "No Content" - successful deletion with no response body.
    
    Args:
        pokemon_id: The ID of the Pokemon to delete
    
    Raises:
        HTTPException: 404 if Pokemon not found
    """
    # Check if the Pokemon exists
    if pokemon_id not in pokemon_db:
        raise HTTPException(status_code=404, detail=f"Pokemon with ID {pokemon_id} not found")
    
    # Remove the Pokemon from the database
    del pokemon_db[pokemon_id]
    
    # Return None (FastAPI will send a 204 No Content response)
    return None


# ============================================================================
# RUNNING THE APPLICATION
# ============================================================================
# You can run this app in two ways:
#
# Method 1 (Recommended): Use uvicorn from command line
#   uvicorn main:app --reload
#
# Method 2: Run directly with Python
#   python main.py
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    # Run the server when executing: python main.py
    # --reload enables auto-reload on code changes (development mode)
    uvicorn.run(app, host="127.0.0.1", port=8000, reload=True)
