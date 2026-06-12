"""Debug GK fast path."""
import urllib.request, json, time

# Check if llama3.2:1b exists on remote Ollama
try:
    req = urllib.request.Request('http://192.168.1.125:11434/api/tags')
    resp = urllib.request.urlopen(req, timeout=5)
    models = json.loads(resp.read().decode()).get('models', [])
    names = [m['name'] for m in models]
    print('Remote Ollama models: {}'.format(names))
    print('  llama3.2:1b exists: {}'.format('llama3.2' in str(names)))
except Exception as e:
    print('Remote Ollama error: {}'.format(e))

# Check local Ollama
try:
    req = urllib.request.Request('http://localhost:11434/api/tags')
    resp = urllib.request.urlopen(req, timeout=5)
    models = json.loads(resp.read().decode()).get('models', [])
    names = [m['name'] for m in models]
    print('Local Ollama models: {}'.format(names))
except Exception as e:
    print('Local Ollama error: {}'.format(e))
