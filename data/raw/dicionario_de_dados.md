# Dicionário de dados: Transportes

Todos os dados são sintéticos. Clientes, CEPs, pessoas e empresas são fictícios. Cada arquivo vem de um sistema de origem diferente, com o formato daquele sistema.

## envios.csv — ERP / plataforma de e-commerce (amostra de 1 em cada 6 envios, pedidos de 04/08 a 01/11/2026)

| Campo | Descrição |
| --- | --- |
| envio_id | Identificador do envio (ENV + 7 dígitos) |
| order_id | Pedido (GCH = Gocase, GBH = GoBeauté, + 6 dígitos) |
| marca | Gocase ou marca GoBeauté |
| cd_origem | CD1 (Fortaleza/CE) ou CD2 (Extrema/MG) |
| data_pedido | Data e hora do pedido (horário de Brasília) |
| cep | CEP de destino como digitado (pode ter hífen ou ter perdido o zero à esquerda) |
| cidade, uf | Destino |
| peso_g | Peso do pacote em gramas |
| valor_pedido | Valor dos produtos (R$) |
| transportadora, servico | Transportadora e serviço contratados |
| codigo_rastreio | Código de rastreio (vazio quando a etiqueta não voltou para o ERP) |
| prazo_exibido_dias_uteis | Prazo mostrado no checkout (dias úteis) |
| data_prometida | Data prometida ao cliente, pela regra de parametros.md |
| frete_cobrado_cliente | Frete pago pelo cliente (0 no frete grátis) |
| custo_frete_cotado | Custo do frete calculado pelo motor de cotação do ERP |

O ERP **não** tem data de entrega. Ela está nos portais das transportadoras.

## portal_expressa_ja.csv — portal Expressa Já (exportação CSV)

codigo_rastreio, data_hora (ISO, horário local do evento), evento (texto em maiúsculas), cidade, uf.

## portal_transnorte.json — portal TransNorte Online (exportação JSON)

`remessas[]`: rastreio, destino {cidade, uf}, historico[] {quando (AAAA-MM-DD HH:MM, horário local), status (código em texto), local}, observacao (opcional, texto livre do portal).

## portal_rapido_sul.csv — portal Rápido Sul (CSV com ponto e vírgula)

rastreio; data_hora (DD/MM/AAAA HH:MM, horário local); ocorrencia (texto); cidade_uf.

## portal_vialog.csv e portal_vialog_codigos.csv — portal ViaLog

awb, timestamp (horário local), cod_status (código numérico), filial. A descrição dos códigos está em portal_vialog_codigos.csv.

## portal_correio_agil.csv — portal Correio Ágil

objeto, data_hora_utc (**UTC**, sufixo Z), descricao, unidade.

Em todos os portais: eventos podem vir duplicados e alguns códigos vêm em minúsculas ou com espaço.

## Tabelas de frete — sistema comercial de cada transportadora

| Arquivo | Formato |
| --- | --- |
| tabela_frete_expressa_ja.csv | faixa de CEP de 8 dígitos (cep_inicio, cep_fim) x faixa de peso (peso_min_g, peso_max_g), valor_frete, prazo_dias_uteis, vigente_desde |
| tabela_frete_transnorte.csv | uf, localidade (CAPITAL inclui a região metropolitana, ou INTERIOR), faixa_peso em texto, valor em texto "R$ 0,00", prazo_dias_uteis, inicio_vigencia (DD/MM/AAAA) |
| tabela_frete_rapido_sul.csv | ponto e vírgula, vírgula decimal; faixa de CEP de 5 dígitos, uma coluna por faixa de peso, prazo_dias_uteis, vigencia em texto |
| tabela_frete_vialog.csv | cep3 (prefixo de 3 dígitos), peso_ate_g, valor, prazo_dias_uteis, vigencia_inicio, vigencia_fim |
| tabela_frete_correio_agil.json | versões com vigência; preços por região > UF > capital/interior, uma posição por faixa de peso |

Faixas de peso: até 300 g, 301 g a 1 kg, 1 a 2 kg, 2 a 5 kg, 5 a 10 kg.

