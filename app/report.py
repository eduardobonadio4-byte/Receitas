"""Relatório em Markdown salvo ao lado do vídeo original."""
from __future__ import annotations

from pathlib import Path

from app.analyzer import RecipeAnalysis
from app.capcut_draft import DraftVariant
from app.media import VideoInfo


def write_report(info: VideoInfo, analysis: RecipeAnalysis, drafts: list[DraftVariant]) -> Path:
    # Um relatório por vídeo (vários vídeos na mesma pasta não se sobrescrevem).
    out = info.path.with_name(f"{info.path.stem}_video_analise.md")

    hooks = "\n".join(
        f"{i + 1}. {h}{'  ⭐ recomendado' if i == analysis.best_hook_index else ''}"
        for i, h in enumerate(analysis.hooks)
    )
    ingredients = "\n".join(f"- {item}" for item in analysis.ingredients) or "- (não identificado)"
    hashtags = " ".join(analysis.hashtags)

    if not drafts:
        projects = "não gerado"
    elif len(drafts) == 1:
        projects = f"`{drafts[0].path}`"
    else:
        projects = f"{len(drafts)} variações A/B em `{drafts[0].path.parent}`"

    ab_section = ""
    if len(drafts) > 1:
        rows = "\n".join(f"| {d.label} | {d.hook} | `{d.path.name}` | | | |" for d in drafts)
        ab_section = f"""
## Teste A/B de ganchos
Exporte as variações, suba como anúncios separados no mesmo conjunto (mesmo público/orçamento)
e preencha após 48–72h. Vencedor = maior retenção nos 3s com CTR igual ou melhor.

| Var. | Gancho | Projeto CapCut | Hook rate (3s) | CTR | CPM |
|---|---|---|---|---|---|
{rows}
"""

    md = f"""# {analysis.recipe_title}

**Arquivo:** `{info.path.name}`
**Duração original:** {info.duration:.2f}s → **corte final:** {analysis.cut_end_seconds:.2f}s
**Motivo do corte:** {analysis.cut_reason}
**Projeto CapCut:** {projects}

## Ganchos (0–3s)
{hooks}
{ab_section}
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
