# Política Comercial — Regras de Negócio Vigentes

Cada seção abaixo é uma regra completa e autônoma. Este arquivo é a fonte única
das regras do RAG: edite aqui e rode `python sync_regras_to_chroma.py`.
Fórmulas e cálculos (margem, positivação, ticket médio) NÃO ficam aqui — vivem
na camada semântica (Cube.js/SQL), que é a fonte de verdade numérica.

## Alçada de desconto

O desconto é medido sobre o preço de tabela. Alçadas: o consultor pode conceder
até 10% por conta própria; entre 10% e 20% é necessária aprovação do supervisor
do departamento; acima de 20% somente a diretoria comercial pode autorizar.
Nunca prometa ao cliente um desconto acima da sua alçada antes da aprovação
formal. Pedidos com desconto fora de alçada são bloqueados no faturamento.

## Margem mínima por pedido

Independentemente da alçada de desconto, nenhum pedido deve ser fechado com
margem inferior a 12% sobre o preço de tabela sem aprovação da diretoria.
Se o desconto solicitado levar a margem abaixo desse piso, a orientação é
renegociar mix ou volume em vez de preço unitário.

## Cliente inadimplente — bloqueio de venda

Cliente com status de inadimplência ativa não pode receber novos pedidos.
A liberação exige quitação dos títulos em atraso ou aprovação expressa da
diretoria comercial. Antes de qualquer proposta, consulte a situação de
crédito do cliente; se houver inadimplência, informe o valor em atraso e os
dias de atraso, e oriente o encaminhamento à cobrança.

## Cliente em análise de crédito

Cliente sinalizado como sujeito a análise de crédito só pode comprar dentro do
limite disponível (limite de crédito menos títulos em aberto e em atraso).
Não confirme pedidos que ultrapassem o saldo disponível; nesses casos o pedido
segue para o comitê de crédito antes do faturamento.

## Prazo de pagamento por classificação do cliente

O prazo máximo de pagamento acompanha o ranking da carteira: clientes OURO
podem comprar com até 45 dias; PRATA até 30 dias; BRONZE até 21 dias.
Clientes RED ou sem histórico recente compram somente à vista, até
reconstruírem três meses consecutivos de compras pagas em dia.

## Venda ao setor público — teto PMVG

Vendas ao canal público (órgãos e entes governamentais) não podem exceder o
PMVG (Preço Máximo de Venda ao Governo) definido pela CMED para cada
apresentação. Toda venda pública ocorre mediante processo licitatório ou
empenho; não existe venda direta informal ao setor público. Ao cotar para o
canal público, confirme que o preço proposto respeita o teto vigente.

## Antibióticos — retenção de receita

A venda de antibióticos exige receituário com retenção de receita pela
farmácia, conforme RDC 471/2021 da ANVISA. Ao atender farmácias clientes,
oriente que a dispensação exige escrituração; não é papel da distribuidora
vender antibióticos a estabelecimentos sem responsável técnico ativo.

## Medicamentos controlados — Portaria 344/98

Medicamentos sujeitos a controle especial (Portaria 344/98) só podem ser
vendidos a clientes com autorização sanitária válida (AFE/AE) e escrituração
no SNGPC em dia. Antes de incluir um item controlado em proposta, confirme a
regularidade documental do cliente. Venda de controlados a cliente sem
autorização é vedada sem exceção.

## Produtos termolábeis — cadeia fria

Produtos termolábeis (insulinas, vacinas, biológicos) exigem transporte
refrigerado entre 2°C e 8°C e possuem prazo e custo logístico diferenciados.
Não prometa prazo de entrega padrão para itens de cadeia fria; confirme a
disponibilidade de rota refrigerada para a região do cliente antes de fechar.

## Política de devolução

Devoluções são aceitas em até 7 dias corridos da emissão da nota fiscal,
mediante motivo registrado (avaria, divergência de pedido ou erro de
faturamento). A devolução estorna o faturamento e pode reverter a positivação
do cliente no período. Fora do prazo, a devolução exige aprovação da
diretoria e análise do estado do produto.

## Estoque antes de qualquer recomendação

Nunca recomende ou prometa um produto sem confirmar estoque disponível.
Se o item estiver zerado, ofereça alternativas do mesmo grupo (produto-pai),
priorizando o mesmo princípio ativo. Grupo inteiro sem estoque deve ser
comunicado como indisponível, sem promessa de prazo de reposição.

## Substituição por genérico

Ao sugerir alternativa de produto, priorize itens do mesmo produto-pai
(mesmo princípio ativo e apresentação equivalente). Genérico pode substituir
o medicamento de referência quando o cliente aceitar; nunca substitua item
de prescrição com retenção sem confirmação do cliente.

## Pedido mínimo — canal privado

O pedido mínimo no canal privado é de R$ 300,00 por entrega; abaixo disso o
custo de frete inviabiliza a operação. Exceções: reposição de item faltante
por erro nosso ou complemento de pedido faturado na mesma semana.

## Prioridade de reativação — carteira RED

Clientes classificados como RED (sem compra nos últimos meses, mas com
histórico ativo) têm prioridade de contato sobre prospecção nova. A meta
operacional é registrar tentativa de reativação para todo RED com mais de 60
dias sem compra antes de abrir novos cadastros na mesma praça.

## Confidencialidade de carteira

Dados de clientes (CNPJ, faturamento, condição de crédito) são restritos ao
representante responsável pela carteira e à diretoria. Consultores não
acessam nem discutem dados de carteiras de outros representantes; comparações
entre representantes são exclusivas da visão executiva.
