#!/usr/bin/env python3
"""
Raspberry Pi Voice Processor - Ponto de entrada principal.

Uso:
    python3 src/main.py                    # Modo interativo
    python3 src/main.py --continuous       # Escuta contínua
    python3 src/main.py --file audio.wav   # Processar arquivo
    python3 src/main.py --test             # Teste rápido
"""

import argparse
import logging
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import VoiceProcessor, ProcessingResult
from src.utils.config import load_config


def setup_logging(level: str = "INFO") -> None:
    """Configura logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_result(result: ProcessingResult) -> None:
    """Imprime resultado formatado."""
    print("\n" + "=" * 60)
    print("RESULTADO")
    print("=" * 60)

    print(f"\n📊 Estatísticas:")
    print(f"   Duração do áudio: {result.audio_duration:.1f}s")
    print(f"   Tempo de transcrição: {result.transcription.processing_time:.2f}s")
    print(f"   Tempo total: {result.total_time:.2f}s")

    print(f"\n📝 Transcrição:")
    print(f"   {result.text}")

    if result.summary:
        print(f"\n📋 Resumo:")
        print(f"   {result.summary}")

    print("\n" + "=" * 60)


def interactive_mode(processor: VoiceProcessor) -> None:
    """Modo interativo."""
    print("\n🎙️  Raspberry Pi Voice Processor")
    print("=" * 40)
    print("Comandos:")
    print("  [ENTER] - Gravar e processar")
    print("  [r]     - Apenas gravar e transcrever")
    print("  [s]     - Resumir última transcrição")
    print("  [q]     - Sair")
    print("=" * 40)

    last_text = ""

    while True:
        try:
            cmd = input("\n> Pressione ENTER para gravar (q=sair): ").strip().lower()

            if cmd == "q":
                print("Saindo...")
                break

            if cmd == "s" and last_text:
                print("\nGerando resumo...")
                response = processor.summarize(last_text)
                print(f"\n📋 Resumo: {response.text}")
                continue

            # Gravar e processar
            print("\n🔴 Gravando... (fale agora)")

            generate_summary = cmd != "r"
            result = processor.process(generate_summary=generate_summary)

            if result.text.strip():
                print_result(result)
                last_text = result.text
            else:
                print("\n⚠️  Nenhuma fala detectada")

        except KeyboardInterrupt:
            print("\n\nInterrompido pelo usuário")
            break


def continuous_mode(processor: VoiceProcessor) -> None:
    """Modo de escuta contínua."""
    print("\n🎙️  Modo de escuta contínua")
    print("Pressione Ctrl+C para parar\n")

    def on_result(result: ProcessingResult):
        print(f"\n[{result.audio_duration:.1f}s] {result.text}")
        if result.summary:
            print(f"  → Resumo: {result.summary}")

    processor.continuous_listen(
        callback=on_result,
        min_duration=1.0,
        generate_summary=True,
    )


def process_file(processor: VoiceProcessor, file_path: str) -> None:
    """Processa arquivo de áudio."""
    print(f"\n📁 Processando arquivo: {file_path}")

    if not Path(file_path).exists():
        print(f"❌ Arquivo não encontrado: {file_path}")
        return

    result = processor.process_file(file_path)
    print_result(result)


def test_mode(processor: VoiceProcessor) -> None:
    """Teste rápido do sistema."""
    print("\n🧪 Teste do sistema")
    print("=" * 40)

    status = processor.get_status()

    print(f"\n✅ Modo: {status['mode']}")
    print(f"✅ Áudio: sample_rate={status['audio']['sample_rate']}, vad={status['audio']['vad_enabled']}")
    print(f"✅ Whisper: model={status['whisper']['model']}, cpp={status['whisper']['use_cpp']}")
    print(f"✅ LLM: provider={status['llm']['provider']}, available={status['llm']['available']}")

    if status['cache']['enabled']:
        cache_stats = status['cache']['stats']
        print(f"✅ Cache: {cache_stats['memory_entries']} em memória, {cache_stats['disk_entries']} em disco")

    print("\n📝 Teste de gravação (3 segundos)...")

    try:
        from src.audio.capture import AudioCapture

        with AudioCapture() as capture:
            devices = capture.list_devices()
            print(f"   Dispositivos disponíveis: {len(devices)}")
            for d in devices[:3]:
                print(f"   - {d['name']}")

        print("✅ Áudio OK")
    except Exception as e:
        print(f"❌ Erro de áudio: {e}")

    print("\n🎯 Sistema pronto para uso!")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Raspberry Pi Voice Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-c", "--config",
        help="Caminho do arquivo de configuração",
        default=None,
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Modo de escuta contínua",
    )
    parser.add_argument(
        "-f", "--file",
        help="Processar arquivo de áudio",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Executar teste do sistema",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Output detalhado",
    )

    args = parser.parse_args()

    # Configurar logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(log_level)

    # Carregar configuração
    try:
        config = load_config(args.config)
    except FileNotFoundError as e:
        print(f"❌ Erro: {e}")
        print("Execute: cp config/config.example.yaml config/config.yaml")
        sys.exit(1)

    # Criar processador
    with VoiceProcessor(config=config) as processor:
        if args.test:
            test_mode(processor)
        elif args.file:
            process_file(processor, args.file)
        elif args.continuous:
            continuous_mode(processor)
        else:
            interactive_mode(processor)


if __name__ == "__main__":
    main()
