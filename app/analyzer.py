"""Análise do conteúdo da receita via Claude API (saída estruturada validada por Pydantic)."""
from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema

from config import (
    CTA_IN_EBOOK, CTA_NOT_IN_EBOOK, DEFAULT_CATEGORIAS, DEFAULT_PASTAS, EBOOK_RECIPES, FORBIDDEN_PATTERNS,
)
from app.media import DeadZones, VideoInfo
from app.transcriber import Segment, format_transcript


class KeyMoment(BaseModel):
    label: str = Field(description="Etapa curta: ingredientes, preparo, forno/frigideira ou pronto")
    seconds: float = Field(description="Segundo do vídeo que melhor mostra essa etapa")


class RecipeAnalysis(BaseModel):
    recipe_name: str = Field(description="Nome da receita. Se já existir no banco, use EXATAMENTE o nome de lá")
    in_ebook: bool = Field(description="True se a receita é uma das 25 do e-book Gostosuras Fit")
    categoria: str = Field(description="Uma das categorias permitidas")
    pasta: str = Field(description="Uma das pastas do Pinterest permitidas")
    cut_end_seconds: float = Field(description="Segundo exato onde o vídeo deve terminar")
    cut_reason: str = Field(description="Por que cortar nesse ponto (1 frase)")
    hook_curiosidade: str = Field(description="Gancho A, estilo curiosidade, até 6 palavras")
    hook_beneficio: str = Field(description="Gancho B, estilo benefício, até 6 palavras")
    hook_erro_comum: str = Field(description="Gancho C, estilo erro comum, até 6 palavras")
    pin_title: str = Field(description="Título do pin, até 100 caracteres, palavra-chave no começo")
    pin_description: str = Field(description="Descrição do pin, 2 a 3 frases, SEM hashtags")
    hashtags: list[str] = Field(description="Exatamente 3 hashtags, cada uma começando com #")
    ingredients: list[str] = Field(description="Ingredientes com quantidades quando faladas")
    voiceover: str = Field(description="Roteiro de locução em off, máximo 45 palavras")
    image_title: str = Field(description="Título curto para a capa/colagem, até 6 palavras")
    image_keyword: str = Field(description="Trecho de image_title a destacar em laranja (a palavra-chave)")
    key_moments: list[KeyMoment] = Field(description="3 ou 4 momentos-chave em ordem: ingredientes, "
                                                     "preparo, forno/frigideira, pronto")
    cta: SkipJsonSchema[str] = ""  # definido pelo código a partir de in_ebook (fora do schema do modelo)

    @property
    def hooks(self) -> list[str]:
        return [self.hook_curiosidade, self.hook_beneficio, self.hook_erro_comum]

    @property
    def full_description(self) -> str:
        return f"{self.pin_description.strip()}\n\n{' '.join(self.hashtags)}".strip()


@dataclass
class AnalysisContext:
    """Dados do Banco de Receitas que orientam a análise."""
    existing_recipes: list[str] = field(default_factory=list)
    categorias: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIAS))
    pastas: list[str] = field(default_factory=lambda: list(DEFAULT_PASTAS))


SYSTEM_PROMPT = f"""Você é editor-chefe do perfil "Receitas Práticas" no Pinterest. Todo pin leva para a página de vendas do e-book Gostosuras Fit (25 receitas fit por R$ 27).
Você recebe a transcrição com timestamps de um vídeo de receita gravado pela equipe, a duração total e os trechos com imagem congelada ou silêncio.

Regras:
- PONTO DE CORTE: termine logo após o último momento útil (prato pronto, última fala relevante ou mordida). Remova sobras: imagem parada, silêncio final, "tchau", câmera sendo desligada. Nunca passe da duração total. Sem sobra, use a duração total.
- GANCHOS (texto dos primeiros 3 segundos, até 6 palavras cada, sem emoji):
  A = curiosidade (ex.: "Big Mac fit? Existe.")
  B = benefício (ex.: "Pizza sem forno em 10 minutos")
  C = erro comum (ex.: "Seu brigadeiro fit fica duro?")
- E-BOOK: marque in_ebook=true só se a receita for uma destas: {", ".join(EBOOK_RECIPES)}. Variações do mesmo prato contam (ex.: "coxinha de frango fit" = coxinha).
- TÍTULO DO PIN: até 100 caracteres, começando pela palavra-chave de busca (ex.: "coxinha fit", "doce sem açúcar", "marmita fit").
- DESCRIÇÃO DO PIN: 2 a 3 frases naturais em português do Brasil, sem hashtags (vão no campo próprio).
  Se a receita NÃO estiver no e-book, a descrição entrega a receita resumida (ingredientes principais + modo de preparo em uma frase) e não promete que ela está no e-book.
- HASHTAGS: exatamente 3.
- LOCUÇÃO: no máximo 45 palavras, ritmo de narração, pronta para voz de IA.
- PROIBIDO em qualquer texto: emagrecer, low carb, perder peso, detox, garantia de resultado, ou qualquer promessa de resultado no corpo. Use só "fit", "leve", "sem adicionar açúcar" e "rico em proteína" quando for verdade.
- PROIBIDO pedir "salva o post", "leia a legenda" ou "chama no direct".
- INGREDIENTES: só o que aparece na transcrição; se não houver, deduza o essencial e mantenha curto.
- TÍTULO DA IMAGEM (capa e colagem): até 6 palavras, com a palavra-chave (ex.: "Coxinha FIT na air fryer", palavra-chave "FIT"). image_keyword precisa ser um trecho exato de image_title.
- MOMENTOS-CHAVE: 3 ou 4, em ordem cronológica e dentro do ponto de corte: ingredientes → preparo → forno/frigideira → pronto. Use os timestamps da transcrição para achar o segundo de cada etapa."""


