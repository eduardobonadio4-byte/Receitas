"""Geração de projetos nativos do CapCut Desktop (pasta do draft + draft_content.json) via pycapcut."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pycapcut as cc
from pycapcut import SEC, ClipSettings, TextBorder, TextSegment, TextStyle, Timerange, TrackType

from app.analyzer import RecipeAnalysis
from app.media import VideoInfo


def safe_draft_name(stem: str, suffix: str = "") -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", stem).strip(" .")
    return f"{name or 'receita'}_auto{suffix}"


@dataclass
class DraftVariant:
    label: str  # "A", "B", "C" (ou "" quando é draft único)
    hook: str
    path: Path


def _text_style(size: float) -> TextStyle:
    return TextStyle(size=size, bold=True, color=(1.0, 1.0, 1.0), align=1, auto_wrapping=True, max_line_width=0.8)


def build_drafts(
    drafts_dir: Path,
    info: VideoInfo,
    analysis: RecipeAnalysis,
    ab_hooks: bool = False,
    hook_duration_s: float = 3.0,
    cta_duration_s: float = 3.0,
    overwrite: bool = False,
) -> list[DraftVariant]:
    """Gera 1 draft (melhor gancho) ou, com ab_hooks, 1 draft por gancho: <nome>_auto_A, _B, _C.

    No modo A/B o gancho recomendado pelo Claude vem sempre como variação A.
    """
    if not ab_hooks:
        hooks = [("", analysis.hooks[analysis.best_hook_index])]
    else:
        best = analysis.best_hook_index
        ordered = [analysis.hooks[best]] + [h for i, h in enumerate(analysis.hooks) if i != best]
        hooks = [(chr(ord("A") + i), h) for i, h in enumerate(ordered)]

    variants = []
    for label, hook in hooks:
        name = safe_draft_name(info.path.stem, f"_{label}" if label else "")
        path = build_draft(drafts_dir, name, info, analysis, hook,
                           hook_duration_s=hook_duration_s, cta_duration_s=cta_duration_s, overwrite=overwrite)
        variants.append(DraftVariant(label, hook, path))
    return variants


def build_draft(
    drafts_dir: Path,
    draft_name: str,
    info: VideoInfo,
    analysis: RecipeAnalysis,
    hook_text: str,
    hook_duration_s: float = 3.0,
    cta_duration_s: float = 3.0,
    overwrite: bool = False,
) -> Path:
    """Cria a pasta do projeto com: vídeo cortado na trilha principal + gancho (início) + CTA (fim)."""
    drafts_dir.mkdir(parents=True, exist_ok=True)
    folder = cc.DraftFolder(str(drafts_dir))

    script = folder.create_draft(draft_name, info.width, info.height, fps=info.fps, allow_replace=overwrite)
    script.add_track(TrackType.video, "principal")
    script.add_track(TrackType.text, "gancho")
    script.add_track(TrackType.text, "cta")

    # --- Vídeo principal, cortado no ponto definido pelo Claude ---
    material = cc.VideoMaterial(str(info.path.resolve()))
    clip_us = min(int(analysis.cut_end_seconds * SEC), material.duration)
    script.add_segment(
        cc.VideoSegment(material, Timerange(0, clip_us), source_timerange=Timerange(0, clip_us)),
        "principal",
    )

    border = TextBorder(color=(0.0, 0.0, 0.0), width=40.0)

    # --- Gancho: 0s a 3s, terço superior ---
    hook_us = min(int(hook_duration_s * SEC), clip_us)
    script.add_segment(
        TextSegment(
            hook_text,
            Timerange(0, hook_us),
            style=_text_style(11.0),
            border=border,
            clip_settings=ClipSettings(transform_y=0.55),
        ),
        "gancho",
    )

    # --- CTA: últimos 3s do clipe, terço inferior (acima da UI do Reels/TikTok) ---
    cta_us = min(int(cta_duration_s * SEC), clip_us)
    script.add_segment(
        TextSegment(
            analysis.cta,
            Timerange(clip_us - cta_us, cta_us),
            style=_text_style(9.0),
            border=border,
            clip_settings=ClipSettings(transform_y=-0.45),
        ),
        "cta",
    )

    script.save()
    return drafts_dir / draft_name
