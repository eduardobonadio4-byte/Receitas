"""Relatório em Markdown salvo ao lado do vídeo original."""
from __future__ import annotations

from pathlib import Path

from app.analyzer import RecipeAnalysis
from app.media import VideoInfo


def write_report(info: VideoInfo, analysis: RecipeAnalysis, draft_path: Path | None) -> Path:
    # Um relatório por vídeo (vários vídeos na mesma pasta não se sobrescrevem).
    out = info.path.with_name(f"{info.path.stem}_video_analise.md")

    hooks = "\n".join(
        f"{i + 1}. {h}{'  ⭐ (usado no CapCut)' if i == analysis.best_hook_index else ''}"
        for i, h in enumerate(analysis.hooks)
    )
    ingredients = "\n".join(f"- {item}" for item in analysis.ingredients) or "- (não identificado)"
    hashtags = " ".join(analysis.hashtags)

    md = f"""# {analysis.recipe_title}

**Arquivo:** `{info.path.name}`
**Duração original:** {info.duration:.2f}s → **corte final:** {analysis.cut_end_seconds:.2f}s
**Motivo do corte:** {analysis.cut_reason}
**Projeto CapCut:** {f'`{draft_path}`' if draft_path else 'não gerado'}

## Ganchos (0–3s)
{hooks}

## CTA final
{analysis.cta}

## Legenda pronta
{analysis.caption}

**Ingredientes:**
{ingredients}

{hashtags}

## Locução em off ({len(analysis.voiceover.split())} palavras)
> {analysis.voiceover}
"""
    out.write_text(md, encoding="utf-8")
    return out
