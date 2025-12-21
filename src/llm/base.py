"""
Interface base para provedores de LLM.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Generator
import time


@dataclass
class LLMResponse:
    """Resposta do LLM."""
    text: str
    model: str
    provider: str
    tokens_input: int = 0
    tokens_output: int = 0
    processing_time: float = 0.0
    cached: bool = False

    @property
    def total_tokens(self) -> int:
        """Total de tokens usados."""
        return self.tokens_input + self.tokens_output

    @property
    def tokens_per_second(self) -> float:
        """Tokens de saída por segundo."""
        if self.processing_time > 0:
            return self.tokens_output / self.processing_time
        return 0

    def to_dict(self) -> dict:
        """Converte para dicionário."""
        return {
            "text": self.text,
            "model": self.model,
            "provider": self.provider,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "processing_time": self.processing_time,
            "cached": self.cached,
        }


class LLMProvider(ABC):
    """Interface base para provedores de LLM."""

    def __init__(
        self,
        model: str,
        max_tokens: int = 200,
        temperature: float = 0.3,
    ):
        """
        Inicializa o provedor.

        Args:
            model: Nome/ID do modelo
            max_tokens: Máximo de tokens na resposta
            temperature: Temperatura (0 = determinístico)
        """
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Nome do provedor."""
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """
        Gera resposta para o prompt.

        Args:
            prompt: Prompt de entrada
            **kwargs: Argumentos adicionais

        Returns:
            Resposta do LLM
        """
        pass

    def stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """
        Gera resposta em streaming.

        Args:
            prompt: Prompt de entrada
            **kwargs: Argumentos adicionais

        Yields:
            Tokens gerados
        """
        # Implementação padrão: retorna tudo de uma vez
        response = self.generate(prompt, **kwargs)
        yield response.text

    def summarize(
        self,
        text: str,
        max_length: Optional[int] = None,
        style: str = "concise",
    ) -> LLMResponse:
        """
        Resume um texto.

        Args:
            text: Texto a resumir
            max_length: Tamanho máximo do resumo em palavras
            style: Estilo (concise, detailed, bullet)

        Returns:
            Resposta com resumo
        """
        style_instructions = {
            "concise": "Faça um resumo muito breve e direto ao ponto.",
            "detailed": "Faça um resumo detalhado mantendo as informações importantes.",
            "bullet": "Faça um resumo em pontos (bullet points).",
        }

        length_instruction = ""
        if max_length:
            length_instruction = f" O resumo deve ter no máximo {max_length} palavras."

        prompt = f"""Resuma o seguinte texto de forma {style}.
{style_instructions.get(style, style_instructions['concise'])}{length_instruction}

Texto:
{text}

Resumo:"""

        return self.generate(prompt)

    def extract_actions(self, text: str) -> LLMResponse:
        """
        Extrai ações/tarefas de um texto.

        Args:
            text: Texto de entrada

        Returns:
            Resposta com ações extraídas
        """
        prompt = f"""Analise o texto abaixo e extraia todas as ações, tarefas ou compromissos mencionados.
Liste cada ação em uma linha separada.

Texto:
{text}

Ações identificadas:"""

        return self.generate(prompt)

    def answer_question(self, context: str, question: str) -> LLMResponse:
        """
        Responde uma pergunta baseada no contexto.

        Args:
            context: Texto de contexto
            question: Pergunta

        Returns:
            Resposta
        """
        prompt = f"""Baseado no contexto abaixo, responda a pergunta de forma direta e concisa.

Contexto:
{context}

Pergunta: {question}

Resposta:"""

        return self.generate(prompt)

    def custom_prompt(
        self,
        template: str,
        text: str,
        **variables,
    ) -> LLMResponse:
        """
        Executa prompt customizado.

        Args:
            template: Template do prompt com {text} e outras variáveis
            text: Texto principal
            **variables: Variáveis adicionais para o template

        Returns:
            Resposta do LLM
        """
        prompt = template.format(text=text, **variables)
        return self.generate(prompt)

    def is_available(self) -> bool:
        """Verifica se o provedor está disponível."""
        try:
            # Teste simples
            response = self.generate("Responda apenas 'ok'")
            return len(response.text) > 0
        except Exception:
            return False

    def get_info(self) -> dict:
        """Retorna informações do provedor."""
        return {
            "provider": self.provider_name,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }


class DummyLLM(LLMProvider):
    """LLM dummy para testes."""

    @property
    def provider_name(self) -> str:
        return "dummy"

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Retorna resposta dummy."""
        return LLMResponse(
            text="[Resposta de teste]",
            model="dummy",
            provider="dummy",
            tokens_input=len(prompt.split()),
            tokens_output=3,
            processing_time=0.001,
        )
