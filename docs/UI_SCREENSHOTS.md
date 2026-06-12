# UI Screenshots

## Setup Page
![Setup Page](docs/images/setup.png)

The setup page shows:
- **Fetch Mode** dropdown (Category / Raw ES Query)
- **Model** dropdown (dynamically loaded from Ollama, defaults to llama3:8b)
- **Category** dropdown (10 intelligence categories)
- **Quick Presets** chips (Infra, Deployment, All Data)
- **Date Range** pickers
- **Session ID** and **Max Turns** inputs
- **Load Data & Start Chat** button

## Chat Page
![Chat Page](docs/images/chat.png)

The chat page shows:
- **Header** with model name, ES cluster status, connection badge
- **Info bar** showing: `7668 docs · llama3:8b-instruct-q8_0 · 0/10 turns`
- **Chat area** with user/bot message bubbles
- **Input row** with textarea and send button
- **Source citations** on each bot answer (e.g., "📄 200 sources")

## Example Interactions

### Listing All Locations
```
User: show me all locations
Bot: **Unique locations (197 total)** (out of 28407 documents):
  • burang (715 docs)
  • karachi (532 docs)
  • lhasa (403 docs)
  ...
  📄 200 sources
```

### Equipment Query
```
User: need a detailed report on equipment J-20
Bot: Based on the retrieved documents, here is a detailed report on J-20:
  - Training at Quepem (Nov 2025)
  - Deployments at Urumqi (multiple dates 2024-2026)
  - Infrastructure at Nantong (Jan 2026)
  ...
  📄 51 sources
```

## Adding Screenshots

To add actual screenshots to this doc:

1. Install a screenshot tool:
   ```bash
   sudo apt install scrot
   ```

2. Capture screenshots:
   ```bash
   scrot docs/images/setup.png
   scrot docs/images/chat.png
   ```

3. Or use browser DevTools (F12) → Capture screenshot
