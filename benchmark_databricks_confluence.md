# Análise de Benchmark Databricks: Performance vs Custo

## Sumário Executivo

Este documento apresenta uma análise abrangente de benchmark do Databricks, comparando 18 tipos diferentes de máquinas em termos de performance e custo para processamento de ingestão bronze de 1 milhão de registros no formato AVRO. A análise inclui um cenário adicional com desconto de 45% nas máquinas da família pds_v6, fornecendo insights valiosos para otimização de custos e seleção de recursos.

### Principais Descobertas

- **Melhor Performance**: D32pds_v6 com 65 segundos de execução
- **Melhor Custo-Benefício**: D8a_v4 e D8pds_v6 apresentam excelente eficiência
- **Impacto do Desconto**: Economia de 18% a 28% nas máquinas pds_v6
- **Recomendação Principal**: D16pds_v6 com desconto oferece o melhor equilíbrio

---

## 1. Introdução e Metodologia

### 1.1 Objetivo

O objetivo deste benchmark é avaliar a relação entre performance e custo de diferentes tipos de máquinas no Databricks, fornecendo dados concretos para tomada de decisões sobre alocação de recursos e otimização de custos em processamentos de dados.

### 1.2 Metodologia

**Configuração do Teste:**
- **Tipo de Processamento**: Ingestão de dados para camada Bronze
- **Formato dos Dados**: AVRO
- **Volume de Dados**: 1 milhão de registros
- **Número de Execuções**: 5 execuções por tipo de máquina
- **Métricas Coletadas**: Tempo de execução, custos detalhados por componente

**Tipos de Máquinas Testadas:**
- 18 tipos diferentes de máquinas Azure
- Incluindo famílias: pds_v6, as_v5, a_v4, s_v3, E_v3, F-series
- Variação de tamanhos: D4 até D32

**Componentes de Custo Analisados:**
- Azure Compute
- DBU (Databricks Units)
- Network
- Disco
- Custo Total

---


## 2. Análise de Performance

### 2.1 Tempo de Execução por Tipo de Máquina

![Gráfico de Tempo de Execução](/home/ubuntu/tempo_execucao.png)

A análise de performance revela diferenças significativas entre os tipos de máquinas testadas:

**Categoria de Alta Performance (< 100 segundos):**
- **D32pds_v6**: 65 segundos - Melhor performance absoluta
- **D16pds_v6**: 79 segundos - Excelente performance com custo moderado
- **D16as_v5**: 79 segundos - Performance equivalente ao D16pds_v6
- **D16a_v4**: 83 segundos - Boa performance com custo competitivo
- **E16_v3**: 93 segundos - Performance sólida, mas custo elevado

**Categoria de Performance Intermediária (100-200 segundos):**
- **D8pds_v6**: 113 segundos - Bom equilíbrio para cargas médias
- **F16**: 121 segundos - Performance aceitável para processamentos não críticos
- **D8as_v5**: 133 segundos - Opção intermediária econômica
- **D8a_v4**: 138 segundos - Melhor custo-benefício da categoria
- **D16s_v3**: 139 segundos - Performance moderada com custo elevado

**Categoria de Performance Inferior (> 200 segundos):**
- **D4pds_v6**: 174 segundos - Adequada para cargas leves
- **F8**: 194 segundos - Performance limitada
- **D4as_v5**: 215 segundos - Opção econômica para processamentos não urgentes
- **D4a_v4**: 231 segundos - Custo baixo, performance limitada
- **D8s_v3**: 232 segundos - Performance inferior ao esperado
- **D4s_v3**: 393 segundos - Performance muito baixa
- **F4**: 516 segundos - Inadequada para processamentos que exigem rapidez
- **F4s_v2**: 900 segundos - Pior performance do benchmark

### 2.2 Insights de Performance

1. **Família pds_v6**: Consistentemente apresenta as melhores performances em suas respectivas categorias de tamanho
2. **Escalabilidade**: Máquinas maiores (D32, D16) oferecem performance significativamente superior
3. **Variação por Família**: Diferenças notáveis entre famílias de máquinas do mesmo tamanho
4. **Consistência**: Baixo desvio padrão indica performance previsível na maioria dos casos

---


## 3. Análise de Custo

### 3.1 Custo Total por Tipo de Máquina

![Gráfico de Custo Total](/home/ubuntu/custo_total.png)

