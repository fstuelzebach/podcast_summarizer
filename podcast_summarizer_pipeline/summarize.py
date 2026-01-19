import logging
import subprocess
from typing import List

logger = logging.getLogger("podcast_pipeline.summarize")

DEFAULT_MODEL = "llama3.2:3b"
MAX_CHARS = 8000


def _ollama_run(prompt: str, model: str) -> str:
    logger.debug("Calling Ollama model=%s prompt_chars=%d", model, len(prompt))

    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        logger.error("Ollama failed: %s", result.stderr)
        raise RuntimeError("Ollama summarization failed")

    return result.stdout.strip()


def _build_chunk_prompt(chunk: str, idx: int, total: int) -> str:
    return f"""
You are a **senior macro strategist** preparing a professional research note.

Your task:
Produce a **comprehensive but readable summary** of the following transcript segment.
Be detailed — write in full sentences, not just bullet fragments.

Focus only on **economic, policy, and market content**.
Ignore small talk, introductions, or off-topic discussion.

Structure the output into exactly these four sections:

1. **Executive Summary** – 8–12 bullet points
2. **Economic Mechanisms** – 3–5 short explanatory paragraphs
3. **Market Implications / Trade Ideas** – 3–5 actionable ideas
4. **Narrative** – a cohesive macro storyline

Transcript chunk {idx}/{total}:
\"\"\"{chunk}\"\"\"
"""


def _build_merge_prompt(partials: List[str]) -> str:
    merged = "\n\n".join(partials)
    return f"""
Merge the following partial macro summaries into ONE coherent research note.

Rules:
- Eliminate duplication
- Preserve nuance
- Keep ALL important insights
- Retain the 4-section structure exactly

Partial summaries:
\"\"\"{merged}\"\"\"
"""


def summarize_with_llama(
    text: str,
    model: str = DEFAULT_MODEL,
    max_chunk_chars: int = MAX_CHARS,
) -> str:
    logger.info("Starting summarization (model=%s)", model)

    chunks = [
        text[i : i + max_chunk_chars]
        for i in range(0, len(text), max_chunk_chars)
    ]

    logger.info("Transcript split into %d chunk(s)", len(chunks))

    partials = []

    for i, chunk in enumerate(chunks, start=1):
        logger.info("Summarizing chunk %d/%d", i, len(chunks))
        prompt = _build_chunk_prompt(chunk, i, len(chunks))
        partials.append(_ollama_run(prompt, model))

    if len(partials) == 1:
        return partials[0]

    logger.info("Merging %d partial summaries", len(partials))
    merge_prompt = _build_merge_prompt(partials)
    return _ollama_run(merge_prompt, model)
