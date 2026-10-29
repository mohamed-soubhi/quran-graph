"""Tests for Ollama models: embeddings (bge-m3) and GLM Arabic generation."""

import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")
GLM_MODEL = os.getenv("GLM_MODEL", "glm-5.3-flash:cloud")


def is_ollama_available() -> bool:
    try:
        res = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return res.status_code == 200
    except Exception:
        return False


@pytest.fixture(autouse=True)
def check_ollama():
    if not is_ollama_available():
        pytest.skip(f"Ollama server not reachable at {OLLAMA_HOST}")


def test_bge_m3_arabic_embeddings():
    """Verify bge-m3 returns equal-length 1024-dimension vectors for Arabic inputs."""
    payload = {
        "model": EMBED_MODEL,
        "input": [
            "الحمد لله رب العالمين",
            "قل هو الله أحد",
        ],
    }
    res = requests.post(f"{OLLAMA_HOST}/api/embed", json=payload, timeout=30)
    assert res.status_code == 200, f"Embed request failed: {res.text}"
    data = res.json()
    embeddings = data.get("embeddings", [])
    assert len(embeddings) == 2, f"Expected 2 embeddings, got {len(embeddings)}"

    dim0 = len(embeddings[0])
    dim1 = len(embeddings[1])
    assert dim0 == 1024, f"Expected 1024 embedding dimension, got {dim0}"
    assert dim1 == 1024, f"Expected 1024 embedding dimension, got {dim1}"
    assert dim0 == dim1, "Embedding vectors have different lengths"


def test_glm_arabic_generation():
    """Verify GLM responds with coherent Arabic text."""
    payload = {
        "model": GLM_MODEL,
        "prompt": "لخّص في جملة: الحمد لله رب العالمين",
        "stream": False,
    }
    res = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=60)
    assert res.status_code == 200, f"Generate request failed: {res.text}"
    data = res.json()
    response_text = data.get("response", "")
    assert response_text.strip(), "Response text is empty"
    # Ensure there is Arabic script in the response
    has_arabic = any("\u0600" <= ch <= "\u06FF" for ch in response_text)
    assert has_arabic, f"Response does not contain Arabic text: {response_text}"
