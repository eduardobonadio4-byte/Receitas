"""Análise do conteúdo da receita via Claude API (saída estruturada validada por Pydantic)."""
from __future__ import annotations

import base64
import re
import unicodedata
from dataclasses import dataclass, field

import anthropic
from typing import Literal

from pydantic import BaseModel, Field
from pydantic.json_schema import SkipJsonSchema

from config import (
    CTA_IN_EBOOK, CTA_NOT_IN_EBOOK, DEFAULT_CATEGORIAS, DEFAULT_PASTAS, EBOOK_CLAIM_PATTERN, EBOOK_RECIPES,
    FORBIDDEN_PATTERNS, NUTRITION_PATTERNS,
)
from app.media import DeadZones, VideoInfo
from app.transcriber import Segment, format_transcript


class KeyMoment(BaseModel):
    label: str = Field(description="Etapa curta: ingredientes, preparo, forno/frigideira ou pronto")
    seconds: float = Field(description="Segundo do vídeo que melhor mostra essa etapa")


class RecipeAnalysis(BaseModel):
    recipe_name: str = Field(description="Nome da receita. Se já existir no banco, use EXATAMENTE o nome de lá")
    ebook_match: Literal["exata", "variacao", "nao"] = Field(
        description="exata = é uma das 25 receitas do e-book no MESMO formato; variacao = usa o sabor/nome de "
                    "uma delas em outro formato (ex.: taco de Big Mac x Big Mac); nao = não tem relação")
    ebook_recipe: str = Field(description="Qual das 25 receitas do e-book (vazio se ebook_match = nao)")
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
    in_ebook: SkipJsonSchema[bool] = False  # = ebook_match == "exata" (definido pelo código)
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
  C = erro comum ligado ao DESEJO do público (comer o lanche/doce sem culpa, com o sabor de verdade), nunca a detalhe técnico de preparo (ex.: "Seu Big Mac fit fica sem graça?", "Brigadeiro fit sem gosto de brigadeiro?")
- E-BOOK (25 receitas): {", ".join(EBOOK_RECIPES)}.
  ebook_match = "exata" só se o vídeo for uma dessas receitas no MESMO formato (ex.: "coxinha de frango fit" = coxinha).
  Se usar o nome/sabor de uma delas em OUTRO formato (taco de Big Mac, wrap de Big Mac, bolo de brigadeiro), é "variacao".
  Em "variacao" ou "nao", NUNCA diga que a receita está no e-book.
- TÍTULO DO PIN: até 100 caracteres, começando pela palavra-chave de busca (ex.: "coxinha fit", "doce sem açúcar", "marmita fit").
- DESCRIÇÃO DO PIN: 2 a 3 frases naturais em português do Brasil, sem hashtags (vão no campo próprio).
  Se ebook_match não for "exata", a descrição entrega a receita resumida (ingredientes principais + modo de preparo em uma frase) e não promete que ela está no e-book.
