"""
Authors: Declan, Sriharsha Ganjam, Santosh
Date: 19th September 2025
Core definition/configuration module for the project.
"""

import os
import pathlib
from dotenv import load_dotenv
from typing import List, Dict, Any
from neo4j import GraphDatabase, basic_auth

# Used for embeddings
try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

# Try import mistralai
try:
    from mistralai import Mistral
except ImportError:
    Mistral = None

# Environment Loading
project_root = pathlib.Path(__file__).resolve().parent
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=str(env_path))
else:
    load_dotenv()

# Configuration Variables
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Getting the API keys for the LLM (Mistral)
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")

# Embedding model config
EMBED_MODEL_NAME = os.getenv("HUGGINGFACE_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
EMBED_DIM = int(os.getenv("EMBEDDING_DIM", "384"))

# Initialize embedding model
try:
    if SentenceTransformer:
        embedding_model = SentenceTransformer(EMBED_MODEL_NAME)
    else:
        embedding_model = None
except Exception as e:
    print(f"Failed to load embedding model: {e}")
    embedding_model = None

# Neo4j Driver
driver = None
neo4j_error = None
if NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD:
    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=basic_auth(NEO4J_USER, NEO4J_PASSWORD))
        # Test connection
        with driver.session(database=NEO4J_DATABASE) as s:
            s.run("RETURN 1").single()
    except Exception as e:
        neo4j_error = str(e)
        driver = None
else:
    neo4j_error = "NEO4J credentials missing"

# Helper Function: Neo4j Read
def run_read_cypher(drv, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    params = params or {}
    try:
        with drv.session(database=NEO4J_DATABASE) as s:
            res = s.run(query, params)
            return [r.data() for r in res]
    except Exception as e:
        print(f"Neo4j query error: {e}")
        return []

# Mistral Client Helpers
def get_mistral_client(api_key: str):
    if Mistral is None or not api_key:
        return None
    try:
        return Mistral(api_key=api_key)
    except Exception as e:
        print(f"Failed to create Mistral client: {e}")
        return None

def mistral_request(client, model, messages, max_tokens=512, temperature=0.2):
    if client is None:
        raise RuntimeError("Mistral client not available")

    try:
        # Try different call patterns depending on SDK version
        if hasattr(client, "chat") and hasattr(client.chat, "complete"):
            resp = client.chat.complete(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temperature
            )
        elif hasattr(client, "chat_completion"):
            resp = client.chat_completion(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temperature
            )
        elif hasattr(client, "chat") and callable(client.chat):
            resp = client.chat(
                model=model, messages=messages,
                max_tokens=max_tokens, temperature=temperature
            )
        else:
            raise RuntimeError("Unable to call Mistral API - no compatible method found")

        # Extract response
        if hasattr(resp, 'choices') and len(resp.choices) > 0:
            if hasattr(resp.choices[0], 'message'):
                return resp.choices[0].message.content
            elif hasattr(resp.choices[0], 'text'):
                return resp.choices[0].text
        elif hasattr(resp, 'content'):
            return resp.content
        
        return str(resp)
        
    except Exception as e:
        raise RuntimeError(f"Mistral API call failed: {str(e)}")