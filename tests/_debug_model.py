"""Debug: test direct LLM call with exact model name."""
import urllib.request, json, time
from openai import OpenAI

client = OpenAI(base_url='http://192.168.1.125:11434/v1', api_key='ollama', timeout=30)

# Test different model names
for model in ['llama3:8b-instruct-q8_0', 'llama3:latest']:
    try:
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[{'role':'user','content':'What is 2+2?'}],
            max_tokens=50,
        )
        print('{}: {} ({:.1f}s)'.format(model, resp.choices[0].message.content.strip(), time.time()-t0))
    except Exception as e:
        print('{}: ERROR {}'.format(model, e))
