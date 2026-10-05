# Automação de Receitas → CapCut → Pinterest (versão Receitas Práticas)

## Resumo
A ferramenta pega uma pasta de vídeos de receita **gravados por nós** e devolve **projetos do CapCut prontos para exportar**, com o vídeo cortado e o gancho e o CTA na tela. Para cada vídeo ela também preenche a linha da receita no **Banco de Receitas do Notion**: título do pin, descrição, os 3 ganchos, CTA, link com `?src` e roteiro de locução. A edição cai de 15 a 20 minutos para cerca de 2 minutos de revisão por vídeo.

**Regra de origem:** só entra na ferramenta vídeo gravado por nós. Os vídeos do TikTok em `1-referencias/` servem só de guia de gravação e nunca são editados nem postados (no Notion: Origem = "Referência (não postar)").

## Onde isso encaixa no funil
- **Canal:** Pinterest (orgânico + Pinterest Ads). Não usamos Meta neste projeto.
- **Destino de cada pin: sempre a página de vendas** (`https://receitaspraticasfit.com.br/?src=pin-<slug>`). Quanto mais pin levar pra venda, melhor.
  - Receita **que está no Gostosuras Fit** ("No e-book" marcado): CTA "Essa e mais 24 receitas por R$ 27".
  - Receita **que não está no e-book**: o pin entrega a receita (ingredientes/passo na descrição) e o CTA vende o produto sem prometer aquela receita lá dentro: "Quer mais receitas assim? 25 por R$ 27".
- **Estilo** no Notion é só o visual do vídeo: *Cru* (vídeo + nome discreto) ou *Padrão* (faixa verde + preço). Os dois vão pra página de vendas.
- **PDF grátis (`/receitas-gratis/`)** fica só para a **Campanha B (isca)** e para os pins antigos já revisados.

## O que a ferramenta faz sozinha (para cada vídeo da pasta)
1. **Transcreve a fala** localmente.
2. **Encontra as sobras do final:** imagem parada, silêncio, "tchau", câmera desligando.
3. **A IA (Claude) analisa a receita** e entrega:
   - o **ponto de corte** final;
   - **3 ganchos** de até 6 palavras, um de cada estilo:
     - A: **curiosidade** ("Big Mac fit? Existe.")
     - B: **benefício** ("Pizza sem forno em 10 minutos")
     - C: **erro comum** ("Seu brigadeiro fit fica duro?")
   - **CTA de Pinterest** que leva à página de vendas: "Essa e mais 24 receitas por R$ 27" (receita do e-book) ou "Quer mais receitas assim? 25 por R$ 27" (fora do e-book). Nunca usar "salva o post", "leia a legenda" ou "chama no direct".
   - **Título do pin** (até 100 caracteres, com a palavra-chave no começo: "coxinha fit", "doce sem açúcar", "marmita fit"…);
   - **Descrição do pin** (2 a 3 frases + 3 hashtags);
   - **roteiro de locução** de até 45 palavras.
4. **Cria o projeto no CapCut** em 9:16, com o vídeo cortado, o gancho de 0 a 3 s e o CTA nos últimos 3 s.
   - Texto fora dos 15% de cima e dos 20% de baixo, que o Pinterest cobre com a interface.
   - Cores da marca: faixa verde #1A3D2B no gancho e faixa laranja #E07A3A no CTA. Fonte Poppins Bold (a Figtree não existe no CapCut; é a mais parecida).
   - Estilo **Cru**: só o nome da receita, discreto, sem faixa nem preço. Nesse estilo não tem A/B de gancho.
5. **Atualiza o Notion** (ver "Integração com o Notion").
6. **Salva um relatório** ao lado do vídeo: `nome-do-video_video_analise.md`.

## Modo teste A/B (`--ab-hooks`)
Cada vídeo vira **3 projetos no CapCut**, idênticos menos o gancho: `receita_auto_A`, `_B` e `_C`.

**Como testar com a nossa verba (R$ 10 a 15/dia):**
1. **Primeiro no orgânico, de graça:** posta as 3 versões como pins normais, com 2 a 3 dias entre elas. Cada uma leva o próprio `?src` (`pin-<slug>-a`, `-b`, `-c`).
2. **Só vira anúncio o vencedor do orgânico.** O A/B pago fica para 1 vídeo por semana no máximo, com as 3 variações no **mesmo grupo de anúncios** da **Campanha A (venda)**.
3. Não decidir com menos de ~1.000 impressões por variação.