A análise de custos revela uma distribuição interessante entre os diferentes componentes:

**Máquinas de Alto Custo (> $1.00):**
- **E16_v3**: $1.36 - Custo mais elevado, principalmente Azure Compute ($1.10)
- **D32pds_v6**: $1.14 - Alto custo justificado pela performance superior
- **F4s_v2**: $1.01 - Custo elevado com performance muito baixa

**Máquinas de Custo Intermediário ($0.50 - $1.00):**
- **D16s_v3**: $0.78 - Custo moderado, performance intermediária
- **F16**: $0.73 - Custo razoável para performance oferecida
- **D4s_v3**: $0.68 - Custo alto para performance limitada
- **D16pds_v6**: $0.66 - Excelente relação custo-performance
- **D16as_v5**: $0.63 - Competitivo em custo e performance
- **D16a_v4**: $0.58 - Melhor custo na categoria de alta performance
- **D8s_v3**: $0.56 - Custo moderado, performance inferior
- **D8as_v5**: $0.52 - Opção econômica com performance aceitável
- **F4**: $0.50 - Custo moderado, performance muito baixa

**Máquinas de Baixo Custo (< $0.50):**
- **F8**: $0.47 - Custo baixo, performance limitada
- **D8pds_v6**: $0.42 - Excelente custo-benefício
- **D8a_v4**: $0.38 - Melhor eficiência de custo
- **D4as_v5**: $0.36 - Opção muito econômica
- **D4a_v4**: $0.34 - Custo muito baixo
- **D4pds_v6**: $0.32 - Menor custo absoluto

### 3.2 Decomposição dos Custos

**Componentes de Custo por Categoria:**

| Componente | Participação Média | Observações |
|------------|-------------------|-------------|
| Azure Compute | 45-60% | Maior componente na maioria das máquinas |
| DBU | 20-35% | Varia conforme tipo e tamanho da máquina |
| Network | 10-15% | Relativamente constante |
| Disco | 5-20% | Varia significativamente entre tipos |

**Insights de Custo:**

1. **Azure Compute**: Representa a maior parcela do custo, especialmente em máquinas de alta performance
2. **DBU**: Componente significativo que varia conforme a capacidade de processamento
3. **Economia de Escala**: Máquinas maiores tendem a ter melhor eficiência de custo por unidade de performance
4. **Variação por Família**: Diferentes famílias apresentam estruturas de custo distintas

---


## 4. Análise Performance vs Custo

### 4.1 Relação Performance-Custo

![Gráfico Performance vs Custo](/home/ubuntu/performance_vs_custo.png)

A análise da relação entre performance e custo permite identificar as opções com melhor custo-benefício:

### 4.2 Categorização por Quadrantes

**Quadrante 1: Alta Performance, Alto Custo**
- **D32pds_v6**: Melhor performance (65s), custo elevado ($1.14)
- **E16_v3**: Performance boa (93s), custo mais alto ($1.36)

*Recomendação*: Ideal para processamentos críticos onde o tempo é prioridade absoluta.

**Quadrante 2: Alta Performance, Custo Moderado**
- **D16pds_v6**: Excelente performance (79s), custo razoável ($0.66)
- **D16as_v5**: Performance equivalente (79s), custo competitivo ($0.63)
- **D16a_v4**: Boa performance (83s), melhor custo da categoria ($0.58)

*Recomendação*: Opções ideais para a maioria dos casos de uso, oferecendo o melhor equilíbrio.

**Quadrante 3: Performance Moderada, Custo Baixo**
- **D8pds_v6**: Performance aceitável (113s), custo baixo ($0.42)
- **D8a_v4**: Performance moderada (138s), excelente custo ($0.38)
- **D4pds_v6**: Performance limitada (174s), custo muito baixo ($0.32)

*Recomendação*: Adequadas para processamentos em lote não urgentes e cargas de desenvolvimento.

**Quadrante 4: Performance Baixa, Custo Alto**
- **F4s_v2**: Performance muito baixa (900s), custo elevado ($1.01)
- **D4s_v3**: Performance baixa (393s), custo moderado ($0.68)

*Recomendação*: Evitar estas opções devido à baixa eficiência.

### 4.3 Eficiência de Custo

![Gráfico de Eficiência de Custo](/home/ubuntu/eficiencia_custo.png)

**Ranking de Eficiência (Custo por Segundo):**

