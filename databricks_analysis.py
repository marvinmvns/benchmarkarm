#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib import rcParams
import warnings
warnings.filterwarnings('ignore')

# Configuração para melhor visualização
plt.style.use('default')
rcParams['font.size'] = 12
rcParams['axes.titlesize'] = 14
rcParams['axes.labelsize'] = 12
rcParams['xtick.labelsize'] = 10
rcParams['ytick.labelsize'] = 10
rcParams['legend.fontsize'] = 10
rcParams['figure.titlesize'] = 16

def load_and_clean_data(file_path):
    """Carrega e limpa os dados do CSV"""
    print("Carregando dados...")
    
    # Ler o CSV com separador correto
    df = pd.read_csv(file_path, sep=';', encoding='utf-8-sig')
    
    print(f"Dados carregados: {df.shape[0]} registros, {df.shape[1]} colunas")
    print("Colunas:", df.columns.tolist())
    
    # Limpar nomes das colunas
    df.columns = df.columns.str.strip()
    
    # Função para converter valores monetários
    def clean_currency(value):
        if pd.isna(value):
            return 0.0
        # Remover espaços, $ e vírgulas, substituir vírgula por ponto
        cleaned = str(value).strip().replace('$', '').replace(' ', '').replace(',', '.')
        try:
            return float(cleaned)
        except:
            return 0.0
    
    # Limpar colunas monetárias
    currency_columns = ['Azure Compute', 'DBU', 'Network', 'Disco', 'Total em $']
    for col in currency_columns:
        if col in df.columns:
            df[col] = df[col].apply(clean_currency)
    
    # Garantir que colunas numéricas sejam do tipo correto
    numeric_columns = ['mean_exec_dur_secs', 'stddev_exec_dur_secs', 'min_exec_dur_secs', 
                      'max_exec_dur_secs', 'execuções']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df

def calculate_metrics(df):
    """Calcula métricas de performance e eficiência"""
    df = df.copy()
    
    # Custo por segundo de execução
    df['custo_por_segundo'] = df['Total em $'] / df['mean_exec_dur_secs']
    
    # Eficiência (inverso do custo por segundo - maior é melhor)
    df['eficiencia'] = 1 / df['custo_por_segundo']
    
    # Performance score (baseado no tempo - menor tempo = melhor performance)
    df['performance_score'] = 1 / df['mean_exec_dur_secs']
    
    # Identificar máquinas pds_v6
    df['is_pds_v6'] = df['worker_type'].str.contains('pds_v6', case=False)
    
    return df

def create_performance_charts(df, output_dir='/home/ubuntu'):
    """Cria gráficos de análise de performance"""
    
    # Configurar cores
    colors = plt.cm.Set3(np.linspace(0, 1, len(df)))
    
    # 1. Gráfico de Tempo de Execução por Tipo de Máquina
    plt.figure(figsize=(14, 8))
    bars = plt.bar(range(len(df)), df['mean_exec_dur_secs'], color=colors, alpha=0.8)
    plt.xlabel('Tipo de Máquina')
    plt.ylabel('Tempo Médio de Execução (segundos)')
    plt.title('Tempo de Execução por Tipo de Máquina\nIngestão Bronze - 1 Milhão de Registros AVRO')
    plt.xticks(range(len(df)), df['worker_type'], rotation=45, ha='right')
    
    # Adicionar valores nas barras
    for i, bar in enumerate(bars):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 1,
                f'{height:.0f}s', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/tempo_execucao.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Gráfico de Custo Total por Tipo de Máquina
    plt.figure(figsize=(14, 8))
    bars = plt.bar(range(len(df)), df['Total em $'], color=colors, alpha=0.8)
    plt.xlabel('Tipo de Máquina')
    plt.ylabel('Custo Total (USD)')
    plt.title('Custo Total por Tipo de Máquina\nIngestão Bronze - 1 Milhão de Registros AVRO')
    plt.xticks(range(len(df)), df['worker_type'], rotation=45, ha='right')
    
    # Adicionar valores nas barras
    for i, bar in enumerate(bars):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                f'${height:.2f}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/custo_total.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 3. Scatter Plot: Performance vs Custo
    plt.figure(figsize=(12, 8))
    
    # Separar máquinas pds_v6 das outras
    pds_v6 = df[df['is_pds_v6']]
    others = df[~df['is_pds_v6']]
    
    plt.scatter(others['mean_exec_dur_secs'], others['Total em $'], 
               alpha=0.7, s=100, label='Outras Máquinas', color='lightblue')
    plt.scatter(pds_v6['mean_exec_dur_secs'], pds_v6['Total em $'], 
               alpha=0.8, s=120, label='Máquinas pds_v6', color='red', marker='s')
    
    # Adicionar labels para cada ponto
    for idx, row in df.iterrows():
        plt.annotate(row['worker_type'], 
                    (row['mean_exec_dur_secs'], row['Total em $']),
                    xytext=(5, 5), textcoords='offset points', fontsize=8)
    
    plt.xlabel('Tempo Médio de Execução (segundos)')
    plt.ylabel('Custo Total (USD)')
    plt.title('Performance vs Custo - Análise Comparativa\nIngestão Bronze - 1 Milhão de Registros AVRO')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/performance_vs_custo.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 4. Gráfico de Eficiência (Custo por Segundo)
    plt.figure(figsize=(14, 8))
    bars = plt.bar(range(len(df)), df['custo_por_segundo'], color=colors, alpha=0.8)
    plt.xlabel('Tipo de Máquina')
    plt.ylabel('Custo por Segundo (USD/s)')
    plt.title('Eficiência de Custo por Tipo de Máquina\nCusto por Segundo de Execução')
    plt.xticks(range(len(df)), df['worker_type'], rotation=45, ha='right')
    
    # Adicionar valores nas barras
    for i, bar in enumerate(bars):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + 0.0001,
                f'${height:.4f}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/eficiencia_custo.png', dpi=300, bbox_inches='tight')
    plt.close()

