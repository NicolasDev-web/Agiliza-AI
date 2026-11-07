# Agiliza AI: prazo que vende e que cumpre

> Projeto do desafio de Transportes (GoHacks Talent). O produto se chama **Agiliza AI**.

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

`python servidor.py` abre **http://localhost:8000**, o login (veja abaixo). O modo apresentação ("Agente trabalhando") tem à esquerda uma conversa
estilo WhatsApp e à direita a *mesa do agente*. A cada pergunta o agente decide quais ferramentas usar
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

### Login, duas telas e o agente no canto

`/` abre o **login com e-mail e senha** (sessão por cookie no servidor, senha guardada com hash). Contas de demonstração, fictícias:

| Quem | Papel (`politicas.csv`) | E-mail | Senha |
| --- | --- | --- | --- |
| Lucas Ferreira | `analista_logistica` | lucas.ferreira@agiliza.ai | Agiliza@Lucas26 |
| Marina Duarte | `gerente` | marina.duarte@agiliza.ai | Agiliza@Marina26 |

Cada **aba** tem a sua própria sessão (`dashboard/sessao-aba.js`): dá para entrar como o Lucas numa aba e como a Marina em outra, no mesmo navegador. Abas abertas por link (sem passar pelo login) usam o cookie do último que entrou.

- **Analista** (`analista.html`): só o essencial. A melhor rota no mapa, os pedidos dele para a Marina com o status ao vivo e o WhatsApp que ele recebeu. "Agente trabalhando" mostra a linha do tempo completa (modo apresentação).
- **Gerente** (`gerente.html`): três números, a fila de decisões (frase grande, prazo de hoje e proposto, números recolhidos), o histórico e o financeiro das rotas trocadas, recolhido numa linha.
- **Agente no canto** (todas as telas): conversa por texto ou **voz**. Para o analista é o planejador completo; para a gerente é um agente de **consulta**, que explica ("por que Marabá?") mas não propõe, não troca rota e não decide por ela (isso vale no código, papel `consulta`).

Como o ciclo fecha, ao vivo (SSE por usuário):

1. O analista pede (escrevendo ou falando); o agente monta a proposta e chama `solicitar_aprovacao`. O pedido cai na fila da Marina na hora.
2. Ela **aprova, ajusta** (muda o prazo e aprova) **ou recusa**, com um motivo opcional.
3. O agente escreve a mensagem de decisão **com as palavras da Marina** (com a IA do evento; sem token, um modelo de frase) e gera um **cartão de imagem** (`src/transporte/cartao.py`).
4. A mensagem e o cartão chegam ao WhatsApp do analista e aparecem na tela dele. A decisão também volta para a conversa do agente.
5. Prazo aprovado **passa a valer dentro da demonstração**: o painel mostra e o agente usa nas consultas. Nada vai ao ERP.
6. Sempre que o agente **troca rotas**, a Marina recebe o alerta financeiro (frete, atraso evitado, saldo). `acionar_pessoa("financeiro")` também cai ali.

O motivo escrito pela gerente é tratado como **dado, nunca como ordem** (no prompt de reescrita e no aviso ao agente).
As regras valem no servidor (`src/transporte/estado.py`, `tests/test_estado.py`): só o gerente decide, nunca a própria proposta, no máximo 12 aprovações por cenário (R$ 15 cada pedido), prazo inteiro de no mínimo 2 dias úteis. O estado fica em `data/processed/estado.db` (gravável, ignorado pelo git); a base do desafio segue só de leitura. "Reiniciar demonstração" na tela da gerente zera tudo.

### Visão geral com filtros e barra de perguntas

No pé das telas do analista e da gerente há a "Visão geral das entregas" (recolhida) e uma barra de perguntas fixa embaixo. Escreva ou fale, por exemplo "Mostre as transportadoras do Pará, das que mais atrasam": os filtros se ajustam e o gráfico, os números e a frase de cima mudam. Os mesmos filtros (mostrar por, estado, transportadora, o que medir, ordem, quantos) podem ser mexidos à mão.

A pergunta vira um filtro pequeno e fechado (`src/transporte/analise.py`); o navegador só desenha o que cabe nele, então nada inventado chega à tela. Sem token de IA, um leitor de frases por palavra-chave resolve (custo zero). Com a IA do evento, uma chamada curta (~550 tokens de entrada, ~60 de saída) devolve o mesmo filtro, validado do mesmo jeito; se ela falhar, cai nas palavras-chave. O texto sob o gráfico sai de modelos de frase com os números do painel (`dashboard/analise.js`), sem chamar IA.

