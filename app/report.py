"""Relatório em Markdown salvo ao lado do vídeo original."""
from __future__ import annotations

from pathlib import Path

from app.analyzer import RecipeAnalysis
from app.capcut_draft import DraftVariant
from app.media import VideoInfo


def write_report(info: VideoInfo, analysis: RecipeAnalysis, drafts: list[DraftVariant], *,
                 estilo_label: str, notion_status: str) -> Path:
    # Um relatório por vídeo (vários vídeos na mesma pasta não se sobrescrevem).
    out = info.path.with_name(f"{info.path.stem}_video_analise.md")

    labels = ["A · curiosidade", "B · benefício", "C · erro comum"]
    hooks = "\n".join(f"- **{label}:** {h}" for label, h in zip(labels, analysis.hooks))
    ingredients = "\n".join(f"- {item}" for item in analysis.ingredients) or "- (não identificado)"

    created = [d for d in drafts if d.path]
    if not created:
        projects = "não gerado"
    elif len(created) == 1:
        projects = f"`{created[0].path}`"
    else:
        projects = f"{len(created)} variações A/B em `{created[0].path.parent}`"

    links = "\n".join(f"- {d.label or 'Pin'}: {d.link}" for d in drafts)

    ab_section = ""
    if len(drafts) > 1:
        rows = "\n".join(f"| {d.label} | {d.hook} | | | | |" for d in drafts)
        ab_section = f"""
## Teste A/B de ganchos
Poste as 3 versões como pins orgânicos, com 2 a 3 dias entre elas, cada uma com o próprio link.
Não decida com menos de ~1.000 impressões por variação.

| Var. | Gancho | Impressões | Taxa de visualização | Cliques de saída | Salvamentos |
|---|---|---|---|---|---|
{rows}
"""

    md = f"""# {analysis.recipe_name}

**Arquivo:** `{info.path.name}`
**Duração original:** {info.duration:.2f}s → **corte final:** {analysis.cut_end_seconds:.2f}s
**Motivo do corte:** {analysis.cut_reason}
**Projeto CapCut:** {projects}
**Estilo:** {estilo_label} · **No e-book:** {'sim' if analysis.in_ebook else 'não'}
**Categoria:** {analysis.categoria or '—'} · **Pasta:** {analysis.pasta or '—'}
**Notion:** {notion_status}

## Ganchos (0–3s)
{hooks}
{ab_section}
## Links do pin
{links}

## CTA
{analysis.cta}

## Título do pin
{analysis.pin_title}

## Descrição do pin
{analysis.full_description}

**Ingredientes:**
{ingredients}

## Locução em off ({len(analysis.voiceover.split())} palavras)
> {analysis.voiceover}
"""
    out.write_text(md, encoding="utf-8")
    return out