## Métricas (Pinterest, não Meta)
| Métrica | Onde ver | Para quê |
|---|---|---|
| **Taxa de visualização** = visualizações de vídeo (2 s+) ÷ impressões | Pinterest Analytics / Ads | Principal: o gancho prendeu? |
| **Cliques de saída** | Analytics / Ads | Desempate: levou pro site? |
| **Salvamentos** | Analytics | Sinal de alcance futuro no orgânico |
| **Leads / vendas** | Hotmart Send e Hotmart, pelo `?src` | O que paga a conta |

**Padrão vencedor:** depois de **5 a 10 vídeos**, vemos qual estilo (A, B ou C) ganhou mais vezes. Esse estilo vira regra no prompt da IA.

## Integração com o Notion (Banco de Receitas)
A ferramenta procura a linha pela coluna **Receita**. Se não achar, cria uma nova, com **Status = "Editado"** e **Origem do vídeo = "Gravado por nós"**.

Se a linha já existe, a ferramenta **só preenche o que está vazio**. O que já foi escrito no Notion (ganchos, título, descrição, CTA, estilo) **vale também para o vídeo**: o CapCut usa esses textos, então vídeo e Notion sempre batem. O Status passa para "Editado" se estava em Ideia ou Texto pronto; Agendado e Publicado não mudam.

| Campo do Notion | Quem preenche |
|---|---|
| Receita, Categoria, Pasta, No e-book, Estilo | Ferramenta sugere, equipe confere |
| Gancho A (curiosidade) / B (benefício) / C (erro comum) | Ferramenta |
| Gancho (o que vai pro ar) | Ferramenta põe o A; troca para o vencedor depois |
| Título do pin, Descrição, CTA | Ferramenta |
| Link do pin (página de vendas + `?src=pin-<slug>`) | Ferramenta |
| Link B / Link C (variações do A/B: `-b` e `-c`) | Ferramenta (só com `--ab-hooks`) |
| Roteiro de locução | Ferramenta |
| Vídeo editado (link do Drive) | Equipe, depois de exportar |
| Data de publicação, Status → Agendado / Publicado | Claude (agendamento pelo Chrome) |
| Impressões, Taxa de visualização %, Cliques de saída, Salvamentos, Vendas/Leads, Gancho vencedor | Claude, 7 dias depois de publicar |

## Fluxo do dia a dia
1. **Gravar → pasta da semana:** `04-Conteudo Pinterest/Gravados/Semana-01` (MP4, MOV ou MKV).
2. **Rodar a ferramenta** (Eduardo): `python main.py "caminho/da/pasta" --ab-hooks`
3. **Revisar no CapCut** (~2 min por vídeo):
   - Conferir o corte, a legibilidade e se o texto não cobre a comida.
   - Exportar para `2-editados/`.
   - Não mover nem renomear o vídeo original depois de rodar a ferramenta.
4. **Revisar no Notion:** ingredientes, título, descrição e se o CTA bate com "No e-book". Subir o vídeo no Drive e colar o link.
5. **Agendar:** Claude agenda 2 a 3 pins por dia pelo Chrome e muda o Status para "Agendado".
6. **Medir (7 dias):** Claude preenche as métricas no Notion e marca o gancho vencedor.

## Quem faz o quê
| Etapa | Responsável |
|---|---|
| Gravar a receita (usando a referência só como guia) | Du e equipe |
| Rodar a ferramenta | Du |
| Revisar e exportar no CapCut | Du e equipe |
| Revisar a linha no Notion e subir o vídeo no Drive | Du e equipe |
| Agendar pins no Pinterest | Claude |
| Preencher métricas e o gancho vencedor | Claude |
| Subir o A/B pago (1 vídeo por semana) | Claude monta pausado, Du liga |
| Atualizar o estilo vencedor no prompt da IA | Du |

## Limitações
- O corte é decidido pela **fala** e pela **imagem parada**. Se o vídeo termina com um take bonito do prato em silêncio, a IA pode cortar antes. Sempre confira o final.
- Quantidades **não faladas** no vídeo são deduzidas e podem vir erradas. Sempre revise.
- Nada de promessa de emagrecimento, "low carb" ou resultado: só "fit", "leve", "sem adicionar açúcar" e "rico em proteína" quando for verdade.
- Se o CapCut atualizar e os projetos sumirem, é ajuste técnico. Não precisa refazer nada.
