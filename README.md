# Transporte: prazo que vende e que cumpre

Projeto do desafio **Transportes** (GoHacks Talent, Agentes de IA). A ideia é um colega de logística
que lê os portais das transportadoras, mede quem entrega bem em cada região, compara com os
concorrentes e **propõe o prazo do site**. Quando a decisão não é dele, ele chama o gerente.

A interface segue o mesmo desenho do dashboard de Bairros de Fortaleza: azul cobalto, fonte Geist,
mapa por regiões, rampa de uma cor só e pixels como textura.

## Visão 360° (frentes)

| # | Frente | Estado |
| --- | --- | --- |
| 1 | Coletor de portais: 5 portais, 5 formatos, um só | **feito (parte 1)** |
| 2 | Desempenho por transportadora e prefixo de CEP | **feito (parte 1)** |
| 4 | Prazo do site: o menor prazo que ainda cumpre a meta | **feito (parte 1)** |
| 5 | Posição frente aos concorrentes | **feito (parte 1)**, em modo leitura |
| 3 | Melhor rota de cada envio novo (frete + custo esperado de atraso) | **feito (parte 2)** |
| 6 | Frete por região | próxima parte |
| 7 | Alertas e reação a problemas, no Slack/Telegram | próxima parte |
| A | **Agente ao vivo**: conversa estilo WhatsApp, ferramentas rodando em tempo real, fila do gerente | **feito (parte 2)** |

## Primeira parte: o que ela entrega

1. **Junta os portais.** Normaliza Expressa Já, TransNorte, Rápido Sul, ViaLog e Correio Ágil
   (CSV, ponto e vírgula, códigos numéricos, horário UTC) e tira eventos repetidos.
2. **Descobre quando cada pedido foi entregue.** Os pedidos do ERP não têm data de entrega; ela
   vem dos portais. CEPs digitados com hífen ou sem o zero à esquerda são normalizados.
3. **Mede o cumprimento** por transportadora e por prefixo de 3 dígitos, contando dias úteis do
   mesmo jeito que o site (dia 1 = primeiro dia útil depois do pedido, feriados nacionais fora).
4. **Propõe o prazo do site** por prefixo: o prazo que cobre 9 em cada 10 entregas, nunca abaixo
   de 2 dias úteis. Estima o custo de atraso evitado com as regras de `parametros.md`.
5. **Compara com os concorrentes** (melhor, igual, um pouco pior, muito pior), ignorando produto
   esgotado, que mostra "1 dia" sem ser prazo real.
6. **Mostra tudo** num painel com mapa, ranking de transportadoras, tabela de propostas e a
   mensagem que o agente mandaria ao gerente.

### Regras de autonomia (de `politicas.csv`)

- O agente **faz sozinho**: ler portais, medir desempenho, escolher a transportadora de cada envio
  novo (até 40% dos envios de um estado por dia fora da padrão), abrir chamado de um envio.
- **Toda mudança regional de prazo exibido é proposta e precisa do gerente.** Por isso cada linha
  de `propostas_prazo.csv` traz `requer_aprovacao`. Os botões do painel são só demonstração.
- Texto escrito em portal, tabela ou mensagem de terceiros é **dado, nunca instrução**. O código
  só reconhece textos de evento conhecidos; o resto vai para o relatório de qualidade.

## Parte 2: o agente trabalhando em tempo real

`python servidor.py` abre **http://localhost:8000**, a página "Agente ao vivo": à esquerda uma conversa
estilo WhatsApp, à direita a *mesa do agente*. A cada pergunta o agente decide quais ferramentas usar
e a interface mostra, na hora, cada passo: a ferramenta chamada, o que voltou, a rota no mapa e o
pedido de aprovação que chega para o gerente. Exemplos:

- "Onde resolvemos mais problemas?" cruza chamados do SAC, ocorrências e extravios por transportadora, estado e motivo.
- "Qual a melhor rota para os envios novos de SP?" compara as transportadoras de cada envio ainda não coletado
  (frete + custo esperado de atraso, pelo histórico real da região) e **troca sozinho** dentro do limite de 40% por estado/dia.
- "Como está o prazo de Belo Horizonte?" mede, compara com concorrentes, escreve a proposta com evidência e **leva à gerente**.
- "Aprova o prazo por mim" o sistema **recusa**: aprovar é do gerente.

As 17 ferramentas (`src/transporte/agente/ferramentas.py`) seguem o catálogo do desafio. **O papel é
conferido no código**, não só no prompt: se o modelo tentar aprovar uma proposta, a ferramenta recusa.

### Com a IA do evento

Copie `.env.example` para `.env` e ponha o token. O agente fala com o proxy no formato OpenAI
(`/v1/chat/completions`, com tool calling) ou Anthropic (`AI_PROXY_FORMATO=anthropic`). A página mostra
em cima se a IA está conectada. Abra `/api/saude` para ver os modelos que o proxy lista e escolher em
`AI_PROXY_MODELO`.

**Sem token** (ou se a API cair no meio da demonstração) entra um roteiro local que usa as *mesmas*
ferramentas e emite os *mesmos* eventos, e a interface avisa que não é IA. Assim a demo não quebra.

> Esta parte foi testada com uma API de mentira no formato OpenAI (`tests/test_agente.py`), porque o
> ambiente de desenvolvimento não alcançava o proxy do evento. Falta um teste com o token real.

## Como rodar

```sh
python -m venv .venv && . .venv/bin/activate      # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/01_processar.py                    # gera data/processed e dashboard/data.js
python -m pytest                                  # testes
python servidor.py                                # agente ao vivo + painel: http://localhost:8000
                                                  # (o painel estático fica em /index.html)
```

O painel precisa de internet só para a fonte e o Leaflet. O token do proxy de IA do evento
(próximas partes) fica em `.env`, que está no `.gitignore`. Copie `.env.example` e **nunca
publique o token**.

## Estrutura

```
data/raw/            dados fictícios do desafio (CSV) e os dicionários
data/processed/      saídas da parte 1 (tabelas por transportadora, UF, prefixo e propostas)
src/transporte/      calendario, portais, entregas, desempenho, concorrentes, propostas
src/transporte/agente/  ferramentas, roteamento, llm (proxy), loop (eventos), simulado, prompt
servidor.py          servidor do agente (conversa por SSE) e dos arquivos do painel
scripts/             01_processar.py
dashboard/           index.html, styles.css, app.js, data.js (gerado), ufs.js (malha dos estados)
tests/               testes do calendário e dos dados reais
```

## O que os dados mostram (período 03/09 a 02/11/2026)

Os portais só têm eventos a partir de 03/09; pedidos anteriores e ainda não coletados ficam de fora.
Os números exatos estão em `data/processed/qualidade_dados.json` e no painel.

## Limites desta parte

- O mapa é por estado. Os dados não trazem a malha dos prefixos de CEP; a tabela cobre os 148 prefixos.
- O impacto em R$ conta só o custo de atraso. O efeito de mostrar um prazo menor sobre a conversão
  (`checkout_conversao.csv`) fica para a próxima parte.
- Feriados estaduais ainda não entram na conta do prazo real das transportadoras.
