# 🍳 Receitas → CapCut (automação em lote)

CLI em Python que pega uma pasta de vídeos de receita e, para cada vídeo:

1. Extrai o áudio com **FFmpeg** e transcreve localmente com **faster-whisper** (com timestamps).
2. Detecta **imagem congelada** e **silêncio** (FFmpeg `freezedetect`/`silencedetect`).
3. Manda transcrição + trechos mortos para o **Claude**, que devolve: ponto de corte final, 3 ganchos, 1 CTA, legenda com ingredientes e hashtags, e roteiro de locução (máx. 45 palavras).
4. Cria um **projeto nativo do CapCut Desktop** (pasta + `draft_content.json`) com:
   - vídeo original na trilha principal, **já cortado** no ponto final;
   - texto do **gancho** de 0s a 3s (terço superior);
   - texto do **CTA** nos últimos 3s (terço inferior).
5. Salva `<nome_do_video>_video_analise.md` ao lado do vídeo com legenda, hashtags, ganchos alternativos e locução.

```
main.py              # CLI + orquestração + progresso (rich)
config.py            # .env + detecção automática da pasta de drafts do CapCut por SO
app/media.py         # ffprobe, extração de áudio, detecção de imagem parada/silêncio
app/transcriber.py   # faster-whisper com cache em disco
app/analyzer.py      # Claude API com saída estruturada (Pydantic) + validação
app/capcut_draft.py  # monta o draft do CapCut (via pycapcut)
app/report.py        # relatório Markdown
```

---

## 1. Instalação

### Python 3.10+ e ambiente virtual

```bash
cd Receitas
python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### FFmpeg

| SO | Comando |
|---|---|
| Windows | `winget install Gyan.FFmpeg` (feche e reabra o terminal) |
| macOS | `brew install ffmpeg` |

Confirme com `ffmpeg -version` e `ffprobe -version`.

### Chave da API

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Edite `.env` e coloque sua `ANTHROPIC_API_KEY` (pegue em console.anthropic.com).

> **Modelo:** o `claude-3-5-sonnet-latest` foi aposentado pela Anthropic e não responde mais. O padrão aqui é `claude-sonnet-5-5` (Sonnet atual). Troque em `CLAUDE_MODEL` no `.env` se quiser.

---

## 2. Como testar (do mais barato ao real)

**Passo 1 — teste sem gastar API** (valida FFmpeg, Whisper e a criação do projeto no CapCut):

```bash
python main.py "C:\Users\voce\Videos\receitas" --mock-claude --whisper-model tiny
```

**Passo 2 — 1 vídeo com o Claude real.** Coloque um único vídeo numa pasta de teste:

```bash
python main.py "C:\Users\voce\Videos\teste" --overwrite
```

Confira o `_video_analise.md` gerado e abra o projeto no CapCut (seção 3).

**Passo 3 — lote completo:**

```bash
python main.py "C:\Users\voce\Videos\receitas"
```

### Opções

| Flag | O que faz |
|---|---|
| `--mock-claude` | Não chama a API (análise fictícia) — para testar o fluxo |
| `--overwrite` | Recria drafts que já existem com o mesmo nome |
| `--skip-capcut` | Só gera análise + relatório |
| `--drafts-dir PASTA` | Força a pasta de projetos do CapCut |
| `--whisper-model X` | `tiny`, `base`, `small` (padrão), `medium`, `large-v3` |

- A transcrição fica em cache em `<pasta>/.recipe_cache/` — rodar de novo não retranscreve (só refaz a análise do Claude).
- O primeiro uso do Whisper baixa o modelo (~75 MB no `tiny`, ~480 MB no `small`).
- Com GPU NVIDIA, use `WHISPER_DEVICE=cuda` no `.env`.

---

## 3. Abrindo os projetos no CapCut

1. **Feche o CapCut** antes de rodar o script (ele reescreve a lista de projetos ao fechar).
2. Rode o script. Ele detecta a pasta de projetos automaticamente:
   - **Windows:** `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`
   - **macOS:** `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` (e os caminhos de container antigos)
   - Se não achar, salva em `./capcut_drafts_output/` e avisa no terminal. Nesse caso, descubra a pasta certa no CapCut em **Configurações → Projetos → Local do rascunho** e use `--drafts-dir` ou `CAPCUT_DRAFTS_DIR` no `.env`.
3. Abra o CapCut. Os projetos aparecem como **`<nome_do_video>_auto`** na tela inicial.
4. Abra, revise o gancho/CTA (fonte, posição) e exporte.

**Importante:**
- O draft aponta para o caminho **absoluto** do vídeo original. Não mova/renomeie o vídeo depois de gerar, ou o CapCut mostra "mídia ausente".
- O formato do `draft_content.json` não é documentado pela ByteDance. A geração usa a lib `pycapcut` (mantida pela comunidade). Se uma atualização do CapCut deixar de abrir os projetos (aparece em branco ou não aparece), atualize a lib com `pip install -U pycapcut` ou use uma versão do CapCut compatível com ela.

---

## 4. Próximos passos sugeridos

- **Variações A/B de gancho:** gerar 3 drafts por vídeo (um por gancho) para testar criativos no Meta Ads.
- **Locução com IA de voz:** mandar o campo `voiceover` para ElevenLabs e adicionar o áudio como trilha no draft.
- **Legendas automáticas:** exportar a transcrição em `.srt` e importar no draft (`pycapcut` tem `import_srt`).
- **Notion:** gravar o conteúdo do `_video_analise.md` numa base do Notion como calendário de postagem.
