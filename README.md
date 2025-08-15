# Pacote de Análise de Benchmark Databricks

Este pacote contém todos os scripts, dados e resultados da análise de benchmark do Databricks realizada para comparar performance vs custo de diferentes tipos de máquinas.

## 📁 Conteúdo do Pacote

### 📊 Dados de Origem
- `dados_originais_benchmark.csv` - Arquivo CSV original fornecido com os dados do benchmark
- `dados_originais.csv` - Dados processados e limpos (cenário original)
- `dados_com_desconto.csv` - Dados com desconto de 45% aplicado nas máquinas pds_v6

### 🐍 Scripts Python
- `databricks_analysis.py` - Script principal de análise que gera todos os gráficos básicos
- `grafico_impacto_customizado.py` - Script para gerar gráficos customizados de impacto do desconto

### 📈 Gráficos Gerados
- `tempo_execucao.png` - Tempo de execução por tipo de máquina
- `custo_total.png` - Custo total por tipo de máquina
- `performance_vs_custo.png` - Scatter plot de performance vs custo
- `eficiencia_custo.png` - Eficiência de custo por segundo
- `comparacao_custos.png` - Comparação de custos antes/depois do desconto
- `comparacao_scatter.png` - Scatter plot comparativo com desconto
- `impacto_custo_customizado.png` - Gráfico customizado de impacto (verde para pds_v6)
- `impacto_pds_v6_foco.png` - Foco apenas nas máquinas pds_v6

### 📄 Documentação
- `benchmark_databricks_confluence.md` - Documento completo para Confluence
- `README.md` - Este arquivo

## 🚀 Como Executar

### Pré-requisitos
```bash
pip install pandas numpy matplotlib seaborn
```

### Executar Análise Principal
```bash
python databricks_analysis.py
```

### Executar Gráficos Customizados
```bash
python grafico_impacto_customizado.py
```

## 📋 Principais Descobertas

- **Melhor Performance**: D32pds_v6 (65 segundos)
- **Melhor Custo-Benefício**: D16pds_v6 com desconto
- **Maior Economia**: 28,4% nas máquinas pds_v6 com desconto de 45%
- **Recomendação**: D16pds_v6 com desconto oferece equilíbrio ideal

## 💰 Impacto do Desconto de 45%

| Máquina | Custo Original | Custo com Desconto | Economia |
|---------|----------------|-------------------|----------|
| D32pds_v6 | $1,14 | $0,82 | 28,4% |
| D16pds_v6 | $0,66 | $0,48 | 27,3% |
| D8pds_v6 | $0,42 | $0,33 | 21,4% |
| D4pds_v6 | $0,32 | $0,26 | 18,3% |

## 📞 Suporte

Para dúvidas sobre a análise ou scripts, consulte a documentação completa no arquivo `benchmark_databricks_confluence.md`.


