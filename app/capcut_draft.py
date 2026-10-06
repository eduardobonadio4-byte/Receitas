"""Geração de projetos nativos do CapCut Desktop (pasta do draft + draft_content.json) via pycapcut."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pycapcut as cc
from pycapcut import SEC, ClipSettings, TextBackground, TextBorder, TextSegment, TextStyle, Timerange, TrackType

from config import (
    BRAND_FONT, BRAND_GREEN, BRAND_ORANGE, CANVAS_H, CANVAS_W, CTA_Y, HOOK_FONT_SIZE, HOOK_MAX_WIDTH, HOOK_Y,
)
from app.media import VideoInfo


@dataclass
class DraftVariant:
    label: str  # "A", "B", "C" (ou "" quando é draft único)
    hook: str
    link: str
    path: Path | None = None


def safe_draft_name(stem: str, suffix: str = "") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    return f"{name or 'receita'}_auto{suffix}"


def _font():
    return getattr(cc.FontType, BRAND_FONT, None)


def _style(size: float, max_width: float = 0.8) -> TextStyle:
    return TextStyle(size=size, bold=True, color=(1.0, 1.0, 1.0), align=1, auto_wrapping=True,
                     max_line_width=max_width)


def two_lines(text: str) -> str:
    """Quebra o texto em no máximo 2 linhas com tamanhos parecidos (fica mais largo e legível)."""
    words = text.split()
    if len(words) < 3:
        return " ".join(words)
    best = min(range(1, len(words)),
               key=lambda i: max(len(" ".join(words[:i])), len(" ".join(words[i:]))))
    return " ".join(words[:best]) + "\n" + " ".join(words[best:])


def _band(color: str) -> TextBackground:
    return TextBackground(color=color, style=1, alpha=1.0, round_radius=0.3)


def build_drafts(
    drafts_dir: Path,
    info: VideoInfo,
    variants: list[DraftVariant],
    *,
    recipe_name: str,
    cut_end_s: float,
    cta: str,
    estilo: str,
    hook_duration_s: float = 3.0,
    cta_duration_s: float = 3.0,
    overwrite: bool = False,
) -> list[DraftVariant]:
    """Gera um projeto por variação: <video>_auto (único) ou <video>_auto_A/_B/_C."""
    for v in variants:
        name = safe_draft_name(info.path.stem, f"_{v.label}" if v.label else "")
        v.path = _build_one(drafts_dir, name, info, v.hook, recipe_name=recipe_name, cut_end_s=cut_end_s,
                            cta=cta, estilo=estilo, hook_duration_s=hook_duration_s,
                            cta_duration_s=cta_duration_s, overwrite=overwrite)
    return variants


def _build_one(
    drafts_dir: Path,
    draft_name: str,
    info: VideoInfo,
    hook_text: str,
    *,
    recipe_name: str,
    cut_end_s: float,
    cta: str,
    estilo: str,
    hook_duration_s: float,
    cta_duration_s: float,
    overwrite: bool,
) -> Path:
    drafts_dir.mkdir(parents=True, exist_ok=True)
    folder = cc.DraftFolder(str(drafts_dir))

    # Sempre 9:16 (Pinterest). Vídeo fora dessa proporção é enquadrado pelo CapCut.
    script = folder.create_draft(draft_name, CANVAS_W, CANVAS_H, fps=info.fps, allow_replace=overwrite)
    script.add_track(TrackType.video, "principal")
    script.add_track(TrackType.text, "gancho")
    script.add_track(TrackType.text, "cta")

    # --- Vídeo principal, cortado no ponto definido pela análise ---
    material = cc.VideoMaterial(str(info.path.resolve()))
    clip_us = min(int(cut_end_s * SEC), material.duration)
    script.add_segment(
        cc.VideoSegment(material, Timerange(0, clip_us), source_timerange=Timerange(0, clip_us)),
        "principal",
    )

    if estilo == "cru":
        # Cru (natural): só o nome da receita, discreto, durante todo o vídeo. Sem faixa nem preço.
        script.add_segment(
            TextSegment(recipe_name, Timerange(0, clip_us), font=_font(), style=_style(6.0),
                        border=TextBorder(color=(0.0, 0.0, 0.0), width=25.0),
                        clip_settings=ClipSettings(transform_y=HOOK_Y)),
            "gancho",
        )
    else:
        # Padrão (com preço): gancho na faixa verde (0-3s) + CTA na faixa laranja (últimos 3s).
        hook_us = min(int(hook_duration_s * SEC), clip_us)
        script.add_segment(
            TextSegment(two_lines(hook_text), Timerange(0, hook_us), font=_font(),
                        style=_style(HOOK_FONT_SIZE, HOOK_MAX_WIDTH),
                        background=_band(BRAND_GREEN), clip_settings=ClipSettings(transform_y=HOOK_Y)),
            "gancho",
        )
        cta_us = min(int(cta_duration_s * SEC), clip_us)
        script.add_segment(
            TextSegment(cta, Timerange(clip_us - cta_us, cta_us), font=_font(), style=_style(8.0),
                        background=_band(BRAND_ORANGE), clip_settings=ClipSettings(transform_y=CTA_Y)),
            "cta",
        )

    script.save()
    return drafts_dir / draft_name
