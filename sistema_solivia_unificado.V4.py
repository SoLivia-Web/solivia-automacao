import os
import json
import pandas as pd
import glob
import re
import time
import random
import sys
import argparse
from openai import OpenAI
from hubspot import HubSpot
from datetime import datetime, timedelta
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ================= CONFIGURAÇÕES GLOBAIS =================
DEEPSEEK_KEY = os.getenv("DEEPSEEK_KEY")
HUBSPOT_TOKEN = os.getenv("HUBSPOT_TOKEN")
MEU_OWNER_ID = os.getenv("MEU_OWNER_ID")
PORTAL_ID = os.getenv("PORTAL_ID")

# ================= DEPURAÇÃO =================
print("=" * 60)
print("🔍 DIAGNÓSTICO DE VARIÁVEIS DE AMBIENTE")
print("=" * 60)
print(f"🔑 DEEPSEEK_KEY: {DEEPSEEK_KEY[:10] + '...' if DEEPSEEK_KEY else '❌ VAZIO'}")
print(f"🔑 HUBSPOT_TOKEN: {HUBSPOT_TOKEN[:10] + '...' if HUBSPOT_TOKEN else '❌ VAZIO'}")
print(f"👤 MEU_OWNER_ID: {MEU_OWNER_ID if MEU_OWNER_ID else '❌ VAZIO'}")
print(f"🏢 PORTAL_ID: {PORTAL_ID if PORTAL_ID else '❌ VAZIO'}")
print("=" * 60)

if not all([DEEPSEEK_KEY, HUBSPOT_TOKEN, MEU_OWNER_ID, PORTAL_ID]):
    raise ValueError("Variáveis de ambiente não configuradas. Crie um arquivo .env com as chaves.")

# ================= ESTRUTURA DE PASTAS =================
PASTA_BASE = Path(__file__).parent
PASTA_DADOS = PASTA_BASE / "dados"
PASTA_TEMPLATES = PASTA_BASE / "templates"
PASTA_ESTADO = PASTA_BASE / "estado"
PASTA_LOGS = PASTA_BASE / "logs"
PASTA_BACKUPS = PASTA_ESTADO / "backups"

# Criar pastas se não existirem
for pasta in [PASTA_DADOS, PASTA_TEMPLATES, PASTA_ESTADO, PASTA_LOGS, PASTA_BACKUPS]:
    pasta.mkdir(parents=True, exist_ok=True)

# ========== ARQUIVOS DE INSTALAÇÃO ==========
CAMINHO_TRABALHO_INST = PASTA_DADOS / "CRM-HUBSPOT-T1.csv"
PASTA_DATABASE = PASTA_DADOS
ARQUIVO_ESTADO_INST = PASTA_ESTADO / "estado_unificado.json"
ARQUIVO_RELATORIO_INST = PASTA_LOGS / "relatorio_diario.txt"
CHECKPOINT_INST = PASTA_BASE / "checkpoint.txt"
ARQUIVO_ERROS_INST = PASTA_ESTADO / "erros_v2.json"
FINALIZADOS_INST = PASTA_ESTADO / "finalizados_inst.json"
NAO_ENCONTRADOS_INST = PASTA_ESTADO / "nao_encontrados_inst.json"
CACHE_FALLBACK_INST = PASTA_ESTADO / "cache_fallback_inst.json"
DIAS_PARA_DECISAO_INST = 45

# ========== ARQUIVOS DE CONSULTORIA ==========
CAMINHO_CSV_EMPREENDIMENTOS = PASTA_DADOS / "empreendimentos_completo_com_descricao_cnae.csv"
CAMINHO_CSV_SOCIOS = PASTA_DADOS / "planilha_final_ROBUSTA.csv"
CAMINHO_TRABALHO_CONS = PASTA_DADOS / "CRM-HUBSPOT-C1.csv"
ARQUIVO_ESTADO_CONS = PASTA_ESTADO / "estado_consultoria.json"
ARQUIVO_RELATORIO_CONS = PASTA_LOGS / "relatorio_consultoria.txt"
CHECKPOINT_CONS = PASTA_BASE / "checkpoint_consultoria.txt"
ARQUIVO_ERROS_CONS = PASTA_ESTADO / "erros_consultoria.json"
FINALIZADOS_CONS = PASTA_ESTADO / "finalizados_cons.json"
NAO_ENCONTRADOS_CONS = PASTA_ESTADO / "nao_encontrados_cons.json"
CACHE_FALLBACK_CONS = PASTA_ESTADO / "cache_fallback_cons.json"
DIAS_PARA_DECISAO_CONS = 30

PASTA_TEMPLATES_CONS = PASTA_TEMPLATES / "TXT CONSULTORIA"
LINK_FORMULARIO_FIXO = "https://u737g.share.hsforms.com/2kgPIh9gKRQ-UhQt6T1CXwQ"

# ================= LOGGING =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[
        logging.FileHandler(PASTA_LOGS / "sistema_unificado.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ================= CLIENTES API =================
# Inicializa cliente DeepSeek
client_ds = OpenAI(api_key=DEEPSEEK_KEY, base_url="https://api.deepseek.com")

# Inicializa HubSpot com token de acesso pessoal (hubspot-client)
print("🔍 Instanciando HubSpot com access_token...")
try:
    hubspot = HubSpot(access_token=HUBSPOT_TOKEN)
    logger.info("✅ HubSpot inicializado com sucesso.")
except Exception as e:
    logger.error(f"❌ Falha ao inicializar HubSpot: {e}")
    raise

# ================= FUNÇÕES DE BACKUP =================
def fazer_backup_automatico(arquivo_json):
    """Faz backup de um arquivo JSON antes de sobrescrevê-lo."""
    if not arquivo_json.exists():
        return
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = PASTA_BACKUPS / f"{arquivo_json.stem}_{timestamp}{arquivo_json.suffix}"
    import shutil
    shutil.copy2(arquivo_json, backup_path)
    logger.info(f"📁 Backup criado: {backup_path.name}")

def salvar_estado_com_backup(estado, arquivo):
    """Salva estado com backup automático."""
    fazer_backup_automatico(arquivo)
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)

# ================= FUNÇÕES COM RETRY =================
@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
def deepseek_create(messages, temperature, enable_search=False):
    kwargs = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": temperature,
    }
    if enable_search:
        kwargs["extra_body"] = {"enable_search": True}
    return client_ds.chat.completions.create(**kwargs)

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
def buscar_contato_por_idsl(idsl):
    public_object_search_request = {
        "filterGroups": [{
            "filters": [{
                "propertyName": "id_sl",
                "operator": "EQ",
                "value": idsl
            }]
        }],
        "properties": ["hs_lead_status"]
    }
    busca = hubspot.crm.contacts.search_api.do_search(
        public_object_search_request=public_object_search_request
    )
    if not busca.results:
        return None, None
    contato = busca.results[0]
    status = contato.properties.get("hs_lead_status", "")
    return contato.id, status

@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=2, max=30), reraise=True)
def hubspot_create_task(payload):
    return hubspot.crm.objects.tasks.basic_api.create(simple_public_object_input_for_create=payload)

