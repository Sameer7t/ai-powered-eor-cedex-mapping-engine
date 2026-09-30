import os
from dotenv import load_dotenv
from google import genai

_client = None


def get_genai_client(api_key: str = None) -> genai.Client:
    """Returns an authenticated Gemini client with lazy loading and key fallback."""
    global _client
    if api_key:
        return genai.Client(api_key=api_key)

    if _client is None:
        load_dotenv()
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            # Do not hard-crash on module import in CI/CD or Docker build steps
            pass
        _client = genai.Client()
    return _client


class LazyGenaiClient:
    """Proxy object so existing references to `client.models...` work transparently."""
    def __getattr__(self, name):
        c = get_genai_client()
        return getattr(c, name)


client = LazyGenaiClient()