| Posição | Máquina | Custo/Segundo | Categoria |
|---------|---------|---------------|-----------|
| 1º | D8a_v4 | $0.0028 | Máxima Eficiência |
| 2º | D8pds_v6 | $0.0037 | Excelente |
| 3º | D4as_v5 | $0.0017 | Muito Boa |
| 4º | D16a_v4 | $0.0070 | Boa |
| 5º | D16as_v5 | $0.0080 | Boa |
| ... | ... | ... | ... |
| Último | F4s_v2 | $0.0011 | Baixa Eficiência |

### 4.4 Recomendações por Cenário de Uso

**Processamentos Críticos (SLA < 2 minutos):**
- Primeira opção: D32pds_v6
- Alternativa: D16pds_v6 ou D16as_v5

**Processamentos Padrão (SLA < 5 minutos):**
- Primeira opção: D16pds_v6, D16as_v5, ou D16a_v4
- Alternativa: D8pds_v6

**Processamentos em Lote (SLA > 10 minutos):**
- Primeira opção: D8a_v4 ou D8pds_v6
- Alternativa: D4pds_v6 para cargas muito leves

**Desenvolvimento e Testes:**
- Primeira opção: D4pds_v6 ou D4a_v4
- Alternativa: D8a_v4 para testes mais robustos

---


## 5. Cenário com Desconto de 45%

### 5.1 Metodologia do Cenário

Foi aplicado um desconto de **45%** especificamente no componente **Azure Compute** das máquinas da família **pds_v6**, simulando uma negociação comercial ou programa de incentivos. Este desconto não afeta os componentes DBU, Network e Disco.

**Máquinas Afetadas:**
- D32pds_v6
- D16pds_v6  
- D8pds_v6
- D4pds_v6

### 5.2 Impacto do Desconto

![Gráfico Comparativo de Custos](/home/ubuntu/comparacao_custos.png)

**Tabela de Impacto Detalhado:**

| Máquina | Custo Original | Azure Compute Original | Azure Compute c/ Desconto | Custo Final | Economia Absoluta | Economia (%) |
|---------|----------------|-------------------------|----------------------------|-------------|-------------------|--------------|
| D32pds_v6 | $1.14 | $0.72 | $0.40 | $0.82 | $0.32 | 28.4% |
| D16pds_v6 | $0.66 | $0.40 | $0.22 | $0.48 | $0.18 | 27.3% |
| D8pds_v6 | $0.42 | $0.20 | $0.11 | $0.33 | $0.09 | 21.4% |
| D4pds_v6 | $0.32 | $0.13 | $0.07 | $0.26 | $0.06 | 18.3% |

### 5.3 Análise Comparativa Pós-Desconto

![Gráfico Scatter Comparativo](/home/ubuntu/comparacao_scatter.png)

**Mudanças no Ranking de Custo-Benefício:**

**Antes do Desconto:**
1. D8a_v4 ($0.38, 138s)
2. D4pds_v6 ($0.32, 174s)
3. D8pds_v6 ($0.42, 113s)
4. D16a_v4 ($0.58, 83s)
5. D16as_v5 ($0.63, 79s)

**Após o Desconto:**
1. D4pds_v6 ($0.26, 174s) ⬆️
2. D8pds_v6 ($0.33, 113s) ⬆️
3. D8a_v4 ($0.38, 138s) ⬇️
4. D16pds_v6 ($0.48, 79s) ⬆️ *Nova entrada no top 5*
5. D16a_v4 ($0.58, 83s) ⬇️

### 5.4 Impacto Competitivo

**D16pds_v6 vs Concorrentes:**
- **Antes**: $0.66 (79s) vs D16as_v5 $0.63 (79s) vs D16a_v4 $0.58 (83s)
- **Depois**: $0.48 (79s) - **Torna-se a opção mais econômica** com performance equivalente ou superior

**D32pds_v6 vs Concorrentes:**
- **Antes**: $1.14 (65s) - Melhor performance, mas custo premium de 75% vs D16as_v5
- **Depois**: $0.82 (65s) - Mantém melhor performance com premium reduzido para 30%

**D8pds_v6 vs Concorrentes:**
- **Antes**: $0.42 (113s) vs D8a_v4 $0.38 (138s)
- **Depois**: $0.33 (113s) - **Torna-se mais econômica** que D8a_v4 com performance 18% superior

