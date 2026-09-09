import os
import json
import numpy as np
from google import genai

client = genai.Client()

# Define the cache file path alongside your other mappings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "mappings", "vector_cache.json")

def _load_cache() -> dict:
    """Loads the vector cache into RAM on startup."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("WARNING: Vector cache is corrupted or empty. Starting fresh.")
            return {}
    return {}

def _save_cache(cache: dict):
    """Writes the updated vector dictionary to disk."""
    # Ensure the directory exists
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

# Initialize the cache in memory once when the module loads
VECTOR_CACHE = _load_cache()


def get_embedding(text: str) -> np.ndarray:
    """Retrieves the embedding from local cache or calls the Gemini API if missing."""
    clean_text = text.strip().lower()

    # 1. Cache Hit: Return immediately
    if clean_text in VECTOR_CACHE:
        return np.array(VECTOR_CACHE[clean_text])

    # 2. Cache Miss: Call the Gemini API
    print(f"    [Vector API Call] Generating new embedding for: '{clean_text}'")
    response = client.models.embed_content(
        model="gemini-embedding-001", # FIX: Updated from text-embedding-004
        contents=clean_text,
    )

    embedding_list = response.embeddings[0].values

    # ... (keep the rest of the function the same)

    # 3. Save to cache
    VECTOR_CACHE[clean_text] = embedding_list
    _save_cache(VECTOR_CACHE)

    return np.array(embedding_list)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Calculates the cosine similarity between two vectors."""
    dot_product = np.dot(vec_a, vec_b)
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def find_best_semantic_match(extracted_text: str, mapping_dict: dict, threshold: float = 0.85) -> str | None:
    """
    Searches a dictionary for the closest semantic match using local vector caching.
    Returns the mapped CEDEX value if it exceeds the threshold, otherwise returns None.
    """
    if not mapping_dict or not extracted_text:
        return None

    # Get the embedding for the newly extracted text from the LLM
    extracted_vector = get_embedding(extracted_text)

    best_match_key = None
    highest_similarity = -1.0

    # Compare against all known human-mapped keys
    for saved_key in mapping_dict.keys():
        saved_vector = get_embedding(saved_key)
        similarity = cosine_similarity(extracted_vector, saved_vector)

        if similarity > highest_similarity:
            highest_similarity = similarity
            best_match_key = saved_key

    # Evaluate against the strict threshold
    if highest_similarity >= threshold:
        print(f"    [Semantic Match] '{extracted_text}' matched with '{best_match_key}' (Score: {highest_similarity:.3f})")
        return mapping_dict[best_match_key]

    print(f"    [Semantic Miss] '{extracted_text}' highest match was '{best_match_key}' (Score: {highest_similarity:.3f})")
    return None