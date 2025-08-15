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

def create_custom_impact_chart():
    """Cria gráfico de impacto customizado com cores específicas"""
    
    # Carregar dados processados
    df_original = pd.read_csv('/home/ubuntu/dados_originais.csv')
    df_discounted = pd.read_csv('/home/ubuntu/dados_com_desconto.csv')
    
    # Preparar dados para o gráfico
    x = np.arange(len(df_original))
    width = 0.35
    
    # Criar figura
    plt.figure(figsize=(16, 10))
    
    # Definir cores baseadas no tipo de máquina
    colors_original = []
    colors_discounted = []
    
    for idx, row in df_original.iterrows():
        if row['is_pds_v6']:
            colors_original.append('lightcoral')  # Vermelho claro para pds_v6 original
            colors_discounted.append('lightgreen')  # Verde para pds_v6 com desconto
        else:
            colors_original.append('lightcoral')  # Vermelho para outras máquinas
            colors_discounted.append('lightcoral')  # Vermelho para outras máquinas (sem mudança)
    
    # Criar barras
    bars1 = plt.bar(x - width/2, df_original['Total em $'], width, 
                   label='Custo Original', alpha=0.8, color=colors_original)
    bars2 = plt.bar(x + width/2, df_discounted['Total em $'], width, 
                   label='Com Desconto 45% (pds_v6)', alpha=0.8, color=colors_discounted)
    
    # Configurar gráfico
    plt.xlabel('Tipo de Máquina', fontsize=14)
    plt.ylabel('Custo Total (USD)', fontsize=14)
    plt.title('Impacto do Desconto de 45% - Máquinas pds_v6\nComparação de Custos por Tipo de Máquina', fontsize=16, pad=20)
    plt.xticks(x, df_original['worker_type'], rotation=45, ha='right')
    
    # Adicionar valores nas barras apenas para máquinas pds_v6
    for i, (bar1, bar2) in enumerate(zip(bars1, bars2)):
        if df_original.iloc[i]['is_pds_v6']:
            # Valor original
            height1 = bar1.get_height()
            plt.text(bar1.get_x() + bar1.get_width()/2., height1 + 0.01,
                    f'${height1:.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
            
            # Valor com desconto
            height2 = bar2.get_height()
            plt.text(bar2.get_x() + bar2.get_width()/2., height2 + 0.01,
                    f'${height2:.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
            
            # Seta indicando redução
            plt.annotate('', xy=(bar2.get_x() + bar2.get_width()/2., height2 + 0.05),
                        xytext=(bar1.get_x() + bar1.get_width()/2., height1 - 0.05),
                        arrowprops=dict(arrowstyle='->', color='darkgreen', lw=2))
            
            # Percentual de economia
            economia_percent = ((height1 - height2) / height1) * 100
            plt.text((bar1.get_x() + bar2.get_x() + bar2.get_width())/2., 
                    max(height1, height2) + 0.08,
                    f'-{economia_percent:.1f}%', ha='center', va='bottom', 
                    fontsize=11, fontweight='bold', color='darkgreen')
    
    # Destacar máquinas pds_v6 com anotações
    pds_v6_machines = df_original[df_original['is_pds_v6']]['worker_type'].tolist()
    for i, machine in enumerate(df_original['worker_type']):
        if machine in pds_v6_machines:
            # Adicionar destaque visual
            plt.axvspan(i - 0.4, i + 0.4, alpha=0.1, color='green', zorder=0)
    
    # Personalizar legenda
    legend_elements = [
        plt.Rectangle((0,0),1,1, facecolor='lightcoral', alpha=0.8, label='Custo Sem Alteração'),
        plt.Rectangle((0,0),1,1, facecolor='lightgreen', alpha=0.8, label='Custo com Desconto 45% (pds_v6)')
    ]
    plt.legend(handles=legend_elements, loc='upper right', fontsize=12)
    
    # Adicionar grid
    plt.grid(True, alpha=0.3, axis='y')
    
    # Adicionar nota explicativa
    plt.figtext(0.5, 0.02, 
               'Nota: Apenas as máquinas da família pds_v6 receberam desconto de 45% no componente Azure Compute',
               ha='center', fontsize=10, style='italic')
    
    plt.tight_layout()
    plt.subplots_adjust(bottom=0.15)
    plt.savefig('/home/ubuntu/impacto_custo_customizado.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print("Gráfico customizado salvo como: impacto_custo_customizado.png")
    
    # Criar também uma versão simplificada apenas com as máquinas pds_v6
    plt.figure(figsize=(12, 8))
    
    # Filtrar apenas máquinas pds_v6
    pds_v6_data = df_original[df_original['is_pds_v6']].copy()
    pds_v6_discounted = df_discounted[df_discounted['is_pds_v6']].copy()
    
    x_pds = np.arange(len(pds_v6_data))
    
    # Criar barras para máquinas pds_v6
    bars1 = plt.bar(x_pds - width/2, pds_v6_data['Total em $'], width, 
                   label='Custo Original', alpha=0.8, color='lightcoral')
    bars2 = plt.bar(x_pds + width/2, pds_v6_discounted['Total em $'], width, 
                   label='Com Desconto 45%', alpha=0.8, color='lightgreen')
    
    plt.xlabel('Máquinas pds_v6', fontsize=14)
    plt.ylabel('Custo Total (USD)', fontsize=14)
    plt.title('Impacto do Desconto de 45% - Foco nas Máquinas pds_v6', fontsize=16, pad=20)
    plt.xticks(x_pds, pds_v6_data['worker_type'], rotation=0)
    
    # Adicionar valores e percentuais
    for i, (bar1, bar2) in enumerate(zip(bars1, bars2)):
        height1 = bar1.get_height()
        height2 = bar2.get_height()
        
        # Valores
        plt.text(bar1.get_x() + bar1.get_width()/2., height1 + 0.01,
                f'${height1:.2f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
        plt.text(bar2.get_x() + bar2.get_width()/2., height2 + 0.01,
                f'${height2:.2f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        # Economia
        economia = height1 - height2
        economia_percent = (economia / height1) * 100
        plt.text((bar1.get_x() + bar2.get_x() + bar2.get_width())/2., 
                max(height1, height2) + 0.05,
                f'Economia: ${economia:.2f}\n({economia_percent:.1f}%)', 
                ha='center', va='bottom', fontsize=10, fontweight='bold', color='darkgreen')
    
    plt.legend(fontsize=12)
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig('/home/ubuntu/impacto_pds_v6_foco.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print("Gráfico focado em pds_v6 salvo como: impacto_pds_v6_foco.png")

if __name__ == "__main__":
    create_custom_impact_chart()
    print("\n=== GRÁFICOS CUSTOMIZADOS CRIADOS ===")
    print("1. impacto_custo_customizado.png - Todas as máquinas com destaque para pds_v6")
    print("2. impacto_pds_v6_foco.png - Foco apenas nas máquinas pds_v6")