### 5.5 ROI do Desconto

**Análise de Retorno sobre Investimento:**

Para um processamento diário de 1 milhão de registros (365 execuções/ano):

| Máquina | Economia Anual | Performance Gain | ROI Score |
|---------|----------------|------------------|-----------|
| D32pds_v6 | $116.80 | Melhor absoluta | ⭐⭐⭐⭐⭐ |
| D16pds_v6 | $65.70 | Excelente | ⭐⭐⭐⭐⭐ |
| D8pds_v6 | $32.85 | Boa | ⭐⭐⭐⭐ |
| D4pds_v6 | $21.90 | Limitada | ⭐⭐⭐ |

**Recomendação Estratégica:**
O desconto de 45% torna as máquinas pds_v6 extremamente competitivas, especialmente D16pds_v6 e D32pds_v6, que passam a oferecer o melhor custo-benefício em suas respectivas categorias de performance.

---


## 6. Conclusões e Recomendações

### 6.1 Principais Conclusões

**Performance:**
- A família **pds_v6** consistentemente oferece a melhor performance em suas respectivas categorias de tamanho
- Existe uma clara correlação entre tamanho da máquina e performance, com **D32pds_v6** liderando com 65 segundos
- Máquinas da série **F** apresentam performance inferior, especialmente F4 e F4s_v2
- A variabilidade de performance entre execuções é baixa, indicando consistência operacional

**Custo:**
- O componente **Azure Compute** representa 45-60% do custo total na maioria das máquinas
- Máquinas menores (D4, D8) oferecem melhor eficiência de custo por segundo de processamento
- Existe uma relação não-linear entre custo e performance, criando oportunidades de otimização

**Impacto do Desconto:**
- O desconto de 45% nas máquinas pds_v6 altera significativamente o cenário competitivo
- **D16pds_v6** com desconto torna-se a opção mais atrativa para a maioria dos casos de uso
- Economia anual potencial de $21.90 a $116.80 por processamento diário

### 6.2 Recomendações Estratégicas

#### 6.2.1 Política de Alocação de Recursos

**Tier 1 - Processamentos Críticos (SLA < 90 segundos):**
- **Primeira escolha**: D32pds_v6 (com desconto: $0.82, 65s)
- **Alternativa**: D16pds_v6 (com desconto: $0.48, 79s)
- **Justificativa**: Melhor performance absoluta com custo otimizado pelo desconto

**Tier 2 - Processamentos Padrão (SLA < 150 segundos):**
- **Primeira escolha**: D16pds_v6 (com desconto: $0.48, 79s)
- **Alternativa**: D16as_v5 ($0.63, 79s) ou D16a_v4 ($0.58, 83s)
- **Justificativa**: Excelente equilíbrio performance-custo, especialmente com desconto

**Tier 3 - Processamentos em Lote (SLA > 200 segundos):**
- **Primeira escolha**: D8pds_v6 (com desconto: $0.33, 113s)
- **Alternativa**: D8a_v4 ($0.38, 138s)
- **Justificativa**: Melhor eficiência de custo para cargas não urgentes

**Tier 4 - Desenvolvimento e Testes:**
- **Primeira escolha**: D4pds_v6 (com desconto: $0.26, 174s)
- **Alternativa**: D4a_v4 ($0.34, 231s)
- **Justificativa**: Custo mínimo para ambientes não produtivos

#### 6.2.2 Estratégia de Negociação

**Prioridade Alta:**
1. **Negociar desconto similar** para máquinas pds_v6 com fornecedor Azure
2. **Estabelecer contratos de longo prazo** para garantir preços preferenciais
3. **Avaliar Reserved Instances** para cargas de trabalho previsíveis

**Prioridade Média:**
1. **Monitorar novos tipos de máquinas** que possam oferecer melhor custo-benefício
2. **Implementar auto-scaling** baseado em demanda para otimizar custos
3. **Avaliar spot instances** para cargas de trabalho tolerantes a interrupções

#### 6.2.3 Implementação Técnica

**Fase 1 - Imediata (0-30 dias):**
- Migrar processamentos críticos para D32pds_v6 ou D16pds_v6 (se desconto disponível)
- Implementar política de alocação baseada em SLA
- Estabelecer monitoramento de custos por tipo de máquina

