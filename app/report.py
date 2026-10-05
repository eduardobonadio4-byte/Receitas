"""Relatório em Markdown salvo ao lado do vídeo original."""
from __future__ import annotations

from pathlib import Path

from app.analyzer import RecipeAnalysis
from app.capcut_draft import DraftVariant
from app.pin_images import PinImages
from app.media import VideoInfo


def _formats_section(drafts: list[DraftVariant], pins: PinImages | None,
                     capa_link: str | None, colagem_link: str | None) -> str:
    """Tabela dos formatos de pin com link e dia sugerido (vídeo dia 1, capa dia 3, colagem dia 5)."""
    rows = []
    video_days = {"": "Dia 1", "A": "Dia 1", "B": "Dia 7", "C": "Dia 9"}
    main_video = drafts[0] if drafts else None
    if main_video:
        name = f"Vídeo {main_video.label}".strip()
        rows.append((name, f"projeto CapCut `{main_video.path.name if main_video.path else '—'}`",
                     main_video.link, video_days[main_video.label]))
    if pins and pins.capa:
        rows.append(("Capa estática", f"`pins/{pins.capa.name}`", capa_link, "Dia 3"))
    if pins and pins.colagem:
        rows.append(("Colagem passo a passo", f"`pins/{pins.colagem.name}`", colagem_link, "Dia 5"))
    for d in drafts[1:]:  # variações B e C do teste A/B, espaçadas depois dos 3 formatos
        rows.append((f"Vídeo {d.label}", f"projeto CapCut `{d.path.name if d.path else '—'}`",
                     d.link, video_days[d.label]))

    table = "\n".join(f"| {fmt} | {arq} | {link} | {dia} |" for fmt, arq, link, dia in rows)
    notes = ""
    if pins and pins.notes:
        notes = "\n" + "\n".join(f"> ⚠ {n}" for n in pins.notes) + "\n"
    return f"""## Formatos
Um vídeo vira até 3 formatos de pin. Publique na ordem abaixo (cada um com o próprio link).

| Formato | Arquivo | Link | Publicar |
|---|---|---|---|
{table}
{notes}"""


def write_report(info: VideoInfo, analysis: RecipeAnalysis, drafts: list[DraftVariant], *,
                 estilo_label: str, notion_status: str, pins: PinImages | None = None,
                 capa_link: str | None = None, colagem_link: str | None = None) -> Path:
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

    formats = _formats_section(drafts, pins, capa_link, colagem_link)

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
{formats}
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
