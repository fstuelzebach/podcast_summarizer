from pathlib import Path
import whisper

class Transcriber:
    def __init__(self, model_name: str = "base"):
        self.model = whisper.load_model(model_name)

    def transcribe(self, mp3_path: Path) -> Path:
        txt_path = mp3_path.with_suffix(".txt")

        if txt_path.exists():
            return txt_path

        result = self.model.transcribe(str(mp3_path))
        txt_path.write_text(result["text"], encoding="utf-8")
        return txt_path