**Fase 2 - Curto Prazo (1-3 meses):**
- Desenvolver automação para seleção dinâmica de tipo de máquina
- Implementar alertas de custo e performance
- Criar dashboards de monitoramento em tempo real

**Fase 3 - Médio Prazo (3-6 meses):**
- Avaliar padrões de uso e otimizar alocações
- Implementar machine learning para predição de demanda
- Estabelecer revisões trimestrais de performance vs custo

### 6.3 Métricas de Sucesso

**KPIs Primários:**
- **Redução de Custo**: Meta de 20-30% de redução no custo total de processamento
- **Melhoria de Performance**: Meta de 15-25% de redução no tempo médio de execução
- **Eficiência Operacional**: Meta de 95% de SLA compliance

**KPIs Secundários:**
- **Utilização de Recursos**: Meta de 80%+ de utilização média
- **Variabilidade de Performance**: Meta de <5% de desvio padrão
- **Satisfação dos Usuários**: Meta de 90%+ de satisfação com performance

### 6.4 Próximos Passos

1. **Validação em Ambiente de Produção**: Executar testes piloto com as recomendações
2. **Análise de Cargas Variadas**: Expandir benchmark para diferentes tipos de processamento
3. **Avaliação de Novas Tecnologias**: Monitorar lançamentos de novos tipos de máquinas
4. **Otimização Contínua**: Estabelecer processo de revisão mensal das métricas

---

## 7. Anexos

### 7.1 Dados Completos do Benchmark

| Máquina | Tempo Médio (s) | Desvio Padrão | Custo Total ($) | Azure Compute ($) | DBU ($) | Network ($) | Disco ($) |
|---------|-----------------|---------------|-----------------|-------------------|---------|-------------|-----------|
| D32pds_v6 | 65 | 1 | 1.14 | 0.72 | 0.33 | 0.05 | 0.04 |
| D16pds_v6 | 79 | 1 | 0.66 | 0.40 | 0.18 | 0.06 | 0.02 |
| D16as_v5 | 79 | 0 | 0.63 | 0.35 | 0.14 | 0.07 | 0.07 |
| D16a_v4 | 83 | 0 | 0.58 | 0.35 | 0.12 | 0.08 | 0.03 |
| E16_v3 | 93 | 1 | 1.36 | 1.10 | 0.17 | 0.06 | 0.03 |
| D8pds_v6 | 113 | 2 | 0.42 | 0.20 | 0.11 | 0.07 | 0.04 |
| F16 | 121 | 1 | 0.73 | 0.52 | 0.11 | 0.07 | 0.03 |
| D8as_v5 | 133 | 4 | 0.52 | 0.26 | 0.10 | 0.07 | 0.09 |
| D8a_v4 | 138 | 2 | 0.38 | 0.20 | 0.08 | 0.06 | 0.04 |
| D16s_v3 | 139 | 2 | 0.78 | 0.46 | 0.19 | 0.07 | 0.06 |
| D4pds_v6 | 174 | 4 | 0.32 | 0.13 | 0.07 | 0.06 | 0.06 |
| F8 | 194 | 5 | 0.47 | 0.27 | 0.07 | 0.07 | 0.06 |
| D4as_v5 | 215 | 6 | 0.36 | 0.11 | 0.07 | 0.07 | 0.11 |
| D4a_v4 | 231 | 13 | 0.34 | 0.14 | 0.06 | 0.07 | 0.07 |
| D8s_v3 | 232 | 9 | 0.56 | 0.29 | 0.12 | 0.07 | 0.08 |
| D4s_v3 | 393 | 61 | 0.68 | 0.32 | 0.10 | 0.07 | 0.19 |
| F4 | 516 | 133 | 0.50 | 0.26 | 0.07 | 0.07 | 0.10 |
| F4s_v2 | 900 | 172 | 1.01 | 0.38 | 0.25 | 0.09 | 0.29 |

### 7.2 Glossário

**Azure Compute**: Custo da infraestrutura de computação na nuvem Azure
**DBU (Databricks Units)**: Unidades de processamento específicas do Databricks
**Network**: Custos de transferência de dados e conectividade de rede
**Disco**: Custos de armazenamento temporário e persistente
**SLA**: Service Level Agreement - Acordo de nível de serviço
**Custo-Benefício**: Relação entre custo total e performance obtida

---

*Documento gerado em Agosto de 2025 - Benchmark Databricks Performance vs Custo*

