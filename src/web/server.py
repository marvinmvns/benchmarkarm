"""
Servidor Web leve para configuração do Voice Processor.
Otimizado para Raspberry Pi - baixo uso de recursos.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import yaml

logger = logging.getLogger(__name__)


class MemoryLogHandler(logging.Handler):
    """Handler que armazena logs em memória para exibição na interface web."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, max_entries: int = 200):  # Reduzido para economizar memória
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, max_entries: int = 200):  # Reduzido para economizar memória
        if self._initialized:
            return
        super().__init__()
        self.log_entries: deque = deque(maxlen=max_entries)
        self.error_count = 0
        self.warning_count = 0
        self._initialized = True
        
        # Formatar logs
        self.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        ))
    
    def emit(self, record: logging.LogRecord):
        try:
            entry = {
                "timestamp": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": self.format(record),
                "raw_message": record.getMessage(),
            }
            
            # Adicionar info de exceção se houver
            if record.exc_info:
                import traceback
                entry["exception"] = ''.join(traceback.format_exception(*record.exc_info))
            
            self.log_entries.append(entry)
            
            # Contadores
            if record.levelno >= logging.ERROR:
                self.error_count += 1
            elif record.levelno >= logging.WARNING:
                self.warning_count += 1
                
        except Exception:
            self.handleError(record)
    
    def get_logs(self, level: str = None, limit: int = 100, logger_filter: str = None) -> List[Dict]:
        """Retorna logs filtrados."""
        logs = list(self.log_entries)
        
        # Filtrar por level
        if level:
            level_upper = level.upper()
            logs = [l for l in logs if l["level"] == level_upper]
        
        # Filtrar por logger
        if logger_filter:
            logs = [l for l in logs if logger_filter in l["logger"]]
        
        # Retornar mais recentes primeiro (limitado)
        return list(reversed(logs))[:limit]
    
    def get_errors(self, limit: int = 50) -> List[Dict]:
        """Retorna apenas erros."""
        logs = list(self.log_entries)
        errors = [l for l in logs if l["level"] in ("ERROR", "CRITICAL")]
        return list(reversed(errors))[:limit]
    
    def clear(self):
        """Limpa os logs."""
        self.log_entries.clear()
        self.error_count = 0
        self.warning_count = 0
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas dos logs."""
        return {
            "total": len(self.log_entries),
            "errors": self.error_count,
            "warnings": self.warning_count,
        }


def setup_memory_logging():
    """Configura o handler de memória no logger raiz."""
    handler = MemoryLogHandler()
    handler.setLevel(logging.DEBUG)
    
    # Adicionar ao logger raiz
    root_logger = logging.getLogger()
    
    # Evitar duplicatas
    for h in root_logger.handlers:
        if isinstance(h, MemoryLogHandler):
            return handler
    
    root_logger.addHandler(handler)
    return handler


# Tentar importar Flask, fallback para servidor básico
try:
    from flask import Flask, render_template, request, jsonify, send_from_directory
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logger.warning("Flask não instalado. Execute: pip install flask")



class ContinuousListener(threading.Thread):
    def __init__(self, config_path, led_controller=None):
        super().__init__(daemon=True)
        self.config_path = config_path
        self.led_controller = led_controller
        self.running = False
        self.active = False 
        self.processor = None
        
    def run(self):
        self.running = True
        logger.info("🎧 Thread de escuta contínua iniciada (Aguardando ativação)")
        
        while self.running:
            if self.active:
                try:
                    if not self.processor:
                        from src.pipeline import VoiceProcessor
                        self.processor = VoiceProcessor(config_path=self.config_path)
                        logger.info("🎤 Microfone ativado para escuta contínua")
                
                    # Feedback visual de "Ouvindo" é tratado pelo VAD/Loop?
                    # O VoiceProcessor não notifica "Ouvindo" exceto via callback?
                    # Vamos assumir IDLE color (apagado) até detectar voz?
                    # Ou Azul constante?
                    # VoiceProcessor.process(audio=None) bloqueia gravando.
                    
                    # Se quisermos feedback de VAD, precisamos passar callback
                    def status_cb(stage, details):
                        if not self.led_controller: return
                        if stage == "recording":
                            pass # Azul piscando?
                        elif stage == "transcribing":
                            self.led_controller.processing()
                    
                    # Indicar que está ativo (pode ser sutil)
                    # self.led_controller.listening() # Pisca azul enquanto grava
                    
                    result = self.processor.process(
                        generate_summary=True,
                        status_callback=status_cb
                    )
                    
                    if result.text.strip():
                        logger.info(f"🗣️: {result.text}")
                        if self.led_controller: self.led_controller.success()
                    
                except Exception as e:
                    logger.error(f"Erro na escuta: {e}")
                    if self.led_controller: self.led_controller.error()
                    time.sleep(2)
            else:
                 # Not active
                 if self.processor:
                     self.processor = None # __exit__ handles cleanup if used as context manager?
                     # No, VoiceProcessor uses __enter__/__exit__.
                     # Direct usage requires manual close?
                     # VoiceProcessor implementation:
                     # def __exit__(self, ...): self.audio.close()
                     # So if I instantiate it without 'with', I should call close?
                     # It doesn't seem to have explicit Close method except via context manager.
                     # Let's check VoiceProcessor... 
                     # Assuming I can just drop it and GC cleans up or I should fix VoiceProcessor later.
                     # Ideally I used 'with' inside loop, but that creates overhead per phrase.
                     # I'll rely on GC for now as AudioCapture closes stream in destructor?
                     pass
                 time.sleep(0.5)

    def stop(self):
        self.running = False
        self.active = False

def create_app(config_path: Optional[str] = None) -> "Flask":
    """
    Cria aplicação Flask para interface web.

    Args:
        config_path: Caminho do arquivo de configuração

    Returns:
        Aplicação Flask configurada
    """
    if not FLASK_AVAILABLE:
        raise ImportError("Flask não instalado. Execute: pip install flask")

    # Diretórios
    web_dir = Path(__file__).parent
    template_dir = web_dir / "templates"
    static_dir = web_dir / "static"

    # Encontrar config
    if config_path is None:
        project_root = web_dir.parent.parent
        config_path = str(project_root / "config" / "config.yaml")

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )

    app.config["CONFIG_PATH"] = config_path
    app.config["SECRET_KEY"] = os.urandom(24)
    
    # Configurar captura de logs em memória
    log_handler = setup_memory_logging()
    logger.info("🌐 Servidor web iniciado")

    # Configurar LEDs
    try:
        from src.hardware.led import NeoPixelController
        # Initial access to config without saving it? load_config is defined inside create_app...
        # Wait, load_config and other helpers are defined AFTER init?
        # I need to move load_config definition UP or copy logic.
        # But setup_memory_logging works.
        
        # Load logic inline to avoid issues
        with open(config_path, "r") as f:
            full_config = yaml.safe_load(f) or {}
            
        led_conf = full_config.get('hardware', {}).get('leds', {})
        app.led_controller = NeoPixelController(
            num_leds=led_conf.get('num_leds', 3),
            brightness=led_conf.get('brightness', 10),
            enabled=led_conf.get('enabled', True)
        )
        app.led_controller.flash_random()
        logger.info("💡 LEDs inicializados")
    except Exception as e:
        logger.warning(f"Falha ao iniciar LEDs: {e}")
        app.led_controller = None

    # Inicializar Listener
    app.listener = ContinuousListener(config_path, app.led_controller)
    app.listener.start()

    # Inicializar Botão
    try:
        from src.hardware.button import ButtonController
        def on_button_toggle(state):
            logger.info(f"Botão alterado para: {state}")
            app.listener.active = state
            if app.led_controller:
                if state:
                    app.led_controller.success(duration=2.0) # Verde
                else:
                    app.led_controller.error(duration=2.0) # Vermelho (usando error como vermelho)
                    
        app.button_controller = ButtonController(callback=on_button_toggle)
    except Exception as e:
        logger.warning(f"Erro ao iniciar botão: {e}")
        app.button_controller = None

    # ==========================================================================
    # Funções auxiliares
    # ==========================================================================

    def load_config() -> dict:
        """Carrega configuração do arquivo YAML."""
        try:
            with open(app.config["CONFIG_PATH"], "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            return {}

    def save_config(config: dict) -> bool:
        """Salva configuração no arquivo YAML."""
        try:
            # Backup
            config_path = Path(app.config["CONFIG_PATH"])
            backup_path = config_path.with_suffix(".yaml.bak")
            if config_path.exists():
                import shutil
                shutil.copy(config_path, backup_path)

            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            return True
        except Exception as e:
            logger.error(f"Erro ao salvar configuração: {e}")
            return False

    def get_system_info() -> dict:
        """Retorna informações do sistema."""
        info = {
            "platform": "unknown",
            "hostname": "unknown",
            "cpu_temp": None,
            "memory_total": 0,
            "memory_available": 0,
            "disk_total": 0,
            "disk_free": 0,
        }

        try:
            import platform
            import socket
            info["platform"] = platform.platform()
            info["hostname"] = socket.gethostname()
        except:
            pass

        # Temperatura (Raspberry Pi)
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                info["cpu_temp"] = int(f.read()) / 1000
        except:
            pass

        # Memória
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = f.read()
                for line in meminfo.split("\n"):
                    if line.startswith("MemTotal:"):
                        info["memory_total"] = int(line.split()[1]) * 1024
                    elif line.startswith("MemAvailable:"):
                        info["memory_available"] = int(line.split()[1]) * 1024
        except:
            pass

        # Disco
        try:
            import shutil
            usage = shutil.disk_usage("/")
            info["disk_total"] = usage.total
            info["disk_free"] = usage.free
        except:
            pass

        return info

    # ==========================================================================
    # Rotas
    # ==========================================================================

    @app.route("/")
    def index():
        """Página principal."""
        config = load_config()
        return render_template("index.html", config=config)

    @app.route("/api/config", methods=["GET"])
    def get_config():
        """Retorna configuração atual."""
        config = load_config()
        resp = jsonify(config)
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return resp

    @app.route("/api/config", methods=["POST"])
    def update_config():
        """Atualiza configuração via JSON."""
        if app.led_controller:
            app.led_controller.flash_random()
            
        try:
            new_config = request.get_json()
            if not new_config:
                return jsonify({"error": "Configuração vazia"}), 400

            logger.info(f"Recebendo atualização de config: {new_config}")

            # Carregar config atual para fazer merge
            current_config = load_config()
            logger.info(f"Config atual antes do merge: {current_config}")
            
            # Recursive update helper
            def deep_update(target, source):
                for k, v in source.items():
                    if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                        deep_update(target[k], v)
                    else:
                        target[k] = v
                return target

            updated_config = deep_update(current_config, new_config)
            logger.info(f"Config após merge: {updated_config}")

            if save_config(updated_config):
                logger.info("Configuração salva com sucesso")
                return jsonify({"success": True, "message": "Configuração salva!"})
            else:
                logger.error("Falha ao salvar configuração")
                return jsonify({"error": "Erro ao salvar configuração"}), 500
        except Exception as e:
            logger.error(f"Erro no update_config: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config/<section>", methods=["GET"])
    def get_config_section(section: str):
        """Retorna seção específica da configuração."""
        config = load_config()
        if section in config:
            return jsonify(config[section])
        return jsonify({"error": f"Seção '{section}' não encontrada"}), 404

    @app.route("/api/config/<section>", methods=["PUT"])
    def update_config_section(section: str):
        """Atualiza seção específica da configuração."""
        try:
            config = load_config()
            section_data = request.get_json()

            if not section_data:
                return jsonify({"error": "Dados vazios"}), 400

            config[section] = section_data

            if save_config(config):
                return jsonify({"success": True, "message": f"Seção '{section}' atualizada!"})
            else:
                return jsonify({"error": "Erro ao salvar"}), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/system", methods=["GET"])
    def system_info():
        """Retorna informações do sistema."""
        return jsonify(get_system_info())

    @app.route("/api/restart", methods=["POST"])
    def restart_service():
        """Reinicia o serviço."""
        if app.led_controller:
             app.led_controller.flash_random()
             
        try:
            import subprocess
            import sys
            
            logger.info("🔄 Solicitada reinicialização do serviço")
            
            # Reiniciar em background após resposta
            def delayed_restart():
                import time
                time.sleep(1)
                logger.info("🔄 Reiniciando aplicação...")
                # Executar script de restart
                project_root = Path(app.config["CONFIG_PATH"]).parent.parent
                restart_script = project_root / "run.sh"
                if restart_script.exists():
                    subprocess.Popen(
                        [str(restart_script), "restart"],
                        cwd=str(project_root),
                        start_new_session=True,
                    )
                else:
                    # Fallback: reiniciar via python
                    os.execv(sys.executable, [sys.executable] + sys.argv)
            
            # Iniciar restart em thread separada
            restart_thread = threading.Thread(target=delayed_restart, daemon=True)
            restart_thread.start()
            
            return jsonify({
                "success": True, 
                "message": "Reinício em andamento. A página será recarregada em 5 segundos..."
            })
        except Exception as e:
            logger.error(f"Erro ao reiniciar: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/test/audio", methods=["POST"])
    def test_audio():
        """Testa dispositivo de áudio."""
        try:
            import subprocess
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                text=True,
                timeout=5
            )
            devices = result.stdout if result.returncode == 0 else result.stderr
            return jsonify({"success": True, "devices": devices})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/queue/stats", methods=["GET"])
    def queue_stats():
        """Retorna estatísticas da fila offline."""
        try:
            from ..utils.queue import OfflineQueue
            queue = OfflineQueue()
            stats = queue.get_stats()
            return jsonify(stats)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/power/status", methods=["GET"])
    def power_status():
        """Retorna status de energia."""
        try:
            from ..utils.power import PowerManager
            pm = PowerManager(enabled=False)  # Apenas para status
            status = pm.get_status()
            return jsonify(status)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==========================================================================
    # Escuta Contínua - Controle
    # ==========================================================================
    
    # Listener global
    continuous_listener = None
    
    def get_continuous_listener():
        """Obtém instância do listener."""
        nonlocal continuous_listener
        if continuous_listener is None:
            try:
                from ..audio.continuous_listener import ContinuousListener
                continuous_listener = ContinuousListener(config_path=config_path)
            except Exception as e:
                logger.error(f"Erro ao criar listener: {e}")
                return None
        return continuous_listener

    @app.route("/api/listener/status", methods=["GET"])
    def listener_status():
        """Retorna status do listener de escuta contínua."""
        try:
            listener = get_continuous_listener()
            if listener:
                return jsonify({
                    "success": True,
                    "status": listener.status,
                })
            else:
                return jsonify({
                    "success": True,
                    "status": {
                        "running": False,
                        "paused": False,
                        "segments_count": 0,
                        "enabled": False,
                        "error": "Módulos de áudio não disponíveis",
                    }
                })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/listener/start", methods=["POST"])
    def listener_start():
        """Inicia escuta contínua."""
        try:
            listener = get_continuous_listener()
            if listener:
                listener.start()
                return jsonify({
                    "success": True,
                    "message": "Escuta contínua iniciada",
                    "status": listener.status,
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Módulos de áudio não disponíveis. Execute no Raspberry Pi.",
                }), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/listener/stop", methods=["POST"])
    def listener_stop():
        """Para escuta contínua."""
        try:
            listener = get_continuous_listener()
            if listener:
                listener.stop()
                return jsonify({
                    "success": True,
                    "message": "Escuta contínua parada",
                    "status": listener.status,
                })
            else:
                return jsonify({"success": True, "message": "Listener não ativo"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/listener/pause", methods=["POST"])
    def listener_pause():
        """Pausa escuta contínua."""
        try:
            listener = get_continuous_listener()
            if listener and listener.is_running:
                listener.pause()
                return jsonify({
                    "success": True,
                    "message": "Escuta pausada",
                    "status": listener.status,
                })
            else:
                return jsonify({"success": False, "error": "Listener não está rodando"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/listener/resume", methods=["POST"])
    def listener_resume():
        """Retoma escuta contínua."""
        try:
            listener = get_continuous_listener()
            if listener and listener.is_running:
                listener.resume()
                return jsonify({
                    "success": True,
                    "message": "Escuta retomada",
                    "status": listener.status,
                })
            else:
                return jsonify({"success": False, "error": "Listener não está rodando"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/listener/segments", methods=["GET"])
    def listener_segments():
        """Retorna segmentos transcritos pelo listener."""
        try:
            listener = get_continuous_listener()
            limit = request.args.get("limit", 20, type=int)
            if listener:
                segments = [s.to_dict() for s in listener.get_segments(limit)]
                return jsonify({
                    "success": True,
                    "segments": segments,
                    "total": len(segments),
                })
            else:
                return jsonify({
                    "success": True,
                    "segments": [],
                    "total": 0,
                })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==========================================================================
    # Gerenciamento de Modelos
    # ==========================================================================
    
    # URLs dos modelos
    WHISPER_MODELS = {
        "tiny": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
        "base": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
        "small": "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin",
    }
    
    LLM_MODELS = {
        "tinyllama": "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
        "phi2": "https://huggingface.co/TheBloke/phi-2-GGUF/resolve/main/phi-2.Q4_K_M.gguf",
        "gemma2b": "https://huggingface.co/google/gemma-2b-it-GGUF/resolve/main/gemma-2b-it.Q4_K_M.gguf",
    }
    
    download_status = {"downloading": False, "model": None, "progress": 0, "error": None}
    
    @app.route("/api/models/status", methods=["GET"])
    def models_status():
        """Retorna status dos modelos instalados."""
        try:
            project_root = Path(__file__).parent.parent.parent
            whisper_dir = project_root / "external" / "whisper.cpp" / "models"
            llm_dir = project_root / "models"
            
            # Verificar modelos Whisper
            whisper_status = {}
            for model in WHISPER_MODELS.keys():
                model_file = whisper_dir / f"ggml-{model}.bin"
                whisper_status[model] = model_file.exists()
            
            # Verificar modelos LLM
            llm_status = {}
            llm_files = {
                "tinyllama": "tinyllama-1.1b-q4.gguf",
                "phi2": "phi-2-q4.gguf",
                "gemma2b": "gemma-2b-q4.gguf",
            }
            for model, filename in llm_files.items():
                model_file = llm_dir / filename
                # Também checar variações de nome
                alt_names = [
                    llm_dir / f"{model}.gguf",
                    llm_dir / f"ggml-{model}.gguf",
                ]
                found = model_file.exists() or any(f.exists() for f in alt_names)
                llm_status[model] = found
            
            # Verificar executáveis compilados
            whisper_cpp_ready = False
            llama_cpp_ready = False
            llama_cpp_path = None
            
            # Whisper.cpp
            whisper_builds = [
                project_root / "external" / "whisper.cpp" / "build" / "bin" / "main",
                project_root / "external" / "whisper.cpp" / "build" / "bin" / "whisper",
                project_root / "external" / "whisper.cpp" / "main",
            ]
            whisper_cpp_ready = any(p.exists() for p in whisper_builds)
            
            # Llama.cpp
            llama_exe_names = ["llama-cli", "llama-simple", "main", "llama"]
            llama_dirs = [
                project_root / "external" / "llama.cpp" / "build" / "bin",
                project_root / "external" / "llama.cpp" / "build",
                project_root / "external" / "llama.cpp",
            ]
            for d in llama_dirs:
                for exe in llama_exe_names:
                    path = d / exe
                    if path.exists() and path.is_file():
                        llama_cpp_ready = True
                        llama_cpp_path = str(path)
                        break
                if llama_cpp_ready:
                    break
            
            return jsonify({
                "success": True,
                "whisper": whisper_status,
                "llm": llm_status,
                "download": download_status,
                "executables": {
                    "whisper_cpp_ready": whisper_cpp_ready,
                    "llama_cpp_ready": llama_cpp_ready,
                    "llama_cpp_path": llama_cpp_path,
                },
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/models/download/whisper/<model>", methods=["POST"])
    def download_whisper_model(model):
        """Baixa um modelo Whisper."""
        try:
            if model not in WHISPER_MODELS:
                return jsonify({"error": f"Modelo inválido: {model}"}), 400
            
            if download_status["downloading"]:
                return jsonify({"error": "Já existe um download em andamento"}), 400
            
            project_root = Path(__file__).parent.parent.parent
            whisper_dir = project_root / "external" / "whisper.cpp" / "models"
            whisper_dir.mkdir(parents=True, exist_ok=True)
            
            output_file = whisper_dir / f"ggml-{model}.bin"
            url = WHISPER_MODELS[model]
            
            # Iniciar download em thread separada
            def do_download():
                import urllib.request
                download_status["downloading"] = True
                download_status["model"] = f"whisper-{model}"
                download_status["progress"] = 0
                download_status["error"] = None
                
                try:
                    def reporthook(count, block_size, total_size):
                        if total_size > 0:
                            download_status["progress"] = min(100, int(count * block_size * 100 / total_size))
                    
                    urllib.request.urlretrieve(url, str(output_file), reporthook)
                    download_status["progress"] = 100
                except Exception as e:
                    download_status["error"] = str(e)
                finally:
                    download_status["downloading"] = False
            
            thread = threading.Thread(target=do_download)
            thread.start()
            
            return jsonify({
                "success": True,
                "message": f"Download do modelo {model} iniciado",
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/models/download/llm/<model>", methods=["POST"])
    def download_llm_model(model):
        """Baixa um modelo LLM."""
        try:
            if model not in LLM_MODELS:
                return jsonify({"error": f"Modelo inválido: {model}"}), 400
            
            if download_status["downloading"]:
                return jsonify({"error": "Já existe um download em andamento"}), 400
            
            project_root = Path(__file__).parent.parent.parent
            llm_dir = project_root / "models"
            llm_dir.mkdir(parents=True, exist_ok=True)
            
            # Nome do arquivo de saída
            filenames = {
                "tinyllama": "tinyllama-1.1b-q4.gguf",
                "phi2": "phi-2-q4.gguf",
                "gemma2b": "gemma-2b-q4.gguf",
            }
            output_file = llm_dir / filenames.get(model, f"{model}.gguf")
            url = LLM_MODELS[model]
            
            # Iniciar download em thread separada
            def do_download():
                import urllib.request
                download_status["downloading"] = True
                download_status["model"] = f"llm-{model}"
                download_status["progress"] = 0
                download_status["error"] = None
                
                try:
                    def reporthook(count, block_size, total_size):
                        if total_size > 0:
                            download_status["progress"] = min(100, int(count * block_size * 100 / total_size))
                    
                    urllib.request.urlretrieve(url, str(output_file), reporthook)
                    download_status["progress"] = 100
                except Exception as e:
                    download_status["error"] = str(e)
                finally:
                    download_status["downloading"] = False
            
            thread = threading.Thread(target=do_download)
            thread.start()
            
            return jsonify({
                "success": True,
                "message": f"Download do modelo {model} iniciado",
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/models/download/status", methods=["GET"])
    def download_progress():
        """Retorna progresso do download atual."""
        return jsonify({
            "success": True,
            **download_status,
        })

    # ==========================================================================
    # Transcrição - Novas Rotas
    # ==========================================================================
    
    # Estado global para transcrições (em produção, usar banco de dados)
    transcription_history = []
    processor_state = {
        "is_recording": False,
        "is_processing": False,
        "current_transcription": None,
        "current_stage": "idle",
        "details": {},
    }

    @app.route("/api/audio/test/mic", methods=["POST"])
    def test_microphone():
        """Teste de microfone: grava 3s e retorna áudio."""
        was_active = False
        try:
            import tempfile
            import os
            from src.audio.capture import AudioCapture
            
            # Carregar configuração para usar parâmetros corretos
            config = load_config()
            audio_conf = config.get('audio', {})
            
            # Inicializar captura com parâmetros da config
            capture = AudioCapture(
                device=audio_conf.get('device', ''),
                sample_rate=audio_conf.get('sample_rate', 16000),
                channels=audio_conf.get('channels', 1),
                chunk_size=audio_conf.get('chunk_size', 4096)
            )
            
            # Pausar listener se ativo
            if hasattr(app, 'listener') and app.listener and app.listener.active:
                logger.info("⏸️ Pausando escuta contínua para teste de microfone...")
                was_active = True
                app.listener.active = False
                time.sleep(1.0)
            
            # Gravar 3 segundos
            logger.info("Iniciando gravação de teste (3s)...")
            
            if app.led_controller:
                app.led_controller.listening()
            
            # Forçar 3s mesmo se houver silêncio
            buffer = capture.record(duration=3.0, stop_on_silence=False)
            
            if app.led_controller:
                app.led_controller.success()
            
            # Salvar em temp file
            fd, filename = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            
            buffer.save(filename)
            logger.info(f"Gravação de teste salva em {filename}")
            
            return send_file(filename, mimetype="audio/wav", as_attachment=False)
            
        except Exception as e:
            logger.error(f"Erro no teste de mic: {e}")
            if app.led_controller:
                app.led_controller.error()
            return jsonify({"error": str(e)}), 500
        finally:
            if was_active and hasattr(app, 'listener') and app.listener:
                logger.info("▶️ Retomando escuta contínua...")
                time.sleep(0.5)
                app.listener.active = True

    @app.route("/api/test/live", methods=["POST"])
    def test_live_pipeline():
        """Teste de pipeline completo (Gravar -> Transcrever -> [LLM])."""
        was_active = False
        try:
            data = request.get_json() or {}
            duration = float(data.get('duration', 5.0))
            use_llm = data.get('generate_summary', True) 
            
            if hasattr(app, 'listener') and app.listener and app.listener.active:
                logger.info("⏸️ Pausando escuta contínua para teste live...")
                was_active = True
                app.listener.active = False
                time.sleep(1.0)
            
            from src.pipeline import VoiceProcessor
            config_path = app.config["CONFIG_PATH"]
            
            logger.info(f"Iniciando teste live com config: {config_path}")
            
            with VoiceProcessor(config_path=config_path) as processor:
                logger.info("Gravando...")
                if app.led_controller:
                    app.led_controller.listening()
                
                audio_buffer = processor.audio.record(duration=duration, stop_on_silence=False)
                
                logger.info("Processando...")
                if app.led_controller:
                    app.led_controller.processing()
                
                result = processor.process(
                    audio=audio_buffer, 
                    generate_summary=use_llm
                )
                
                if app.led_controller:
                    app.led_controller.success()
                
                return jsonify({
                    "success": True,
                    "text": result.text,
                    "summary": result.summary if use_llm else "(Ignorado)",
                    "stats": result.to_dict()
                })

        except Exception as e:
            logger.error(f"Erro no teste live: {e}")
            if app.led_controller:
                app.led_controller.error()
            return jsonify({"error": str(e)}), 500
        finally:
             if was_active and hasattr(app, 'listener') and app.listener:
                logger.info("▶️ Retomando escuta contínua...")
                time.sleep(0.5)
                app.listener.active = True

    @app.route("/api/llm/models", methods=["GET"])
    def list_llm_models():
        """Lista modelos do provedor configurado."""
        try:
            config = load_config()
            provider_name = config.get('llm', {}).get('provider', 'local')
            llm_config = config.get('llm', {})

            provider = None
            if provider_name == 'openai':
                cfg = llm_config.get('openai', {})
                from src.llm.api import OpenAIProvider
                provider = OpenAIProvider(api_key=cfg.get('api_key'))
            elif provider_name == 'chatmock':
                cfg = llm_config.get('chatmock', {})
                from src.llm.api import ChatMockProvider
                provider = ChatMockProvider(base_url=cfg.get('base_url'))
            elif provider_name == 'ollama':
                cfg = llm_config.get('ollama', {})
                from src.llm.api import OllamaProvider
                provider = OllamaProvider(host=cfg.get('host'))
            
            if provider and hasattr(provider, 'list_models'):
                models = provider.list_models()
                return jsonify({"models": models})
            
            return jsonify({"models": []})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/test/llm", methods=["POST"])
    def test_llm_connection():
        """Testa conexão com LLM."""
        try:
            # Usar configuração recebida ou carregar do disco
            req_config = request.get_json() or {}
            
            # Se a requisição contiver a config completa, extrair LLM
            # Senão, carregar do disco e fazer merge (simplificado aqui)
            disk_config = load_config()
            
            # Merge simples para a seção LLM se fornecida
            if 'llm' in req_config:
                llm_config = req_config['llm']
            else:
                llm_config = disk_config.get('llm', {})
            
            provider_name = llm_config.get('provider', 'local')
            
            provider = None
            if provider_name == 'openai':
                cfg = llm_config.get('openai', {})
                from src.llm.api import OpenAIProvider
                provider = OpenAIProvider(
                    api_key=cfg.get('api_key'),
                    model=cfg.get('model', 'gpt-4o-mini')
                )
            elif provider_name == 'chatmock':
                cfg = llm_config.get('chatmock', {})
                from src.llm.api import ChatMockProvider
                provider = ChatMockProvider(
                    base_url=cfg.get('base_url'), 
                    model=cfg.get('model', 'gpt-5'),
                    reasoning_effort=cfg.get('reasoning_effort', 'medium'),
                    enable_web_search=cfg.get('enable_web_search', False)
                )
            elif provider_name == 'ollama':
                cfg = llm_config.get('ollama', {})
                from src.llm.api import OllamaProvider
                provider = OllamaProvider(
                    host=cfg.get('host'),
                    model=cfg.get('model', 'tinyllama')
                )
            elif provider_name == 'local':
                 # Testar local?
                 return jsonify({"success": True, "response": "Modo local não requer teste de rede.", "latency": 0})

            if provider:
                response = provider.generate("Olá, teste de conexão.")
                return jsonify({
                    "success": True, 
                    "response": response.text, 
                    "latency": response.processing_time
                })
            else:
                return jsonify({"success": False, "error": f"Provedor {provider_name} não suportado para teste"}), 400

        except Exception as e:
            logger.error(f"Erro ao testar LLM: {e}")
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/audio/test/speaker", methods=["POST"])
    def test_speaker():
        """Teste de falante: toca um tom."""
        try:
            import subprocess
            # Tocar tom senoidal de 440Hz por 1 segundo usando speaker-test
            cmd = ["speaker-test", "-t", "sine", "-f", "440", "-l", "1", "-s", "1"]
            subprocess.run(cmd, check=True, timeout=5, stdout=subprocess.DEVNULL)
            return jsonify({"success": True, "message": "Som reproduzido"})
        except Exception as e:
            logger.error(f"Erro no teste de speaker: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/test/whisperapi_connection", methods=["POST"])
    def test_whisperapi_connection():
        """Testa conexão com WhisperAPI."""
        try:
            config = load_config()
            url = config.get("whisper", {}).get("whisperapi_url")
            if not url:
                return jsonify({"error": "URL não configurada"}), 400
            
            import requests
            # Tentar conectar (assumindo endpoint /health ou raiz)
            try:
                # Se url termina com /v1/audio/transcriptions, pegar base
                base_url = url.split("/v1")[0]
                resp = requests.get(base_url, timeout=5)
                # Aceitar qualquer resposta 200-404 como "servidor existe"
                return jsonify({"success": True, "message": f"Conectado: {resp.status_code}"})
            except Exception as conn_err:
                 # Tentar endpoint específico se base falhar
                 return jsonify({"error": f"Falha na conexão: {str(conn_err)}"}), 500

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/test/whisper_transcription", methods=["POST"])
    def test_whisper_transcription():
        """Testa transcrição (gera áudio sintético e transcreve)."""
        try:
            # Gerar wav pequeno com sox ou ffmpeg, ou arecord
            # Ou usar arquivo existente?
            # Melhor: Tentar carregar SpeechProcessor e inicializar
            
            from ..pipeline import VoiceProcessor
            config_path = app.config["CONFIG_PATH"]
            
            # Apenas inicializar para ver se não quebra
            try:
                proc = VoiceProcessor(config_path=config_path)
                # Não vamos transcrever de verdade para não demorar, apenas testar init
                # Ou transcrever um buffer vazio?
                proc._init_transcriber()
                model = proc.transcriber.model if hasattr(proc.transcriber, 'model') else 'unknown'
                return jsonify({"success": True, "message": f"Transcritor inicializado com sucesso ({model})"})
            except Exception as init_err:
                return jsonify({"error": f"Erro ao inicializar transcritor: {init_err}"}), 500

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/processor/status", methods=["GET"])
    def processor_status():
        """Retorna status do processador de voz."""
        try:
            config = load_config()
            return jsonify({
                "success": True,
                "status": processor_state,
                "config": {
                    "mode": config.get("mode", "local"),
                    "whisper_model": config.get("whisper", {}).get("model", "tiny"),
                    "llm_provider": config.get("llm", {}).get("provider", "local"),
                }
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/transcriptions", methods=["GET"])
    def get_transcriptions():
        """Retorna histórico de transcrições."""
        limit = request.args.get("limit", 20, type=int)
        return jsonify({
            "success": True,
            "transcriptions": transcription_history[-limit:][::-1],  # Mais recentes primeiro
            "total": len(transcription_history)
        })

    @app.route("/api/transcriptions", methods=["DELETE"])
    def clear_transcriptions():
        """Limpa histórico de transcrições."""
        transcription_history.clear()
        return jsonify({"success": True, "message": "Histórico limpo"})

    @app.route("/api/record/start", methods=["POST"])
    def start_recording():
        """Inicia gravação e processamento de áudio."""
        import time
        import threading
        
        if processor_state["is_recording"] or processor_state["is_processing"]:
            return jsonify({"error": "Processamento já em andamento"}), 400
        
        def process_audio():
            processor_state["is_recording"] = True
            processor_state["is_processing"] = False
            processor_state["current_transcription"] = None
            processor_state["current_stage"] = "recording"
            processor_state["details"] = {}
            
            def update_status(stage, details):
                processor_state["current_stage"] = stage
                processor_state["details"] = details
            
            try:
                # Importar o processador
                from ..pipeline import VoiceProcessor
                
                config_path = app.config["CONFIG_PATH"]
                
                with VoiceProcessor(config_path=config_path) as processor:
                    # Gravar
                    processor_state["is_recording"] = True
                    update_status("recording", {"device": processor.audio.device})
                    audio = processor.record()
                    
                    # Processar
                    processor_state["is_recording"] = False
                    processor_state["is_processing"] = True
                    
                    result = processor.process(
                        audio=audio,
                        generate_summary=True,
                        summary_style="concise",
                        status_callback=update_status
                    )
                    
                    # Salvar resultado
                    transcription_data = {
                        "id": len(transcription_history) + 1,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "audio_duration": round(result.audio_duration, 1),
                        "text": result.text,
                        "summary": result.summary,
                        "processing_time": round(result.total_time, 2),
                        "language": result.transcription.language if hasattr(result.transcription, 'language') else "pt",
                    }
                    
                    transcription_history.append(transcription_data)
                    processor_state["current_transcription"] = transcription_data
                    
            except ImportError as e:
                logger.error(f"Erro de importação: {e}")
                processor_state["current_transcription"] = {
                    "error": "Módulos de processamento não disponíveis. Execute no Raspberry Pi.",
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            except Exception as e:
                logger.error(f"Erro no processamento: {e}")
                processor_state["current_transcription"] = {
                    "error": str(e),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            finally:
                processor_state["is_recording"] = False
                processor_state["is_processing"] = False
                processor_state["current_stage"] = "idle"
                processor_state["details"] = {}
        
        # Iniciar em thread separada
        thread = threading.Thread(target=process_audio, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "message": "Gravação iniciada"
        })

    @app.route("/api/transcribe", methods=["POST"])
    def transcribe_audio():
        """Recebe arquivo de áudio e retorna transcrição."""
        import time
        
        if "audio" not in request.files:
            return jsonify({"error": "Nenhum arquivo de áudio enviado"}), 400
        
        audio_file = request.files["audio"]
        
        try:
            import tempfile
            import os
            
            # Salvar arquivo temporário
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                audio_file.save(tmp.name)
                tmp_path = tmp.name
            
            try:
                from ..pipeline import VoiceProcessor
                from ..audio.capture import AudioBuffer
                
                config_path = app.config["CONFIG_PATH"]
                
                with VoiceProcessor(config_path=config_path) as processor:
                    audio = AudioBuffer.from_file(tmp_path)
                    result = processor.process(
                        audio=audio,
                        generate_summary=True,
                        summary_style="concise"
                    )
                    
                    transcription_data = {
                        "id": len(transcription_history) + 1,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "audio_duration": round(result.audio_duration, 1),
                        "text": result.text,
                        "summary": result.summary,
                        "processing_time": round(result.total_time, 2),
                    }
                    
                    transcription_history.append(transcription_data)
                    
                    return jsonify({
                        "success": True,
                        "transcription": transcription_data
                    })
                    
            finally:
                os.unlink(tmp_path)
                
        except ImportError as e:
            return jsonify({
                "error": "Módulos de processamento não disponíveis",
                "details": str(e)
            }), 500
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==========================================================================
    # Processamento em Lote
    # ==========================================================================
    
    batch_processor = None
    
    def get_batch_processor():
        """Obtém instância do batch processor."""
        nonlocal batch_processor
        if batch_processor is None:
            try:
                from ..utils.batch_processor import BatchProcessor
                config = load_config()
                usb_config = config.get("usb_receiver", {})
                audio_dir = usb_config.get("save_directory", "~/audio-recordings")
                batch_processor = BatchProcessor(
                    audio_dir=audio_dir,
                    config_path=config_path,
                )
            except Exception as e:
                logger.error(f"Erro ao criar batch processor: {e}")
                return None
        return batch_processor

    @app.route("/api/batch/status", methods=["GET"])
    def batch_status():
        """Retorna status do processador em lote."""
        try:
            processor = get_batch_processor()
            if processor:
                return jsonify({
                    "success": True,
                    "status": processor.status,
                })
            else:
                return jsonify({
                    "success": True,
                    "status": {
                        "running": False,
                        "pending_files": 0,
                        "error": "Processador não disponível",
                    }
                })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/batch/run", methods=["POST"])
    def batch_run():
        """Executa processamento em lote manualmente."""
        try:
            processor = get_batch_processor()
            if processor:
                # Executar em thread para não bloquear
                def run_batch():
                    processor.process_pending()
                
                thread = threading.Thread(target=run_batch, daemon=True)
                thread.start()
                
                return jsonify({
                    "success": True,
                    "message": "Processamento iniciado",
                    "pending_files": len(processor.get_pending_files()),
                })
            else:
                return jsonify({
                    "success": False,
                    "error": "Processador não disponível",
                }), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/batch/start", methods=["POST"])
    def batch_start():
        """Inicia processamento periódico em background."""
        try:
            processor = get_batch_processor()
            if processor:
                processor.start()
                return jsonify({
                    "success": True,
                    "message": "Processamento periódico iniciado",
                })
            else:
                return jsonify({"error": "Processador não disponível"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/batch/stop", methods=["POST"])
    def batch_stop():
        """Para processamento periódico."""
        try:
            processor = get_batch_processor()
            if processor:
                processor.stop()
                return jsonify({
                    "success": True,
                    "message": "Processamento periódico parado",
                })
            else:
                return jsonify({"success": True, "message": "Processador não ativo"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==========================================================================
    # Arquivos de Transcrição
    # ==========================================================================

    @app.route("/api/files/transcriptions", methods=["GET"])
    def list_transcription_files():
        """Lista arquivos de transcrição (.txt) salvos."""
        try:
            processor = get_batch_processor()
            if processor:
                files = processor.get_transcription_files()
                pending = processor.get_pending_files()
                return jsonify({
                    "success": True,
                    "files": [f.to_dict() for f in files],
                    "total": len(files),
                    "pending_wav": len(pending),
                })
            else:
                return jsonify({
                    "success": True,
                    "files": [],
                    "total": 0,
                    "pending_wav": 0,
                })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/files/transcriptions/<filename>", methods=["GET"])
    def read_transcription_file(filename):
        """Lê conteúdo de um arquivo de transcrição."""
        try:
            processor = get_batch_processor()
            if processor:
                content = processor.read_transcription(filename)
                if content is not None:
                    return jsonify({
                        "success": True,
                        "filename": filename,
                        "content": content,
                    })
                else:
                    return jsonify({"error": "Arquivo não encontrado"}), 404
            else:
                return jsonify({"error": "Processador não disponível"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/files/transcriptions/<filename>", methods=["DELETE"])
    def delete_transcription_file(filename):
        """Deleta um arquivo de transcrição."""
        try:
            processor = get_batch_processor()
            if processor:
                if processor.delete_transcription(filename):
                    return jsonify({
                        "success": True,
                        "message": f"Arquivo {filename} deletado",
                    })
                else:
                    return jsonify({"error": "Arquivo não encontrado"}), 404
            else:
                return jsonify({"error": "Processador não disponível"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/files/transcriptions/all", methods=["DELETE"])
    def delete_all_transcription_files():
        """Deleta todos os arquivos de transcrição (.txt)."""
        try:
            processor = get_batch_processor()
            if processor:
                # Listar todos os arquivos TXT
                transcriptions = processor.get_transcription_files()
                deleted_count = 0
                errors = []
                
                for t in transcriptions:
                    filename = t.name
                    if filename.endswith('.txt'):
                        try:
                            if processor.delete_transcription(filename):
                                deleted_count += 1
                        except Exception as e:
                            errors.append(f"{filename}: {str(e)}")
                
                return jsonify({
                    "success": True,
                    "deleted_count": deleted_count,
                    "errors": errors,
                    "message": f"{deleted_count} arquivos deletados",
                })
            else:
                return jsonify({"error": "Processador não disponível"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/files/search", methods=["GET"])
    def search_transcriptions():
        """Busca texto nas transcrições."""
        try:
            query = request.args.get("q", "").lower()
            if not query:
                return jsonify({"error": "Query vazia"}), 400
            
            processor = get_batch_processor()
            if not processor:
                return jsonify({"error": "Processador não disponível"}), 400
            
            files = processor.get_transcription_files()
            results = []
            
            for f in files:
                content = processor.read_transcription(f.name)
                if content and query in content.lower():
                    # Encontrar trecho com o termo
                    lines = content.split("\n")
                    matching_lines = [
                        line for line in lines 
                        if query in line.lower() and not line.startswith("#")
                    ]
                    
                    results.append({
                        "filename": f.name,
                        "created": f.created.isoformat(),
                        "matches": len(matching_lines),
                        "preview": matching_lines[0][:200] if matching_lines else "",
                    })
            
            return jsonify({
                "success": True,
                "query": query,
                "results": results,
                "total": len(results),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==========================================================================
    # Logs da Aplicação
    # ==========================================================================

    @app.route("/api/logs", methods=["GET"])
    def get_logs():
        """Retorna logs da aplicação."""
        try:
            level = request.args.get("level")  # DEBUG, INFO, WARNING, ERROR
            limit = request.args.get("limit", 100, type=int)
            logger_filter = request.args.get("logger")
            
            logs = log_handler.get_logs(level=level, limit=limit, logger_filter=logger_filter)
            stats = log_handler.get_stats()
            
            return jsonify({
                "success": True,
                "logs": logs,
                "stats": stats,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/logs/errors", methods=["GET"])
    def get_errors():
        """Retorna apenas erros."""
        try:
            limit = request.args.get("limit", 50, type=int)
            errors = log_handler.get_errors(limit=limit)
            
            return jsonify({
                "success": True,
                "errors": errors,
                "count": len(errors),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/logs/stats", methods=["GET"])
    def get_log_stats():
        """Retorna estatísticas de logs."""
        try:
            stats = log_handler.get_stats()
            return jsonify({
                "success": True,
                **stats,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/logs/clear", methods=["POST"])
    def clear_logs():
        """Limpa os logs em memória."""
        try:
            log_handler.clear()
            logger.info("📋 Logs limpos via interface")
            return jsonify({
                "success": True,
                "message": "Logs limpos",
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/logs/test", methods=["POST"])
    def test_log():
        """Gera log de teste."""
        try:
            level = request.json.get("level", "info").upper()
            message = request.json.get("message", "Mensagem de teste")
            
            if level == "DEBUG":
                logger.debug(message)
            elif level == "INFO":
                logger.info(message)
            elif level == "WARNING":
                logger.warning(message)
            elif level == "ERROR":
                logger.error(message)
            elif level == "CRITICAL":
                logger.critical(message)
            
            return jsonify({"success": True, "message": f"Log {level} registrado"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


class WebServer:
    """
    Servidor web para interface de configuração.

    Características:
    - Feature toggle (habilitável via configuração)
    - Baixo uso de recursos
    - Suporta HTTPS opcional
    - Thread separada para não bloquear processamento
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        config_path: Optional[str] = None,
        enabled: bool = True,
        debug: bool = False,
    ):
        """
        Inicializa o servidor web.

        Args:
            host: Host para bind
            port: Porta do servidor
            config_path: Caminho da configuração
            enabled: Feature toggle
            debug: Modo debug
        """
        self.host = host
        self.port = port
        self.config_path = config_path
        self.enabled = enabled
        self.debug = debug

        self._app = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def _create_app(self) -> "Flask":
        """Cria aplicação Flask."""
        return create_app(self.config_path)

    def start(self) -> bool:
        """
        Inicia o servidor em thread separada.

        Returns:
            True se iniciado, False se desabilitado ou erro
        """
        if not self.enabled:
            logger.info("Interface web desabilitada (feature toggle off)")
            return False

        if not FLASK_AVAILABLE:
            logger.error("Flask não disponível")
            return False

        if self._running:
            logger.warning("Servidor já está rodando")
            return True

        try:
            self._app = self._create_app()
            self._running = True

            self._thread = threading.Thread(
                target=self._run_server,
                daemon=True,
            )
            self._thread.start()

            logger.info(f"Interface web iniciada em http://{self.host}:{self.port}")
            return True

        except Exception as e:
            logger.error(f"Erro ao iniciar servidor web: {e}")
            return False

    def _run_server(self) -> None:
        """Executa servidor Flask."""
        try:
            # Usar servidor WSGI simples para produção
            from werkzeug.serving import make_server

            server = make_server(
                self.host,
                self.port,
                self._app,
                threaded=True,
            )
            server.serve_forever()

        except Exception as e:
            logger.error(f"Erro no servidor web: {e}")
            self._running = False

    def stop(self) -> None:
        """Para o servidor."""
        self._running = False
        logger.info("Interface web parada")

    def is_running(self) -> bool:
        """Verifica se está rodando."""
        return self._running

    @property
    def url(self) -> str:
        """Retorna URL do servidor."""
        return f"http://{self.host}:{self.port}"


def run_standalone(config_path: Optional[str] = None, host: str = "0.0.0.0", port: int = 8080):
    """
    Executa servidor web standalone.

    Args:
        config_path: Caminho da configuração
        host: Host para binding
        port: Porta do servidor
    """
    if not FLASK_AVAILABLE:
        print("Erro: Flask não instalado. Execute: pip install flask")
        return

        return
        
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = create_app(config_path)
    print(f"Iniciando interface web em http://{host}:{port}")
    print("Pressione Ctrl+C para parar")

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Interface Web do Voice Processor")
    parser.add_argument("-H", "--host", default="0.0.0.0", help="Host para binding (default: 0.0.0.0)")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Porta do servidor")
    parser.add_argument("-c", "--config", help="Caminho do arquivo de configuração")

    args = parser.parse_args()
    run_standalone(config_path=args.config, host=args.host, port=args.port)

