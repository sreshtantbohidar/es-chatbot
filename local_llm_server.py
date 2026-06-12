"""
Local LLM Server using llama.cpp
OpenAI-compatible API server for Qwen2.5-7B-Instruct-Q4_K_M
"""
import os
import sys
import time
import subprocess
import signal

MODEL_PATH = "/home/sresht/models/qwen2.5-7b-instruct-q4km/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
SERVER_PORT = 11435  # Different from remote Ollama on 11434
CTX_SIZE = 8192

def start_server():
    """Start llama.cpp server with CUDA support."""
    cmd = [
        "python3", "-m", "llama_cpp.server",
        "--model", MODEL_PATH,
        "--n_gpu_layers", "35",  # Offload all layers to GPU (7B fits in 6GB)
        "--ctx_size", str(CTX_SIZE),
        "--host", "0.0.0.0",
        "--port", str(SERVER_PORT),
        "--chat_format", "chatml",
    ]
    
    print(f"Starting llama.cpp server on port {SERVER_PORT}...")
    print(f"Model: {MODEL_PATH}")
    print(f"GPU layers: 35, Context: {CTX_SIZE}")
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    
    # Wait for server to be ready
    import httpx
    for i in range(60):
        time.sleep(2)
        try:
            r = httpx.get(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=2)
            if r.status_code == 200:
                print(f"Server ready on port {SERVER_PORT}!")
                return proc
        except:
            pass
        print(f"  Waiting... ({(i+1)*2}s)")
    
    print("Server failed to start!")
    proc.kill()
    return None

if __name__ == "__main__":
    proc = start_server()
    if proc:
        print(f"\nServer PID: {proc.pid}")
        print(f"API: http://127.0.0.1:{SERVER_PORT}/v1")
        print("Press Ctrl+C to stop")
        try:
            proc.wait()
        except KeyboardInterrupt:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            print("\nServer stopped")
