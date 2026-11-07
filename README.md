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

`python servidor.py` abre **http://localhost:8000**, uma tela de entrada com dois usuários (veja
"Dois usuários" abaixo). A tela do analista é o "Agente ao vivo": à esquerda uma conversa
estilo WhatsApp, à direita a *mesa do agente*. A cada pergunta o agente decide quais ferramentas usar
e a interface mostra, na hora, cada passo: a ferramenta chamada, o que voltou, a rota no mapa e o
pedido de aprovação que chega para o gerente. Exemplos:

- "Onde resolvemos mais problemas?" cruza chamados do SAC, ocorrências e extravios por transportadora, estado e motivo.
- "Qual a melhor rota para os envios novos de SP?" compara as transportadoras de cada envio ainda não coletado
  (frete + custo esperado de atraso, pelo histórico real da região) e **troca sozinho** dentro do limite de 40% por estado/dia.
- "Qual prazo do site precisa mudar?" mede, compara com concorrentes, escreve a proposta com evidência e **leva à gerente**.
- "A Marina já respondeu?" o agente consulta a fila e conta o que ela decidiu.
- "Aprova o prazo por mim" o sistema **recusa**: aprovar é do gerente.

As 18 ferramentas (`src/transporte/agente/ferramentas.py`) seguem o catálogo do desafio. **O papel é
conferido no código**, não só no prompt: se o modelo tentar aprovar uma proposta, a ferramenta recusa.

### Dois usuários, duas telas

Hackathon: **sem senha**. A tela de entrada (`/`) tem dois cartões; a escolha fica na aba, então dá para abrir
os dois lado a lado (ou `agente.html?como=lucas` e `gerente.html?como=marina`).

| Usuário | Papel (`politicas.csv`) | Tela |
| --- | --- | --- |
| Lucas Ferreira | `analista_logistica` | conversa com o agente, vê a melhor rota no mapa, acompanha o que a gerente respondeu |
| Marina Duarte | `gerente` | fila de aprovação, placar, histórico e **financeiro** |

Como o ciclo fecha, ao vivo (SSE por usuário):

1. O agente monta a proposta e chama `solicitar_aprovacao`; o pedido cai na fila da Marina na hora.
2. Ela **aprova, ajusta** (muda o prazo e aprova) **ou recusa**, com comentário.
3. A decisão volta para a tela do Lucas, para a conversa e para o agente (próxima resposta).
4. Prazo aprovado **passa a valer dentro da demonstração**: o painel mostra e o agente usa nas consultas. Nada vai ao ERP.
5. Sempre que o agente **troca rotas**, a Marina recebe um alerta financeiro: quanto o frete sobe ou cai,
   quanto de atraso se evita e o saldo, envio a envio. `acionar_pessoa("financeiro")` também cai ali.

As regras valem no servidor, não só na tela (`src/transporte/estado.py`, `tests/test_estado.py`): só o gerente decide,
nunca a própria proposta, no máximo 12 aprovações por cenário (R$ 15 cada pedido), prazo inteiro e de no mínimo 2 dias úteis.
O estado fica em `data/processed/estado.db` (gravável, ignorado pelo git); a base do desafio segue só de leitura.
O botão "Reiniciar demonstração" na tela da gerente zera tudo para repetir a apresentação.

### Base de dados e geografia real

Os dados ficam numa base **SQLite** (`data/processed/transporte.db`, 17 tabelas com índice, construída
em ~3 s por `python scripts/02_base_de_dados.py`; o servidor monta sozinho se faltar). O agente consulta
com SQL e só o **resumo** chega ao modelo, então o gasto de tokens é mínimo. O servidor sobe em menos de
meio segundo e a base é aberta só para leitura.

As coordenadas das cidades vêm dos **municípios do IBGE** (`data/ref/`, dados reais). Os 127 destinos casam
todos. Com elas o mapa da rota vai do CD até a **cidade** do pedido, com a distância em linha reta, e o
painel mostra cada prefixo de CEP como um ponto na sua cidade. Pedidos, prazos e transportadoras seguem
**fictícios**, e a interface avisa a origem de cada coisa.

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
data/ref/            municípios do IBGE (coordenadas reais)
data/processed/      saídas da parte 1 e a base SQLite (transporte.db, gerada)
src/transporte/      calendario, portais, entregas, desempenho, concorrentes, propostas
src/transporte/agente/  ferramentas, roteamento, llm (proxy), loop (eventos), simulado, prompt
servidor.py          servidor: conversa por SSE, eventos por usuário, aprovações, arquivos do painel
src/transporte/estado.py   usuários, fila de aprovação, alertas financeiros, tempo real (estado.db)
src/transporte/base.py, geo.py   base SQLite e geografia (coordenadas, distâncias)
scripts/             01_processar.py, 02_base_de_dados.py
dashboard/           login.html, agente.html (analista), gerente.html, index.html (painel), usuario.js, *.css, data.js (gerado)
tests/               testes do calendário e dos dados reais
```

## O que os dados mostram (período 03/09 a 02/11/2026)

Os portais só têm eventos a partir de 03/09; pedidos anteriores e ainda não coletados ficam de fora.
Os números exatos estão em `data/processed/qualidade_dados.json` e no painel.

## Limites desta parte

- O fundo do mapa é por estado (não há malha de prefixos de CEP); os prefixos aparecem como pontos nas cidades.
- A distância é em linha reta, não por estrada.
- O impacto em R$ conta só o custo de atraso. O efeito de mostrar um prazo menor sobre a conversão
  (`checkout_conversao.csv`) fica para a próxima parte.
- Feriados estaduais ainda não entram na conta do prazo real das transportadoras.
