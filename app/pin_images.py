"""Pins estáticos a partir do vídeo: capa (prato pronto) e colagem passo a passo, em JPG 1000x1500 (2:3).

Fluxo: amostra frames com o FFmpeg → pré-filtro por nitidez/brilho → o Claude escolhe olhando as imagens
(descarta mão na frente, prato não pronto, texto/marca d'água de terceiros) → renderiza com Pillow.
Sem o Claude (modo mock), fica só a escolha automática por nitidez/brilho.
"""
from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from config import BRAND_GREEN, BRAND_LIGHT_GREEN, BRAND_ORANGE, PIN_FONT_FILE, PIN_H, PIN_W
from app.analyzer import RecipeAnalysis
from app.media import VideoInfo

MARGIN_X, MARGIN_Y = int(PIN_W * 0.10), int(PIN_H * 0.10)  # textos fora dos 10% das bordas
CONTENT_W = PIN_W - 2 * MARGIN_X
WHITE = (255, 255, 255)
PRICE_BADGE = "R$ 27"


@dataclass
class Candidate:
    id: str
    t: float
    path: Path
    sharpness: float = 0.0
    brightness: float = 0.0

    @property
    def score(self) -> float:
        # Penaliza frame escuro ou estourado; nitidez manda no resto.
        light = 1.0 if 60 <= self.brightness <= 215 else 0.35
        return self.sharpness * light


@dataclass
class PinImages:
    capa: Path | None = None
    colagem: Path | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- frames
def _extract(video: Path, t: float, out: Path, width: int | None = None) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", str(video), "-frames:v", "1", "-q:v", "2"]
    if width:
        cmd += ["-vf", f"scale={width}:-2"]
    subprocess.run(cmd + [str(out)], check=True, capture_output=True)
    return out


def _measure(c: Candidate) -> Candidate:
    gray = np.asarray(Image.open(c.path).convert("L"), dtype=np.float32)
    lap = (-4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:])
    c.sharpness = float(lap.var())
    c.brightness = float(gray.mean())
    return c


def _sample(video: Path, start: float, end: float, n: int, prefix: str, work: Path) -> list[Candidate]:
    end = max(end, start + 0.1)
    times = [start + (end - start) * i / max(n - 1, 1) for i in range(n)]
    cands = []
    for i, t in enumerate(times, 1):
        path = _extract(video, t, work / f"{prefix}{i}.jpg", width=540)
        cands.append(_measure(Candidate(f"{prefix}{i}", round(t, 2), path)))
    return cands


def _top(cands: list[Candidate], k: int) -> list[Candidate]:
    return sorted(cands, key=lambda c: c.score, reverse=True)[:k]


def _thumb(path: Path) -> bytes:
    img = Image.open(path).convert("RGB")
    img.thumbnail((384, 384))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return buf.getvalue()


# ---------------------------------------------------------------- desenho
def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(PIN_FONT_FILE), size)


