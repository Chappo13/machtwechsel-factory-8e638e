# Code Style

- Python 3.11+ with type hints on all function signatures
- Async functions for anything that calls external APIs
- Use pathlib.Path instead of os.path
- Logging via `logging.getLogger(__name__)` — no print()
- Config loading only through backend/config/__init__.py
- LLM calls only through backend/utils/llm.py
- Error handling: let pipeline orchestrator catch and log, don't silently swallow
- FFmpeg: always use subprocess.run with capture_output=True, check=True
- File paths: always Path objects, never raw strings in business logic
