import pandas as pd
import os
from pathlib import Path
import shutil
from datetime import datetime

print("="*70)
print("🔧 REORGANIZADOR - GITHUB ACTIONS")
print("="*70)

# ========== CAMINHOS (estrutura do GitHub) ==========
PASTA_BASE = Path(__file__).parent
PASTA_DADOS = PASTA_BASE / "dados"
PASTA_RAW_INSTALACAO = PASTA_DADOS / "raw" / "instalacao"
PASTA_RAW_CONSULTORIA = PASTA_DADOS / "raw" / "consultoria"
PASTA_BACKUPS = PASTA_DADOS / "backups"

# Criar pastas se não existirem
PASTA_BACKUPS.mkdir(parents=True, exist_ok=True)

# ========== BACKUP DOS CSVS ==========
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

def fazer_backup_csv(caminho):
    if caminho.exists():
        backup = PASTA_BACKUPS / f"{caminho.stem}_backup_{timestamp}{caminho.suffix}"
        shutil.copy2(caminho, backup)
        print(f"   ✅ Backup criado: {backup.name}")

# ========== PROCESSAR PIPELINE ==========
def processar_pipeline(pasta_raw, arquivo_final, nome_pipeline):
    print(f"\n{'='*50}")
    print(f"📂 PROCESSANDO {nome_pipeline}")
    print('='*50)

    if not pasta_raw.exists():
        print(f"⚠️ Pasta {pasta_raw} não encontrada. Pulando...")
        return

    contato_path = pasta_raw / "CONTATO.csv"
    empresa_path = pasta_raw / "EMPRESA.csv"

    if not contato_path.exists() or not empresa_path.exists():
        print(f"❌ CONTATO.csv ou EMPRESA.csv não encontrados em {pasta_raw}")
        return

    # Lê os CSVs
    df_contato = pd.read_csv(contato_path, dtype=str, sep=',', encoding='utf-8-sig')
    df_empresa = pd.read_csv(empresa_path, dtype=str, sep=',', encoding='utf-8-sig')

    # Merge
    df_merged = df_empresa.merge(
        df_contato[['ID_SL', 'PrimeiroNome', 'Sobrenome', 'Email', 'DDD_Telefone']],
        on='ID_SL',
        how='left'
    )
    df_merged['NOME_CONTATO'] = df_merged['PrimeiroNome'] + ' ' + df_merged['Sobrenome']

    # Prepara dados
    colunas = ['CNPJ_Completo', 'ID_SL', 'Nome da Empresa', 'NOME_CONTATO', 'CNAE_Principal']
    df_novos = df_merged[colunas].copy()
    df_novos.columns = ['CNPJ', 'IDSL', 'NOME_EMPRESA', 'NOME_CONTATO', 'SEGMENTO']
    df_novos['CNPJ'] = df_novos['CNPJ'].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)
    df_novos['SEGMENTO'] = df_novos['SEGMENTO'].str.upper()

    # Separa C1 (consultoria) e T1 (restante)
    df_novos_c1 = df_novos[df_novos['SEGMENTO'] == 'CONSULTORIA'].copy()
    df_novos_t1 = df_novos[df_novos['SEGMENTO'] != 'CONSULTORIA'].copy()

    # Lê o CSV existente (se houver)
    if arquivo_final.exists():
        df_existente = pd.read_csv(arquivo_final, dtype=str, sep=';', encoding='utf-8-sig')
    else:
        df_existente = pd.DataFrame(columns=['CNPJ', 'IDSL', 'NOME_EMPRESA', 'NOME_CONTATO', 'SEGMENTO', 'STATUS'])

    # Filtra duplicatas (pelo IDSL)
    ids_existentes = set(df_existente['IDSL'].tolist())
    df_novos_filtrado = df_novos_t1[~df_novos_t1['IDSL'].isin(ids_existentes)]

    # Se for C1, adiciona os de consultoria
    if nome_pipeline == "C1":
        df_novos_filtrado = df_novos_c1[~df_novos_c1['IDSL'].isin(ids_existentes)]

    # Concatena
    df_atualizado = pd.concat([df_existente, df_novos_filtrado], ignore_index=True)

    # Salva
    df_atualizado.to_csv(arquivo_final, index=False, sep=';', encoding='utf-8-sig')
    print(f"   ✅ {nome_pipeline}: {len(df_existente)} → {len(df_atualizado)} (+{len(df_atualizado)-len(df_existente)})")

# ========== EXECUTAR ==========
print("\n📂 Verificando pastas...")

# T1
arquivo_t1 = PASTA_DADOS / "CRM-HUBSPOT-T1.csv"
fazer_backup_csv(arquivo_t1)
processar_pipeline(PASTA_RAW_INSTALACAO, arquivo_t1, "T1")

# C1
arquivo_c1 = PASTA_DADOS / "CRM-HUBSPOT-C1.csv"
fazer_backup_csv(arquivo_c1)
processar_pipeline(PASTA_RAW_CONSULTORIA, arquivo_c1, "C1")

print("\n" + "="*70)
print("✅ REORGANIZADOR CONCLUÍDO!")
print(f"💾 Backups salvos em: {PASTA_BACKUPS}")
print("="*70)