## cabecas_cep.csv — base de CEP

prefixo_cep5, prefixo_cep3, cidade, uf, localidade (capital, metropolitana ou interior).

## concorrentes_prazos.csv — robô de coleta no checkout dos concorrentes (semanal, painel de CEPs)

data_coleta, concorrente, cep, uf, cidade, produto_referencia, estoque_exibido (disponivel ou esgotado), prazo_dias_uteis, frete, frete_gratis_acima_de.

## checkout_conversao.csv — analytics do site (agregado diário)

data, prefixo_cep3, uf, prazo_exibido_dias_uteis, frete_exibido (0 = frete grátis), sessoes_checkout (sessões que chegaram ao cálculo de frete), pedidos.

## regras_site.json — configuração atual do site

Regra de prazo, frete cobrado por UF, frete grátis, roteamento padrão por UF e localidade, margens de segurança, prazo e frete por prefixo de 3 dígitos, histórico de alterações.

## politicas.json, ferramentas.json, parametros.md

Limites de cada papel, metas e custos; catálogo de ferramentas com papéis; parâmetros de negócio.

## Tabelas complementares dos sistemas de logística

Exportações dos sistemas internos (ERP, WMS, motor de frete, financeiro e torre de controle). Mesma amostra de envios.csv (1 em cada 6). Datas e horas em horário de Brasília. Ocorrências e chamados começam em 03/09/2026 (início da integração com os portais).

| Arquivo | Sistema | Conteúdo |
| --- | --- | --- |
| envios.csv (colunas novas no fim) | ERP | sku_principal, qtd_itens, qtd_volumes, nota_fiscal (vazia se ainda não faturado), data_postagem (data da coleta; vazia se ainda não coletado) |
| itens_envio.csv | ERP | envio_id, order_id, linha, sku, quantidade, valor_total_item (soma dos itens = valor_pedido) |
| envios_expedicao.csv | WMS | NF e chave da NF-e, separação, coleta (= evento de postagem no portal, quando há), embalagem, volumes, dimensões, peso cubado, valor declarado, endereço resumido |
| produtos.csv | Cadastro de produtos | sku, ean, nome, marca, categoria, peso e dimensões da unidade, preço de lista |
| embalagens.csv | WMS | embalagens padrão com peso cubado (fator 6000 cm³/kg) |
| cds.csv | Cadastro | centros de distribuição, corte de pedidos e janela de coleta |
| transportadoras.csv | Contratos | CNPJ, contrato e vigência, SLA, multa por atraso, taxas, seguro, faturamento, contato e portal |
| transportadoras_cobertura_sla.csv | Contratos | quem atende cada UF e localidade e o SLA contratual em dias úteis |
| cotacoes_frete.csv | Motor de cotação do site | uma linha por envio e transportadora candidata: valor_cotado pela tabela carregada no motor, prazo da transportadora, prazo que seria exibido, selecionada (1 = transportadora usada) |
| ctes.csv | Financeiro (CT-e recebidos) | CT-e normal por envio coletado e complementares (reentrega, devolução); peso aferido, cubado e taxado; frete pela tabela vigente na data do pedido; fatura |
| faturas_frete.csv | Financeiro (contas a pagar) | faturas quinzenais por transportadora, abatimento de indenizações, vencimento e pagamento |
| ocorrencias_entrega.csv | Torre de controle | tentativas sem sucesso, devoluções e extravios (dos portais) e avarias (SAC) |
| chamados_transportadoras.csv | SAC das transportadoras | chamados abertos pelo time: motivo, abertura, resposta, status |
| indenizacoes.csv | SAC das transportadoras | pedidos de indenização por extravio e avaria, decisão e fatura de abatimento |
| feriados.csv | Calendário | feriados nacionais (descontados pela regra do site) e estaduais (só as transportadoras param) |
| historico_regras_site.csv | Motor de frete do site | versões de transportadora padrão, prazo exibido e frete cobrado por prefixo ao longo do tempo |
| concorrentes.csv | Coleta de concorrentes | concorrentes monitorados, produtos e método de coleta |