# ================= FUNÇÕES AUXILIARES =================
def gerar_link_contato(contato_id):
    return f"https://app.hubspot.com/contacts/{PORTAL_ID}/record/0-1/{contato_id}"

def proximo_dia_util(data_base, dias_para_somar):
    data_final = data_base
    dias_adicionados = 0
    while dias_adicionados < dias_para_somar:
        data_final += timedelta(days=1)
        if data_final.weekday() < 5:
            dias_adicionados += 1
    return data_final.replace(hour=9, minute=0, second=0, microsecond=0)

def formatar_para_html_hubspot(texto_markdown):
    texto_html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', texto_markdown)
    texto_html = texto_html.replace('\n', '<br>')
    return texto_html

def converter_notacao_cientifica(valor):
    if pd.isna(valor) or valor == "":
        return ""
    try:
        valor_ajustado = str(valor).replace(',', '.')
        return str(int(float(valor_ajustado))).zfill(14)
    except:
        num = "".join(filter(str.isdigit, str(valor)))
        return num.zfill(14) if num else ""

def criar_tarefa_hubspot(assunto, corpo, contato_id, dias_uteis):
    data_venc = proximo_dia_util(datetime.now(), dias_uteis)
    timestamp_ms = int(data_venc.timestamp() * 1000)
    tarefa_input = {
        "properties": {
            "hs_timestamp": timestamp_ms,
            "hs_task_subject": assunto,
            "hs_task_body": corpo,
            "hs_task_status": "NOT_STARTED",
            "hubspot_owner_id": MEU_OWNER_ID
        },
        "associations": [
            {
                "to": {"id": contato_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}]
            }
        ]
    }
    try:
        response = hubspot_create_task(tarefa_input)
        link = gerar_link_contato(contato_id)
        logger.info(f"✅ Tarefa '{assunto}' criada! ID: {response.id} - {link}")
        return response.id
    except Exception as e:
        logger.error(f"❌ Erro ao criar tarefa '{assunto}': {e}")
        return None

def buscar_emails_abertos_ordenados(contato_id):
    emails_abertos = []
    try:
        associacoes = hubspot.crm.associations.v4.basic_api.get_page("contact", contato_id, "email")
        for assoc in associacoes.results:
            try:
                email = hubspot.crm.objects.basic_api.get_by_id(
                    "email", assoc.to_object_id,
                    properties=["hs_email_subject", "hs_email_open_count", "hs_email_last_open_date"]
                )
                props = email.properties
                assunto = props.get("hs_email_subject", "").strip()
                open_count_raw = props.get("hs_email_open_count", "0")
                data_abertura = props.get("hs_email_last_open_date", "")
                try:
                    open_count = int(float(open_count_raw))
                except:
                    open_count = 0
                if open_count > 0 and assunto:
                    emails_abertos.append({
                        "assunto": assunto,
                        "aberturas": open_count,
                        "data_abertura": data_abertura
                    })
            except Exception:
                continue
        emails_abertos.sort(key=lambda x: x["data_abertura"])
        return emails_abertos
    except Exception as e:
        logger.error(f"Erro ao buscar emails abertos: {e}")
        return []

# ================= FUNÇÕES DE ESTADO (com backup) =================
def carregar_estado(arquivo):
    if arquivo.exists():
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"Arquivo de estado {arquivo} corrompido. Recriando...")
            arquivo.unlink()
            return {}
    return {}

def obter_estado_contato(contato_id, arquivo_estado):
    estado = carregar_estado(arquivo_estado)
    if contato_id not in estado:
        estado[contato_id] = {
            "used_subjects": [],
            "etapas_criadas": [],
            "textos": {},
            "decisao_final": None,
            "data_primeiro_contato": None,
            "finalizado": False
        }
    else:
        estado[contato_id].setdefault("used_subjects", [])
        estado[contato_id].setdefault("etapas_criadas", [])
        estado[contato_id].setdefault("textos", {})
        estado[contato_id].setdefault("decisao_final", None)
        estado[contato_id].setdefault("data_primeiro_contato", None)
        estado[contato_id].setdefault("finalizado", False)
    return estado, estado[contato_id]

def salvar_estado(estado, arquivo):
    salvar_estado_com_backup(estado, arquivo)

def carregar_erros(arquivo_erros):
    if arquivo_erros.exists():
        try:
            with open(arquivo_erros, 'r', encoding='utf-8') as f:
                dados = json.load(f)
                return set(dados.get("erros", []))
        except:
            return set()
    return set()

def salvar_erros(erros_set, arquivo_erros):
    with open(arquivo_erros, 'w', encoding='utf-8') as f:
        json.dump({"erros": list(erros_set)}, f, indent=2)

def carregar_finalizados(arquivo):
    if arquivo.exists():
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def salvar_finalizados(finalizados_set, arquivo):
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(sorted(list(finalizados_set)), f, indent=2)

def carregar_nao_encontrados(arquivo):
    if arquivo.exists():
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def salvar_nao_encontrados(nao_encontrados_set, arquivo):
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(sorted(list(nao_encontrados_set)), f, indent=2)