def apply_discount_scenario(df, discount_percent=45):
    """Aplica desconto de 45% nas máquinas pds_v6"""
    df_discounted = df.copy()
    
    # Aplicar desconto apenas no Azure Compute das máquinas pds_v6
    mask = df_discounted['is_pds_v6']
    df_discounted.loc[mask, 'Azure Compute'] = df_discounted.loc[mask, 'Azure Compute'] * (1 - discount_percent/100)
    
    # Recalcular o total
    df_discounted['Total em $'] = (df_discounted['Azure Compute'] + 
                                  df_discounted['DBU'] + 
                                  df_discounted['Network'] + 
                                  df_discounted['Disco'])
    
    # Recalcular métricas
    df_discounted['custo_por_segundo'] = df_discounted['Total em $'] / df_discounted['mean_exec_dur_secs']
    df_discounted['eficiencia'] = 1 / df_discounted['custo_por_segundo']
    
    return df_discounted

def create_comparison_charts(df_original, df_discounted, output_dir='/home/ubuntu'):
    """Cria gráficos comparativos antes e depois do desconto"""
    
    # 1. Comparação de Custo Total - Antes vs Depois
    plt.figure(figsize=(14, 8))
    
    x = np.arange(len(df_original))
    width = 0.35
    
    bars1 = plt.bar(x - width/2, df_original['Total em $'], width, 
                   label='Sem Desconto', alpha=0.8, color='lightcoral')
    bars2 = plt.bar(x + width/2, df_discounted['Total em $'], width, 
                   label='Com Desconto 45% (pds_v6)', alpha=0.8, color='lightgreen')
    
    plt.xlabel('Tipo de Máquina')
    plt.ylabel('Custo Total (USD)')
    plt.title('Comparação de Custos: Cenário Original vs Desconto 45% (pds_v6)')
    plt.xticks(x, df_original['worker_type'], rotation=45, ha='right')
    plt.legend()
    
    # Adicionar valores nas barras
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                    f'${height:.2f}', ha='center', va='bottom', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/comparacao_custos.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Scatter Plot Comparativo
    plt.figure(figsize=(12, 8))
    
    # Dados originais
    pds_v6_orig = df_original[df_original['is_pds_v6']]
    others_orig = df_original[~df_original['is_pds_v6']]
    
    # Dados com desconto
    pds_v6_disc = df_discounted[df_discounted['is_pds_v6']]
    
    plt.scatter(others_orig['mean_exec_dur_secs'], others_orig['Total em $'], 
               alpha=0.7, s=100, label='Outras Máquinas', color='lightblue')
    plt.scatter(pds_v6_orig['mean_exec_dur_secs'], pds_v6_orig['Total em $'], 
               alpha=0.8, s=120, label='pds_v6 (Original)', color='red', marker='s')
    plt.scatter(pds_v6_disc['mean_exec_dur_secs'], pds_v6_disc['Total em $'], 
               alpha=0.8, s=120, label='pds_v6 (45% Desconto)', color='green', marker='D')
    
    plt.xlabel('Tempo Médio de Execução (segundos)')
    plt.ylabel('Custo Total (USD)')
    plt.title('Impacto do Desconto de 45% nas Máquinas pds_v6\nPerformance vs Custo')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/comparacao_scatter.png', dpi=300, bbox_inches='tight')
    plt.close()

