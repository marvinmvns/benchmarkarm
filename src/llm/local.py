"""
LLM local usando llama.cpp.
Otimizado para Raspberry Pi com modelos quantizados.
"""

import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, Generator

from .base import LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class LocalLLM(LLMProvider):
    """
    LLM local usando llama.cpp.

    Modelos recomendados para Raspberry Pi:
    - TinyLlama 1.1B (Q4): ~670MB, rápido
    - Phi-2 2.7B (Q4): ~1.6GB, mais capaz
    - Gemma 2B (Q4): ~1.5GB, alternativa
    """

    # Mapeamento de modelos conhecidos
    KNOWN_MODELS = {
        "tinyllama": "tinyllama-1.1b-q4.gguf",
        "phi2": "phi-2-q4.gguf",
        "gemma-2b": "gemma-2b-q4.gguf",
    }

    def __init__(
        self,
        model: str = "tinyllama",
        model_path: Optional[str] = None,
        context_size: int = 512,
        threads: int = 4,
        max_tokens: int = 150,
        temperature: float = 0.3,
        quantization: str = "q4_0",
        llama_cpp_path: Optional[str] = None,
        models_dir: Optional[str] = None,
        use_server_mode: bool = True,  # OTIMIZADO: server mode por padrão
        server_port: int = 8080,
    ):
        """
        Inicializa LLM local.

        Args:
            model: Nome do modelo ou caminho
            model_path: Caminho explícito do modelo
            context_size: Tamanho do contexto (menor = mais rápido)
            threads: Número de threads
            max_tokens: Tokens máximos na resposta
            temperature: Temperatura
            quantization: Quantização do modelo
            llama_cpp_path: Caminho para llama.cpp
            models_dir: Diretório de modelos
            use_server_mode: Usar servidor persistente (5-10s mais rápido)
            server_port: Porta do servidor llama.cpp
        """
        super().__init__(model, max_tokens, temperature)

        self.context_size = context_size
        self.threads = threads
        self.quantization = quantization
        self.use_server_mode = use_server_mode
        self.server_port = server_port
        self._server = None

        # Encontrar caminhos
        self._project_root = self._find_project_root()
        self.llama_cpp_path = llama_cpp_path or self._find_llama_cpp()
        self.models_dir = models_dir or str(self._project_root / "models")

        # Resolver caminho do modelo
        if model_path:
            self.model_path = model_path
        else:
            self.model_path = self._resolve_model_path(model)

        # Verificar disponibilidade
        self._available = self._check_available()

        if self._available:
            logger.info(
                f"LLM local inicializado: {model}, "
                f"context={context_size}, threads={threads}, "
                f"server_mode={use_server_mode}"
            )

            # OTIMIZADO: Iniciar servidor se habilitado
            if use_server_mode:
                try:
                    self._start_server()
                except Exception as e:
                    logger.warning(
                        f"Não foi possível iniciar servidor llama.cpp: {e}. "
                        f"Usando modo subprocess."
                    )
                    self.use_server_mode = False
        else:
            logger.warning(
                f"LLM local não disponível. "
                f"Verifique llama.cpp em {self.llama_cpp_path}"
            )

    @property
    def provider_name(self) -> str:
        return "local"

    def _find_project_root(self) -> Path:
        """Encontra diretório raiz do projeto."""
        current = Path(__file__).resolve()
        for parent in current.parents:
            if (parent / "config").is_dir() or (parent / "external").is_dir():
                return parent
        return current.parent.parent.parent

    def _find_llama_cpp(self) -> str:
        """Encontra executável do llama.cpp."""
        # Nomes possíveis do executável (llama.cpp renomeou 'main' para 'llama-cli')
        exe_names = ["llama-cli", "llama-simple", "main", "llama"]
        
        search_dirs = [
            self._project_root / "external" / "llama.cpp" / "build" / "bin",
            self._project_root / "external" / "llama.cpp" / "build",
            self._project_root / "external" / "llama.cpp",
            Path.home() / "llama.cpp" / "build" / "bin",
            Path.home() / "llama.cpp" / "build",
            Path.home() / "llama.cpp",
            Path("/usr/local/bin"),
            Path("/usr/bin"),
        ]

        for search_dir in search_dirs:
            for exe_name in exe_names:
                path = search_dir / exe_name
                if path.exists() and path.is_file():
                    return str(path)

        # Retornar caminho padrão esperado
        return str(self._project_root / "external" / "llama.cpp" / "build" / "bin" / "llama-cli")

    def _resolve_model_path(self, model: str) -> str:
        """Resolve caminho do modelo."""
        # Se é um caminho absoluto
        if os.path.isabs(model) and os.path.exists(model):
            return model

        # Se é um modelo conhecido
        if model in self.KNOWN_MODELS:
            model_file = self.KNOWN_MODELS[model]
            return os.path.join(self.models_dir, model_file)

        # Tentar encontrar no diretório de modelos
        models_path = Path(self.models_dir)
        for pattern in [f"{model}*.gguf", f"*{model}*.gguf"]:
            matches = list(models_path.glob(pattern))
            if matches:
                return str(matches[0])

        # Retornar caminho esperado
        return os.path.join(self.models_dir, f"{model}.gguf")

    def _check_available(self) -> bool:
        """Verifica se LLM está disponível."""
        exe_path = Path(self.llama_cpp_path)
        model_path = Path(self.model_path)
        return exe_path.exists() and model_path.exists()

    def _start_server(self) -> None:
        """Inicia servidor llama.cpp para inferência mais rápida."""
        if self._server is not None:
            return

        try:
            self._server = LlamaCppServer(
                model_path=self.model_path,
                host="127.0.0.1",
                port=self.server_port,
                threads=self.threads,
                context_size=self.context_size,
            )
            self._server.start()
            logger.info(f"✅ Servidor llama.cpp iniciado na porta {self.server_port}")
        except Exception as e:
            logger.error(f"Erro ao iniciar servidor llama.cpp: {e}")
            self._server = None
            raise

    def _stop_server(self) -> None:
        """Para servidor llama.cpp."""
        if self._server is not None:
            try:
                self._server.stop()
                self._server = None
                logger.info("Servidor llama.cpp parado")
            except Exception as e:
                logger.error(f"Erro ao parar servidor: {e}")

    def _check_server_health(self) -> bool:
        """Verifica se o servidor está saudável."""
        if self._server is None:
            return False

        try:
            import httpx
            response = httpx.get(
                f"http://127.0.0.1:{self.server_port}/health",
                timeout=2,
            )
            return response.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """
        Gera resposta usando llama.cpp.

        Args:
            prompt: Prompt de entrada
            **kwargs: Argumentos adicionais (max_tokens, temperature)

        Returns:
            Resposta do LLM
        """
        if not self._available:
            raise RuntimeError(
                "LLM local não disponível. "
                "Execute scripts/install.sh para instalar."
            )

        start_time = time.time()
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)

        # Formatar prompt para chat
        formatted_prompt = self._format_prompt(prompt)

        # OTIMIZADO: Usar servidor se disponível
        if self.use_server_mode and self._server is not None:
            # Verificar saúde do servidor e reiniciar se necessário
            if not self._check_server_health():
                logger.warning("Servidor llama.cpp não responde, reiniciando...")
                self._stop_server()
                try:
                    self._start_server()
                except Exception as e:
                    logger.error(f"Falha ao reiniciar servidor: {e}. Usando subprocess.")
                    self.use_server_mode = False
                    # Fallthrough para subprocess

            # Tentar usar servidor
            if self.use_server_mode and self._server is not None:
                try:
                    text = self._server.generate(formatted_prompt, max_tokens)
                    processing_time = time.time() - start_time

                    # Estimar tokens
                    tokens_input = len(formatted_prompt.split())
                    tokens_output = len(text.split())

                    return LLMResponse(
                        text=text,
                        model=self.model,
                        provider=self.provider_name,
                        tokens_input=tokens_input,
                        tokens_output=tokens_output,
                        processing_time=processing_time,
                    )
                except Exception as e:
                    logger.error(f"Erro ao usar servidor llama.cpp: {e}. Usando subprocess.")
                    # Fallthrough para subprocess

        # Fallback: Executar llama.cpp via subprocess
        cmd = [
            self.llama_cpp_path,
            "-m", self.model_path,
            "-p", formatted_prompt,
            "-n", str(max_tokens),
            "-c", str(self.context_size),
            "-t", str(self.threads),
            "--temp", str(temperature),
            "--no-display-prompt",
            "-e",  # Escape sequences
        ]

        # Opções adicionais para performance
        if kwargs.get("low_memory", True):
            cmd.extend(["--mlock"])  # Lock memory

        logger.debug(f"Executando LLM via subprocess: {' '.join(cmd[:6])}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,  # 2 minutos timeout
            )

            if result.returncode != 0:
                logger.error(f"Erro llama.cpp: {result.stderr}")
                raise RuntimeError(f"llama.cpp falhou: {result.stderr}")

            # Extrair texto da resposta
            output = result.stdout.strip()

            # Limpar output (remover linhas de debug)
            lines = output.split('\n')
            text_lines = [
                line for line in lines
                if not line.startswith('[') and
                not line.startswith('llama_') and
                not 'tokens/second' in line.lower()
            ]
            text = '\n'.join(text_lines).strip()

            processing_time = time.time() - start_time

            # Estimar tokens
            tokens_input = len(formatted_prompt.split())
            tokens_output = len(text.split())

            return LLMResponse(
                text=text,
                model=self.model,
                provider=self.provider_name,
                tokens_input=tokens_input,
                tokens_output=tokens_output,
                processing_time=processing_time,
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout na geração de texto")

    def _format_prompt(self, prompt: str) -> str:
        """Formata prompt para o modelo."""
        # Formato para TinyLlama/Llama-2 chat
        if "tinyllama" in self.model.lower() or "llama" in self.model.lower():
            return f"""<|system|>
Você é um assistente útil que responde em português de forma concisa.
</s>
<|user|>
{prompt}
</s>
<|assistant|>
"""

        # Formato para Phi-2
        if "phi" in self.model.lower():
            return f"""Instruct: {prompt}
Output:"""

        # Formato para Gemma
        if "gemma" in self.model.lower():
            return f"""<start_of_turn>user
{prompt}<end_of_turn>
<start_of_turn>model
"""

        # Formato genérico
        return f"""### Instrução:
{prompt}

### Resposta:
"""

    def stream(self, prompt: str, **kwargs) -> Generator[str, None, None]:
        """
        Gera resposta em streaming.

        Args:
            prompt: Prompt de entrada
            **kwargs: Argumentos adicionais

        Yields:
            Tokens gerados
        """
        if not self._available:
            raise RuntimeError("LLM local não disponível")

        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        temperature = kwargs.get("temperature", self.temperature)
        formatted_prompt = self._format_prompt(prompt)

        cmd = [
            self.llama_cpp_path,
            "-m", self.model_path,
            "-p", formatted_prompt,
            "-n", str(max_tokens),
            "-c", str(self.context_size),
            "-t", str(self.threads),
            "--temp", str(temperature),
            "--no-display-prompt",
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        try:
            for line in process.stdout:
                # Filtrar linhas de debug
                if not line.startswith('[') and not line.startswith('llama_'):
                    yield line
        finally:
            process.terminate()

    def is_available(self) -> bool:
        """Verifica se está disponível."""
        return self._available

    def get_info(self) -> dict:
        """Retorna informações do provedor."""
        info = super().get_info()
        info.update({
            "model_path": self.model_path,
            "context_size": self.context_size,
            "threads": self.threads,
            "available": self._available,
            "server_mode": self.use_server_mode,
            "server_running": self._server is not None,
        })
        return info

    def __del__(self):
        """Destructor - para servidor ao destruir objeto."""
        try:
            self._stop_server()
        except Exception:
            pass


class LlamaCppServer:
    """
    Servidor llama.cpp para inferência mais rápida.
    Mantém modelo carregado em memória.
    """

    def __init__(
        self,
        model_path: str,
        host: str = "127.0.0.1",
        port: int = 8080,
        threads: int = 4,
        context_size: int = 512,
    ):
        """
        Inicializa servidor llama.cpp.

        Args:
            model_path: Caminho do modelo
            host: Host do servidor
            port: Porta do servidor
            threads: Número de threads
            context_size: Tamanho do contexto
        """
        self.model_path = model_path
        self.host = host
        self.port = port
        self.threads = threads
        self.context_size = context_size
        self._process = None

    def start(self) -> None:
        """Inicia o servidor."""
        if self._process is not None:
            return

        project_root = Path(__file__).parent.parent.parent
        server_path = project_root / "external" / "llama.cpp" / "server"

        if not server_path.exists():
            raise RuntimeError("Servidor llama.cpp não encontrado")

        cmd = [
            str(server_path),
            "-m", self.model_path,
            "--host", self.host,
            "--port", str(self.port),
            "-t", str(self.threads),
            "-c", str(self.context_size),
        ]

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Aguardar servidor iniciar
        time.sleep(2)
        logger.info(f"Servidor llama.cpp iniciado em {self.host}:{self.port}")

    def stop(self) -> None:
        """Para o servidor."""
        if self._process is not None:
            self._process.terminate()
            self._process.wait()
            self._process = None
            logger.info("Servidor llama.cpp parado")

    def generate(self, prompt: str, max_tokens: int = 150) -> str:
        """Gera resposta via API do servidor."""
        import httpx

        response = httpx.post(
            f"http://{self.host}:{self.port}/completion",
            json={
                "prompt": prompt,
                "n_predict": max_tokens,
                "temperature": 0.3,
            },
            timeout=120,
        )

        response.raise_for_status()
        return response.json()["content"]

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
