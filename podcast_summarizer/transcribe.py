import logging
from pathlib import Path

logger = logging.getLogger("podcast_summarizer.transcribe")


class Transcriber:
    """Speech-to-text with faster-whisper (fast on CPU) or openai-whisper.

    engine: "auto" tries faster-whisper first, then openai-whisper. faster-whisper
    has no wheels on some platforms (e.g. Intel Macs), so both stay supported.
    The model is loaded lazily, so runs where every episode is cached or comes
    with a feed transcript never load it.
    """

    def __init__(self, model_name: str = "small", engine: str = "auto"):
        self.model_name = model_name
        self.engine = engine
        self._model = None
        self._kind = None

    @property
    def label(self) -> str:
        return f"{self._kind or self.engine}:{self.model_name}"

    def _load(self) -> None:
        if self._model is not None:
            return
        if self.engine in ("auto", "faster"):
            try:
                from faster_whisper import WhisperModel
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                self._kind = "faster"
                logger.info("Loaded faster-whisper model=%s", self.model_name)
                return
            except ImportError:
                if self.engine == "faster":
                    raise
        import whisper
        self._model = whisper.load_model(self.model_name)
        self._kind = "openai"
        logger.info("Loaded openai-whisper model=%s", self.model_name)

    def transcribe(self, mp3_path: Path) -> Path:
        txt_path = mp3_path.with_suffix(".txt")
        if txt_path.exists():
            return txt_path

        self._load()
        if self._kind == "faster":
            segments, _info = self._model.transcribe(str(mp3_path), vad_filter=True)
            text = " ".join(s.text.strip() for s in segments)
        else:
            text = self._model.transcribe(str(mp3_path))["text"]

        tmp = txt_path.with_suffix(".txt.part")
        tmp.write_text(text.strip(), encoding="utf-8")
        tmp.replace(txt_path)
        return txt_path
