"""Organizer gateway: verified OpenAI-compatible tool calling on /v1."""
from urllib.parse import urlsplit
from ..config import settings
from .local_client import LocalOpenAICompatibleClient


class GatewayClient(LocalOpenAICompatibleClient):
    def __init__(self, request_func=None):
        url = settings.llm_gateway_url.rstrip('/')
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('LLM_GATEWAY_URL must be an HTTPS base URL without credentials, query or fragment')
        if not settings.llm_gateway_api_key or not settings.llm_model:
            raise ValueError('LLM_GATEWAY_API_KEY and LLM_MODEL are required for the gateway backend')
        base = url if url.endswith('/v1') else url + '/v1'
        super().__init__(base_url=base, model=settings.llm_model,
                         api_key=settings.llm_gateway_api_key, request_func=request_func)
