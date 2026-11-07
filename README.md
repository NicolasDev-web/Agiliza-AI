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
| 3 | Escolha da transportadora de cada envio novo | próxima parte |
| 6 | Frete por região | próxima parte |
| 7 | Alertas e reação a problemas, no Slack/Telegram | próxima parte |

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

## Como rodar

```sh
python -m venv .venv && . .venv/bin/activate      # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/01_processar.py                    # gera data/processed e dashboard/data.js
python -m pytest                                  # testes
python -m http.server 8000 --directory dashboard  # abra http://localhost:8000
```

O painel precisa de internet só para a fonte e o Leaflet. O token do proxy de IA do evento
(próximas partes) fica em `.env`, que está no `.gitignore`. Copie `.env.example` e **nunca
publique o token**.

## Estrutura

```
data/raw/            dados fictícios do desafio (CSV) e os dicionários
data/processed/      saídas da parte 1 (tabelas por transportadora, UF, prefixo e propostas)
src/transporte/      calendario, portais, entregas, desempenho, concorrentes, propostas
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