class FrameChoice(BaseModel):
    capa_id: str = Field(description="ID do melhor frame para a capa, ou vazio se nenhum serve")
    step_ids: list[str] = Field(description="Um ID por passo, na ordem dos passos; vazio se nenhum serve")


FRAME_PROMPT = """Você escolhe frames de um vídeo de receita para virar pins do Pinterest.
CAPA (IDs C*): escolha o frame do PRATO PRONTO mais nítido, bem iluminado e apetitoso, com o prato inteiro visível.
PASSOS (IDs S*): para cada passo, escolha o frame que mostra melhor aquela etapa, nítido e bem iluminado.
Descarte sempre: frame borrado, escuro, com mão ou utensílio cobrindo a comida, ou com QUALQUER texto, logo,
@usuário ou marca d'água de terceiros (TikTok, Reels, Kwai etc.). Se nenhum candidato servir, devolva vazio."""


class AnalysisError(RuntimeError):
    pass


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def find_forbidden_terms(a: RecipeAnalysis) -> list[str]:
    blob = _normalize(" ".join([a.pin_title, a.pin_description, a.voiceover, a.image_title, *a.hooks, *a.hashtags]))
    return [term for term, pattern in FORBIDDEN_PATTERNS.items() if re.search(pattern, blob)]


def _fmt_intervals(intervals: list[tuple[float, float]]) -> str:
    return ", ".join(f"{a:.2f}-{b:.2f}s" for a, b in intervals) or "nenhum"


class RecipeAnalyzer:
    def __init__(self, api_key: str | None, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def analyze(self, info: VideoInfo, segments: list[Segment], dead: DeadZones,
                ctx: AnalysisContext) -> RecipeAnalysis:
        prompt = (
            f"Arquivo: {info.path.name}\n"
            f"Duração total: {info.duration:.2f}s\n"
            f"Trechos com imagem congelada: {_fmt_intervals(dead.freezes)}\n"
            f"Trechos em silêncio: {_fmt_intervals(dead.silences)}\n\n"
            f"Categorias permitidas: {', '.join(ctx.categorias)}\n"
            f"Pastas permitidas: {', '.join(ctx.pastas)}\n"
            f"Receitas já no banco (reuse o nome exato se for a mesma): "
            f"{'; '.join(ctx.existing_recipes) or 'nenhuma'}\n\n"
            f"Transcrição:\n{format_transcript(segments)}"
        )

        analysis = self._call(prompt)
        forbidden = find_forbidden_terms(analysis)
        if forbidden:
            # Uma nova tentativa, avisando o que foi usado indevidamente.
            analysis = self._call(prompt + f"\n\nATENÇÃO: uma versão anterior usou termos proibidos "
                                           f"({', '.join(forbidden)}). Não use esses termos nem sinônimos.")
            forbidden = find_forbidden_terms(analysis)
            if forbidden:
                raise AnalysisError(f"Texto gerado com termos proibidos: {', '.join(forbidden)}")

        return sanitize(analysis, info.duration, ctx)

    def choose_frames(self, capa: list[tuple[str, bytes]],
                      steps: list[tuple[str, list[tuple[str, bytes]]]]) -> FrameChoice:
        """Escolhe frames olhando as imagens. capa/steps trazem (id, jpeg_bytes)."""
        def image_block(data: bytes) -> dict:
            return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                "data": base64.b64encode(data).decode()}}

        content: list[dict] = [{"type": "text", "text": "CANDIDATOS PARA A CAPA:"}]
        for frame_id, data in capa:
            content += [{"type": "text", "text": frame_id}, image_block(data)]
        for i, (label, cands) in enumerate(steps, 1):
            content.append({"type": "text", "text": f"PASSO {i} ({label}):"})
            for frame_id, data in cands:
                content += [{"type": "text", "text": frame_id}, image_block(data)]

        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=FRAME_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=FrameChoice,
            )
        except anthropic.APIError as e:
            raise AnalysisError(f"Falha ao escolher frames: {e}") from e
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise AnalysisError("Escolha de frames sem resposta válida")
        return response.parsed_output

    def _call(self, prompt: str) -> RecipeAnalysis:
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
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
        return response.parsed_output


