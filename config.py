"""Configuração central: variáveis de ambiente e detecção da pasta de drafts do CapCut."""
from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv"}

# Pastas de referência (vídeos do TikTok usados só como guia de gravação): nunca processar.
REFERENCE_DIR_NAMES = {"1-referencias"}

# ---------------------------------------------------------------- Negócio (Gostosuras Fit)
SALES_PAGE_URL = os.environ.get("SALES_PAGE_URL", "https://receitaspraticasfit.com.br/")

# As 25 receitas do e-book Gostosuras Fit (define "No e-book" e o CTA).
EBOOK_RECIPES = [
    "Big Mac", "hot dog", "pizza de frigideira", "mini pizza", "esfirra", "coxinha",
    "tortinha de frango", "nuggets", "McChicken", "crepioca", "pão de milho", "tortinha de morango",
    "pavê", "bombom de morango", "banoffee", "bolo de caneca", "bolo de pote", "cheesecake",
    "brigadeiro", "Chokito", "cookies", "mousse de maracujá", "pudim", "picolé", "bombom de banana",
]

CTA_IN_EBOOK = "Essa e mais 24 receitas por R$ 27"
CTA_NOT_IN_EBOOK = "Quer mais receitas assim? 25 por R$ 27"

# Termos proibidos (promessa de resultado). Regex sobre texto sem acento e minúsculo.
FORBIDDEN_PATTERNS = {
    "emagrecer": r"emagrec",
    "low carb": r"low\s*-?\s*carb",
    "perder peso": r"perd\w*\s+(de\s+)?peso",
    "detox": r"detox",
    "garantia de resultado": r"garanti\w*\s+(de\s+)?resultado|resultados?\s+garantid",
}

# Opções do Banco de Receitas (usadas quando o Notion não está configurado;
# com o Notion ativo, as opções são lidas do próprio banco).
DEFAULT_CATEGORIAS = ["Lanche", "Doce", "Salgado", "Café da manhã", "Marmita"]
DEFAULT_PASTAS = [
    "Lanches Fit Fáceis", "Doces Fit sem Açúcar", "Receitas Saudáveis Fáceis",
    "Marmita Fit e Almoço Saudável", "Café da Manhã Saudável",
]
ESTILOS = {"padrao": "Padrão (com preço)", "cru": "Cru (natural)"}

# ---------------------------------------------------------------- Marca (CapCut)
BRAND_GREEN = "#1A3D2B"
BRAND_ORANGE = "#E07A3A"
BRAND_LIGHT_GREEN = "#9BE3BE"
# Figtree não existe no catálogo de fontes do CapCut; Poppins Bold é a mais próxima.
BRAND_FONT = os.environ.get("CAPCUT_FONT", "Poppins_Bold")
CANVAS_W, CANVAS_H = 1080, 1920  # 9:16

# Pins estáticos (capa e colagem): 2:3, mesma fonte do CapCut.
PIN_W, PIN_H = 1000, 1500
PIN_FONT_FILE = Path(__file__).resolve().parent / "assets" / "fonts" / "Poppins-Bold.ttf"

# Área segura do Pinterest: nada nos 15% de cima nem nos 20% de baixo.
# No CapCut, transform_y vai de +1 (topo) a -1 (base), em unidades de meia tela:
#   limite de cima  = 1 - 2*0.15 = +0.70 ; limite de baixo = -1 + 2*0.20 = -0.60
SAFE_TOP_Y, SAFE_BOTTOM_Y = 0.70, -0.60
HOOK_Y = 0.42   # centro do gancho, com folga abaixo de +0.70
CTA_Y = -0.38   # centro do CTA, com folga acima de -0.60

# Pasta usada quando nenhuma instalação do CapCut é encontrada (ex.: Linux, testes).
FALLBACK_DRAFTS_DIR = Path(__file__).resolve().parent / "capcut_drafts_output"


def capcut_draft_candidates() -> list[Path]:
    """Caminhos conhecidos da pasta de projetos do CapCut Desktop, por sistema operacional."""
    system = platform.system()
    home = Path.home()

    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        return [
            local / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            local / "CapCut Drafts",
        ]
    if system == "Darwin":
        return [
            home / "Movies" / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            home / "Library" / "Containers" / "com.lemon.lvoverseas" / "Data" / "Movies"
            / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft",
            home / "Library" / "Containers" / "com.lemon.capcut" / "Data" / "Documents"
            / "JianyingPro" / "drafts",
        ]
    return []  # CapCut Desktop não existe para Linux


def detect_capcut_drafts_dir() -> tuple[Path, bool]:
    """Retorna (pasta, encontrada). Prioridade: CAPCUT_DRAFTS_DIR > caminho padrão do SO > fallback local."""
    override = os.environ.get("CAPCUT_DRAFTS_DIR")
    if override:
        return Path(override).expanduser(), True

    for candidate in capcut_draft_candidates():
        if candidate.is_dir():
            return candidate, True

    return FALLBACK_DRAFTS_DIR, False


@dataclass
class Settings:
    anthropic_api_key: str | None = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))
    claude_model: str = field(default_factory=lambda: os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"))
    whisper_model: str = field(default_factory=lambda: os.environ.get("WHISPER_MODEL", "small"))
    whisper_language: str = field(default_factory=lambda: os.environ.get("WHISPER_LANGUAGE", "pt"))
    whisper_device: str = field(default_factory=lambda: os.environ.get("WHISPER_DEVICE", "cpu"))

    notion_token: str | None = field(default_factory=lambda: os.environ.get("NOTION_TOKEN"))
    notion_data_source_id: str = field(default_factory=lambda: os.environ.get(
        "NOTION_DATA_SOURCE_ID", "8d44c394-93f3-49d2-af5a-33b259f707ff"))  # Banco de Receitas

    # Layout dos textos no CapCut
    hook_duration_s: float = 3.0
    cta_duration_s: float = 3.0
    min_clip_duration_s: float = 3.0


settings = Settings()
