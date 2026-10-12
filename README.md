# Mind OS

A small decision-review product that sends one idea to four AI reviewers in parallel: business, technology, psychology and execution. Results stream back as each reviewer finishes.

## What is implemented

- Four role-specific reviewers executed concurrently with `ThreadPoolExecutor`.
- DeepSeek-compatible chat-completions calls.
- Server-Sent Events for incremental results.
- Per-IP daily quota tracking.
- Flask UI plus supporting content-generation workflows.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Set `DEEPSEEK_API_KEY`, then run:

```bash
python app.py
```

Optional environment variables: `MODEL_NAME`, `AGENT_MODEL`, `FLASK_HOST`, `FLASK_PORT`, `FLASK_DEBUG` and `DATA_FILE`.

## Main files

- `app.py` — Flask routes, quota handling, concurrent reviewers and SSE stream.
- `prompt_design.md` — intent classification and action/critique output design.
- `templates/` and `static/` — product interface.

## Status

Prototype snapshot. The repository demonstrates the interaction and orchestration design; production deployment still requires durable storage, authentication and provider-level monitoring.