def _cover(img: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left, top = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((left, top, left + w, top + h))


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _wrap(words: list[str], font: ImageFont.FreeTypeFont, max_w: int) -> list[list[int]]:
    """Quebra em linhas; devolve índices das palavras de cada linha."""
    space = font.getlength(" ")
    lines, cur, cur_w = [], [], 0.0
    for i, word in enumerate(words):
        w = font.getlength(word)
        if cur and cur_w + space + w > max_w:
            lines.append(cur)
            cur, cur_w = [], 0.0
        cur_w += (space if cur else 0) + w
        cur.append(i)
    if cur:
        lines.append(cur)
    return lines


def _keyword_mask(words: list[str], title: str, keyword: str) -> list[bool]:
    start = title.casefold().find(keyword.casefold()) if keyword else -1
    end = start + len(keyword)
    mask, pos = [], 0
    for word in words:
        idx = title.find(word, pos)
        mask.append(start >= 0 and idx < end and idx + len(word) > start)
        pos = idx + len(word)
    return mask


def _draw_kicker(draw: ImageDraw.ImageDraw, y: int) -> int:
    font, tracking = _font(30), 5
    text = "RECEITAS PRÁTICAS"
    total = sum(font.getlength(ch) for ch in text) + tracking * (len(text) - 1)
    x = (PIN_W - total) / 2
    for ch in text:
        draw.text((x, y), ch, font=font, fill=_hex(BRAND_LIGHT_GREEN))
        x += font.getlength(ch) + tracking
    return y + 44


def _draw_title(draw: ImageDraw.ImageDraw, y: int, title: str, keyword: str) -> int:
    words = title.split()
    mask = _keyword_mask(words, title, keyword)
    # Prefere 2 linhas com fonte >= 64; senão, a maior fonte que caiba em 3 linhas.
    def fits(sz: int, max_lines: int):
        f = _font(sz)
        ls = _wrap(words, f, CONTENT_W)
        return (f, ls) if len(ls) <= max_lines and all(f.getlength(w) <= CONTENT_W for w in words) else None

    choice = next((fits(sz, 2) for sz in range(92, 63, -4) if fits(sz, 2)), None) \
        or next((fits(sz, 3) for sz in range(92, 39, -4) if fits(sz, 3)), None) \
        or fits(40, 99)
    font, lines = choice
    size = font.size
    space, line_h = font.getlength(" "), int(size * 1.12)
    for line in lines:
        line_w = sum(font.getlength(words[i]) for i in line) + space * (len(line) - 1)
        x = (PIN_W - line_w) / 2
        for i in line:
            draw.text((x, y), words[i], font=font, fill=_hex(BRAND_ORANGE) if mask[i] else WHITE)
            x += font.getlength(words[i]) + space
        y += line_h
    return y


def _footer_height(cta: str) -> tuple[int, list[list[int]], ImageFont.FreeTypeFont]:
    font = _font(40)
    lines = _wrap(cta.split(), font, CONTENT_W)[:2]
    return len(lines) * 52 + 24 + 84, lines, font


def _draw_footer(draw: ImageDraw.ImageDraw, cta: str) -> int:
    """Desenha CTA + selo 'R$ 27' encostados na margem de baixo. Retorna o topo do rodapé."""
    height, lines, font = _footer_height(cta)
    words = cta.split()
    top = y = PIN_H - MARGIN_Y - height
    for line in lines:
        text = " ".join(words[i] for i in line)
        draw.text((PIN_W / 2, y), text, font=font, fill=WHITE, anchor="ma")
        y += 52
    y += 24
    badge_font = _font(48)
    bw = badge_font.getlength(PRICE_BADGE) + 64
    x0 = (PIN_W - bw) / 2
    draw.rounded_rectangle((x0, y, x0 + bw, y + 84), radius=42, fill=_hex(BRAND_ORANGE))
    draw.text((PIN_W / 2, y + 42), PRICE_BADGE, font=badge_font, fill=WHITE, anchor="mm")
    return top


def _gradient_overlay(top_end: float = 0.48) -> Image.Image:
    """Degradê verde no topo (até top_end da altura) e na base (a partir de 52%)."""
    y = np.linspace(0, 1, PIN_H)
    top = np.clip(1 - y / top_end, 0, 1) ** 1.0 * 240
    bottom = np.clip((y - 0.52) / 0.48, 0, 1) ** 1.2 * 248
    alpha = np.maximum(top, bottom).astype(np.uint8)
    alpha_img = Image.fromarray(np.repeat(alpha[:, None], PIN_W, axis=1), "L")
    overlay = Image.new("RGBA", (PIN_W, PIN_H), _hex(BRAND_GREEN) + (0,))
    overlay.putalpha(alpha_img)
    return overlay


def render_capa(frame: Path, title: str, keyword: str, cta: str, out: Path) -> Path:
    base = _cover(Image.open(frame).convert("RGB"), PIN_W, PIN_H).convert("RGBA")

    # Textos numa camada própria, com sombra suave por baixo para ler sobre qualquer foto.
    text_layer = Image.new("RGBA", (PIN_W, PIN_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(text_layer)
    y = _draw_kicker(draw, MARGIN_Y)
    title_bottom = _draw_title(draw, y, title, keyword)
    _draw_footer(draw, cta)

    # O degradê de cima vai até um pouco abaixo do título (mínimo 42% da altura).
    img = Image.alpha_composite(base, _gradient_overlay(max(0.42, (title_bottom + 160) / PIN_H)))
    shadow_alpha = text_layer.getchannel("A").filter(ImageFilter.GaussianBlur(8)).point(lambda a: int(a * 0.6))
    shadow = Image.new("RGBA", (PIN_W, PIN_H), (8, 25, 16, 0))
    shadow.putalpha(shadow_alpha)
    img = Image.alpha_composite(Image.alpha_composite(img, shadow), text_layer).convert("RGB")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=92)
    return out


def render_colagem(frames: list[Path], title: str, keyword: str, cta: str, out: Path) -> Path:
    img = Image.new("RGB", (PIN_W, PIN_H), _hex(BRAND_GREEN))
    draw = ImageDraw.Draw(img)
    y = _draw_kicker(draw, MARGIN_Y)
    title_bottom = _draw_title(draw, y, title, keyword)
    footer_top = _draw_footer(draw, cta)

    gap, n = 24, len(frames)
    area_top, area_bottom = title_bottom + 28, footer_top - 36
    area_h = area_bottom - area_top
    if n == 4:
        cols, rows = 2, 2
    else:
        cols, rows = n, 1
    cell_w = (CONTENT_W - gap * (cols - 1)) // cols
    cell_h = min((area_h - gap * (rows - 1)) // rows, int(cell_w * 16 / 9))
    grid_h = rows * cell_h + gap * (rows - 1)
    y0 = area_top + (area_h - grid_h) // 2

    num_font = _font(36)
    for i, frame in enumerate(frames):
        r, c = divmod(i, cols)
        x, y = MARGIN_X + c * (cell_w + gap), y0 + r * (cell_h + gap)
        tile = _cover(Image.open(frame).convert("RGB"), cell_w, cell_h)
        mask = Image.new("L", (cell_w, cell_h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, cell_w - 1, cell_h - 1), radius=28, fill=255)
        img.paste(tile, (x, y), mask)
        cx, cy, rad = x + 46, y + 46, 30
        draw.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=_hex(BRAND_ORANGE), outline=WHITE, width=3)
        draw.text((cx, cy), str(i + 1), font=num_font, fill=WHITE, anchor="mm")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=92)
    return out


# ---------------------------------------------------------------- orquestração
MIN_STEPS = 3


def _review(picker, cands: list[Candidate]) -> dict:
    """Pede ao Claude o veredito de cada frame. Sem picker (mock) devolve {}."""
    if picker is None or not cands:
        return {}
    return picker.review_frames([(c.id, _thumb(c.path)) for c in cands])


def _valid(c: Candidate, verdicts: dict) -> bool:
    v = verdicts.get(c.id)
    return v is not None and not v.has_text and v.shows_food_or_hands


def _best_capa(cands: list[Candidate], verdicts: dict) -> Candidate | None:
    ok = [c for c in cands if _valid(c, verdicts)]
    if not ok:
        return None
    return max(ok, key=lambda c: (verdicts[c.id].dish_ready, verdicts[c.id].score, c.score))


MIN_GAP_S = 1.0       # passos da colagem precisam estar a pelo menos 1s um do outro
SIMILAR_MAX_DIFF = 12  # diferença média (0-255) abaixo disso = quadro praticamente igual


def _signature(c: Candidate) -> np.ndarray:
    return np.asarray(Image.open(c.path).convert("L").resize((32, 56)), dtype=np.float32)


def _too_similar(c: Candidate, taken: list[Candidate]) -> bool:
    sig = _signature(c)
    return any(abs(c.t - o.t) < MIN_GAP_S or np.abs(sig - _signature(o)).mean() < SIMILAR_MAX_DIFF
               for o in taken)


def _best_step(cands: list[Candidate], verdicts: dict, target: float, taken: list[Candidate]) -> Candidate | None:
    """Melhor quadro limpo do passo: nota visual, perdendo pontos quanto mais longe do momento-chave.
    Quadros repetidos (muito perto no tempo ou visualmente iguais a um já escolhido) ficam de fora."""
    ok = [c for c in cands if _valid(c, verdicts) and not _too_similar(c, taken)]
    if not ok:
        return None
    return max(ok, key=lambda c: (verdicts[c.id].score - 1.5 * abs(c.t - target), c.score))


def build_pin_images(info: VideoInfo, analysis: RecipeAnalysis, out_dir: Path, work: Path,
                     picker=None) -> PinImages:
    """Gera <nome>_capa.jpg e <nome>_colagem.jpg em out_dir. `picker` = RecipeAnalyzer (None no mock).

    Com o Claude, só entram frames SEM texto e COM comida/mãos preparando; se não houver frame bom,
    a peça é pulada (com aviso) em vez de sair com quadro ruim.
    """
    result = PinImages()
    video, end = info.path, analysis.cut_end_seconds
    stem = video.stem

    # 1ª passada: capa no final (prato pronto) + passos em volta de cada momento-chave.
    capa_cands = _top(_sample(video, end * 0.6, max(end - 0.15, 0.1), 10, "C", work), 6)
    steps = []
    for k, m in enumerate(analysis.key_moments, 1):
        lo, hi = max(m.seconds - 0.8, 0), min(m.seconds + 0.8, end - 0.05)
        steps.append((m, _top(_sample(video, lo, hi, 4, f"S{k}-", work), 3)))

    if picker is None:  # mock: só nitidez/brilho
        result.notes.append("Modo mock: frames escolhidos só por nitidez, sem checar texto queimado. Revise.")
        capa_pick = capa_cands[0]
        step_picks = [cands[0] for _m, cands in steps]
    else:
        try:
            verdicts = _review(picker, capa_cands + [c for _m, cands in steps for c in cands])

            capa_pick = _best_capa(capa_cands, verdicts)
            if capa_pick is None:  # 2ª passada: procura o prato pronto em boa parte do vídeo
                wide = _top(_sample(video, end * 0.3, max(end - 0.15, 0.1), 14, "CW", work), 8)
                capa_pick = _best_capa(wide, _review(picker, wide))

            step_picks = []
            for k, (m, cands) in enumerate(steps, 1):
                taken = list(step_picks)
                pick = _best_step(cands, verdicts, m.seconds, taken)
                if pick is None:  # 2ª passada: janela maior em volta do momento
                    lo, hi = max(m.seconds - 2.5, 0), min(m.seconds + 2.5, end - 0.05)
                    wide = _top(_sample(video, lo, hi, 6, f"SW{k}-", work), 4)
                    pick = _best_step(wide, _review(picker, wide), m.seconds, taken)
                if pick is None:
                    result.notes.append(f"Passo '{m.label}' sem quadro limpo e diferente dos outros "
                                        f"(texto, sem comida ou repetido): ficou de fora.")
                else:
                    step_picks.append(pick)
        except Exception as e:  # avaliação falhou: não arrisca publicar frame com texto
            result.notes.append(f"Avaliação dos frames pelo Claude falhou ({e}); capa e colagem não geradas.")
            return result

    if capa_pick is None:
        result.notes.append("Capa não gerada: nenhum frame do prato pronto sem texto queimado.")
    else:
        capa_full = _extract(video, capa_pick.t, work / "capa_full.jpg")
        result.capa = render_capa(capa_full, analysis.image_title, analysis.image_keyword, analysis.cta,
                                  out_dir / f"{stem}_capa.jpg")

    step_picks.sort(key=lambda c: c.t)  # colagem sempre em ordem cronológica
    if len(step_picks) < MIN_STEPS:
        result.notes.append(f"Colagem não gerada: só {len(step_picks)} passo(s) com quadro limpo (mínimo {MIN_STEPS}).")
    else:
        step_full = [_extract(video, c.t, work / f"step{i}_full.jpg") for i, c in enumerate(step_picks, 1)]
        result.colagem = render_colagem(step_full, analysis.image_title, analysis.image_keyword, analysis.cta,
                                        out_dir / f"{stem}_colagem.jpg")
    return result
