"""
Provedores de LLM via API (OpenAI, Anthropic, Ollama).
"""

import logging
import os
import time
from typing import Optional, Generator

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """Provedor OpenAI (GPT-4, GPT-3.5, etc.)."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_tokens: int = 200,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
    ):
        """
        Inicializa provedor OpenAI.

        Args:
            model: Modelo (gpt-4o-mini, gpt-4o, gpt-3.5-turbo)
            max_tokens: Tokens máximos
            temperature: Temperatura
            api_key: API key (ou usar OPENAI_API_KEY)
        """
        super().__init__(model, max_tokens, temperature)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    def _get_client(self):
        """Retorna cliente OpenAI."""
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "openai não instalado. Execute: pip install openai"
                )
        return self._client

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Gera resposta usando OpenAI API."""
        if not self.api_key:
            raise ValueError("API key não configurada")

        start_time = time.time()
        client = self._get_client()

        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Você é um assistente útil que responde em português de forma concisa."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            processing_time = time.time() - start_time
            message = response.choices[0].message.content

            return LLMResponse(
                text=message.strip(),
                model=self.model,
                provider=self.provider_name,
                tokens_input=response.usage.prompt_tokens,
                tokens_output=response.usage.completion_tokens,
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"Erro OpenAI: {e}")
            raise

    def stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Gera resposta em streaming."""
        if not self.api_key:
            raise ValueError("API key não configurada")

        client = self._get_client()
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        stream = client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um assistente útil que responde em português de forma concisa."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )

        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


class AnthropicProvider(LLMProvider):
    """Provedor Anthropic (Claude)."""

    def __init__(
        self,
        model: str = "claude-3-haiku-20240307",
        max_tokens: int = 200,
        temperature: float = 0.3,
        api_key: Optional[str] = None,
    ):
        """
        Inicializa provedor Anthropic.

        Args:
            model: Modelo (claude-3-haiku, claude-3-sonnet, claude-3-opus)
            max_tokens: Tokens máximos
            temperature: Temperatura
            api_key: API key (ou usar ANTHROPIC_API_KEY)
        """
        super().__init__(model, max_tokens, temperature)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._client = None

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def _get_client(self):
        """Retorna cliente Anthropic."""
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError(
                    "anthropic não instalado. Execute: pip install anthropic"
                )
        return self._client

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Gera resposta usando Anthropic API."""
        if not self.api_key:
            raise ValueError("API key não configurada")

        start_time = time.time()
        client = self._get_client()

        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system="Você é um assistente útil que responde em português de forma concisa.",
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            processing_time = time.time() - start_time
            text = response.content[0].text

            return LLMResponse(
                text=text.strip(),
                model=self.model,
                provider=self.provider_name,
                tokens_input=response.usage.input_tokens,
                tokens_output=response.usage.output_tokens,
                processing_time=processing_time,
            )

        except Exception as e:
            logger.error(f"Erro Anthropic: {e}")
            raise

    def stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Gera resposta em streaming."""
        if not self.api_key:
            raise ValueError("API key não configurada")

        client = self._get_client()
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        with client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system="Você é um assistente útil que responde em português de forma concisa.",
            messages=[
                {"role": "user", "content": prompt}
            ],
        ) as stream:
            for text in stream.text_stream:
                yield text


class OllamaProvider(LLMProvider):
    """Provedor Ollama (servidor local)."""

    def __init__(
        self,
        model: str = "tinyllama",
        max_tokens: int = 200,
        temperature: float = 0.3,
        host: str = "http://localhost:11434",
    ):
        """
        Inicializa provedor Ollama.

        Args:
            model: Modelo (tinyllama, phi, gemma, etc.)
            max_tokens: Tokens máximos
            temperature: Temperatura
            host: URL do servidor Ollama
        """
        super().__init__(model, max_tokens, temperature)
        self.host = host.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "ollama"

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Gera resposta usando Ollama."""
        import httpx

        start_time = time.time()
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        try:
            response = httpx.post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": temperature,
                    },
                    "stream": False,
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            processing_time = time.time() - start_time

            return LLMResponse(
                text=data["response"].strip(),
                model=self.model,
                provider=self.provider_name,
                tokens_input=data.get("prompt_eval_count", 0),
                tokens_output=data.get("eval_count", 0),
                processing_time=processing_time,
            )

        except httpx.ConnectError:
            raise RuntimeError(
                f"Não foi possível conectar ao Ollama em {self.host}. "
                "Verifique se o servidor está rodando."
            )
        except Exception as e:
            logger.error(f"Erro Ollama: {e}")
            raise

    def stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """Gera resposta em streaming."""
        import httpx

        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        with httpx.stream(
            "POST",
            f"{self.host}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature,
                },
                "stream": True,
            },
            timeout=120,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    import json
                    data = json.loads(line)
                    if "response" in data:
                        yield data["response"]

    def list_models(self) -> list[str]:
        """Lista modelos disponíveis no Ollama."""
        import httpx

        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=10)
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def is_available(self) -> bool:
        """Verifica se Ollama está disponível."""
        import httpx

        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False


def get_provider(
    provider: str,
    model: Optional[str] = None,
    **kwargs,
) -> LLMProvider:
    """
    Factory function para criar provedores.

    Args:
        provider: Nome do provedor (local, openai, anthropic, ollama)
        model: Modelo (opcional, usa padrão do provedor)
        **kwargs: Argumentos adicionais

    Returns:
        Instância do provedor
    """
    providers = {
        "local": (lambda: __import__("src.llm.local", fromlist=["LocalLLM"]).LocalLLM),
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
        "ollama": OllamaProvider,
    }

    if provider not in providers:
        raise ValueError(f"Provedor desconhecido: {provider}")

    provider_class = providers[provider]
    if callable(provider_class):
        provider_class = provider_class()

    if model:
        kwargs["model"] = model

    return provider_class(**kwargs)
