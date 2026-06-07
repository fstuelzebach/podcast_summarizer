import logging
import subprocess
from typing import List, Protocol

logger = logging.getLogger("podcast_summarizer.summarize")

MAX_CHARS = 8000


# ---------------------------------------------------------------------------
# Provider protocol — any backend must implement this
# ---------------------------------------------------------------------------

class LLMProvider(Protocol):
    def run(self, prompt: str) -> str: ...


# ---------------------------------------------------------------------------
# Ollama / Llama backend
# ---------------------------------------------------------------------------

class OllamaProvider:
    def __init__(self, model: str = "llama3.2:3b"):
        self.model = model

    def run(self, prompt: str) -> str:
        logger.debug("Ollama model=%s prompt_chars=%d", self.model, len(prompt))
        result = subprocess.run(
            ["ollama", "run", self.model],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            logger.error("Ollama stderr: %s", result.stderr)
            raise RuntimeError(f"Ollama failed: {result.stderr}")
        return result.stdout.strip()


# ---------------------------------------------------------------------------
# Anthropic / Claude backend
# ---------------------------------------------------------------------------

class ClaudeProvider:
    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        try:
            import anthropic
        except ImportError as e:
            raise ImportError("Run: pip install anthropic") from e

        from .config import ANTHROPIC_API_KEY
        self.model = model
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def run(self, prompt: str) -> str:
        logger.debug("Claude model=%s prompt_chars=%d", self.model, len(prompt))
        message = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------

def get_provider(backend: str, model: str | None = None) -> LLMProvider:
    """
    backend: "ollama" | "claude"
    model:   override default model for that backend (optional)
    """
    match backend.lower():
        case "ollama":
            return OllamaProvider(model=model or "llama3.2:3b")
        case "claude":
            return ClaudeProvider(model=model or "claude-haiku-4-5-20251001")
        case _:
            raise ValueError(f"Unknown backend '{backend}'. Choose: ollama | claude")


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_chunk_prompt(chunk: str, idx: int, total: int) -> str:
    return f"""
You are a senior macro strategist preparing a professional research note.

Produce a comprehensive but readable summary of the following transcript segment.
Write in full sentences, not bullet fragments.
Focus only on economic, policy, and market content.
Ignore small talk, introductions, or off-topic discussion.

Structure output into exactly these four sections:
1. Executive Summary – 8–12 bullet points
2. Economic Mechanisms – 3–5 explanatory paragraphs
3. Market Implications / Trade Ideas – 3–5 actionable ideas
4. Narrative – a cohesive macro storyline

Transcript chunk {idx}/{total}:
\"\"\"{chunk}\"\"\"
"""


def _build_merge_prompt(partials: List[str]) -> str:
    merged = "\n\n".join(partials)
    return f"""
Merge the following partial macro summaries into ONE coherent research note.
- Eliminate duplication
- Preserve nuance
- Keep ALL important insights
- Retain the 4-section structure exactly

Partial summaries:
\"\"\"{merged}\"\"\"
"""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def summarize(
    text: str,
    backend: str = "ollama",
    model: str | None = None,
    max_chunk_chars: int = MAX_CHARS,
) -> str:
    provider = get_provider(backend, model)
    logger.info("Summarizing with backend=%s model=%s", backend, getattr(provider, "model", "?"))

    chunks = [text[i: i + max_chunk_chars] for i in range(0, len(text), max_chunk_chars)]
    logger.info("Transcript split into %d chunk(s)", len(chunks))

    partials = []
    for i, chunk in enumerate(chunks, start=1):
        logger.info("Summarizing chunk %d/%d", i, len(chunks))
        partials.append(provider.run(_build_chunk_prompt(chunk, i, len(chunks))))

    if len(partials) == 1:
        return partials[0]

    logger.info("Merging %d partial summaries", len(partials))
    return provider.run(_build_merge_prompt(partials))