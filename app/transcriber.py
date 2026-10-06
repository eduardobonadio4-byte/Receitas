"""Transcrição local com faster-whisper (com cache em disco para não retranscrever)."""
from __future__ import annotations

import json
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class Segment:
    start: float
    end: float
    text: str


def load_wav(path: Path) -> np.ndarray:
    """Lê o WAV mono 16 kHz/16 bits que o FFmpeg já extraiu e devolve float32 em [-1, 1].

    Passar o áudio pronto evita o decodificador interno do faster-whisper (PyAV), que quebra em
    algumas versões ("open() got an unexpected keyword argument 'metadata_errors'").
    """
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise ValueError(f"WAV inesperado em {path.name}: precisa ser mono 16 bits")
        frames = wav.readframes(wav.getnframes())
    return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


class Transcriber:
    def __init__(self, model_size: str, language: str, device: str = "cpu"):
        self.model_size = model_size
        self.language = language
        self.device = device
        self._model = None  # carregado sob demanda (o primeiro uso baixa o modelo)

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            compute_type = "int8" if self.device in ("auto", "cpu") else "float16"
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=compute_type)
        return self._model

    def _run(self, audio: np.ndarray) -> list[Segment]:
        segments, _info = self._load().transcribe(
            audio,
            language=self.language or None,
            vad_filter=True,
            beam_size=5,
        )
        # A transcrição acontece enquanto os segmentos são lidos, então os erros de GPU aparecem aqui.
        return [Segment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments]

    def transcribe(self, audio_path: Path, cache_path: Path | None = None) -> list[Segment]:
        if cache_path and cache_path.exists():
            return [Segment(**s) for s in json.loads(cache_path.read_text(encoding="utf-8"))]

        audio = load_wav(audio_path)
        try:
            result = self._run(audio)
        except RuntimeError as e:
            # GPU NVIDIA detectada mas sem as bibliotecas CUDA (cublas/cudnn): cai para a CPU e segue.
            if self.device == "cpu" or not any(k in str(e).lower() for k in ("cublas", "cudnn", "cuda")):
                raise
            self.device, self._model = "cpu", None
            result = self._run(audio)

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps([asdict(s) for s in result], ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return result


def format_transcript(segments: list[Segment]) -> str:
    if not segments:
        return "(sem fala detectada)"
    return "\n".join(f"[{s.start:06.2f} - {s.end:06.2f}] {s.text}" for s in segments)