def _limit_words(text: str, n: int) -> str:
    words = text.split()
    return " ".join(words[:n]) if len(words) > n else text.strip()


def sanitize(a: RecipeAnalysis, duration: float, ctx: AnalysisContext | None = None,
             min_clip: float = 3.0) -> RecipeAnalysis:
    """Garante limites seguros e aplica as regras fixas de negócio."""
    ctx = ctx or AnalysisContext()
    a.cut_end_seconds = round(max(min(min_clip, duration), min(a.cut_end_seconds, duration)), 2)
    a.hook_curiosidade = _limit_words(a.hook_curiosidade, 6)
    a.hook_beneficio = _limit_words(a.hook_beneficio, 6)
    a.hook_erro_comum = _limit_words(a.hook_erro_comum, 6)
    a.pin_title = a.pin_title.strip()[:100]
    tags = [t.strip().replace(" ", "") for t in a.hashtags if t.strip()]
    a.hashtags = [t if t.startswith("#") else f"#{t}" for t in tags][:3]
    a.voiceover = _limit_words(a.voiceover, 45)
    if a.categoria not in ctx.categorias:
        a.categoria = ""
    if a.pasta not in ctx.pastas:
        a.pasta = ""
    # Sem cortar palavras (cortar quebra a frase); a arte reduz a fonte para caber.
    a.image_title = (a.image_title or a.recipe_name).strip()
    if not a.image_keyword or a.image_keyword.casefold() not in a.image_title.casefold():
        a.image_keyword = a.image_title.split()[0] if a.image_title else ""
    end = a.cut_end_seconds
    moments = sorted((m for m in a.key_moments if 0 <= m.seconds <= end), key=lambda m: m.seconds)[:4]
    if len(moments) < 3:  # sem momentos confiáveis: distribui 4 pontos ao longo do vídeo
        labels = ["ingredientes", "preparo", "forno/frigideira", "pronto"]
        moments = [KeyMoment(label=lab, seconds=round(end * f, 2))
                   for lab, f in zip(labels, (0.12, 0.38, 0.64, 0.9))]
    a.key_moments = moments
    a.cta = CTA_IN_EBOOK if a.in_ebook else CTA_NOT_IN_EBOOK
    return a


def mock_analysis(info: VideoInfo, segments: list[Segment], ctx: AnalysisContext | None = None) -> RecipeAnalysis:
    """Análise fictícia para testar o fluxo sem gastar API."""
    last_speech = segments[-1].end + 1.0 if segments else info.duration
    return sanitize(RecipeAnalysis(
        recipe_name=info.path.stem,
        in_ebook=False,
        categoria="Doce",
        pasta="Doces Fit sem Açúcar",
        cut_end_seconds=min(last_speech, info.duration),
        cut_reason="Mock: corte 1s após a última fala",
        hook_curiosidade="Bolo fit sem farinha? Existe.",
        hook_beneficio="Pronto em 10 minutos",
        hook_erro_comum="Seu bolo fit fica seco?",
        pin_title=f"{info.path.stem} fit: receita fácil",
        pin_description="Descrição de teste gerada pelo modo --mock-claude. Receita resumida aqui.",
        hashtags=["#receitafit", "#docefit", "#semacucar"],
        ingredients=["Ingrediente 1", "Ingrediente 2"],
        voiceover="Locução de teste gerada sem chamar a API.",
        image_title="Bolo FIT de caneca em 3 minutos",
        image_keyword="FIT",
        key_moments=[],  # mock: distribui automaticamente
    ), info.duration, ctx)
