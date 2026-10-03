"""CLI: processa uma pasta de vídeos de receita e gera projetos prontos no CapCut Desktop.

Uso:
    python main.py <pasta_dos_videos> [--overwrite] [--mock-claude] [--drafts-dir PASTA]
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from config import VIDEO_EXTENSIONS, detect_capcut_drafts_dir, settings
from app import media
from app.analyzer import AnalysisError, RecipeAnalyzer, mock_analysis
from app.capcut_draft import build_drafts
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
    p = argparse.ArgumentParser(description="Automação de vídeos de receita → projetos CapCut")
    p.add_argument("input_dir", type=Path, help="Pasta com os vídeos (.mp4, .mov, .mkv)")
    p.add_argument("--drafts-dir", type=Path, help="Pasta de projetos do CapCut (padrão: detecção automática)")
    p.add_argument("--overwrite", action="store_true", help="Sobrescreve drafts já existentes com o mesmo nome")
    p.add_argument("--mock-claude", action="store_true", help="Não chama a API (análise fictícia, para testes)")
    p.add_argument("--ab-hooks", action="store_true",
                   help="Cria 1 draft por gancho (_A, _B, _C) para teste A/B de criativos")
    p.add_argument("--skip-capcut", action="store_true", help="Gera só a análise/relatório, sem criar o draft")
    p.add_argument("--whisper-model", default=settings.whisper_model, help="tiny|base|small|medium|large-v3")
    return p.parse_args()


def find_videos(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS)


def process_video(
    video: Path,
    transcriber: Transcriber,
    analyzer: RecipeAnalyzer | None,
    drafts_dir: Path,
    args: argparse.Namespace,
    step,
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
    analysis = analyzer.analyze(info, segments, dead) if analyzer else mock_analysis(info, segments)

    drafts = []
    if not args.skip_capcut:
        step("gerando projetos CapCut (A/B)" if args.ab_hooks else "gerando projeto CapCut")
        drafts = build_drafts(
            drafts_dir, info, analysis,
            ab_hooks=args.ab_hooks,
            hook_duration_s=settings.hook_duration_s,
            cta_duration_s=settings.cta_duration_s,
            overwrite=args.overwrite,
        )

    step("salvando relatório")
    report = write_report(info, analysis, drafts)
    if wav:
        wav.unlink(missing_ok=True)

    return Result(
        video=video.name,
        ok=True,
        detail=f"{', '.join(d.path.name for d in drafts) or '(sem draft)'} · {report.name}",
        cut=f"{info.duration:.1f}s → {analysis.cut_end_seconds:.1f}s",
    )


def main() -> int:
    args = parse_args()

    if not args.input_dir.is_dir():
        console.print(f"[red]Pasta não encontrada:[/] {args.input_dir}")
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
                results.append(process_video(video, transcriber, analyzer, drafts_dir, args, step))
                progress.console.print(f"[green]✔[/] {video.name}")
            except FileExistsError:
                results.append(Result(video.name, False, "draft já existe (use --overwrite)"))
                progress.console.print(f"[yellow]⚠[/] {video.name}: draft já existe (use --overwrite)")
            except (media.FFmpegError, AnalysisError, ValueError, OSError) as e:
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
