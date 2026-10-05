# 🍳 Receitas Práticas → CapCut → Notion (Pinterest)

CLI em Python que pega uma pasta de vídeos de receita **gravados pela equipe** e, para cada vídeo:

1. Extrai o áudio com **FFmpeg** e transcreve localmente com **faster-whisper**.
2. Detecta **imagem congelada** e **silêncio** no final (FFmpeg `freezedetect`/`silencedetect`).
3. Manda tudo para o **Claude**, que devolve: ponto de corte, 3 ganchos (A curiosidade, B benefício, C erro comum, até 6 palavras), se a receita está no e-book Gostosuras Fit, título e descrição do pin, 3 hashtags, categoria/pasta e roteiro de locução (até 45 palavras). Termos proibidos (emagrecer, low carb, detox…) disparam uma nova tentativa automática.
4. Define o **CTA pelo código**: receita do e-book → "Essa e mais 24 receitas por R$ 27"; fora do e-book → "Quer mais receitas assim? 25 por R$ 27".
5. Cria o **projeto nativo do CapCut Desktop** em 9:16, com o vídeo cortado e os textos dentro da área segura do Pinterest:
   - **Padrão (com preço):** gancho na faixa verde `#1A3D2B` (0–3s) + CTA na faixa laranja `#E07A3A` (últimos 3s).
   - **Cru (natural):** só o nome da receita, discreto, sem faixa nem preço.
6. Atualiza a linha da receita no **Banco de Receitas do Notion** (cria se não existir).
7. Gera 2 pins estáticos JPG 1000x1500 (2:3) em `pins/`, ao lado do vídeo, sem gravar nada a mais:
   - **`<nome>_capa.jpg`**: o melhor frame do prato pronto, com degradê verde, título com a palavra-chave em laranja, CTA e selo "R$ 27".
   - **`<nome>_colagem.jpg`**: 3 ou 4 momentos-chave (ingredientes → preparo → forno → pronto) numa grade numerada.
   - Os frames são pré-filtrados por nitidez e brilho, e o **Claude escolhe olhando as imagens**: descarta borrado, escuro, mão na frente e texto ou marca d'água de terceiros. No `--mock-claude` só vale o filtro automático.
8. Salva `<nome_do_video>_video_analise.md` ao lado do vídeo, com a seção **Formatos**: vídeo no dia 1, capa no dia 3, colagem no dia 5 (variações B/C do A/B nos dias 7 e 9).

Links de cada pin: `https://receitaspraticasfit.com.br/?src=pin-<slug>` (no A/B: `-a`, `-b`, `-c`; capa: `-capa`; colagem: `-colagem`).

```
main.py              # CLI + orquestração + progresso (rich)
config.py            # .env, regras de negócio (e-book, CTAs, termos proibidos), marca e pasta do CapCut
app/media.py         # ffprobe, extração de áudio, detecção de imagem parada/silêncio
app/transcriber.py   # faster-whisper com cache em disco
app/analyzer.py      # Claude API com saída estruturada (Pydantic) + validação
app/capcut_draft.py  # monta o draft do CapCut (via pycapcut)
app/notion_sync.py   # Banco de Receitas (API oficial do Notion)
app/pinterest.py     # slug e links ?src
app/pin_images.py    # capa e colagem (frames + Pillow)
assets/fonts/        # Poppins Bold (licença OFL), usada nas imagens
app/report.py        # relatório Markdown
```

---

## 1. Instalação

### Jeito rápido (Windows)

1. Coloque o projeto em `C:\Receitas` (fora do OneDrive).
2. Dê dois cliques em **`INSTALAR.bat`**. Ele confere Python 3.11+ e FFmpeg (e diz como instalar se faltar), cria o `.venv`, instala as dependências e cria o `.env`.
3. Preencha `ANTHROPIC_API_KEY` e `NOTION_TOKEN` no `.env` (o Bloco de Notas abre sozinho).
4. Arraste a pasta com o vídeo de teste para cima do **`TESTAR.bat`**. Ele roda primeiro com `--mock-claude` (sem gastar API e sem gravar no Notion) e, se der certo, roda de verdade. Tudo fica salvo em `teste-log.txt`.

O passo a passo manual está abaixo.


