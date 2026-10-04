# Automação de Receitas → CapCut: o que é e como vamos usar

## Resumo
Criamos uma ferramenta que transforma uma pasta de vídeos de receita brutos em **projetos do CapCut prontos para exportar**: o vídeo já vem cortado e com os textos na tela. Junto com cada vídeo sai um arquivo com **legenda, ingredientes, hashtags e roteiro de locução**. Edição que levava de 15 a 20 minutos por vídeo vira só revisar e exportar.

## O que a ferramenta faz sozinha (para cada vídeo da pasta)
1. **Ouve o vídeo e transcreve a fala**, direto no computador.
2. **Encontra as sobras do final**: imagem parada, silêncio, "tchau", câmera sendo desligada.
3. **A IA (Claude) analisa a receita** e entrega:
   - o **ponto de corte** final do vídeo;
   - **3 opções de gancho** (o texto que aparece nos primeiros 3 segundos para segurar quem está rolando o feed);
   - **1 CTA** para o final (ex.: "Salva pra fazer no fim de semana");
   - **legenda pronta** com ingredientes e hashtags;
   - **roteiro de locução** de até 45 palavras, para usar depois com voz de IA.
4. **Cria o projeto no CapCut** com o vídeo cortado, o gancho no início (0 a 3s) e o CTA nos últimos 3s.
5. **Salva um relatório** ao lado do vídeo original: `nome-do-video_video_analise.md`.

## Modo teste A/B (o mais importante para os anúncios)
Com a opção `--ab-hooks`, cada vídeo vira **3 projetos no CapCut**, iguais em tudo, menos no gancho:
- `receita_auto_A` → gancho que a IA recomendou como o melhor
- `receita_auto_B` → segunda opção
- `receita_auto_C` → terceira opção

Os 3 ganchos sempre seguem estilos diferentes: **curiosidade**, **benefício** e **erro comum/polêmica**. O objetivo é descobrir com dados qual estilo prende mais o nosso público, em vez de escolher no achismo.

## Como vamos usar no dia a dia

**1. Gravação → pasta**
Os vídeos brutos vão para uma pasta da semana (ex.: `Receitas/Semana-01`). Formatos aceitos: MP4, MOV e MKV.

**2. Rodar a ferramenta** (Eduardo roda no computador)
```
python main.py "caminho/da/pasta" --ab-hooks
```

**3. Revisar no CapCut** (o passo humano, ~2 min por vídeo)
- Abrir o CapCut. Os projetos aparecem como `_auto_A`, `_B` e `_C`.
- Conferir: o corte ficou bom? O texto está legível e não cobre a comida?
- Ajustar fonte e posição se precisar e **exportar**.
- **Não mover nem renomear o vídeo original** depois de rodar a ferramenta, senão o CapCut perde o arquivo.

**4. Revisar o relatório (`_video_analise.md`)**
- Conferir a legenda e os ingredientes. A IA pode errar quantidades se elas não forem faladas no vídeo.
- Copiar a legenda e as hashtags na hora de postar.

**5. Subir os anúncios no Meta Ads**
- As 3 variações (A, B, C) do mesmo vídeo vão **no mesmo conjunto de anúncios**, com o mesmo público e o mesmo orçamento. Assim só o gancho muda.
- Verba mínima: cerca de **R$30 por variação**. Com menos que isso o resultado é sorte, não dado.

**6. Anotar os resultados (depois de 48 a 72h)**
O relatório de cada vídeo tem uma tabela pronta:

| Var. | Gancho | Hook rate (3s) | CTR | CPM |
|---|---|---|---|---|

- **Hook rate** = visualizações de 3s ÷ impressões. É a métrica principal: mostra se o gancho prendeu.
- **CTR** desempata.

**7. Definir o padrão vencedor**
Não escolhemos vencedor vídeo a vídeo. Depois de **5 a 10 vídeos testados**, vemos **qual estilo ganhou mais vezes** (curiosidade, benefício ou erro comum). Esse estilo vira regra para a IA, e os próximos ganchos já saem nesse padrão.

## Quem faz o quê
| Etapa | Responsável |
|---|---|
| Gravar e colocar os vídeos na pasta | Equipe |
| Rodar a ferramenta | Eduardo |
| Revisar e exportar no CapCut | Equipe |
| Revisar legenda/ingredientes e postar | Equipe |
| Subir os anúncios A/B | Eduardo |
| Preencher a tabela de resultados | Equipe |
| Atualizar o estilo vencedor na IA | Eduardo |

## Limitações (para não ter surpresa)
- A IA decide o corte pela **fala** e pela **imagem parada**. Se o vídeo termina com um take bonito do prato em silêncio, ela pode cortar antes. Sempre confira o final.
- Ingredientes e quantidades que **não foram falados** no vídeo são deduzidos pela IA e podem vir errados. Sempre revise.
- Se o CapCut atualizar e os projetos pararem de aparecer, avise o Eduardo: é ajuste técnico, não precisa refazer nada.

## Próximos passos planejados
- Legendas automáticas da fala já colocadas no vídeo (aumenta a retenção de quem assiste sem som).
- Locução com voz de IA a partir do roteiro gerado.
- Resultados do A/B registrados no Notion como calendário de postagem.
