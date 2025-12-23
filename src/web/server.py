"""
Servidor Web leve para configuração do Voice Processor.
Otimizado para Raspberry Pi - baixo uso de recursos.
"""

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Tentar importar Flask, fallback para servidor básico
try:
    from flask import Flask, render_template, request, jsonify, send_from_directory
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logger.warning("Flask não instalado. Execute: pip install flask")


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
        return jsonify(config)

    @app.route("/api/config", methods=["POST"])
    def update_config():
        """Atualiza configuração."""
        try:
            new_config = request.get_json()
            if not new_config:
                return jsonify({"error": "Configuração vazia"}), 400

            if save_config(new_config):
                return jsonify({"success": True, "message": "Configuração salva!"})
            else:
                return jsonify({"error": "Erro ao salvar configuração"}), 500
        except Exception as e:
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
        """Reinicia o serviço (placeholder)."""
        return jsonify({"success": True, "message": "Reinício solicitado"})

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
    # Transcrição - Novas Rotas
    # ==========================================================================
    
    # Estado global para transcrições (em produção, usar banco de dados)
    transcription_history = []
    processor_state = {
        "is_recording": False,
        "is_processing": False,
        "current_transcription": None,
    }

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
            
            try:
                # Importar o processador
                from ..pipeline import VoiceProcessor
                
                config_path = app.config["CONFIG_PATH"]
                
                with VoiceProcessor(config_path=config_path) as processor:
                    # Gravar
                    processor_state["is_recording"] = True
                    audio = processor.record()
                    
                    # Processar
                    processor_state["is_recording"] = False
                    processor_state["is_processing"] = True
                    
                    result = processor.process(
                        audio=audio,
                        generate_summary=True,
                        summary_style="concise"
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