### Python 3.11+ e ambiente virtual

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
cp .env.exemplo .env      # Windows: copy .env.exemplo .env
```

Edite `.env` e coloque sua `ANTHROPIC_API_KEY` (pegue em console.anthropic.com).

### Notion (Banco de Receitas)

1. Crie uma integração interna em **notion.so/profile/integrations** → copie o token para `NOTION_TOKEN` no `.env`.
2. No Notion, abra o **Banco de Receitas** → `•••` → **Conexões** → adicione a integração. Sem isso a API responde "não encontrado".
3. `NOTION_DATA_SOURCE_ID` já vem preenchido com o ID do Banco de Receitas.

Como a ferramenta escreve no Notion:
- Procura a linha pela coluna **Receita** (a IA recebe a lista de nomes do banco e reutiliza o nome exato). Se não achar, cria a linha.
- Em linha existente, **só preenche campos vazios**. O que a equipe já escreveu (ganchos, título, descrição, CTA, estilo) prevalece e **também vai para o vídeo**, para o CapCut e o Notion baterem.
- Sempre: `Origem do vídeo` = "Gravado por nós". `Status` vai para "Editado" se estava em Ideia/Texto pronto (Agendado/Publicado não mudam).
- Nunca toca em `Vídeo editado`, datas ou métricas.
- Sem `NOTION_TOKEN` (ou com `--no-notion`) a ferramenta roda normalmente, só sem o Notion.

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
| `--mock-claude` | Não chama a API (análise fictícia) e **não grava no Notion**: só mostra no terminal o que seria escrito |
| `--ab-hooks` | Cria 3 projetos por vídeo, um por gancho (`_auto_A`, `_B`, `_C`). Só no estilo Padrão |
| `--estilo padrao\|cru` | Visual do vídeo quando o Notion ainda não define o `Estilo` da receita (padrão: `padrao`) |
| `--no-notion` | Não lê nem escreve no Banco de Receitas |
| `--sem-imagens` | Pula a capa e a colagem (gera só o vídeo) |
| `--overwrite` | Recria drafts que já existem com o mesmo nome |
| `--skip-capcut` | Só gera análise + relatório |
| `--drafts-dir PASTA` | Força a pasta de projetos do CapCut |
| `--whisper-model X` | `tiny`, `base`, `small` (padrão), `medium`, `large-v3` |

- Pastas chamadas `1-referencias` (vídeos do TikTok usados só como guia) são recusadas.
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
4. Abra, revise o gancho/CTA e exporte para `2-editados/`.

> **Fonte:** a Figtree não existe no catálogo de fontes do CapCut, então os textos saem em **Poppins Bold** (a mais parecida). Para trocar, use `CAPCUT_FONT` no `.env` com outro nome do catálogo do `pycapcut`.

**Importante:**
- O draft aponta para o caminho **absoluto** do vídeo original. Não mova/renomeie o vídeo depois de gerar, ou o CapCut mostra "mídia ausente".
- O formato do `draft_content.json` não é documentado pela ByteDance. A geração usa a lib `pycapcut` (mantida pela comunidade). Se uma atualização do CapCut deixar de abrir os projetos (aparece em branco ou não aparece), atualize a lib com `pip install -U pycapcut` ou use uma versão do CapCut compatível com ela.

---

## 4. Teste A/B de ganchos (Pinterest)

```bash
python main.py "C:\caminho\Semana-01" --ab-hooks
```

Cada vídeo vira 3 projetos idênticos, menos o gancho: A (curiosidade), B (benefício) e C (erro comum). Cada um tem seu link (`?src=pin-<slug>-a`, `-b`, `-c`). No Notion, `Gancho` e `Link do pin` ficam com a variação A até o vencedor ser marcado; `Link B` e `Link C` recebem os links das outras variações.

Com R$ 10–15/dia de verba:
1. **Primeiro no orgânico, de graça:** poste as 3 versões como pins normais, com 2 a 3 dias entre elas.
2. **Só o vencedor do orgânico vira anúncio.** A/B pago: no máximo 1 vídeo por semana, com as 3 variações no mesmo grupo de anúncios da Campanha A (venda).
3. Não decida com menos de ~1.000 impressões por variação. Métrica principal: **taxa de visualização** (vídeo 2s+ ÷ impressões). Desempate: cliques de saída.
4. Depois de 5 a 10 vídeos, o estilo que ganhou mais vezes vira regra no `SYSTEM_PROMPT` (`app/analyzer.py`).

## 5. Próximos passos sugeridos

- **Locução com IA de voz:** mandar o campo `voiceover` para ElevenLabs e adicionar o áudio como trilha no draft.
- **Legendas automáticas:** exportar a transcrição em `.srt` e importar no draft (`pycapcut` tem `import_srt`).
