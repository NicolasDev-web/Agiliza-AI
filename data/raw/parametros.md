# Parâmetros de negócio: Transportes Gocase e GoBeauté

Data de referência: segunda-feira, 02/11/2026, 08:00 (feriado de Finados). O histórico cobre os pedidos de 04/08 a 01/11/2026 (90 dias). Os portais das transportadoras foram exportados em 02/11/2026 às 06:00 (horário de Brasília).

## Operação

- Dois centros de distribuição: **CD1 em Fortaleza/CE** (atende Nordeste e Norte) e **CD2 em Extrema/MG** (atende Sudeste, Sul e Centro-Oeste). Cerca de 6% dos pedidos saem do outro CD por falta de estoque.
- Cinco transportadoras: Expressa Já, TransNorte, Rápido Sul, ViaLog e Correio Ágil. Cada uma tem seu portal, sua tabela de frete e seu formato.
- A postagem acontece no dia 1 (primeiro dia útil depois do pedido), à tarde.
- `envios.csv` é uma amostra aleatória de **1 em cada 6 envios**. `checkout_conversao.csv` tem todas as sessões e pedidos.

## Regra de prazo exibido (oficial)

- Prazo exibido = **1 dia útil de separação + SLA contratual da transportadora cotada**, em dias úteis, + margem de segurança do prefixo (se houver, ver regras_site.json).
- **Contagem:** o primeiro dia útil depois do pedido é o dia 1. A data prometida é o dia útil número (prazo exibido). Exemplo: pedido na quarta com prazo 4: quinta (1), sexta (2), segunda (3), terça (4) = data prometida.
- **Dias úteis da regra:** segunda a sexta, exceto feriados nacionais: 07/09/2026, 12/10/2026, 02/11/2026, 15/11/2026, 20/11/2026, 25/12/2026, 01/01/2027.
- O SLA contratual de cada transportadora por região está nas tabelas de frete (campo de prazo). Referência para capital e região metropolitana; interior tem +1 dia útil (Norte +2).

| Transportadora | SLA por região (capital) |
| --- | --- |
| Expressa Já | SE 3, S 5, CO 5, NE 5, N 8 |
| TransNorte | SE 4, CO 5, NE 6, N 7 |
| Rápido Sul | SE 3, S 3, CO 5, NE 7 |
| ViaLog | SE 2, S 4, CO 4, NE 6, N 8 |
| Correio Ágil | SE 4, S 5, CO 5, NE 7, N 9 |

## Feriados estaduais

As transportadoras não entregam nos feriados estaduais da UF de destino, mas a regra de prazo do site só desconta os feriados nacionais.

| Data | UF | Feriado |
| --- | --- | --- |
| 05/08/2026 | PB | Fundação do Estado da Paraíba |
| 16/09/2026 | AL | Emancipação Política de Alagoas |
| 05/10/2026 | TO | Criação do Estado do Tocantins |
| 05/10/2026 | RR | Criação do Estado de Roraima |
| 19/10/2026 | PI | Dia do Piauí |

## Frete

- O cliente paga o frete cobrado da região (regras_site.json); **frete grátis para pedidos a partir de R$ 199.00**.
- O custo do frete é o valor da tabela da transportadora vigente na data do pedido, pela faixa de CEP e de peso. O ERP grava em `custo_frete_cotado` o valor que o motor de cotação calculou.
- Política: frete cobrado nunca abaixo de 60% do custo sem aprovação do gerente.

## Custo de quebrar o prazo (por envio entregue depois da data prometida)

| Item | Valor |
| --- | --- |
| Contato de atendimento | R$ 9.00 por contato |
| Probabilidade de contato | 35% com 1 a 2 dias úteis de atraso, 60% com 3 a 5, 85% com 6 ou mais |
| Cancelamento | perde a margem de contribuição do pedido (55% do valor) + R$ 12.00 de logística reversa |
| Recompra | cliente com atraso recompra com metade da probabilidade (28% para 14%); em média 2 pedidos em 12 meses |

| Dias úteis de atraso | Probabilidade de cancelamento |
| --- | --- |
| 1 a 2 | 4% |
| 3 a 5 | 10% |
| 6 a 10 | 22% |
| Mais de 10 | 40% |

## Margem e conversão

- Margem de contribuição do produto: 55% do valor do pedido (CMV de 24% mais impostos e taxas).
- Margem de frete = frete cobrado − custo do frete.
- A conversão do checkout cai quando o prazo ou o frete exibidos ficam piores que os dos concorrentes (ver checkout_conversao.csv e concorrentes_prazos.csv). Entre 21/09 e 04/10 houve um teste A/B de frete em SP, RJ, MG, PR (metade das sessões viu frete R$ 5.00 menor).
- Metas: cumprimento de prazo de pelo menos 92% por prefixo de 3 dígitos (politicas.json).

## Mudanças regionais

- Toda mudança de prazo exibido, frete cobrado, roteamento padrão, tabela do motor de cotação ou frete grátis é proposta pelo planejador e só vale depois da aprovação do gerente (R$ 15.00 por aprovação, no máximo 12 por cenário).
- O analista escolhe a transportadora de cada envio novo sem aprovação, dentro dos limites de politicas.json.