def carregar_cache_fallback(arquivo):
    if arquivo.exists():
        try:
            with open(arquivo, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def salvar_cache_fallback(cache, arquivo):
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

# ================= PIPELINE INSTALAÇÃO (adaptado para CSV + STATUS) =================
def construir_indice_csv(pasta):
    arquivos = glob.glob(os.path.join(pasta, "*.csv"))
    if not arquivos:
        return {}
    idx = {}
    codificacoes = ['utf-8', 'latin-1', 'cp1252', 'utf-8-sig']
    for arquivo in arquivos:
        for enc in codificacoes:
            try:
                df = pd.read_csv(arquivo, dtype=str, encoding=enc, sep=None, engine='python',
                                 on_bad_lines='skip', keep_default_na=False)
                col_cnpj = df.columns[0]
                df[col_cnpj] = df[col_cnpj].astype(str).fillna('')
                df[col_cnpj] = df[col_cnpj].str.replace(r'\D', '', regex=True).str.zfill(14)
                
                for _, row in df.iterrows():
                    cnpj = row[col_cnpj]
                    if cnpj and len(cnpj) == 14 and cnpj not in idx:
                        dados = row.to_dict()
                        dados['NOME_EMPRESA'] = dados.get('Razao', '') or dados.get('Nome_Fantasia', '')
                        dados['RAZAO_SOCIAL'] = dados.get('Razao', '')
                        dados['NOME_FANTASIA'] = dados.get('Nome_Fantasia', '')
                        dados['SOCIO'] = dados.get('Socios_Nome', '').split('|')[0] if dados.get('Socios_Nome') else ''
                        dados['CIDADE'] = dados.get('Municipio', '')
                        dados['EMAIL'] = dados.get('Email', '')
                        idx[cnpj] = dados
                break
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.warning(f"Erro ao ler {arquivo} com codificação {enc}: {e}")
                continue
    logger.info(f"Índice CSV construído com {len(idx)} registros.")
    return idx

def buscar_dados_por_cnpj(cnpj, indice, nome_empresa_fallback=None):
    cnpj_limpo = ''.join(filter(str.isdigit, str(cnpj)))
    if not cnpj_limpo:
        return None
    
    resultado = indice.get(cnpj_limpo.zfill(14))
    if resultado:
        return resultado
    
    if not nome_empresa_fallback or not str(nome_empresa_fallback).strip():
        return None
    
    nome_busca = str(nome_empresa_fallback).strip().upper()
    nome_busca = re.sub(r'[^\w\s]', '', nome_busca)
    
    if len(cnpj_limpo) >= 5:
        prefixo_5 = cnpj_limpo[:5]
        candidatos = [(c, d) for c, d in indice.items() if c.startswith(prefixo_5)]
        
        for cnpj_idx, dados in candidatos:
            razao = str(dados.get('RAZAO_SOCIAL', '')).upper()
            razao = re.sub(r'[^\w\s]', '', razao)
            fantasia = str(dados.get('NOME_FANTASIA', '')).upper()
            fantasia = re.sub(r'[^\w\s]', '', fantasia)
            
            if nome_busca == razao or nome_busca == fantasia:
                logger.info(f"   🔄 Fallback PREFIXO(5)+NOME: '{nome_empresa_fallback}' -> CNPJ {cnpj_idx}")
                return dados
        
        if len(candidatos) == 1:
            logger.info(f"   🔄 Fallback PREFIXO(5) ÚNICO: -> CNPJ {candidatos[0][0]}")
            return candidatos[0][1]
    
    for cnpj_idx, dados in indice.items():
        razao = str(dados.get('RAZAO_SOCIAL', '')).upper()
        razao = re.sub(r'[^\w\s]', '', razao)
        fantasia = str(dados.get('NOME_FANTASIA', '')).upper()
        fantasia = re.sub(r'[^\w\s]', '', fantasia)
        
        if nome_busca == razao or nome_busca == fantasia:
            logger.info(f"   🔄 Fallback NOME EXATO: '{nome_empresa_fallback}' -> CNPJ {cnpj_idx}")
            return dados
    
    return None

def gerar_email_instalacao(segmento, dados_lead=None, texto_anterior=None, toque_idx=0, pesquisa_online=False):
    segmento_upper = segmento.upper().strip()
    pasta_segmento = PASTA_TEMPLATES / f"TXT INSTALAÇÃO" / segmento_upper
    if not pasta_segmento.exists():
        possiveis = list(PASTA_TEMPLATES.glob(f"TXT INSTALAÇÃO/**/{segmento_upper}"))
        if possiveis:
            pasta_segmento = possiveis[0]
        else:
            raise FileNotFoundError(f"Pasta do segmento não encontrada: {pasta_segmento}")
    nomes_toques = ["TOQUE 1.txt", "TOQUE 2.txt", "TOQUE 3.txt", "TOQUE 4.txt"]
    if toque_idx >= len(nomes_toques):
        raise ValueError(f"Índice de toque inválido: {toque_idx}")
    arquivo_instrucao = pasta_segmento / nomes_toques[toque_idx]
    if not arquivo_instrucao.exists():
        raise FileNotFoundError(f"Arquivo de instrução não encontrado: {arquivo_instrucao}")
    with open(arquivo_instrucao, 'r', encoding='utf-8') as f:
        instrucao = f.read()
    mensagens = [{"role": "system", "content": "Você é o Nicolas, consultor da SoLivia Engenharia. Escreva e-mails ultra-personalizados seguindo rigorosamente as instruções."}]
    if texto_anterior:
        mensagens.append({"role": "user", "content": f"Considere o seguinte e-mail anterior como contexto:\n{texto_anterior}"})
    if dados_lead:
        dados_str = (f"Empresa: {dados_lead.get('NOME_EMPRESA', '')}\n"
                     f"Sócio: {dados_lead.get('SOCIO', '')}\n"
                     f"Cidade: {dados_lead.get('CIDADE', '')}\n"
                     f"Email: {dados_lead.get('EMAIL', '')}\n")
        prompt = f"{instrucao}\n\nDADOS DO LEAD:\n{dados_str}\n\nRedija o e-mail."
    else:
        prompt = f"{instrucao}\n\nRedija o e-mail agora."
    mensagens.append({"role": "user", "content": prompt})
    try:
        response = deepseek_create(mensagens, 0.6, enable_search=pesquisa_online)
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Erro ao gerar e-mail: {e}")
        raise

def verificar_decisao_final_inst(estado_contato, contato_id):
    if estado_contato["decisao_final"] is not None:
        return False
    if estado_contato["data_primeiro_contato"] is None:
        return False
    data_inicio = datetime.fromisoformat(estado_contato["data_primeiro_contato"])
    if datetime.now() < data_inicio + timedelta(days=DIAS_PARA_DECISAO_INST):
        return False
    emails_abertos = buscar_emails_abertos_ordenados(contato_id)
    total_aberturas = sum(e["aberturas"] for e in emails_abertos)
    decisao = "NUTRIÇÃO" if total_aberturas > 4 else "DESCARTE"
    logger.info(f"🎯 Decisão final para {gerar_link_contato(contato_id)}: {decisao} (total aberturas={total_aberturas})")
    corpo = f"Decisão baseada em {total_aberturas} aberturas de e-mail no período de {DIAS_PARA_DECISAO_INST} dias."
    criar_tarefa_hubspot(decisao, corpo, contato_id, 0)
    estado_contato["decisao_final"] = decisao
    estado_contato["finalizado"] = True
    return True

def processar_lead_instalacao(contato_id, dados_lead, segmento, relatorio, arquivo_estado, pesquisa_online, df, idx_linha):
    estado_geral, estado_contato = obter_estado_contato(contato_id, arquivo_estado)
    if estado_contato.get("finalizado", False):
        return
    if "T1" not in estado_contato["etapas_criadas"]:
        logger.info(f"🚀 Novo lead instalação: {dados_lead.get('NOME_EMPRESA', 'Desconhecido')} - {gerar_link_contato(contato_id)} (Segmento: {segmento})")
        texto_t1 = gerar_email_instalacao(segmento, dados_lead=dados_lead, toque_idx=0, pesquisa_online=pesquisa_online)
        criar_tarefa_hubspot("T1", formatar_para_html_hubspot(texto_t1), contato_id, 2)
        estado_contato["etapas_criadas"] = ["T1"]
        estado_contato["textos"]["T1"] = texto_t1
        estado_contato["data_primeiro_contato"] = datetime.now().isoformat()
        df.at[idx_linha, 'STATUS'] = 'T1'
        salvar_estado(estado_geral, arquivo_estado)
        relatorio["t1_criadas"] += 1
        return
    etapas = estado_contato["etapas_criadas"]
    if len(etapas) >= 4:
        if verificar_decisao_final_inst(estado_contato, contato_id):
            df.at[idx_linha, 'STATUS'] = 'FINALIZADO'
            salvar_estado(estado_geral, arquivo_estado)
            relatorio["decisoes_finais"] += 1
        return
    used_subjects = set(estado_contato["used_subjects"])
    proximo_idx = len(etapas)
    rotulos = ["CASE", "BUMP", "FINAL"]
    proximo_rotulo = rotulos[proximo_idx - 1]
    emails_abertos = buscar_emails_abertos_ordenados(contato_id)
    if not emails_abertos:
        return
    emails_disponiveis = [e for e in emails_abertos if e["assunto"] not in used_subjects]
    if not emails_disponiveis:
        return
    email_usar = emails_disponiveis[0]
    logger.info(f"➡️ Avançando para {proximo_rotulo} com base no email '{email_usar['assunto']}' - {gerar_link_contato(contato_id)}")
    etapa_anterior = etapas[-1]
    texto_anterior = estado_contato["textos"].get(etapa_anterior)
    if not texto_anterior:
        logger.error("Texto da etapa anterior não encontrado!")
        return
    novo_texto = gerar_email_instalacao(segmento, dados_lead=dados_lead, texto_anterior=texto_anterior, toque_idx=proximo_idx, pesquisa_online=pesquisa_online)
    dias = 2 if proximo_rotulo == "CASE" else 3
    criar_tarefa_hubspot(proximo_rotulo, formatar_para_html_hubspot(novo_texto), contato_id, dias)
    used_subjects.add(email_usar["assunto"])
    estado_contato["used_subjects"] = list(used_subjects)
    estado_contato["etapas_criadas"].append(proximo_rotulo)
    estado_contato["textos"][proximo_rotulo] = novo_texto
    df.at[idx_linha, 'STATUS'] = proximo_rotulo
    salvar_estado(estado_geral, arquivo_estado)
    relatorio["etapas_avancadas"] += 1

def executar_pipeline_instalacao(modo, pesquisa_online=False, apenas_catalogar=False):
    logger.info("="*60)
    if apenas_catalogar:
        logger.info("📋 MODO CATALOGAÇÃO: Apenas identificando leads não qualificados (sem criar tarefas).")
    else:
        logger.info("🚀 PIPELINE DE INSTALAÇÃO (Prospecção de novas instalações)")
    logger.info(f"Modo: {'COMPLETO' if modo == 'full' else 'APENAS ERROS'}")
    logger.info(f"Pesquisa online: {'ATIVADA' if pesquisa_online else 'DESATIVADA'}")
    logger.info("="*60)

    relatorio = {"t1_criadas": 0, "etapas_avancadas": 0, "decisoes_finais": 0, "erros": 0}
    finalizados = carregar_finalizados(FINALIZADOS_INST)
    nao_encontrados = carregar_nao_encontrados(NAO_ENCONTRADOS_INST)
    cache_fallback = carregar_cache_fallback(CACHE_FALLBACK_INST)
    STATUS_IGNORAR = {"UNQUALIFIED"}

    if not CAMINHO_TRABALHO_INST.exists():
        logger.error(f"Arquivo de entrada não encontrado: {CAMINHO_TRABALHO_INST}")
        return

    try:
        df = pd.read_csv(CAMINHO_TRABALHO_INST, dtype=str, encoding='utf-8-sig', sep=';')
    except Exception as e:
        logger.error(f"Erro ao ler CSV de instalação: {e}")
        return

    if 'STATUS' not in df.columns:
        df['STATUS'] = ''

    for idx, row in df.iterrows():
        idsl = str(row['IDSL']).strip()
        if idsl in finalizados:
            df.at[idx, 'STATUS'] = 'FINALIZADO'
        elif idsl in nao_encontrados:
            df.at[idx, 'STATUS'] = 'NAO_ENCONTRADO'
        elif pd.isna(df.at[idx, 'STATUS']) or df.at[idx, 'STATUS'] == '':
            df.at[idx, 'STATUS'] = 'EM_ANDAMENTO'

    df_processar = df[df['STATUS'].isin(['', 'EM_ANDAMENTO'])].copy()
    total_ativos = len(df_processar)
    logger.info(f"📊 Total de leads ATIVOS para processar: {total_ativos} (de {len(df)} totais)")

    if total_ativos == 0:
        logger.info("✅ Nenhum lead ativo. Encerrando.")
        return

    csv_indice = construir_indice_csv(PASTA_DADOS) if PASTA_DADOS.exists() else {}

    erros_atuais = set(carregar_erros(ARQUIVO_ERROS_INST))

    if modo == "errors":
        if not erros_atuais:
            logger.info("Nenhum erro anterior registrado. Nada a reprocessar.")
            return
        indices_processar = [idx for idx in df_processar.index if idx in erros_atuais]
        checkpoint_usado = False
    else:
        indices_processar = df_processar.index.tolist()
        checkpoint_usado = True

    contador = 0
    for idx in indices_processar:
        contador += 1
        row = df_processar.loc[idx]
        idsl_raw = str(row['IDSL']).strip()
        cnpj_raw = str(row['CNPJ']).strip()
        nome_empresa = str(row.get('NOME_EMPRESA', '')).strip()
        segmento = str(row.get('SEGMENTO', '')).strip()

        if not segmento:
            logger.warning(f"Linha {idx+1}: Segmento vazio. Pulando.")
            relatorio["erros"] += 1
            erros_atuais.add(idx)
            continue

        cnpj_limpo = converter_notacao_cientifica(cnpj_raw)
        if not cnpj_limpo:
            logger.warning(f"Linha {idx+1}: CNPJ inválido.")
            relatorio["erros"] += 1
            erros_atuais.add(idx)
            continue

        dados_lead = None
        if idsl_raw in cache_fallback:
            dados_lead = cache_fallback[idsl_raw]
            logger.info(f"⚡ Cache fallback usado para {idsl_raw}")
        else:
            dados_lead = buscar_dados_por_cnpj(cnpj_limpo, csv_indice, nome_empresa)
            if dados_lead:
                cache_fallback[idsl_raw] = dados_lead
                salvar_cache_fallback(cache_fallback, CACHE_FALLBACK_INST)

        if not dados_lead:
            logger.warning(f"CNPJ {cnpj_limpo} não encontrado na base técnica.")
            relatorio["erros"] += 1
            erros_atuais.add(idx)
            nao_encontrados.add(idsl_raw)
            salvar_nao_encontrados(nao_encontrados, NAO_ENCONTRADOS_INST)
            df.at[idx, 'STATUS'] = 'NAO_ENCONTRADO'
            continue

        try:
            contato_id, lead_status = buscar_contato_por_idsl(idsl_raw)
            if not contato_id:
                logger.warning(f"Contato com IDSL {idsl_raw} não encontrado no HubSpot.")
                relatorio["erros"] += 1
                erros_atuais.add(idx)
                continue

            logger.info(f"✅ Contato encontrado: {gerar_link_contato(contato_id)} (status: {lead_status})")

            if lead_status and lead_status.upper() in STATUS_IGNORAR:
                logger.info(f"👎 Lead {idsl_raw} com status '{lead_status}' -> adicionando aos finalizados.")
                finalizados.add(idsl_raw)
                salvar_finalizados(finalizados, FINALIZADOS_INST)
                df.at[idx, 'STATUS'] = 'FINALIZADO'
                continue

            if apenas_catalogar:
                continue

            processar_lead_instalacao(contato_id, dados_lead, segmento, relatorio, ARQUIVO_ESTADO_INST, pesquisa_online, df, idx)
            erros_atuais.discard(idx)
        except Exception as e:
            logger.error(f"Erro ao processar lead: {e}", exc_info=True)
            relatorio["erros"] += 1
            erros_atuais.add(idx)

        if checkpoint_usado:
            with open(CHECKPOINT_INST, 'w') as f:
                f.write(str(idx))
        salvar_erros(erros_atuais, ARQUIVO_ERROS_INST)
        
        if contador % 10 == 0:
            logger.info(f"📊 Progresso: {contador}/{len(indices_processar)} | T1={relatorio['t1_criadas']} | Avanç={relatorio['etapas_avancadas']} | Finais={relatorio['decisoes_finais']} | Erros={relatorio['erros']}")
        
        time.sleep(1)

    df.to_csv(CAMINHO_TRABALHO_INST, index=False, encoding='utf-8-sig', sep=';')
    logger.info(f"💾 CSV atualizado com novos STATUS: {CAMINHO_TRABALHO_INST}")

    if not apenas_catalogar:
        with open(ARQUIVO_RELATORIO_INST, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO INSTALAÇÃO - {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write(f"T1 criadas: {relatorio['t1_criadas']}\n")
            f.write(f"Etapas avançadas: {relatorio['etapas_avancadas']}\n")
            f.write(f"Decisões finais: {relatorio['decisoes_finais']}\n")
            f.write(f"Erros nesta execução: {relatorio['erros']}\n")
            f.write(f"Total de erros pendentes: {len(erros_atuais)}\n")
            f.write(f"Total de finalizados: {len(finalizados)}\n")
            f.write(f"Total de CNPJs não encontrados: {len(nao_encontrados)}\n")
            f.write(f"Total em cache de fallback: {len(cache_fallback)}\n")
        logger.info(f"\n📄 Relatório Instalação salvo em {ARQUIVO_RELATORIO_INST}")

    salvar_erros(erros_atuais, ARQUIVO_ERROS_INST)
    salvar_finalizados(finalizados, FINALIZADOS_INST)
    salvar_nao_encontrados(nao_encontrados, NAO_ENCONTRADOS_INST)
    salvar_cache_fallback(cache_fallback, CACHE_FALLBACK_INST)

# ================= PIPELINE CONSULTORIA (adaptado para CSV + STATUS) =================
def carregar_indice_empreendimentos(csv_path):
    if not csv_path.exists():
        logger.error(f"Arquivo CSV não encontrado: {csv_path}")
        return {}
    try:
        df = pd.read_csv(csv_path, dtype=str, encoding='utf-8', sep=None, engine='python', on_bad_lines='skip')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, dtype=str, encoding='latin-1', sep=None, engine='python', on_bad_lines='skip')
    except Exception as e:
        logger.error(f"Erro ao ler CSV: {e}")
        return {}
    
    col_cnpj = 'NumCPFCNPJ'
    if col_cnpj not in df.columns:
        col_cnpj = df.columns[0]
        logger.warning(f"Coluna 'NumCPFCNPJ' não encontrada. Usando primeira coluna: {col_cnpj}")
    
    df[col_cnpj] = df[col_cnpj].astype(str).str.replace(r'\D', '', regex=True).str.zfill(14)
    indice = {}
    for _, row in df.iterrows():
        cnpj = row[col_cnpj]
        if cnpj and len(cnpj) == 14:
            indice[cnpj] = row.to_dict()
    logger.info(f"Índice de empreendimentos carregado com {len(indice)} registros.")
    return indice

def carregar_indice_socios(csv_path):
    if not csv_path.exists():
        logger.warning(f"Arquivo de sócios não encontrado: {csv_path}.")
        return {}
    try:
        df = pd.read_csv(csv_path, dtype=str, encoding='utf-8', sep=None, engine='python', on_bad_lines='skip')
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, dtype=str, encoding='latin-1', sep=None, engine='python', on_bad_lines='skip')
    except Exception as e:
        logger.error(f"Erro ao ler CSV de sócios: {e}")
        return {}
    
    col_id = 'ID_SL'
    col_socio = 'Socios_Nome'
    if col_id not in df.columns or col_socio not in df.columns:
        return {}
    
    df[col_id] = df[col_id].astype(str).str.strip()
    indice = {}
    for _, row in df.iterrows():
        idsl = row[col_id]
        if idsl and idsl != 'nan':
            indice[idsl] = {"Socios_Nome": row.get(col_socio, "")}
    logger.info(f"Índice de sócios carregado com {len(indice)} registros.")
    return indice

def formatar_nome_socio(nome_raw):
    if pd.isna(nome_raw) or not nome_raw or nome_raw == 'nan':
        return ""
    primeiro = nome_raw.split('|')[0].strip()
    palavras = primeiro.lower().split()
    palavras_capitalizadas = [p.capitalize() for p in palavras]
    return ' '.join(palavras_capitalizadas)

def ler_link_laudo():
    caminho_link = PASTA_TEMPLATES / "TXT CONSULTORIA" / "LINK DO LAUDO.txt"
    if not caminho_link.exists():
        return ""
    with open(caminho_link, 'r', encoding='utf-8') as f:
        return f.read().strip()

def ler_template_completo(caminho_template):
    with open(caminho_template, 'r', encoding='utf-8') as f:
        return f.read().strip()

def escolher_template_primeiro_email():
    variacoes = ["TOQUE 1 - A.txt", "TOQUE 1 - B.txt", "TOQUE 1 - C.txt"]
    for v in variacoes:
        if not (PASTA_TEMPLATES / "TXT CONSULTORIA" / v).exists():
            return None
    escolhido = random.choice(variacoes)
    return ler_template_completo(PASTA_TEMPLATES / "TXT CONSULTORIA" / escolhido)

def ler_template_segundo_email():
    caminho = PASTA_TEMPLATES / "TXT CONSULTORIA" / "TOQUE 2.txt"
    if not caminho.exists():
        return None
    return ler_template_completo(caminho)

def formatar_data_br(data_str):
    if not data_str or pd.isna(data_str):
        return ""
    try:
        if isinstance(data_str, str) and '-' in data_str:
            partes = data_str.split('-')
            if len(partes) == 3:
                return f"{partes[2]}/{partes[1]}/{partes[0]}"
        return str(data_str)
    except:
        return str(data_str)

def calcular_idade_em_meses(data_conexao_str):
    if not data_conexao_str or pd.isna(data_conexao_str):
        return 0
    try:
        if '/' in data_conexao_str:
            data = datetime.strptime(data_conexao_str, '%d/%m/%Y')
        else:
            data = datetime.strptime(data_conexao_str, '%Y-%m-%d')
    except:
        return 0
    hoje = datetime.now()
    meses = (hoje.year - data.year) * 12 + (hoje.month - data.month)
    return max(0, meses)

def calcular_perdas(potencia_kwp_str, meses_desde_instalacao, tarifa=0.75, hsp=4.5, pr=0.8, dias=30, perc_perda_extra=0.15):
    try:
        pot_str = str(potencia_kwp_str).replace(',', '.')
        potencia = float(pot_str)
    except:
        return (0.0, 0.0, 0.0)
    
    geracao_mensal_kwh = potencia * hsp * pr * dias
    perda_mensal_kwh = geracao_mensal_kwh * perc_perda_extra
    perda_mensal_reais = perda_mensal_kwh * tarifa
    perda_anual_reais = perda_mensal_reais * 12
    perda_total_reais = perda_mensal_reais * meses_desde_instalacao
    return (round(perda_mensal_reais, 2), round(perda_anual_reais, 2), round(perda_total_reais, 2))

def substituir_placeholders_consultoria(template_texto, dados_lead, dados_socio, link_laudo, link_formulario):
    def limpar_valor(v):
        return "" if pd.isna(v) else str(v)
    
    nome_titular = ""
    if dados_socio and dados_socio.get("Socios_Nome"):
        nome_titular = formatar_nome_socio(dados_socio.get("Socios_Nome"))
    if not nome_titular:
        nome_titular = limpar_valor(dados_lead.get("NomTitularEmpreendimento", ""))
    
    potencia_str = limpar_valor(dados_lead.get("MdaPotenciaInstalada", "0"))
    data_conexao_str = dados_lead.get("DatConexao", "")
    meses = calcular_idade_em_meses(data_conexao_str)
    perda_mensal, perda_anual, perda_total = calcular_perdas(potencia_str, meses)
    
    def fmt_numero(valor):
        return "0,00" if valor == 0 else f"{valor:.2f}".replace(".", ",")
    
    link_laudo_html = f'<a href="{link_laudo}">exemplo de laudo</a>' if link_laudo else ''
    link_formulario_html = f'<a href="{link_formulario}">responda 4 perguntas rápidas.</a>' if link_formulario else ''
    
    substituicoes = {
        "{{NomTitularEmpreendimento}}": nome_titular,
        "{{NomeFantasia}}": limpar_valor(dados_lead.get("NomeFantasia", "")),
        "{{MdaPotenciaInstalada}}": limpar_valor(dados_lead.get("MdaPotenciaInstalada", "")),
        "{{NomMunicipio}}": limpar_valor(dados_lead.get("NomMunicipio", "")),
        "{{SigUF}}": limpar_valor(dados_lead.get("SigUF", "")),
        "{{DatConexao}}": formatar_data_br(dados_lead.get("DatConexao", "")),
        "{{LINK_LAUDO}}": link_laudo_html,
        "{{LINK_FORMULARIO}}": link_formulario_html,
        "{{NomFabricanteInversor}}": limpar_valor(dados_lead.get("NomFabricanteInversor", "")),
        "{{NomModeloInversor}}": limpar_valor(dados_lead.get("NomModeloInversor", "")),
        "{{QtdModulos}}": limpar_valor(dados_lead.get("QtdModulos", "")),
        "{{NomFabricanteModulo}}": limpar_valor(dados_lead.get("NomFabricanteModulo", "")),
        "{{PerdaMensal}}": fmt_numero(perda_mensal),
        "{{PerdaAnual}}": fmt_numero(perda_anual),
        "{{PerdaTotal}}": fmt_numero(perda_total),
    }
    
    texto = template_texto
    for ph, valor in substituicoes.items():
        texto = texto.replace(ph, valor)
    return texto

def gerar_email_consultoria(dados_emp, socio_nome, link_laudo, link_formulario, tipo="C1"):
    if tipo == "C1":
        template_text = escolher_template_primeiro_email()
    elif tipo == "FOLLOW_UP":
        template_text = ler_template_segundo_email()
    else:
        raise ValueError(f"Tipo inválido: {tipo}")
    
    if not template_text:
        raise ValueError("Template não encontrado.")
    
    socio_dict = {"Socios_Nome": socio_nome} if socio_nome else None
    return substituir_placeholders_consultoria(template_text, dados_emp, socio_dict, link_laudo, link_formulario)

def verificar_decisao_final_cons(estado_contato, contato_id):
    if estado_contato.get("decisao_final") is not None:
        return False
    if estado_contato.get("data_primeiro_contato") is None:
        return False
    
    data_inicio = datetime.fromisoformat(estado_contato["data_primeiro_contato"])
    if datetime.now() < data_inicio + timedelta(days=DIAS_PARA_DECISAO_CONS):
        return False
    
    emails_abertos = buscar_emails_abertos_ordenados(contato_id)
    total_aberturas = sum(e["aberturas"] for e in emails_abertos)
    decisao = "NUTRIÇÃO" if total_aberturas > 2 else "DESCARTE"
    logger.info(f"🎯 Decisão final Consultoria para {gerar_link_contato(contato_id)}: {decisao} (aberturas={total_aberturas})")
    corpo = f"Decisão baseada em {total_aberturas} aberturas de e-mail no período de {DIAS_PARA_DECISAO_CONS} dias."
    criar_tarefa_hubspot(decisao, corpo, contato_id, 0)
    estado_contato["decisao_final"] = decisao
    estado_contato["finalizado"] = True
    return True

def processar_lead_consultoria(contato_id, dados_emp, socio_nome, relatorio, df, idx_linha):
    estado_geral, estado_contato = obter_estado_contato(contato_id, ARQUIVO_ESTADO_CONS)
    
    if estado_contato.get("finalizado", False):
        return
    
    link_laudo = ler_link_laudo()
    link_formulario = LINK_FORMULARIO_FIXO
    
    if "C1" not in estado_contato["etapas_criadas"]:
        nome_fantasia = dados_emp.get('NomeFantasia', 'Cliente sem nome fantasia')
        if pd.isna(nome_fantasia) or nome_fantasia == '':
            nome_fantasia = 'Cliente sem nome fantasia'
        
        logger.info(f"🚀 Novo lead Consultoria: {nome_fantasia} - {gerar_link_contato(contato_id)}")
        
        try:
            texto_c1 = gerar_email_consultoria(dados_emp, socio_nome, link_laudo, link_formulario, tipo="C1")
            criar_tarefa_hubspot("C1", formatar_para_html_hubspot(texto_c1), contato_id, 2)
            estado_contato["etapas_criadas"] = ["C1"]
            estado_contato["textos"]["C1"] = texto_c1
            estado_contato["data_primeiro_contato"] = datetime.now().isoformat()
            df.at[idx_linha, 'STATUS'] = 'C1'
            salvar_estado(estado_geral, ARQUIVO_ESTADO_CONS)
            relatorio["c1_criadas"] += 1
        except Exception as e:
            logger.error(f"Erro ao criar C1: {e}")
            relatorio["erros"] += 1
        return
    
    if "C1" in estado_contato["etapas_criadas"] and "FOLLOW_UP" not in estado_contato["etapas_criadas"]:
        if verificar_decisao_final_cons(estado_contato, contato_id):
            df.at[idx_linha, 'STATUS'] = 'FINALIZADO'
            salvar_estado(estado_geral, ARQUIVO_ESTADO_CONS)
            relatorio["decisoes_finais"] += 1
            return
        
        emails_abertos = buscar_emails_abertos_ordenados(contato_id)
        if not emails_abertos:
            return
        
        logger.info(f"📨 Primeiro e-mail aberto! Criando FOLLOW_UP para {gerar_link_contato(contato_id)}")
        
        try:
            texto_followup = gerar_email_consultoria(dados_emp, socio_nome, link_laudo, link_formulario, tipo="FOLLOW_UP")
            criar_tarefa_hubspot("FOLLOW_UP", formatar_para_html_hubspot(texto_followup), contato_id, 3)
            estado_contato["etapas_criadas"].append("FOLLOW_UP")
            estado_contato["textos"]["FOLLOW_UP"] = texto_followup
            df.at[idx_linha, 'STATUS'] = 'FOLLOW_UP'
            salvar_estado(estado_geral, ARQUIVO_ESTADO_CONS)
            relatorio["followups_criados"] += 1
        except Exception as e:
            logger.error(f"Erro ao criar FOLLOW_UP: {e}")
            relatorio["erros"] += 1
        return
    
    if verificar_decisao_final_cons(estado_contato, contato_id):
        df.at[idx_linha, 'STATUS'] = 'FINALIZADO'
        salvar_estado(estado_geral, ARQUIVO_ESTADO_CONS)
        relatorio["decisoes_finais"] += 1

def executar_pipeline_consultoria(modo, apenas_catalogar=False):
    logger.info("="*60)
    if apenas_catalogar:
        logger.info("📋 MODO CATALOGAÇÃO: Apenas identificando leads não qualificados (sem criar tarefas).")
    else:
        logger.info("🚀 PIPELINE DE CONSULTORIA (Diagnóstico solar)")
    logger.info(f"Modo: {'COMPLETO' if modo == 'full' else 'APENAS ERROS'}")
    logger.info("="*60)

    relatorio = {"c1_criadas": 0, "followups_criados": 0, "decisoes_finais": 0, "erros": 0}
    finalizados = carregar_finalizados(FINALIZADOS_CONS)
    nao_encontrados = carregar_nao_encontrados(NAO_ENCONTRADOS_CONS)
    cache_fallback = carregar_cache_fallback(CACHE_FALLBACK_CONS)
    STATUS_IGNORAR = {"UNQUALIFIED"}

    indice_emp = carregar_indice_empreendimentos(CAMINHO_CSV_EMPREENDIMENTOS)
    if not indice_emp:
        logger.error("Nenhum dado carregado. Verifique o caminho do CSV de empreendimentos.")
        return

    indice_socios = carregar_indice_socios(CAMINHO_CSV_SOCIOS)

    if not CAMINHO_TRABALHO_CONS.exists():
        logger.error(f"Arquivo de entrada não encontrado: {CAMINHO_TRABALHO_CONS}")
        return

    try:
        df = pd.read_csv(CAMINHO_TRABALHO_CONS, dtype=str, encoding='utf-8-sig', sep=';')
    except Exception as e:
        logger.error(f"Erro ao ler CSV de consultoria: {e}")
        return

    if 'STATUS' not in df.columns:
        df['STATUS'] = ''

    for idx, row in df.iterrows():
        idsl = str(row['IDSL']).strip()
        if idsl in finalizados:
            df.at[idx, 'STATUS'] = 'FINALIZADO'
        elif idsl in nao_encontrados:
            df.at[idx, 'STATUS'] = 'NAO_ENCONTRADO'
        elif pd.isna(df.at[idx, 'STATUS']) or df.at[idx, 'STATUS'] == '':
            df.at[idx, 'STATUS'] = 'EM_ANDAMENTO'

    df_processar = df[df['STATUS'].isin(['', 'EM_ANDAMENTO'])].copy()
    total_ativos = len(df_processar)
    logger.info(f"📊 Total de leads ATIVOS para processar: {total_ativos} (de {len(df)} totais)")

    if total_ativos == 0:
        logger.info("✅ Nenhum lead ativo. Encerrando.")
        return

    erros_atuais = set(carregar_erros(ARQUIVO_ERROS_CONS))

    if modo == "errors":
        if not erros_atuais:
            logger.info("Nenhum erro anterior registrado. Nada a reprocessar.")
            return
        indices_processar = [idx for idx in df_processar.index if idx in erros_atuais]
        checkpoint_usado = False
    else:
        indices_processar = df_processar.index.tolist()
        checkpoint_usado = True

    contador = 0
    for idx in indices_processar:
        contador += 1
        row = df_processar.loc[idx]
        idsl_raw = str(row['IDSL']).strip()
        cnpj_raw = str(row['CNPJ']).strip()
        nome_empresa = str(row.get('NOME_EMPRESA', '')).strip()

        if not cnpj_raw or not idsl_raw:
            logger.warning(f"Linha {idx+1}: CNPJ ou IDSL vazio. Pulando.")
            relatorio["erros"] += 1
            erros_atuais.add(idx)
            continue

        cnpj_limpo = converter_notacao_cientifica(cnpj_raw)
        if not cnpj_limpo:
            logger.warning(f"Linha {idx+1}: CNPJ inválido.")
            relatorio["erros"] += 1
            erros_atuais.add(idx)
            continue

        dados_emp = None
        if idsl_raw in cache_fallback:
            dados_emp = cache_fallback[idsl_raw]
            logger.info(f"⚡ Cache fallback usado para {idsl_raw}")
        else:
            dados_emp = indice_emp.get(cnpj_limpo.zfill(14))
            if not dados_emp and nome_empresa:
                nome_busca = nome_empresa.upper().strip()
                nome_busca = re.sub(r'[^\w\s]', '', nome_busca)
                if len(cnpj_limpo) >= 5:
                    prefixo_5 = cnpj_limpo[:5]
                    candidatos = [(c, d) for c, d in indice_emp.items() if c.startswith(prefixo_5)]
                    for cnpj_idx, dados in candidatos:
                        nome_fantasia = str(dados.get('NomeFantasia', '')).upper()
                        nome_fantasia = re.sub(r'[^\w\s]', '', nome_fantasia)
                        razao = str(dados.get('Razao', '')).upper()
                        razao = re.sub(r'[^\w\s]', '', razao)
                        if nome_busca == nome_fantasia or nome_busca == razao:
                            dados_emp = dados
                            break
                    if not dados_emp and len(candidatos) == 1:
                        dados_emp = candidatos[0][1]
                if not dados_emp:
                    for cnpj_idx, dados in indice_emp.items():
                        nome_fantasia = str(dados.get('NomeFantasia', '')).upper()
                        nome_fantasia = re.sub(r'[^\w\s]', '', nome_fantasia)
                        razao = str(dados.get('Razao', '')).upper()
                        razao = re.sub(r'[^\w\s]', '', razao)
                        if nome_busca == nome_fantasia or nome_busca == razao:
                            dados_emp = dados
                            break
            
            if dados_emp:
                cache_fallback[idsl_raw] = dados_emp
                salvar_cache_fallback(cache_fallback, CACHE_FALLBACK_CONS)

        if not dados_emp:
            logger.warning(f"CNPJ {cnpj_limpo} não encontrado na base de empreendimentos.")
            relatorio["erros"] += 1
            erros_atuais.add(idx)
            nao_encontrados.add(idsl_raw)
            salvar_nao_encontrados(nao_encontrados, NAO_ENCONTRADOS_CONS)
            df.at[idx, 'STATUS'] = 'NAO_ENCONTRADO'
            continue

        try:
            contato_id, lead_status = buscar_contato_por_idsl(idsl_raw)
            if not contato_id:
                logger.warning(f"Contato com IDSL {idsl_raw} não encontrado no HubSpot.")
                relatorio["erros"] += 1
                erros_atuais.add(idx)
                continue

            logger.info(f"✅ Contato encontrado: {gerar_link_contato(contato_id)} (status: {lead_status})")

            if lead_status and lead_status.upper() in STATUS_IGNORAR:
                logger.info(f"👎 Lead {idsl_raw} com status '{lead_status}' -> adicionando aos finalizados.")
                finalizados.add(idsl_raw)
                salvar_finalizados(finalizados, FINALIZADOS_CONS)
                df.at[idx, 'STATUS'] = 'FINALIZADO'
                continue

            if apenas_catalogar:
                continue

            socio_nome = ""
            if indice_socios and idsl_raw in indice_socios:
                socio_nome = formatar_nome_socio(indice_socios[idsl_raw].get("Socios_Nome", ""))

            processar_lead_consultoria(contato_id, dados_emp, socio_nome, relatorio, df, idx)
            erros_atuais.discard(idx)
        except Exception as e:
            logger.error(f"Erro ao processar lead consultoria: {e}", exc_info=True)
            relatorio["erros"] += 1
            erros_atuais.add(idx)

        if checkpoint_usado:
            with open(CHECKPOINT_CONS, 'w') as f:
                f.write(str(idx))
        salvar_erros(erros_atuais, ARQUIVO_ERROS_CONS)
        
        if contador % 10 == 0:
            logger.info(f"📊 Progresso Consultoria: {contador}/{len(indices_processar)} | C1={relatorio['c1_criadas']} | FU={relatorio['followups_criados']} | Finais={relatorio['decisoes_finais']} | Erros={relatorio['erros']}")
        
        time.sleep(1)

    df.to_csv(CAMINHO_TRABALHO_CONS, index=False, encoding='utf-8-sig', sep=';')
    logger.info(f"💾 CSV atualizado com novos STATUS: {CAMINHO_TRABALHO_CONS}")

    if not apenas_catalogar:
        with open(ARQUIVO_RELATORIO_CONS, "w", encoding="utf-8") as f:
            f.write(f"RELATÓRIO CONSULTORIA - {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")
            f.write(f"E-mails C1 criados: {relatorio['c1_criadas']}\n")
            f.write(f"Follow-ups criados: {relatorio['followups_criados']}\n")
            f.write(f"Decisões finais (30 dias): {relatorio['decisoes_finais']}\n")
            f.write(f"Erros: {relatorio['erros']}\n")
            f.write(f"Total de finalizados: {len(finalizados)}\n")
            f.write(f"Total de CNPJs não encontrados: {len(nao_encontrados)}\n")
            f.write(f"Total em cache de fallback: {len(cache_fallback)}\n")
        logger.info(f"\n📄 Relatório Consultoria salvo em {ARQUIVO_RELATORIO_CONS}")

    salvar_erros(erros_atuais, ARQUIVO_ERROS_CONS)
    salvar_finalizados(finalizados, FINALIZADOS_CONS)
    salvar_nao_encontrados(nao_encontrados, NAO_ENCONTRADOS_CONS)
    salvar_cache_fallback(cache_fallback, CACHE_FALLBACK_CONS)

# ================= MAIN (com argumentos CLI) =================
def main():
    parser = argparse.ArgumentParser(description="Sistema SoLivia - Prospecção Unificada")
    parser.add_argument('--instalacao', action='store_true', help='Executa apenas o pipeline de instalação')
    parser.add_argument('--consultoria', action='store_true', help='Executa apenas o pipeline de consultoria')
    parser.add_argument('--ambos', action='store_true', help='Executa ambos os pipelines (instalação depois consultoria)')
    parser.add_argument('--catalogar', action='store_true', help='Modo catálogo: apenas identifica leads não qualificados (não cria tarefas)')
    parser.add_argument('--modo', choices=['full', 'errors'], default='full', help='Modo de execução: full ou errors')
    parser.add_argument('--pesquisa', action='store_true', help='Ativa pesquisa online para e-mails de instalação')
    args = parser.parse_args()

    # Se nenhum argumento específico for passado, usa o menu interativo
    if not any([args.instalacao, args.consultoria, args.ambos]):
        print("\n" + "="*60)
        print(" SISTEMA SOLIVIA - PROSPECÇÃO UNIFICADA")
        print("="*60)
        print("1. Instalação (novas instalações)")
        print("2. Consultoria (diagnóstico solar)")
        print("3. Ambos (Instalação depois Consultoria)")
        print("4. Catalogar finalizados (apenas popular JSON, sem criar tarefas)")
        print("="*60)
        opcao = input("Escolha uma opção (1,2,3,4): ").strip()

        if opcao == "4":
            print("\n📋 Modo de catalogação selecionado.")
            pipeline = input("Qual pipeline catalogar? (1 = Instalação, 2 = Consultoria, 3 = Ambos): ").strip()
            if pipeline in ("1", "3"):
                executar_pipeline_instalacao(modo="full", pesquisa_online=False, apenas_catalogar=True)
            if pipeline in ("2", "3"):
                executar_pipeline_consultoria(modo="full", apenas_catalogar=True)
            return

        modo_inst = "full"
        modo_cons = "full"
        pesquisa_online = False

        if opcao in ("1", "3"):
            modo = input("Modo para INSTALAÇÃO? (1=Completo, 2=Só erros): ").strip()
            modo_inst = "errors" if modo == "2" else "full"
            resp = input("Deseja ativar pesquisa online para os e-mails de instalação? (s/n): ").strip().lower()
            pesquisa_online = resp == "s"

        if opcao in ("2", "3"):
            modo = input("Modo para CONSULTORIA? (1=Completo, 2=Só erros): ").strip()
            modo_cons = "errors" if modo == "2" else "full"

        if opcao in ("1", "3"):
            executar_pipeline_instalacao(modo_inst, pesquisa_online, apenas_catalogar=False)
        if opcao in ("2", "3"):
            executar_pipeline_consultoria(modo_cons, apenas_catalogar=False)
    else:
        # Modo CLI
        if args.catalogar:
            if args.instalacao or args.ambos:
                executar_pipeline_instalacao(modo="full", pesquisa_online=False, apenas_catalogar=True)
            if args.consultoria or args.ambos:
                executar_pipeline_consultoria(modo="full", apenas_catalogar=True)
        else:
            if args.instalacao or args.ambos:
                executar_pipeline_instalacao(modo=args.modo, pesquisa_online=args.pesquisa, apenas_catalogar=False)
            if args.consultoria or args.ambos:
                executar_pipeline_consultoria(modo=args.modo, apenas_catalogar=False)

if __name__ == "__main__":
    main()
