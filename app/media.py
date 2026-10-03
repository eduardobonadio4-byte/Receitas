"""Operações com FFmpeg/FFprobe: metadados, extração de áudio e detecção de trechos parados."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


@dataclass
class VideoInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: int
    has_audio: bool = True

    @property
    def is_vertical(self) -> bool:
        return self.height >= self.width


@dataclass
class DeadZones:
    """Intervalos (início, fim) em segundos onde o vídeo está congelado ou em silêncio."""
    freezes: list[tuple[float, float]] = field(default_factory=list)
    silences: list[tuple[float, float]] = field(default_factory=list)


def ensure_ffmpeg() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise FFmpegError(f"'{binary}' não encontrado no PATH. Instale o FFmpeg (veja o README).")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise FFmpegError(f"Falha ao executar {cmd[0]}: {result.stderr.strip()[-500:]}")
    return result


def probe(path: Path) -> VideoInfo:
    out = _run([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]).stdout
    data = json.loads(out)
    video = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    if video is None:
        raise FFmpegError(f"{path.name} não possui faixa de vídeo")

    width, height = int(video["width"]), int(video["height"])

    # Vídeos de celular gravados em pé costumam vir com flag de rotação de 90/270°.
    rotation = 0
    for side in video.get("side_data_list", []):
        if "rotation" in side:
            rotation = int(side["rotation"])
    rotation = int(video.get("tags", {}).get("rotate", rotation))
    if abs(rotation) % 180 == 90:
        width, height = height, width

    num, _, den = video.get("avg_frame_rate", "30/1").partition("/")
    try:
        fps = round(float(num) / float(den or 1))
    except (ValueError, ZeroDivisionError):
        fps = 30

    duration = float(data["format"].get("duration") or video.get("duration") or 0)
    has_audio = any(s.get("codec_type") == "audio" for s in data["streams"])
    return VideoInfo(path=path, duration=duration, width=width, height=height, fps=fps or 30,
                     has_audio=has_audio)


def extract_audio(video: Path, out_wav: Path) -> Path:
    """Extrai áudio mono 16 kHz (formato ideal para Whisper)."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(video),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_wav),
    ])
    return out_wav


def _parse_intervals(stderr: str, kind: str, total: float) -> list[tuple[float, float]]:
    starts = [float(x) for x in re.findall(rf"{kind}_start: ?([\d.]+)", stderr)]
    ends = [float(x) for x in re.findall(rf"{kind}_end: ?([\d.]+)", stderr)]
    intervals = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else total  # trecho que vai até o fim do arquivo
        intervals.append((round(start, 2), round(end, 2)))
    return intervals


def detect_dead_zones(video: Path, duration: float, has_audio: bool = True) -> DeadZones:
    """Detecta imagem congelada (freezedetect) e silêncio (silencedetect) numa única passada."""
    cmd = ["ffmpeg", "-v", "info", "-nostats", "-i", str(video),
           "-vf", "freezedetect=n=0.003:d=1.5", "-map", "0:v:0"]
    if has_audio:
        cmd += ["-af", "silencedetect=n=-35dB:d=1.5", "-map", "0:a:0?"]
    cmd += ["-f", "null", "-"]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    stderr = result.stderr
    return DeadZones(
        freezes=_parse_intervals(stderr, "lavfi.freezedetect.freeze", duration),
        silences=_parse_intervals(stderr, "silence", duration),
    )
