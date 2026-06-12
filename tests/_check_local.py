"""Check local Ollama models."""
import urllib.request, json

# Check both Ollama servers
for url in ['http://192.168.1.125:11434', 'http://localhost:11434']:
    try:
        req = urllib.request.Request(f'{url}/api/tags')
        resp = urllib.request.urlopen(req, timeout=5)
        models = json.loads(resp.read().decode()).get('models', [])
        print(f"\n{'='*50}")
        print(f"Ollama at {url}: {len(models)} models")
        print('='*50)
        for m in models:
            size = m.get('size', 0) / 1e9
            print(f"  {m['name']:45s} {size:.1f} GB")
    except Exception as e:
        print(f"\n{url}: {e}")
