"""Análise do conteúdo da receita via Claude API (saída estruturada validada por Pydantic)."""
from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

from app.media import DeadZones, VideoInfo
from app.transcriber import Segment, format_transcript


class RecipeAnalysis(BaseModel):
    recipe_title: str = Field(description="Nome curto da receita")
    cut_end_seconds: float = Field(description="Segundo exato onde o vídeo deve terminar")
    cut_reason: str = Field(description="Por que cortar nesse ponto (1 frase)")
    hooks: list[str] = Field(description="Exatamente 3 ganchos de texto para 0-3s, máx 8 palavras cada")
    best_hook_index: int = Field(description="Índice (0, 1 ou 2) do gancho mais forte")
    cta: str = Field(description="CTA de engajamento para o final, máx 10 palavras")
    caption: str = Field(description="Legenda pronta para Reels/TikTok, sem hashtags")
    ingredients: list[str] = Field(description="Lista de ingredientes com quantidades quando mencionadas")
    hashtags: list[str] = Field(description="8 a 12 hashtags, cada uma começando com #")
    voiceover: str = Field(description="Roteiro de locução em off, máximo 45 palavras")


SYSTEM_PROMPT = """Você é editor-chefe de um perfil de receitas curtas (Reels/TikTok/Shorts) focado em retenção e engajamento.
Você recebe a transcrição com timestamps de um vídeo de receita, a duração total e os trechos onde a imagem fica congelada ou há silêncio.

Regras:
- PONTO DE CORTE: termine logo após o último momento útil (prato pronto, última fala relevante ou mordida/reação). Remova sobras: imagem parada, silêncio final, "tchau", câmera sendo desligada. Nunca ultrapasse a duração total. Se não houver sobra, use a duração total.
- GANCHOS: 3 opções diferentes (curiosidade, benefício, erro comum/polêmica), máx 8 palavras, legíveis em 3 segundos, sem emoji no meio da frase.
- CTA: 1 frase curta que gere comentário ou salvamento (ex.: "Salva pra fazer no fim de semana").
- LEGENDA: tom natural em português do Brasil, 2-4 linhas, termina com pergunta para comentários.
- INGREDIENTES: só o que aparece na transcrição; se não houver, deduza o essencial da receita e mantenha curto.
- LOCUÇÃO: no máximo 45 palavras, ritmo de narração, pronta para IA de voz.
Escreva tudo em português do Brasil."""


class AnalysisError(RuntimeError):
    pass


def _fmt_intervals(intervals: list[tuple[float, float]]) -> str:
    return ", ".join(f"{a:.2f}-{b:.2f}s" for a, b in intervals) or "nenhum"


class RecipeAnalyzer:
    def __init__(self, api_key: str | None, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze(self, info: VideoInfo, segments: list[Segment], dead: DeadZones) -> RecipeAnalysis:
        user_prompt = (
            f"Arquivo: {info.path.name}\n"
            f"Duração total: {info.duration:.2f}s\n"
            f"Trechos com imagem congelada: {_fmt_intervals(dead.freezes)}\n"
            f"Trechos em silêncio: {_fmt_intervals(dead.silences)}\n\n"
            f"Transcrição:\n{format_transcript(segments)}"
        )

        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                output_format=RecipeAnalysis,
            )
        except anthropic.AuthenticationError as e:
            raise AnalysisError("ANTHROPIC_API_KEY inválida ou ausente") from e
        except anthropic.NotFoundError as e:
            raise AnalysisError(f"Modelo '{self.model}' não encontrado — ajuste CLAUDE_MODEL") from e
        except anthropic.RateLimitError as e:
            raise AnalysisError("Rate limit da API atingido — tente novamente em instantes") from e
        except anthropic.APIStatusError as e:
            raise AnalysisError(f"Erro da API ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise AnalysisError("Sem conexão com a API da Anthropic") from e

        if response.stop_reason == "refusal":
            raise AnalysisError("O modelo recusou a solicitação para este vídeo")
        if response.parsed_output is None:
            raise AnalysisError(f"Resposta sem JSON válido (stop_reason={response.stop_reason})")

        return sanitize(response.parsed_output, info.duration)


def sanitize(a: RecipeAnalysis, duration: float, min_clip: float = 3.0) -> RecipeAnalysis:
    """Garante limites seguros antes de montar o draft."""
    a.cut_end_seconds = round(max(min(min_clip, duration), min(a.cut_end_seconds, duration)), 2)
    a.hooks = [h.strip() for h in a.hooks if h.strip()][:3] or [a.recipe_title]
    if not 0 <= a.best_hook_index < len(a.hooks):
        a.best_hook_index = 0
    a.hashtags = [h if h.startswith("#") else f"#{h}" for h in (t.strip().replace(" ", "") for t in a.hashtags) if h]
    words = a.voiceover.split()
    if len(words) > 45:
        a.voiceover = " ".join(words[:45])
    return a


def mock_analysis(info: VideoInfo, segments: list[Segment]) -> RecipeAnalysis:
    """Análise fictícia para testar o fluxo do CapCut sem gastar API."""
    last_speech = segments[-1].end + 1.0 if segments else info.duration
    return sanitize(RecipeAnalysis(
        recipe_title=info.path.stem,
        cut_end_seconds=min(last_speech, info.duration),
        cut_reason="Mock: corte 1s após a última fala",
        hooks=["Você está fazendo isso errado", "Receita em 1 minuto", "Ninguém acredita que é fácil"],
        best_hook_index=0,
        cta="Salva pra fazer depois!",
        caption="Legenda de teste gerada pelo modo --mock-claude.\nVocê faria essa receita?",
        ingredients=["Ingrediente 1", "Ingrediente 2"],
        hashtags=["#receita", "#receitafacil", "#culinaria"],
        voiceover="Locução de teste gerada sem chamar a API.",
    ), info.duration)