def generate_summary_table(df_original, df_discounted):
    """Gera tabela resumo das análises"""
    
    # Top 5 melhores em cada categoria
    summary = {}
    
    # Melhor performance (menor tempo)
    summary['Melhor Performance'] = df_original.nsmallest(5, 'mean_exec_dur_secs')[['worker_type', 'mean_exec_dur_secs', 'Total em $']]
    
    # Menor custo
    summary['Menor Custo'] = df_original.nsmallest(5, 'Total em $')[['worker_type', 'mean_exec_dur_secs', 'Total em $']]
    
    # Melhor custo-benefício (menor custo por segundo)
    summary['Melhor Custo-Benefício'] = df_original.nsmallest(5, 'custo_por_segundo')[['worker_type', 'mean_exec_dur_secs', 'Total em $', 'custo_por_segundo']]
    
    # Impacto do desconto nas máquinas pds_v6
    pds_v6_comparison = []
    for idx, row in df_original[df_original['is_pds_v6']].iterrows():
        original_cost = row['Total em $']
        discounted_cost = df_discounted.loc[idx, 'Total em $']
        savings = original_cost - discounted_cost
        savings_percent = (savings / original_cost) * 100
        
        pds_v6_comparison.append({
            'worker_type': row['worker_type'],
            'custo_original': original_cost,
            'custo_com_desconto': discounted_cost,
            'economia': savings,
            'economia_percent': savings_percent
        })
    
    summary['Impacto Desconto pds_v6'] = pd.DataFrame(pds_v6_comparison)
    
    return summary

if __name__ == "__main__":
    # Carregar e processar dados
    df = load_and_clean_data('/home/ubuntu/upload/CSCbenchmarkajustadov2(1).csv')
    df = calculate_metrics(df)
    
    print("\n=== DADOS CARREGADOS ===")
    print(df[['worker_type', 'mean_exec_dur_secs', 'Total em $', 'custo_por_segundo', 'is_pds_v6']].head(10))
    
    # Criar gráficos originais
    print("\n=== CRIANDO GRÁFICOS ORIGINAIS ===")
    create_performance_charts(df)
    
    # Aplicar cenário de desconto
    print("\n=== APLICANDO CENÁRIO DE DESCONTO ===")
    df_discounted = apply_discount_scenario(df, 45)
    
    # Criar gráficos comparativos
    print("\n=== CRIANDO GRÁFICOS COMPARATIVOS ===")
    create_comparison_charts(df, df_discounted)
    
    # Gerar resumo
    print("\n=== GERANDO RESUMO ===")
    summary = generate_summary_table(df, df_discounted)
    
    # Salvar dados processados
    df.to_csv('/home/ubuntu/dados_originais.csv', index=False)
    df_discounted.to_csv('/home/ubuntu/dados_com_desconto.csv', index=False)
    
    print("\n=== ANÁLISE CONCLUÍDA ===")
    print("Gráficos salvos:")
    print("- tempo_execucao.png")
    print("- custo_total.png") 
    print("- performance_vs_custo.png")
    print("- eficiencia_custo.png")
    print("- comparacao_custos.png")
    print("- comparacao_scatter.png")
    
    # Exibir resumo das máquinas pds_v6
    print("\n=== RESUMO MÁQUINAS pds_v6 ===")
    pds_v6_data = df[df['is_pds_v6']][['worker_type', 'mean_exec_dur_secs', 'Total em $']]
    print(pds_v6_data)
    
    print("\n=== IMPACTO DO DESCONTO ===")
    print(summary['Impacto Desconto pds_v6'])

