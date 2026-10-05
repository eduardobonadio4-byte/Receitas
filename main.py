"""CLI: processa uma pasta de vídeos de receita e gera projetos prontos no CapCut Desktop.

Uso:
    python main.py <pasta_dos_videos> [--ab-hooks] [--estilo padrao|cru] [--overwrite] [--mock-claude]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from config import (
    ESTILOS, REFERENCE_DIR_NAMES, SALES_PAGE_URL, VIDEO_EXTENSIONS, detect_capcut_drafts_dir, settings,
)
from app import media
from app.analyzer import AnalysisContext, AnalysisError, RecipeAnalysis, RecipeAnalyzer, mock_analysis
from app.capcut_draft import DraftVariant, build_drafts
from app.notion_sync import NotionClient, NotionError, NotionRow
from app.pinterest import pin_link, slugify
from app.report import write_report
from app.transcriber import Transcriber

console = Console()

CACHE_DIRNAME = ".recipe_cache"


@dataclass
class Result:
    video: str
    ok: bool
    detail: str
    cut: str = "-"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Automação de vídeos de receita → projetos CapCut + Notion")
    p.add_argument("input_dir", type=Path, help="Pasta com os vídeos gravados por nós (.mp4, .mov, .mkv)")
    p.add_argument("--drafts-dir", type=Path, help="Pasta de projetos do CapCut (padrão: detecção automática)")
    p.add_argument("--overwrite", action="store_true", help="Sobrescreve drafts já existentes com o mesmo nome")
    p.add_argument("--mock-claude", action="store_true", help="Não chama a API (análise fictícia, para testes)")
    p.add_argument("--ab-hooks", action="store_true",
                   help="Cria 1 draft por gancho (_A, _B, _C) para teste A/B (só no estilo padrão)")
    p.add_argument("--estilo", choices=sorted(ESTILOS), default="padrao",
                   help="Visual do vídeo quando o Notion ainda não define o Estilo (padrão: padrao)")
    p.add_argument("--no-notion", action="store_true", help="Não lê nem escreve no Banco de Receitas")
    p.add_argument("--skip-capcut", action="store_true", help="Gera só a análise/relatório, sem criar o draft")
    p.add_argument("--whisper-model", default=settings.whisper_model, help="tiny|base|small|medium|large-v3")
    return p.parse_args()


def is_reference_path(path: Path) -> bool:
    return any(part.lower() in REFERENCE_DIR_NAMES for part in path.resolve().parts)


def find_videos(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)


def merge_with_notion(analysis: RecipeAnalysis, row: NotionRow | None) -> None:
    """O que a equipe já escreveu no Notion prevalece sobre o que a IA gerou (vídeo e Notion batem)."""
    if row is None:
        return
    keep = {
        "Gancho A (curiosidade)": "hook_curiosidade",
        "Gancho B (benefício)": "hook_beneficio",
        "Gancho C (erro comum)": "hook_erro_comum",
        "Título do pin": "pin_title",
        "Roteiro de locução": "voiceover",
        "CTA": "cta",
        "Categoria": "categoria",
        "Pasta": "pasta",
    }
    for notion_field, attr in keep.items():
        value = row.get(notion_field)
        if value:
            setattr(analysis, attr, value)
    if row.get("Descrição"):
        analysis.pin_description, analysis.hashtags = row.get("Descrição"), []
    if row.get("No e-book"):
        analysis.in_ebook = True


def process_video(
    video: Path,
    transcriber: Transcriber,
    analyzer: RecipeAnalyzer | None,
    notion: NotionClient | None,
    ctx: AnalysisContext,
    drafts_dir: Path,
    args: argparse.Namespace,
    step,
    step_print=print,
) -> Result:
    cache = video.parent / CACHE_DIRNAME

    step("lendo metadados")
    info = media.probe(video)

    segments, wav = [], None
    if info.has_audio:
        step("extraindo áudio (ffmpeg)")
        wav = media.extract_audio(video, cache / f"{video.stem}.wav")

        step(f"transcrevendo (whisper {transcriber.model_size})")
        segments = transcriber.transcribe(wav, cache / f"{video.stem}.transcript.json")

    step("detectando imagem parada/silêncio")
    dead = media.detect_dead_zones(video, info.duration, has_audio=info.has_audio)

    step("analisando com Claude" if analyzer else "análise mock")
    analysis = analyzer.analyze(info, segments, dead, ctx) if analyzer else mock_analysis(info, segments, ctx)

    row = notion.find(analysis.recipe_name) if notion else None
    merge_with_notion(analysis, row)

    # Estilo: o do Notion manda; senão, o da linha de comando.
    estilo = next((k for k, label in ESTILOS.items() if row and row.get("Estilo") == label), args.estilo)
    ab = args.ab_hooks and estilo == "padrao"

    slug = slugify(analysis.recipe_name)
    on_air_hook = (row.get("Gancho") if row else None) or analysis.hook_curiosidade
    if ab:
        variants = [DraftVariant(label, hook, pin_link(SALES_PAGE_URL, slug, label))
                    for label, hook in zip("ABC", analysis.hooks)]
    else:
        variants = [DraftVariant("", on_air_hook, pin_link(SALES_PAGE_URL, slug))]

    if not args.skip_capcut:
        step("gerando projetos CapCut (A/B)" if ab else "gerando projeto CapCut")
        build_drafts(
            drafts_dir, info, variants,
            recipe_name=analysis.recipe_name,
            cut_end_s=analysis.cut_end_seconds,
            cta=analysis.cta,
            estilo=estilo,
            hook_duration_s=settings.hook_duration_s,
            cta_duration_s=settings.cta_duration_s,
            overwrite=args.overwrite,
        )

    notion_status = "desativado"
    if notion:
        dry_run = args.mock_claude  # no modo mock, só mostra o que seria escrito
        step("simulando escrita no Notion" if dry_run else "atualizando Notion")
        links = {v.label: v.link for v in variants}
        action, written = notion.upsert(analysis.recipe_name, {
            "Gancho A (curiosidade)": analysis.hook_curiosidade,
            "Gancho B (benefício)": analysis.hook_beneficio,
            "Gancho C (erro comum)": analysis.hook_erro_comum,
            "Gancho": analysis.hook_curiosidade,
            "Título do pin": analysis.pin_title,
            "Descrição": analysis.full_description,
            "CTA": analysis.cta,
            "Link do pin": variants[0].link,  # no A/B, o link da variação A (= Gancho)
            "Link B": links.get("B"),
            "Link C": links.get("C"),
            "Roteiro de locução": analysis.voiceover,
            "Estilo": ESTILOS[estilo],
            "No e-book": analysis.in_ebook,
            "Categoria": analysis.categoria,
            "Pasta": analysis.pasta,
            "Origem do vídeo": "Gravado por nós",
            "Status": "Editado",
        }, dry_run=dry_run)
        notion_status = f"linha \"{analysis.recipe_name}\" {action}"
        if dry_run:
            notion_status += " (mock: nada foi gravado)"
            step_print(f"[magenta]Notion (simulação, nada gravado) — linha \"{analysis.recipe_name}\" "
                       f"{action}:[/]")
            for name, value in written.items():
                step_print(f"   [cyan]{name}[/]: {escape(str(value))}")

    step("salvando relatório")
    report = write_report(info, analysis, variants, estilo_label=ESTILOS[estilo], notion_status=notion_status)
    if wav:
        wav.unlink(missing_ok=True)

    drafts = ", ".join(v.path.name for v in variants if v.path) or "(sem draft)"
    return Result(
        video=video.name,
        ok=True,
        detail=f"{drafts} · relatório: {report} · Notion: {notion_status}",
        cut=f"{info.duration:.1f}s → {analysis.cut_end_seconds:.1f}s",
    )


def main() -> int:
    args = parse_args()

    if not args.input_dir.is_dir():
        console.print(f"[red]Pasta não encontrada:[/] {args.input_dir}")
        return 1

    if is_reference_path(args.input_dir):
        console.print("[red]Essa pasta é de referências (TikTok). Só processamos vídeos gravados por nós.[/]")
        return 1

    try:
        media.ensure_ffmpeg()
    except media.FFmpegError as e:
        console.print(f"[red]{e}[/]")
        return 1

    if not args.mock_claude and not settings.anthropic_api_key:
        console.print("[red]Defina ANTHROPIC_API_KEY no arquivo .env[/] (ou rode com --mock-claude para testar)")
        return 1

    videos = find_videos(args.input_dir)
    if not videos:
        console.print(f"[yellow]Nenhum vídeo {sorted(VIDEO_EXTENSIONS)} em {args.input_dir}[/]")
        return 1

    if args.drafts_dir:
        drafts_dir, found = args.drafts_dir, True
    else:
        drafts_dir, found = detect_capcut_drafts_dir()

    console.print(Panel.fit(
        f"[bold]Vídeos:[/] {len(videos)}\n"
        f"[bold]Drafts CapCut:[/] {drafts_dir}"
        + ("  [magenta](A/B: 3 por vídeo)[/]" if args.ab_hooks and not args.skip_capcut else "")
        + ("" if found else "\n[yellow]CapCut não encontrado — drafts salvos na pasta local acima. "
                            "Copie-os para a pasta de projetos do CapCut ou use --drafts-dir.[/]")
        + f"\n[bold]Claude:[/] {'MOCK' if args.mock_claude else settings.claude_model}"
        + f"   [bold]Whisper:[/] {args.whisper_model} ({settings.whisper_language})",
        title="🍳 Receitas → CapCut",
    ))

    notion, ctx = None, AnalysisContext()
    if not args.no_notion:
        if not settings.notion_token:
            console.print("[yellow]NOTION_TOKEN não definido — seguindo sem Notion (use --no-notion para "
                          "esconder este aviso).[/]")
        else:
            try:
                notion = NotionClient(settings.notion_token, settings.notion_data_source_id)
                with console.status("Lendo o Banco de Receitas no Notion..."):
                    notion.load()
            except (NotionError, OSError) as e:
                console.print(f"[red]Notion: {e}[/]\nCorrija o .env ou rode com --no-notion.")
                return 1
            ctx = AnalysisContext(
                existing_recipes=notion.recipe_names,
                categorias=notion.options("Categoria") or ctx.categorias,
                pastas=notion.options("Pasta") or ctx.pastas,
            )
            console.print(f"Notion: {len(notion.rows)} receitas no banco.")

    transcriber = Transcriber(args.whisper_model, settings.whisper_language, settings.whisper_device)
    analyzer = None if args.mock_claude else RecipeAnalyzer(settings.anthropic_api_key, settings.claude_model)

    results: list[Result] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.fields[video]}"),
        TextColumn("{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("", total=len(videos), video="")
        for video in videos:
            progress.update(task, video=video.name, description="iniciando")

            def step(msg: str) -> None:
                progress.update(task, description=msg)

            try:
                results.append(process_video(video, transcriber, analyzer, notion, ctx, drafts_dir, args, step,
                                              progress.console.print))
                progress.console.print(f"[green]✔[/] {video.name}")
            except FileExistsError:
                results.append(Result(video.name, False, "draft já existe (use --overwrite)"))
                progress.console.print(f"[yellow]⚠[/] {video.name}: draft já existe (use --overwrite)")
            except (media.FFmpegError, AnalysisError, NotionError, ValueError, OSError) as e:
                results.append(Result(video.name, False, str(e)))
                progress.console.print(f"[red]✘[/] {video.name}: {e}")
            except Exception as e:  # erro inesperado (ex.: download do modelo Whisper) não derruba o lote
                results.append(Result(video.name, False, f"{type(e).__name__}: {e}"))
                progress.console.print(f"[red]✘[/] {video.name}: {type(e).__name__}: {e}")
            progress.advance(task)

    table = Table(title="Resumo")
    table.add_column("Vídeo")
    table.add_column("Status")
    table.add_column("Corte")
    table.add_column("Saída / erro", overflow="fold")
    for r in results:
        table.add_row(r.video, "[green]OK[/]" if r.ok else "[red]ERRO[/]", r.cut, r.detail)
    console.print(table)

    if any(r.ok for r in results) and not args.skip_capcut:
        console.print("[bold]Próximo passo:[/] feche e reabra o CapCut Desktop — os projetos '*_auto' "
                      "aparecem em Projetos, prontos para exportar.")
    return 0 if all(r.ok for r in results) else 2


if __name__ == "__main__":
    sys.exit(main())