### WhatsApp por QR code (sem API da Meta)

A Marina conecta o WhatsApp dela lendo um QR code, uma vez, na tela dela ("WhatsApp do Lucas"). Dali em diante cada decisão sai pelo número dela para o número do analista, com o texto escrito pelo agente e o cartão em imagem.

1. Uma vez: `cd whatsapp && npm install` (precisa de Node 18+).
2. No `.env`: `WHATSAPP_DESTINO=55DDDNUMERO` (o número do Lucas, só dígitos). Nunca vai para o repositório.
3. `python servidor.py` liga a ponte sozinho. Entre como Marina, abra a tela de decisões, e no celular: WhatsApp > Aparelhos conectados > Conectar um aparelho.

Estados da mensagem: **enviada** (ponte conectada), **pendente** (ponte ligada, QR ainda não lido: sai sozinha quando a Marina conectar), **prévia** (sem ponte: a tela do Lucas mostra a mensagem como o WhatsApp mostraria). Qualquer falha vira aviso e a demonstração segue.

Para ensaiar sem celular: `WHATSAPP_SIMULAR=1 python servidor.py` mostra um QR de mentira; `curl -X POST localhost:8765/simular/escanear` "conecta".

Atenção: é o WhatsApp Web (biblioteca Baileys), não a via oficial. Serve para a demonstração; use um número de teste, porque o WhatsApp pode restringir números usados assim. A sessão fica em `whatsapp/sessao/` (fora do git).

### Voz

O microfone do agente usa o reconhecimento de voz do navegador (pt-BR, Chrome/Edge, sem gastar token). Em navegador sem isso, grava o áudio e o servidor transcreve por `/v1/audio/transcriptions` do proxy do evento (`AI_PROXY_MODELO_AUDIO`, padrão `whisper-1`), **se o proxy tiver um modelo de áudio**: abra `/api/saude` e veja a lista. O botão de alto-falante faz o agente ler as respostas em voz alta (versão curta, sem lista).

O que a voz entende errado é consertado antes de o agente ler: o reconhecedor devolve até 3 alternativas, o servidor fica com a que mais parece logística e troca trechos quase iguais a nomes conhecidos ("trans norte" → TransNorte, "maraba" → Marabá, "seis dias" → 6 dias). A tela mostra "entendi: …" para a pessoa conferir. Código em `src/transporte/agente/entender.py`.

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

### Se a tela ainda for a antiga

O sintoma é abrir `http://localhost:8000` e ver só o painel ou o chat antigo. Quase sempre é o **servidor velho ainda rodando** na porta 8000.

1. Abra `http://localhost:8000/api/saude`. A versão nova mostra `"app": "Agiliza AI"` e a versão do commit. Se der erro 404 ou faltar isso, é o servidor antigo.
2. Feche o antigo (Windows: `netstat -ano | findstr :8000` e `taskkill /PID <número> /F`; Mac/Linux: `lsof -i :8000` e `kill <pid>`), rode `git pull` e `python servidor.py`.
3. O terminal agora imprime o endereço de entrada e avisa se a porta estava ocupada (e em qual porta subiu).

Telas: `/login.html` (entrada), `/analista.html`, `/gerente.html`, `/agente.html` (modo apresentação) e `/index.html` (painel de dados).

## Estrutura

```
data/raw/            dados fictícios do desafio (CSV) e os dicionários
data/ref/            municípios do IBGE (coordenadas reais)
data/processed/      saídas da parte 1 e a base SQLite (transporte.db, gerada)
src/transporte/      calendario, portais, entregas, desempenho, concorrentes, propostas
src/transporte/agente/  ferramentas, roteamento, llm (proxy), loop (eventos), simulado, prompt
servidor.py          servidor: conversa por SSE, eventos por usuário, aprovações, arquivos do painel
src/transporte/estado.py   login, fila de aprovação, alertas financeiros, tempo real (estado.db)
src/transporte/cartao.py, whatsapp.py   cartão de imagem e envio da decisão ao analista (pela ponte em whatsapp/)
src/transporte/analise.py              pergunta -> filtro dos gráficos
src/transporte/dicas.py                dicas do agente para o analista
src/transporte/agente/entender.py     correção do que a voz entendeu e versão falada da resposta
src/transporte/base.py, geo.py   base SQLite e geografia (coordenadas, distâncias)
scripts/             01_processar.py, 02_base_de_dados.py
dashboard/           login, analista, gerente, agente (modo apresentação), index (painel), widget.js (agente no canto), data.js (gerado)
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
