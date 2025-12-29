#!/usr/bin/env python3
"""
Teste de Fallback para Whisper.cpp Local
Simula falha de todos os servidores API para testar transcrição local.
"""
import time
import wave
import numpy as np
import os

print("="*60)
print("TESTE DE FALLBACK PARA WHISPER.CPP LOCAL")
print("="*60)

# 1. Criar arquivo de áudio de teste
print("\n1. Criando arquivo de áudio de teste...")
sample_rate = 16000
duration = 3  # 3 segundos
samples = np.random.randint(-100, 100, sample_rate * duration, dtype=np.int16)

test_audio = "/tmp/test_fallback.wav"
with wave.open(test_audio, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    wav.writeframes(samples.tobytes())
print(f"   Arquivo criado: {test_audio}")

# 2. Criar cliente com URLs INVÁLIDAS para forçar fallback
print("\n2. Criando cliente WhisperAPI com URLs inválidas...")
from src.transcription.whisper import WhisperAPIClient

client = WhisperAPIClient(
    base_url="http://192.168.99.99:3001",  # URL inválida
    base_urls=[
        "http://192.168.99.98:3001",
        "http://192.168.99.97:3001",
    ],
    language="pt",
    timeout=5,
    fallback_to_local=True,
    use_job_manager=False,  # Desabilitar para teste mais rápido
    local_config={
        "model": "tiny",
        "use_cpp": True,
        "threads": 2,
        "beam_size": 1,
    },
)
print(f"   URLs (inválidas): {client.urls}")
print(f"   Fallback local: {client.fallback_to_local}")

# 3. Testar transcrição
print("\n3. Iniciando transcrição (deve falhar nas APIs e usar fallback)...")
print("   Isso pode levar alguns segundos enquanto tenta cada servidor...")
start = time.time()

try:
    result = client.transcribe(test_audio, language="pt")
    elapsed = time.time() - start
    
    print("\n" + "="*60)
    print("RESULTADO DO FALLBACK LOCAL:")
    print("="*60)
    print(f"  Servidor usado: {result.server_url}")
    print(f"  Texto: {result.text[:100] if result.text else '(vazio/silêncio)'}")
    print(f"  Tempo total: {elapsed:.1f}s")
    print(f"  Modelo: {result.model}")
    print("="*60)
    
    if "local" in str(result.server_url).lower():
        print("\n✅ FALLBACK LOCAL FUNCIONOU COM SUCESSO!")
    
except Exception as e:
    elapsed = time.time() - start
    print(f"\n❌ ERRO após {elapsed:.1f}s: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
try:
    os.unlink(test_audio)
except:
    pass

print("\nTeste concluído!")
