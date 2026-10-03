"""Configuração central: variáveis de ambiente e detecção da pasta de drafts do CapCut."""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}

# Pasta usada quando nenhuma instalação do CapCut é encontrada (ex.: Linux, testes).
FALLBACK_DRAFTS_DIR = Path(__file__).resolve().parent / "capcut_drafts_output"


def capcut_draft_candidates() -> list[Path]:
    """Caminhos conhecidos da pasta de projetos do CapCut Desktop, por sistema operacional."""
    system = platform.system()
    home = Path.home()

    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [
            local / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            local / "CapCut Drafts",
        ]
    if system == "Darwin":
        return [
            home / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            home / "Library" / "Containers" / "com.lemon.lvoverseas" / "Data" / "Movies"
            / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            home / "Library" / "Containers" / "com.lemon.capcut" / "Data" / "Documents"
            / "JianyingPro" / "drafts",
        ]
    return []  # CapCut Desktop não existe para Linux


def detect_capcut_drafts_dir() -> tuple[Path, bool]:
    """Retorna (pasta, encontrada). Prioridade: CAPCUT_DRAFTS_DIR > caminho padrão do SO > fallback local."""
    override = os.environ.get("CAPCUT_DRAFTS_DIR")
    if override:
        return Path(override).expanduser(), True

    for candidate in capcut_draft_candidates():
        if candidate.is_dir():
            return candidate, True

    return FALLBACK_DRAFTS_DIR, False


@dataclass
class Settings:
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))
    claude_model: str = field(default_factory=lambda: os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"))
    whisper_model: str = field(default_factory=lambda: os.environ.get("WHISPER_MODEL", "small"))
    whisper_language: str = field(default_factory=lambda: os.environ.get("WHISPER_LANGUAGE", "pt"))
    whisper_device: str = field(default_factory=lambda: os.environ.get("WHISPER_DEVICE", "auto"))

    # Layout dos textos no CapCut
    hook_duration_s: float = 3.0
    cta_duration_s: float = 3.0
    min_clip_duration_s: float = 3.0


settings = Settings()