- HASHTAGS: exatamente 3.
- LOCUÇÃO: no máximo 45 palavras, ritmo de narração, pronta para voz de IA.
- PROIBIDO citar números nutricionais em qualquer texto: calorias, kcal, gramas de proteína/carboidrato/gordura etc. "Rico em proteína" pode, se for verdade.
- PROIBIDO em qualquer texto: emagrecer, low carb, perder peso, detox, garantia de resultado, ou qualquer promessa de resultado no corpo. Use só "fit", "leve", "sem adicionar açúcar" e "rico em proteína" quando for verdade.
- PROIBIDO pedir "salva o post", "leia a legenda" ou "chama no direct".
- INGREDIENTES: só o que aparece na transcrição; se não houver, deduza o essencial e mantenha curto.
- TÍTULO DA IMAGEM (capa e colagem): até 6 palavras, com a palavra-chave (ex.: "Coxinha FIT na air fryer", palavra-chave "FIT"). image_keyword precisa ser um trecho exato de image_title.
- MOMENTOS-CHAVE: 3 ou 4, em ordem cronológica e dentro do ponto de corte: ingredientes → preparo → forno/frigideira → pronto. Use os timestamps da transcrição para achar o segundo de cada etapa."""


class FrameVerdict(BaseModel):
    id: str = Field(description="ID do frame avaliado")
    has_text: bool = Field(description="True se há QUALQUER texto escrito na imagem: legenda, título, preço, "
                                       "logo, @usuário, marca d'água, emoji (texto em embalagem/rótulo também conta)")
    shows_food_or_hands: bool = Field(description="True se a comida (ou mãos preparando a comida) aparece com "
                                                  "clareza e ocupa boa parte do quadro; False se o quadro está vazio, "
                                                  "mostra só bancada/fundo, pessoa falando ou utensílio sem comida")
    dish_ready: bool = Field(description="True se mostra o prato PRONTO para comer, inteiro e bem apresentado")
    score: int = Field(description="Nota visual 0 a 10: nitidez, luz, apetite, sem obstrução")


class FrameReview(BaseModel):
    verdicts: list[FrameVerdict] = Field(description="Uma avaliação para CADA frame recebido")


FRAME_PROMPT = """Você revisa frames de um vídeo de receita que vão virar pins do Pinterest. Avalie CADA frame recebido.
Seja rigoroso com texto: qualquer letra, número, legenda queimada, logo ou marca d'água conta como has_text=true,
mesmo pequeno ou no canto. Quadro sem comida visível (só bancada, fundo, rosto, mão vazia) é shows_food_or_hands=false."""


class AnalysisError(RuntimeError):
    pass


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


def find_forbidden_terms(a: RecipeAnalysis) -> list[str]:
    blob = _normalize(" ".join([a.pin_title, a.pin_description, a.voiceover, a.image_title, *a.hooks, *a.hashtags]))
    found = [term for term, pattern in FORBIDDEN_PATTERNS.items() if re.search(pattern, blob)]
    found += [f"número nutricional ({term})" for term, pattern in NUTRITION_PATTERNS.items() if re.search(pattern, blob)]
    if a.ebook_match != "exata" and re.search(EBOOK_CLAIM_PATTERN, blob):
        found.append("diz que a receita está no e-book, mas ela não está nesse formato")
    return found


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
            analysis = self._call(prompt + f"\n\nATENÇÃO: uma versão anterior quebrou regras "
                                           f"({'; '.join(forbidden)}). Corrija: nada de termos proibidos, "
                                           f"nada de números nutricionais e não prometa o e-book se não for exata.")
            forbidden = find_forbidden_terms(analysis)
            if forbidden:
                raise AnalysisError(f"Texto gerado com termos proibidos: {', '.join(forbidden)}")

        return sanitize(analysis, info.duration, ctx)

    def review_frames(self, frames: list[tuple[str, bytes]]) -> dict[str, FrameVerdict]:
        """Avalia cada frame (id, jpeg_bytes) olhando a imagem. Devolve {id: veredito}."""
        content: list[dict] = [{"type": "text", "text": f"{len(frames)} frames para avaliar:"}]
        for frame_id, data in frames:
            content += [{"type": "text", "text": frame_id},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": base64.b64encode(data).decode()}}]
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=FRAME_PROMPT,
                messages=[{"role": "user", "content": content}],
                output_format=FrameReview,
            )
        except anthropic.APIError as e:
            raise AnalysisError(f"Falha ao avaliar frames: {e}") from e
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise AnalysisError("Avaliação de frames sem resposta válida")
        return {v.id: v for v in response.parsed_output.verdicts}

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
    a.in_ebook = a.ebook_match == "exata"
    a.cta = CTA_IN_EBOOK if a.in_ebook else CTA_NOT_IN_EBOOK
    return a


def mock_analysis(info: VideoInfo, segments: list[Segment], ctx: AnalysisContext | None = None) -> RecipeAnalysis:
    """Análise fictícia para testar o fluxo sem gastar API."""
    last_speech = segments[-1].end + 1.0 if segments else info.duration
    return sanitize(RecipeAnalysis(
        recipe_name=info.path.stem,
        ebook_match="nao",
        ebook_recipe="",
        categoria="Doce",
        pasta="Doces Fit sem Açúcar",
        cut_end_seconds=min(last_speech, info.duration),
        cut_reason="Mock: corte 1s após a última fala",
        hook_curiosidade="Bolo fit sem farinha? Existe.",
        hook_beneficio="Pronto em 10 minutos",
        hook_erro_comum="Seu bolo fit fica sem graça?",
        pin_title=f"{info.path.stem} fit: receita fácil",
        pin_description="Descrição de teste gerada pelo modo --mock-claude. Receita resumida aqui.",
        hashtags=["#receitafit", "#docefit", "#semacucar"],
        ingredients=["Ingrediente 1", "Ingrediente 2"],
        voiceover="Locução de teste gerada sem chamar a API.",
        image_title="Bolo FIT de caneca em 3 minutos",
        image_keyword="FIT",
        key_moments=[],  # mock: distribui automaticamente
    ), info.duration, ctx)
