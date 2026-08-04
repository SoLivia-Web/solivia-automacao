from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from weasyprint import HTML
import io
import base64
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from datetime import date, datetime
import warnings
import json
import os
import hashlib
import threading


warnings.filterwarnings("ignore")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

# ============================================================
# CONFIGURAÇÃO DO GOOGLE APPS SCRIPT (salvar PDF)
# ============================================================
APPS_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbzpiRjXd2ENmkrk5d4bCNEq36deqgCLObVC5L_tyUEFzlP1EMnCzR5R3O_3PEFnlAusSQ/exec'
TOKEN = 'x9K2mP5vR8tY3wL7qZ1nB4fJ6cH5sU9e'

# ============================================================
# CONFIGURAÇÃO: ÁREA DO CLIENTE (criação automática)
# ============================================================
URL_AREA_CLIENTE = 'https://script.google.com/macros/s/AKfycbw75sx77HBdie37fqoBg60wWgbb5QxD9uN5-Ee3aemwy8jVP2lqDImO0Brx4iFzsVan/exec'

# ============================================================
# CONFIGURAÇÃO: AUTENTIQUE (ASSINATURA DIGITAL)
# ============================================================
AUTENTIQUE_API_KEY_SOLIVIA = "d5a81d2cb0a0c68a91152fa00189a275f477fe44f403a158f4061224c1bd4f68"
AUTENTIQUE_API_KEY_NICOLAS = "52216c13e8e032e7ebef8b87f5955651acd7463e3a303c45a3aeb207fde3e463"

ASSINANTE_SOLIVIA = {
    "email": "contato@solivia.com.br",
    "nome": "SoLivia Engenharia",
    "api_key": AUTENTIQUE_API_KEY_SOLIVIA
}

ASSINANTE_NICOLAS = {
    "email": "ncalves91@gmail.com",
    "nome": "Nícolas Alves de Sá",
    "api_key": AUTENTIQUE_API_KEY_NICOLAS
}

# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def format_moeda_sem_prefixo(valor):
    try:
        return f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

def format_moeda(valor):
    try:
        return f"R$ {float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def format_cep(cep):
    cep_str = str(cep).strip()
    if len(cep_str) == 8:
        return f"{cep_str[:5]}-{cep_str[5:]}"
    return cep_str

def obter_cor_resultado_suave(valor, limite_neg=-1000, limite_pos=1000):
    import math
    if valor is None or math.isnan(valor):
        return {'bg': '#f8fafc', 'text': '#0b2f5c'}
    vermelho_claro = [255, 235, 238]
    vermelho_escuro = [183, 28, 28]
    verde_claro = [232, 245, 233]
    verde_escuro = [27, 94, 32]
    neutro = [255, 249, 196]
    if abs(valor) < 50:
        return {'bg': f'rgb({neutro[0]},{neutro[1]},{neutro[2]})', 'text': '#0b2f5c'}
    if valor < 0:
        t = min(abs(valor) / abs(limite_neg), 1)
        r = round(vermelho_claro[0] + (vermelho_escuro[0] - vermelho_claro[0]) * t * 0.5)
        g = round(vermelho_claro[1] + (vermelho_escuro[1] - vermelho_claro[1]) * t * 0.5)
        b = round(vermelho_claro[2] + (vermelho_escuro[2] - vermelho_claro[2]) * t * 0.5)
    else:
        t = min(valor / limite_pos, 1)
        r = round(verde_claro[0] + (verde_escuro[0] - verde_claro[0]) * t * 0.5)
        g = round(verde_claro[1] + (verde_escuro[1] - verde_claro[1]) * t * 0.5)
        b = round(verde_claro[2] + (verde_escuro[2] - verde_claro[2]) * t * 0.5)
    luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    text_color = '#ffffff' if luminancia > 0.5 else '#0b2f5c'
    return {'bg': f'rgb({r},{g},{b})', 'text': text_color}

def gerar_marcos_20(linhas):
    max_ano = min(len(linhas), 26)
    indices = set()
    for i in range(1, 7):
        if i < max_ano:
            indices.add(i)
    for i in [8, 10, 12, 14, 16, 18]:
        if i < max_ano:
            indices.add(i)
    for i in range(19, min(max_ano, 26)):
        indices.add(i)
    if len(indices) < 20:
        extra = []
        for i in range(0, max_ano):
            if i not in indices:
                extra.append(i)
        indices.update(extra[:20 - len(indices)])
    return sorted(list(indices))

    # ============================================================
# FUNÇÃO PARA CONVERTER IMAGEM DO DRIVE PARA BASE64
# ============================================================
def imagem_drive_para_base64(url):
    print(f"🔍 [imagem_drive] Recebeu URL: {url}")
    if not url:
        print("⚠️ URL vazia")
        return ''
    if url.startswith('data:image'):
        print("✅ Já é base64")
        return url

    # Se for URL do Google Drive, tenta extrair o ID para usar thumbnail
    import re
    match = re.search(r'id=([^&]+)', url)
    if match:
        file_id = match.group(1)
        # Usa o formato thumbnail que é mais amigável para download
        url_thumb = f"https://drive.google.com/thumbnail?id={file_id}&sz=w800"
        print(f"🔄 Usando thumbnail: {url_thumb}")
        url = url_thumb  # substitui pela URL de thumbnail

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        print(f"⏳ Baixando de {url}")
        resp = requests.get(url, timeout=30, headers=headers, allow_redirects=True)
        print(f"📡 Status: {resp.status_code}, Content-Type: {resp.headers.get('Content-Type')}")

        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', '')
            if 'image' in content_type:
                encoded = base64.b64encode(resp.content).decode()
                print(f"✅ Base64 gerado (primeiros 60): {encoded[:60]}...")
                return f"data:image/jpeg;base64,{encoded}"
            else:
                print(f"⚠️ Content-Type não é imagem: {content_type}")
                # Tenta salvar o início da resposta para depuração
                print(f"📄 Primeiros 200 bytes: {resp.text[:200]}")
        else:
            print(f"❌ Status {resp.status_code}")
    except Exception as e:
        print(f"❌ Exceção: {e}")

    # Fallback: retorna a URL original (pode não funcionar no WeasyPrint)
    print(f"⚠️ Usando fallback: URL original")
    return url

def gerar_grafico_payback(dados_simulacao):
    try:
        investimento = dados_simulacao.get('investimento', 0)
        consumo_mensal = dados_simulacao.get('consumo_atual', 0)
        tarifa = dados_simulacao.get('tarifa', 0.75)
        payback_anos = dados_simulacao.get('payback_anos', 0)
        payback_meses = dados_simulacao.get('payback_meses', 0)
        linhas = dados_simulacao.get('linhas', [])

        if not linhas or len(linhas) < 2:
            anos = 25
            resultado_acumulado = -investimento
            valores = [-investimento]
            for i in range(1, anos + 1):
                eficiencia = max(1 - (i-1) * 0.0055, 0)
                geracao = consumo_mensal * eficiencia
                tarifa_ano = tarifa * (1 + 0.085) ** (i-1)
                economia_mensal = geracao * tarifa_ano * 0.8
                economia_anual = economia_mensal * 12 - 150
                if i <= dados_simulacao.get('prazo_financiamento', 0):
                    economia_anual -= investimento / (dados_simulacao.get('prazo_financiamento', 1) * 12) * 12
                resultado_acumulado += max(economia_anual, 0)
                valores.append(resultado_acumulado)
        else:
            valores = [-investimento] + [l.get('resultadoAcumulado', 0) for l in linhas]

        anos_array = np.arange(0, len(valores))
        res_solar = np.array(valores)

        taxa_cdb = 0.135
        taxa_poup = 0.0847
        imposto_renda = 0.15
        cdb_bruto = investimento * (1 + taxa_cdb) ** anos_array
        cdb_liq = investimento + (cdb_bruto - investimento) * (1 - imposto_renda)
        poupanca = investimento * (1 + taxa_poup) ** anos_array
        lucro_cdb_liq = cdb_liq - investimento
        lucro_poup = poupanca - investimento

        AZUL_SOLIVIA = '#1e4b8c'
        AMARELO_SOL = '#ffd700'
        VERDE_MUITO_CLARO = '#e8f5e9'
        VERMELHO_MUITO_CLARO = '#ffebee'
        CINZA_MERCADO = '#cbd5e1'

        fig, ax = plt.subplots(figsize=(10, 5.5), facecolor='white')
        fig.subplots_adjust(bottom=0.15, top=0.92, left=0.1, right=0.95)

        cor_barras = [VERDE_MUITO_CLARO if x >= 0 else VERMELHO_MUITO_CLARO for x in res_solar]
        barras = ax.bar(anos_array, res_solar, color=cor_barras,
                        edgecolor=AZUL_SOLIVIA, linewidth=0.5, alpha=0.9,
                        label='SOLAR ACUMULADO')

        ax.plot(anos_array, lucro_cdb_liq, color=AMARELO_SOL, marker='o',
                linewidth=2.5, markersize=5, label='RENDIMENTO CDB (líq. IR)')
        ax.plot(anos_array, lucro_poup, color=CINZA_MERCADO, marker='s',
                linewidth=2.5, markersize=5, label='RENDIMENTO POUPANÇA')

        ax.axhline(y=0, color=AZUL_SOLIVIA, linestyle='--', linewidth=1.5, alpha=0.6)

        if payback_anos is not None and payback_anos < 25:
            payback_pos = payback_anos + payback_meses/12
            ax.axvline(x=payback_pos, color='#e11d48', linestyle=':', linewidth=2, alpha=0.8)
            ax.text(payback_pos, ax.get_ylim()[1] * 0.85,
                    f'PAYBACK\n{payback_anos}a {payback_meses}m',
                    ha='center', va='top', fontsize=10, fontweight='bold',
                    color='#e11d48',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#e11d48'))

        ax.set_xlabel('Ano', fontsize=10, fontweight='bold', color=AZUL_SOLIVIA)
        ax.set_ylabel('Resultado Financeiro (R$)', fontsize=10, fontweight='bold', color=AZUL_SOLIVIA)
        ax.set_xticks([0, 5, 10, 15, 20, 25])
        ax.set_xticklabels([f'Ano {int(a)}' for a in [0, 5, 10, 15, 20, 25]],
                           fontweight='bold', color=AZUL_SOLIVIA)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(AZUL_SOLIVIA)
        ax.spines['bottom'].set_color(AZUL_SOLIVIA)

        ax.legend(loc='upper left', fontsize=9, frameon=True, edgecolor=AZUL_SOLIVIA, facecolor='white')
        ax.grid(True, alpha=0.15, linestyle='--', color=AZUL_SOLIVIA)

        for idx, (ano_val, barra) in enumerate(zip(anos_array, barras)):
            if ano_val in [0, 5, 10, 15, 20, 25] and ano_val < len(res_solar):
                altura = barra.get_height()
                va = 'bottom' if altura >= 0 else 'top'
                offset = 0.02 * ax.get_ylim()[1] if altura >= 0 else -0.02 * ax.get_ylim()[1]
                ax.text(barra.get_x() + barra.get_width()/2, altura + offset,
                        f'R$ {res_solar[idx]:,.0f}',
                        ha='center', va=va, fontsize=9, fontweight='bold', color=AZUL_SOLIVIA)

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight', facecolor='white')
        buf.seek(0)
        plt.close()
        return base64.b64encode(buf.getvalue()).decode('utf-8')

    except Exception as e:
        print(f"❌ Erro no gráfico: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================
# FUNÇÕES DE BUSCA E CRIAÇÃO
# ============================================================
def buscar_cliente_por_id(cliente_id):
    try:
        senha_admin = 'SoLiVi@64253798@'
        cliente_id_str = str(cliente_id)
        payload = {
            "acao": "adminObterCliente",
            "idCliente": cliente_id_str,
            "senhaAdmin": senha_admin
        }
        print(f"🔍 Buscando cliente com ID: {cliente_id_str}")
        response = requests.post(URL_AREA_CLIENTE, json=payload, timeout=30)
        print(f"📡 Status da resposta: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"📦 Dados retornados: {data}")
            if data.get('success'):
                return data.get('cliente')
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar cliente: {e}")
        return None

def buscar_cliente_por_documento_id(document_id):
    try:
        senha_admin = 'SoLiVi@64253798@'
        payload = {
            "acao": "adminListarClientes",
            "senhaAdmin": senha_admin
        }
        response = requests.post(URL_AREA_CLIENTE, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                clientes = data.get('clientes', [])
                for cliente_resumido in clientes:
                    payload_cliente = {
                        "acao": "adminObterCliente",
                        "idCliente": cliente_resumido['id'],
                        "senhaAdmin": senha_admin
                    }
                    resp_cliente = requests.post(URL_AREA_CLIENTE, json=payload_cliente, timeout=30)
                    if resp_cliente.status_code == 200:
                        dados_cliente = resp_cliente.json()
                        if dados_cliente.get('success'):
                            cliente_completo = dados_cliente.get('cliente', {})
                            documentos = cliente_completo.get('documentos', {})
                            contrato = documentos.get('contrato', {})
                            if contrato.get('document_id') == document_id:
                                return cliente_completo
        return None
    except Exception as e:
        print(f"❌ Erro ao buscar cliente por document_id: {e}")
        return None

def atualizar_aprovacao_cliente(cliente_id):
    print(f"✅ Atualizando aprovação do cliente {cliente_id}")
    pass

def criar_cliente_area_cliente(dados_cliente):
    payload = {
        "acao": "criarClienteViaOrcamento",
        "dados": {
            "nome": dados_cliente.get('nome_cliente', ''),
            "email": dados_cliente.get('email', ''),
            "telefone": dados_cliente.get('telefone', ''),
            "cep": dados_cliente.get('cep', ''),
            "endereco": dados_cliente.get('endereco', '') + (f", {dados_cliente.get('numero_endereco', '')}" if dados_cliente.get('numero_endereco') else '')
        }
    }
    try:
        response = requests.post(URL_AREA_CLIENTE, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"❌ Erro ao criar cliente na Área do Cliente: {e}")
        return {'success': False, 'error': str(e)}

# ============================================================
# FUNÇÃO: ENVIAR PARA ASSINATURA AUTENTIQUE (COM POSITIONS)
# ============================================================
def enviar_para_assinatura_autentique(
    pdf_bytes,
    nome_documento,
    cliente_email,
    cliente_nome,
    assinante_empresa=None,
    posicao_engenheiro=None,
    posicao_cliente=None
):
    if assinante_empresa is None:
        assinante_empresa = ASSINANTE_SOLIVIA

    if posicao_engenheiro is None:
        posicao_engenheiro = {"x": 450, "y": 650, "z": 1, "page": 6}  # assinatura da empresa (SoLivia) – lado direito
    if posicao_cliente is None:
        posicao_cliente = {"x": 150, "y": 650, "z": 1, "page": 6}     # assinatura do cliente – lado esquerd

    api_key = assinante_empresa["api_key"]

    query = """
mutation CreateDocumentMutation($document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!) {
    createDocument(
        sandbox: true,
        document: $document,
        signers: $signers,
        file: $file
    ) {
        id
        name
        created_at
        signatures {
            public_id
            name
            email
            link {
                short_link
            }
        }
    }
}
    """

    variables = {
        "document": {"name": nome_documento},
        "signers": [
            {
                "email": assinante_empresa["email"],
                "name": assinante_empresa["nome"],
                "action": "SIGN",
                "positions": [
                    {
                        "x": posicao_engenheiro["x"],
                        "y": posicao_engenheiro["y"],
                        "z": posicao_engenheiro["z"]
                    }
                ]
            },
            {
                "email": cliente_email,
                "name": cliente_nome,
                "action": "SIGN",
                "positions": [
                    {
                        "x": posicao_cliente["x"],
                        "y": posicao_cliente["y"],
                        "z": posicao_cliente["z"]
                    }
                ]
            }
        ]
    }

    operations = {"query": query, "variables": variables}
    map_payload = {"file": ["variables.file"]}


    url = "https://autentique-proxy.ncalves91.workers.dev/v2/graphql"

    response = requests.post(
        url,
        data={"operations": json.dumps(operations), "map": json.dumps(map_payload)},
        files={"file": (nome_documento, pdf_bytes, "application/pdf")},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=60,
        proxies={}
    )

    if response.status_code == 200:
        dados = response.json()
        # LOG DA RESPOSTA COMPLETA (MELHORIA A)
        print(f"🔍 Resposta completa da Autentique: {json.dumps(dados, indent=2)}")
        if "errors" in dados:
            return {"success": False, "error": dados["errors"]}
        resultado = dados.get("data", {}).get("createDocument", {})
        link_assinatura = None
        signatures = resultado.get("signatures", [])
        for sig in signatures:
            # Tenta diferentes caminhos (MELHORIA A)
            link = sig.get("link", {})
            if link and link.get("short_link"):
                link_assinatura = link["short_link"]
                break
            # Se não tiver link, pode estar diretamente no signature
            if sig.get("short_link"):
                link_assinatura = sig["short_link"]
                break
        return {
            "success": True,
            "document_id": resultado.get("id"),
            "link_assinatura": link_assinatura,
            "data": resultado
        }
    else:
        return {"success": False, "error": response.text}

# ============================================================
# FUNÇÃO: BAIXAR PDF ASSINADO
# ============================================================
def baixar_pdf_assinado(document_id, api_key):
    print(f"📥 [baixar_pdf] Iniciando download para {document_id}")
    query = """
    query DownloadDocument($id: UUID!) {
        document(id: $id) {
            files {
                signed
            }
        }
    }
    """
    variables = {"id": document_id}
    print(f"📥 [baixar_pdf] Query preparada")
    try:
        response = requests.post(
            "https://autentique-proxy.ncalves91.workers.dev/v2/graphql",
            json={"query": query, "variables": variables},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=60,
            proxies={}
        )
        print(f"📥 [baixar_pdf] Status da resposta: {response.status_code}")
        if response.status_code != 200:
            print(f"❌ Erro na requisição GraphQL: {response.status_code}")
            return None
        data = response.json()
        print(f"📥 [baixar_pdf] Resposta JSON recebida (keys): {data.keys()}")
        if "errors" in data:
            print(f"❌ Erro GraphQL: {data['errors']}")
            return None
        signed_url = data.get("data", {}).get("document", {}).get("files", {}).get("signed")
        if not signed_url:
            print("❌ Nenhum signed URL encontrado")
            return None
        print(f"📥 [baixar_pdf] URL obtida: {signed_url}")

        pdf_response = requests.get(
            f"https://autentique-proxy.ncalves91.workers.dev/?url={signed_url}",
            timeout=60,
            proxies={}
        )
        print(f"📥 [baixar_pdf] Download do PDF - status: {pdf_response.status_code}")
        if pdf_response.status_code == 200:
            print(f"✅ PDF baixado com sucesso: {len(pdf_response.content)} bytes")
            return pdf_response.content
        else:
            print(f"❌ Erro ao baixar PDF via Worker: {pdf_response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Exceção em baixar_pdf_assinado: {e}")
        import traceback
        traceback.print_exc()
        return None

# ============================================================
# ROTAS
# ============================================================

@app.route('/gerar_proposta', methods=['POST'])
def gerar_proposta_api():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'error': 'Dados não fornecidos'}), 400

        sim_data = dados.get('dados', {})
        print("📦 Nome do cliente:", sim_data.get('nome_cliente'))
        print("📦 Investimento recebido:", sim_data.get('investimento'))
        print(f"🔍 Imagens recebidas no payload: {dados.get('imagens', {})}")

        # ===== FALLBACK PARA E-MAIL (SE VAZIO) =====
        email_cliente = sim_data.get('email', '').strip()
        if not email_cliente:
            nome_sanitizado = sim_data.get('nome_cliente', 'cliente').replace(' ', '_').lower()
            timestamp = int(datetime.now().timestamp())
            email_cliente = f"{nome_sanitizado}.{timestamp}@temp.solivia.com.br"
            sim_data['email'] = email_cliente
            print(f"📧 E-mail temporário gerado: {email_cliente}")

        # ===== CRIAÇÃO DO CLIENTE =====
        resultado_cliente = criar_cliente_area_cliente(sim_data)
        pasta_id_destino = None
        if resultado_cliente.get('success'):
            cliente_id = resultado_cliente.get('id')

            # ===== SALVA CPF/CNPJ EM dados_preproposta =====
            cpf_cnpj = sim_data.get('cpf_cnpj', '')
            if cpf_cnpj:
                try:
                    cliente_atual = buscar_cliente_por_id(cliente_id)
                    if cliente_atual:
                        dados_preproposta = cliente_atual.get('dados_preproposta', {})
                        dados_preproposta['cpf_cnpj'] = cpf_cnpj
                        payload_update = {
                            "acao": "adminAtualizarCliente",
                            "idCliente": str(cliente_id),
                            "campos": {
                                "dados_preproposta": dados_preproposta
                            },
                            "senhaAdmin": "SoLiVi@64253798@"
                        }
                        requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                        print(f"✅ CPF/CNPJ salvo em dados_preproposta: {cpf_cnpj}")
                except Exception as e:
                    print(f"⚠️ Erro ao salvar CPF: {e}")

            pasta_id_destino = resultado_cliente.get('pastaId')
            senha = resultado_cliente.get('senha_temporaria')
            print(f"✅ Cliente criado: ID {cliente_id}, Pasta {pasta_id_destino}, Senha: {senha}")
        else:
            print(f"⚠️ Cliente não criado: {resultado_cliente.get('error')}")

        # ===== RESTO DA FUNÇÃO (GERAÇÃO DO PDF, SALVAMENTO, ETC.) =====
        nome_cliente = sim_data.get('nome_cliente', '')
        telefone = sim_data.get('telefone', '')
        email = sim_data.get('email', '')
        foto_capa_miolo = sim_data.get('foto_capa_miolo', None)
        cep = sim_data.get('cep', '')
        endereco = sim_data.get('endereco', '')
        numero_endereco = sim_data.get('numero_endereco', '')
        cpf_cnpj = sim_data.get('cpf_cnpj', '')
        valor_conta = sim_data.get('valor_conta', 0)
        prazo_financiamento = sim_data.get('prazo_financiamento', 0)
        potencia_kwp = sim_data.get('potencia_kwp', 0)
        investimento = sim_data.get('investimento', 0)
        economia_mensal = sim_data.get('economia_mensal', 0)
        payback_anos = sim_data.get('payback_anos', 0)
        payback_meses = sim_data.get('payback_meses', 0)
        vpl = sim_data.get('vpl', 0)
        tir = sim_data.get('tir', 0)
        co2_anual = sim_data.get('co2_anual', 0)
        arvores = sim_data.get('arvores', 0)
        tarifa = sim_data.get('tarifa', 0)
        hsp = sim_data.get('hsp', 0)
        consumo_atual = sim_data.get('consumo_atual', 0)
        qtd_modulos = sim_data.get('qtd_modulos', 0)
        area = sim_data.get('area', 0)
        distribuidora = sim_data.get('distribuidora', 'Concessionária local')
        investimento_ajustado = sim_data.get('investimento_ajustado', investimento)
        custo_visita = sim_data.get('custo_visita', 0)
        distancia_km = sim_data.get('distancia_km', 0)
        itens_recebidos = sim_data.get('itens_escopo', [])
        linhas_recebidas = sim_data.get('linhas', [])

        itens_escopo = []
        for item in itens_recebidos:
            preco_str = item.get('preco', '0,00').replace('.', '').replace(',', '.')
            try:
                preco_num = float(preco_str)
            except ValueError:
                preco_num = 0.0
            itens_escopo.append({
                'desc': item.get('desc', ''),
                'marca': item.get('marca', 'Conforme projeto'),
                'qtd': item.get('qtd', '1'),
                'preco': f"{preco_num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            })

        if not itens_escopo:
            itens_escopo = [{
                'desc': 'Sistema Fotovoltaico',
                'marca': 'Conforme projeto',
                'qtd': '1',
                'preco': f"{investimento_ajustado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            }]

        grafico_base64 = None
        if consumo_atual > 0 and investimento > 0:
            dados_grafico = {
                'investimento': investimento,
                'consumo_atual': consumo_atual,
                'tarifa': tarifa,
                'payback_anos': payback_anos,
                'payback_meses': payback_meses,
                'prazo_financiamento': prazo_financiamento,
                'linhas': linhas_recebidas
            }
            grafico_base64 = gerar_grafico_payback(dados_grafico)
            if grafico_base64:
                print("✅ Gráfico gerado com sucesso")

        # ===== CORREÇÃO: projecao_20 sem depender de string para cálculo =====
        projecao_20 = []
        resultado_acumulado_numerico = 0  # variável numérica para cálculo

        if linhas_recebidas and len(linhas_recebidas) >= 2:
            indices = gerar_marcos_20(linhas_recebidas)
            for i in indices:
                if i < len(linhas_recebidas):
                    l = linhas_recebidas[i]
                    ano = l.get('ano', i+1)
                    saldo_poupanca = investimento * (1 + 0.0847) ** ano
                    saldo_cdb_bruto = investimento * (1 + 0.135) ** ano
                    saldo_cdb_liquido = investimento + (saldo_cdb_bruto - investimento) * (1 - 0.15)
                    cor = obter_cor_resultado_suave(l.get('resultadoAcumulado', 0))
                    projecao_20.append({
                        'ano': ano,
                        'custoSemSolarMes': format_moeda_sem_prefixo(l.get('custoSemSolarMes', 0)),
                        'eficiencia': round(l.get('eficiencia', 100), 1),
                        'tarifa': format_moeda_sem_prefixo(l.get('tarifa', 0)),
                        'custoComSolarMes': format_moeda_sem_prefixo(l.get('custoComSolarMes', 0)),
                        'economiaAnual': format_moeda_sem_prefixo(l.get('economiaAnual', 0)),
                        'resultadoAcumulado': format_moeda_sem_prefixo(l.get('resultadoAcumulado', 0)),
                        'saldoPoupanca': format_moeda_sem_prefixo(saldo_poupanca),
                        'saldoCDB': format_moeda_sem_prefixo(saldo_cdb_liquido),
                        'cor_fundo': cor['bg'],
                        'cor_texto': cor['text']
                    })
        else:
            for i in range(1, 26):
                if len(projecao_20) >= 20:
                    break
                if i in [1,2,3,4,5,6,8,10,12,14,16,18,19,20,21,22,23,24,25]:
                    eficiencia_val = max(1 - (i-1) * 0.0055, 0)
                    tarifa_ano = tarifa * (1 + 0.085) ** (i-1)
                    geracao_mensal = consumo_atual * eficiencia_val
                    economia_anual = (geracao_mensal * tarifa_ano * 0.8) * 12 - 150
                    if i <= prazo_financiamento:
                        economia_anual -= investimento / (prazo_financiamento * 12) * 12
                    if i == 1:
                        resultado_acumulado_numerico = -investimento + max(economia_anual, 0)
                    else:
                        resultado_acumulado_numerico += max(economia_anual, 0)

                    custo_sem = consumo_atual * tarifa_ano + consumo_atual * tarifa_ano * 0.04
                    custo_com = max(0, (consumo_atual - geracao_mensal + 30) * tarifa_ano)
                    saldo_poupanca = investimento * (1 + 0.0847) ** i
                    saldo_cdb_bruto = investimento * (1 + 0.135) ** i
                    saldo_cdb_liquido = investimento + (saldo_cdb_bruto - investimento) * (1 - 0.15)
                    cor = obter_cor_resultado_suave(resultado_acumulado_numerico)
                    projecao_20.append({
                        'ano': i,
                        'custoSemSolarMes': format_moeda_sem_prefixo(custo_sem),
                        'eficiencia': round(eficiencia_val*100, 1),
                        'tarifa': format_moeda_sem_prefixo(tarifa_ano),
                        'custoComSolarMes': format_moeda_sem_prefixo(custo_com),
                        'economiaAnual': format_moeda_sem_prefixo(max(economia_anual, 0)),
                        'resultadoAcumulado': format_moeda_sem_prefixo(resultado_acumulado_numerico),
                        'saldoPoupanca': format_moeda_sem_prefixo(saldo_poupanca),
                        'saldoCDB': format_moeda_sem_prefixo(saldo_cdb_liquido),
                        'cor_fundo': cor['bg'],
                        'cor_texto': cor['text']
                    })

        cep_formatado = format_cep(cep)
        area_str = f"{area:.1f}" if area and area > 0 else "a ser dimensionada"
        economia_mensal_str = format_moeda(economia_mensal) if economia_mensal and economia_mensal > 0 else "a ser calculada"
        diagnostico = f"""Prezado(a) {nome_cliente},

Realizamos uma análise detalhada do seu consumo de energia elétrica com base nos dados fornecidos (CEP: {cep_formatado}, valor da conta: {format_moeda(valor_conta)}).

Identificamos um consumo médio de {consumo_atual:.1f} kWh/mês, o que equivale a uma demanda significativa de energia. Com base nesse consumo, projetamos um sistema fotovoltaico com potência de {potencia_kwp:.2f} kWp, composto por {qtd_modulos} módulos de 700W, ocupando uma área aproximada de {area_str} m².

O investimento total estimado para este projeto é de {format_moeda(investimento_ajustado)}, com uma economia mensal projetada de {economia_mensal_str}. O retorno do investimento (payback) está estimado em {payback_anos} anos e {payback_meses} meses, considerando a valorização da tarifa de energia e a degradação natural dos módulos ao longo dos anos.

Além da economia financeira, este sistema contribuirá para a preservação do meio ambiente, evitando a emissão de {co2_anual:.0f} kg de CO₂ por ano, o que equivale a plantar {arvores:.1f} árvores.
"""
        destaque_final = "A SoLivia Engenharia está pronta para executar este projeto com excelência, garantindo a máxima eficiência e durabilidade do seu sistema solar."

        solucao_texto = f"""A solução proposta consiste na instalação de um sistema fotovoltaico conectado à rede elétrica (on-grid), que permitirá a geração de energia limpa e renovável diretamente no seu imóvel. Este projeto foi dimensionado com base no seu consumo atual e nas condições de irradiação solar da sua região.

Vale ressaltar que esta é uma <span class="destaque-pre-proposta">pré-proposta</span>, elaborada a partir de dados iniciais. Para a validação final e detalhamento técnico completo, será necessária uma visita técnica ao local, onde serão confirmadas as condições estruturais, a orientação do telhado e demais especificidades do imóvel."""

        beneficios = [
            "Proteção contra aumentos tarifários: gere sua própria energia e fique imune aos reajustes anuais da conta de luz.",
            "Monitoramento do sistema: acompanhe a geração e o consumo em tempo real, com total transparência.",
            "Energia limpa e sustentável: reduza sua pegada de carbono e contribua com um futuro mais verde."
        ]

        inclusos = [
            "Engenharia e Homologação (Gestão completa de ponta a ponta com a concessionária de energia)",
            "Aquisição e Logística de Equipamentos (Garantia de compra e entrega segura de todo o sistema fotovoltaico)",
            "Instalação Técnica Especializada (Mão de obra qualificada para montagem e configuração do sistema)",
            "Suporte (Monitoramento e assistência técnica garantida pós-instalação)",
            "Garantia do Serviço"
        ]
        exclusos = [
            "Obras civis (reformas de telhado ou alvenaria)",
            "Adequação elétrica pesada (caso o quadro ou a entrada de energia do imóvel esteja fora das normas atuais)"
        ]

        LOGO_CENTRAL = "https://i.imgur.com/HkYPKmQ.png"
        LOGO_RODAPE = "https://i.imgur.com/gdnq1ok.png"
        SELO = "https://i.imgur.com/hVtSG8M.png"
        FOTO_CAPA_MIOLO = "https://images.unsplash.com/photo-1509391366360-2e959784a276?w=600&h=300&fit=crop"

        dados_template = {
            "NUM_PROPOSTA": sim_data.get('num_proposta', f"#{date.today().strftime('%Y%m%d')}-001"),
            "TIPO_PROJETO": "PRÉ-PROPOSTA",
            "NOME_CLIENTE": nome_cliente,
            "CPF_CNPJ": cpf_cnpj,
            "FOTO_CAPA_MIOLO": foto_capa_miolo or FOTO_CAPA_MIOLO,
            "TELEFONE_CLIENTE": telefone,
            "ENDERECO": endereco,
            "NUMERO_ENDERECO": numero_endereco,
            "FOTO_PROVA": None,
            "LOGO_CENTRAL": LOGO_CENTRAL,
            "LOGO_RODAPE": LOGO_RODAPE,
            "SELO_QUALIDADE": SELO,
            "FRASE_IMPACTO": "Energia solar: economia, sustentabilidade e valorização do seu imóvel",
            "DIAGNOSTICO": diagnostico,
            "DESTAQUE_FINAL": destaque_final,
            "SOLUCAO_TEXTO": solucao_texto,
            "BENEFICIOS": beneficios,
            "INCLUSOS": inclusos,
            "EXCLUSOS": exclusos,
            "ITENS_ESCOPO": itens_escopo,
            "VALOR_TOTAL": format_moeda(investimento_ajustado),
            "CONDICAO_1": "À vista",
            "CONDICAO_2": "Cartão de crédito",
            "CONDICAO_3": "Financiamento",
            "PRAZO_EXECUCAO": "15 dias úteis",
            "VALIDADE_PROPOSTA": "10 dias úteis",
            "DATA_EMISSAO": date.today().strftime("%d/%m/%Y"),
            "REVISAO": "RV00",
            "CONTATOS": "contato@solivia.com.br",
            "PROJECAO_20": projecao_20,
            "GRAFICO_BASE64": grafico_base64,
            "CUSTO_VISITA": format_moeda(custo_visita),
            "DISTANCIA_VISITA": f"{distancia_km:.1f} km"
        }

        html_content = render_template('pre_proposta.html', **dados_template)
        pdf_bytes = HTML(string=html_content).write_pdf()

        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        payload = {
            'token': TOKEN,
            'acao': 'salvar_pdf',
            'dados': {
                'nome_cliente': nome_cliente or 'cliente',
                'pdf_base64': pdf_base64,
                'nome_arquivo': f"PreProposta_{nome_cliente or 'cliente'}_{date.today().strftime('%Y%m%d')}.pdf",
                'pasta_id': pasta_id_destino,
                'cliente_id': cliente_id   # <-- ADICIONAR ESTA LINHA
            }
        }

        response = requests.post(APPS_SCRIPT_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                # ===== SALVA A PROJEÇÃO DA PRÉ-PROPOSTA NO CLIENTE =====
                try:
                    cliente_id = resultado_cliente.get('id')
                    if cliente_id:
                        cliente = buscar_cliente_por_id(cliente_id)
                        if cliente:
                            dados_visita = cliente.get('dados_visita', {})
                            # Salva as primeiras 5 linhas da projeção
                            if linhas_recebidas and len(linhas_recebidas) >= 2:
                                dados_visita['projecao_preproposta'] = linhas_recebidas[:5]
                                dados_visita['investimento_preproposta'] = investimento
                                dados_visita['tarifa_preproposta'] = tarifa
                                print(f"✅ Projeção da pré-proposta salva para cliente {cliente_id}")

                            payload_update = {
                                "acao": "adminAtualizarCliente",
                                "idCliente": str(cliente_id),
                                "campos": {
                                    "dados_visita": dados_visita
                                },
                                "senhaAdmin": "SoLiVi@64253798@"
                            }
                            requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                except Exception as e:
                    print(f"⚠️ Erro ao salvar projeção da pré-proposta: {e}")

                return jsonify({'success': True, 'url': result.get('url'), 'message': 'Proposta salva no Google Drive'})
            else:
                return jsonify({'success': False, 'error': result.get('error', 'Erro ao salvar no Drive')}), 500
        else:
            return jsonify({'success': False, 'error': f'Erro ao comunicar com o Google Apps Script: {response.status_code}'}), 500

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/enviar_para_assinatura', methods=['POST'])
def api_enviar_para_assinatura():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        cliente_id = dados.get('cliente_id')
        pdf_base64 = dados.get('pdf_base64')
        nome_documento = dados.get('nome_documento', 'Contrato.pdf')
        tipo_assinante = dados.get('tipo_assinante', 'empresa')
        posicao_engenheiro = dados.get('posicao_engenheiro')
        posicao_cliente = dados.get('posicao_cliente')

        if not cliente_id:
            return jsonify({'success': False, 'error': 'cliente_id é obrigatório'}), 400
        if not pdf_base64:
            return jsonify({'success': False, 'error': 'pdf_base64 é obrigatório'}), 400

        cliente = buscar_cliente_por_id(cliente_id)
        if not cliente:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        if tipo_assinante == 'engenheiro':
            assinante = ASSINANTE_NICOLAS
        else:
            assinante = ASSINANTE_SOLIVIA

        pdf_bytes = base64.b64decode(pdf_base64)

        resultado = enviar_para_assinatura_autentique(
            pdf_bytes=pdf_bytes,
            nome_documento=nome_documento,
            cliente_email=cliente['email'],
            cliente_nome=cliente['nome'],
            assinante_empresa=assinante,
            posicao_engenheiro=posicao_engenheiro,
            posicao_cliente=posicao_cliente
        )

        if resultado['success']:
            document_id = resultado['document_id']

            try:
                cliente_atual = buscar_cliente_por_id(cliente_id)
                if cliente_atual:
                    docs = cliente_atual.get('documentos', {})
                    if 'contrato' not in docs:
                        docs['contrato'] = {}
                    docs['contrato']['document_id'] = document_id
                    docs['contrato']['status'] = 'enviado'
                    docs['contrato']['data_envio'] = datetime.now().isoformat()

                    payload_update = {
                        "acao": "adminAtualizarCliente",
                        "idCliente": str(cliente_id),
                        "campos": {
                            "documentos": docs,
                            "etapa_atual": "documentos"
                        },
                        "senhaAdmin": "SoLiVi@64253798@"
                    }
                    requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                    print(f"✅ document_id {document_id} salvo no cliente {cliente_id}")
            except Exception as e:
                print(f"⚠️ Erro ao salvar document_id: {e}")

            return jsonify({
                'success': True,
                'document_id': document_id,
                'link_assinatura': resultado['link_assinatura']
            })
        else:
            return jsonify({'success': False, 'error': resultado['error']}), 500

    except Exception as e:
        print(f"❌ Erro em /api/enviar_para_assinatura: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# FUNÇÃO AUXILIAR: PROCESSAR CONTRATO ASSINADO (MELHORIA B)
# ============================================================
def processar_contrato_assinado(document_id):
    try:
        print(f"🔍 [BACKGROUND] Iniciando processamento para {document_id}")
        # Busca cliente (com retry)
        cliente = buscar_cliente_por_documento_id(document_id)
        if not cliente:
            print(f"❌ [BACKGROUND] Cliente não encontrado, tentando novamente em 3s...")
            import time
            time.sleep(3)
            cliente = buscar_cliente_por_documento_id(document_id)
            if not cliente:
                print(f"❌ [BACKGROUND] Cliente não encontrado após retry.")
                return
        print(f"✅ [BACKGROUND] Cliente encontrado: {cliente['nome']} (ID: {cliente['id']})")

        # Baixa o PDF assinado
        pdf_bytes = baixar_pdf_assinado(document_id, AUTENTIQUE_API_KEY_SOLIVIA)
        if not pdf_bytes:
            print("❌ [BACKGROUND] Falha no download do PDF")
            return
        print(f"✅ [BACKGROUND] PDF baixado: {len(pdf_bytes)} bytes")

        # 1. Substitui o PDF na pasta do cliente
        payload = {
            'acao': 'substituirPdfAssinado',
            'senhaAdmin': 'SoLiVi@64253798@',
            'cliente_id': cliente['id'],
            'pdf_bytes': base64.b64encode(pdf_bytes).decode('utf-8'),
            'nome_arquivo': f"Contrato_Assinado_{cliente['nome'].replace(' ', '_')}.pdf"
        }
        resp = requests.post(URL_AREA_CLIENTE, json=payload, timeout=60)
        if resp.status_code == 200:
            result = resp.json()
            if result.get('success'):
                print(f"✅ [BACKGROUND] PDF assinado salvo: {result.get('url')}")

                # 2. Atualizar status do contrato e avançar etapa
                try:
                    cliente_atual = buscar_cliente_por_id(cliente['id'])
                    if cliente_atual:
                        docs = cliente_atual.get('documentos', {})
                        if 'contrato' in docs:
                            docs['contrato']['status'] = 'assinado'
                            docs['contrato']['url_assinado'] = result.get('url')
                            docs['contrato']['data_assinatura'] = datetime.now().isoformat()

                        payload_update = {
                            "acao": "adminAtualizarCliente",
                            "idCliente": str(cliente['id']),
                            "campos": {
                                "documentos": docs,
                                "etapa_atual": "instalacao"
                            },
                            "senhaAdmin": "SoLiVi@64253798@"
                        }
                        resp_update = requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                        if resp_update.status_code == 200:
                            print(f"✅ [BACKGROUND] Etapa atualizada para 'instalacao' e contrato marcado como assinado")
                        else:
                            print(f"❌ [BACKGROUND] Erro ao atualizar etapa: {resp_update.status_code}")
                except Exception as e:
                    print(f"⚠️ [BACKGROUND] Erro ao atualizar status: {e}")
            else:
                print(f"❌ [BACKGROUND] Erro ao salvar PDF: {result.get('error')}")
        else:
            print(f"❌ [BACKGROUND] Erro HTTP: {resp.status_code}")

    except Exception as e:
        print(f"❌ [BACKGROUND] Exceção: {e}")
        import traceback
        traceback.print_exc()

# ============================================================
# WEBHOOK AUTENTIQUE (MELHORIA C)
# ============================================================

@app.route('/webhook/autentique', methods=['POST'])
def webhook_autentique():
    try:
        data = request.json
        print(f"📨 Webhook recebido: {data}")
        event = data.get('event', {})
        event_type = event.get('type') if isinstance(event, dict) else None
        # Se o event for um dicionário, o document_id pode estar em event['data']['id']
        document_id = event.get('data', {}).get('id') if isinstance(event, dict) else None

        if not document_id:
            # Fallback: tenta buscar em outro lugar
            document_id = data.get('data', {}).get('id')

        print(f"📌 Evento: {event_type}, Documento: {document_id}")

        if event_type == 'document.finished' and document_id:
            print("✅ Documento finalizado – iniciando processamento em background...")
            threading.Thread(target=processar_contrato_assinado, args=(document_id,)).start()
            return jsonify({'status': 'ok'}), 200

        return jsonify({'status': 'ignored'}), 200
    except Exception as e:
        print(f"❌ Exceção no webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ============================================================
# ROTA MANUAL: FORÇAR ATUALIZAÇÃO DE ASSINATURA
# ============================================================
@app.route('/api/forcar_atualizacao_assinatura', methods=['POST'])
def forcar_atualizacao_assinatura():
    try:
        dados = request.get_json()
        document_id = dados.get('document_id')
        if not document_id:
            return jsonify({'success': False, 'error': 'document_id não fornecido'}), 400

        # 1. Verificar se o documento está finalizado
        api_key = AUTENTIQUE_API_KEY_SOLIVIA
        query = """
        query DocumentStatus($id: UUID!) {
            document(id: $id) {
                status
                files { signed }
            }
        }
        """
        response = requests.post(
            "https://autentique-proxy.ncalves91.workers.dev/v2/graphql",
            json={"query": query, "variables": {"id": document_id}},
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=30
        )
        print(f"📡 Resposta da consulta de status: {response.text}")
        if response.status_code != 200:
            return jsonify({'success': False, 'error': 'Erro ao consultar status do documento'}), 500
        data = response.json()
        status = data.get('data', {}).get('document', {}).get('status')
        signed_url = data.get('data', {}).get('document', {}).get('files', {}).get('signed')

        if status != 'finished' or not signed_url:
            return jsonify({
                'success': False,
                'message': 'O contrato ainda não está completamente assinado.',
                'status': status
            }), 200

        # 2. Se estiver finalizado, baixa o PDF e atualiza
        processar_contrato_assinado(document_id)

        return jsonify({'success': True, 'message': 'Contrato assinado e planilha atualizada'})

    except Exception as e:
        print(f"❌ Exceção: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTA PRINCIPAL: GERAR RELATÓRIO DE CONFORMIDADE
# ============================================================

@app.route('/gerar_relatorio_conformidade', methods=['POST'])
def gerar_relatorio_conformidade():
    # ===== FUNÇÃO AUXILIAR PARA FORÇAR CORS =====
    def _cors_response(data, status=200):
        resp = jsonify(data)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return resp, status

    try:
        dados = request.get_json()
        if not dados:
            return _cors_response({'success': False, 'error': 'Dados não fornecidos'}, 400)

        tipo = dados.get('tipo')
        if tipo not in ['sem_adequacao', 'com_adequacao', 'fast_track']:
            return _cors_response({'success': False, 'error': 'Tipo de relatório inválido'}, 400)

        template_map = {
            'sem_adequacao': 'relatorio_sem_adequacao.html',
            'com_adequacao': 'relatorio_com_adequacao.html',
            'fast_track': 'relatorio_fast_track.html'
        }
        template_file = template_map[tipo]

        cliente_id = dados.get('cliente_id')

        hash_input = f"{cliente_id}{dados.get('data_visita', '')}{tipo}{datetime.now().isoformat()}"
        hash_documento = hashlib.sha256(hash_input.encode()).hexdigest()

        protocolo = None
        if cliente_id:
            try:
                cliente = buscar_cliente_por_id(cliente_id)
                if cliente:
                    dados_visita = cliente.get('dados_visita', {})
                    contador_diario = dados_visita.get('contador_diario', {})
                    data_atual = datetime.now().strftime('%Y-%m-%d')

                    proximo = contador_diario.get(data_atual, 0) + 1
                    contador_diario[data_atual] = proximo

                    protocolo = f"VT-{datetime.now().strftime('%Y%m%d')}-{cliente_id}-{proximo:03d}"
                    dados_visita['contador_diario'] = contador_diario
                    dados_visita['ultimo_protocolo'] = protocolo

                    payload_protocolo = {
                        "acao": "adminAtualizarCliente",
                        "idCliente": str(cliente_id),
                        "campos": {
                            "dados_visita": dados_visita
                        },
                        "senhaAdmin": "SoLiVi@64253798@"
                    }
                    requests.post(URL_AREA_CLIENTE, json=payload_protocolo, timeout=30)
                    print(f"✅ Protocolo gerado: {protocolo}")
                else:
                    print("⚠️ Cliente não encontrado para gerar protocolo")
            except Exception as e:
                print(f"⚠️ Erro ao gerar protocolo: {e}")

        context = {
            'RAZAO_SOCIAL': 'SoLivia Engenharia LTDA',
            'NOME_FANTASIA': 'SoLivia Engenharia',
            'CNPJ': '49.972.976/0001-15',
            'TELEFONE': '(11) 5028-2426',
            'EMAIL': 'contato@solivia.com.br',
            'SITE': 'solivia.com.br',
            'ENDERECO_EMPRESA': 'Rua Jerônimo Bueno, 28 - São Paulo/SP',
            'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
            'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
            'SELO_QUALIDADE': 'https://i.imgur.com/hVtSG8M.png',
            'URL_VALIDACAO': f"https://script.google.com/macros/s/AKfycbw75sx77HBdie37fqoBg60wWgbb5QxD9uN5-Ee3aemwy8jVP2lqDImO0Brx4iFzsVan/exec?hash={hash_documento}",
            'NUM_RELATORIO': f"RT-{datetime.now().year}-{str(1).zfill(3)}",
            'DATA_EMISSAO': datetime.now().strftime('%d/%m/%Y'),
            'HORA_EMISSAO': datetime.now().strftime('%H:%M'),
            'NUM_PROTOCOLO': protocolo or f"VT-{datetime.now().strftime('%Y%m%d')}-{cliente_id or '000'}",
            'HASH_DOCUMENTO': hash_documento,
            'ENGENHEIRO_RESPONSAVEL': dados.get('engenheiro', 'Nícolas Alves de Sá'),
            'CREA_NUMERO': dados.get('crea', '5071237870'),
            'NUM_PROPOSTA': dados.get('num_proposta', ''),
            'NOME_CLIENTE': dados.get('nome_cliente', ''),
            'ENDERECO': dados.get('endereco', ''),
            'CPF_CNPJ': dados.get('cpf_cnpj', ''),
            'CONCESSIONARIA': dados.get('concessionaria', ''),
            'DATA_VISITA': dados.get('data_visita', ''),
            'OBSERVACOES_GERAIS': dados.get('observacoes_gerais', ''),
        }

        if tipo == 'sem_adequacao':
            context.update({
                'POTENCIA': dados.get('potencia', ''),
                'QTD_MODULOS': dados.get('qtd_modulos', ''),
                'INVERSOR': dados.get('inversor', ''),
                'GERACAO': dados.get('geracao', ''),
                'INVESTIMENTO': format_moeda(dados.get('investimento', 0)),
                'OBSERVACOES': dados.get('observacoes', ''),
            })
        elif tipo == 'com_adequacao':
            context.update({
                'DESAFIO_1': dados.get('desafio1', ''),
                'DESAFIO_2': dados.get('desafio2', ''),
                'DESAFIO_3': dados.get('desafio3', ''),
                'ADEQUACAO_LAYOUT_1': dados.get('adequacao_layout1', ''),
                'ADEQUACAO_LAYOUT_2': dados.get('adequacao_layout2', ''),
                'GERACAO_ORIGINAL': dados.get('geracao_original', ''),
                'GERACAO_OTIMIZADA': dados.get('geracao_otimizada', ''),
                'QTD_MODULOS_OPCAO1': dados.get('modulos_op1', ''),
                'INVERSOR_OPCAO1': dados.get('inversor_op1', ''),
                'VALOR_OPCAO1': format_moeda(dados.get('valor_op1', 0)),
                'GERACAO_OPCAO1': dados.get('geracao_op1', ''),
                'QTD_MODULOS_OPCAO2': dados.get('modulos_op2', ''),
                'INVERSOR_OPCAO2': dados.get('inversor_op2', ''),
                'VALOR_OPCAO2': format_moeda(dados.get('valor_op2', 0)),
                'GERACAO_OPCAO2': dados.get('geracao_op2', ''),
                'RECOMENDACAO_TECNICA': dados.get('recomendacao', ''),
                'LOCAL_QUADRO': dados.get('local_quadro', ''),
                'ADEQUACAO_TECNICA_1': dados.get('adequacao_tec1', ''),
                'ADEQUACAO_TECNICA_2': dados.get('adequacao_tec2', ''),
                'ADEQUACAO_TECNICA_3': dados.get('adequacao_tec3', ''),
                'VALOR_ADEQUACOES': format_moeda(dados.get('valor_adequacoes', 0)),
                'REFORCO_ESTRUTURAL': dados.get('reforco_estrutural', ''),
            })
            adequacoes = dados.get('adequacoes', ['geracao', 'homologacao'])
            context['ADEQUACOES'] = adequacoes
        elif tipo == 'fast_track':
            context.update({
                'GERACAO_ORIGINAL': dados.get('geracao_original', ''),
                'GERACAO_OTIMIZADA': dados.get('geracao_otimizada', ''),
                'QTD_MODULOS': dados.get('qtd_modulos', ''),
                'POTENCIA_INVERSOR': dados.get('potencia_inversor', ''),
                'LOCAL_INVERSOR': dados.get('local_inversor', ''),
                'OBSERVACOES': dados.get('observacoes', ''),
                'INVESTIMENTO': format_moeda(dados.get('investimento', 0)),
            })

        imagens = dados.get('imagens', {})
        for key, value in imagens.items():
            if value:
                context[key.upper()] = f"data:image/png;base64,{value}"

        html_rendered = render_template(template_file, **context)
        pdf_bytes = HTML(string=html_rendered).write_pdf()

        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        payload_script = {
            'token': TOKEN,
            'acao': 'salvar_pdf',
            'dados': {
                'nome_cliente': context['NOME_CLIENTE'] or 'cliente',
                'pdf_base64': pdf_base64,
                'tipo_documento': 'Visita_Tecnica',
                'cliente_id': cliente_id,
                'hash_documento': hash_documento,
                'subpasta': 'Visita_Tecnica',
            }
        }

        response = requests.post(APPS_SCRIPT_URL, json=payload_script)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                url = result.get('url')
                croqui_url = None

                # ===== SALVA A IMAGEM DO CROQUI NO DRIVE =====
                if dados.get('imagens') and dados['imagens'].get('croqui_layout'):
                    try:
                        imagem_base64 = dados['imagens']['croqui_layout']
                        nome_cliente = context.get('NOME_CLIENTE', 'cliente')
                        payload_imagem = {
                            'token': TOKEN,
                            'acao': 'salvar_imagem',
                            'dados': {
                                'cliente_id': cliente_id,
                                'nome_cliente': nome_cliente,
                                'imagem_base64': imagem_base64,
                                'subpasta': 'Visita_Tecnica',
                                'nome_arquivo': f'croqui_{cliente_id}.png'
                            }
                        }
                        response_img = requests.post(APPS_SCRIPT_URL, json=payload_imagem, timeout=180)
                        if response_img.status_code == 200:
                            result_img = response_img.json()
                            if result_img.get('success'):
                                croqui_url = result_img.get('url')
                                print(f"✅ Croqui salvo no Drive: {croqui_url}")
                            else:
                                print(f"⚠️ Erro ao salvar imagem no Drive: {result_img.get('error')}")
                        else:
                            print(f"⚠️ Erro ao comunicar com Apps Script: {response_img.status_code}")
                    except Exception as e:
                        print(f"⚠️ Erro ao salvar imagem: {e}")

                # ===== SALVA DADOS TÉCNICOS =====
                if cliente_id:
                    try:
                        cliente = buscar_cliente_por_id(cliente_id)
                        if cliente:
                            dados_visita = cliente.get('dados_visita', {})

                            # ---- SALVA DADOS COMUNS ----
                            dados_visita['hash_documento'] = hash_documento
                            dados_visita['relatorio_url'] = url
                            if protocolo and 'ultimo_protocolo' not in dados_visita:
                                dados_visita['ultimo_protocolo'] = protocolo

                            if dados.get('imagens') and dados['imagens'].get('croqui_layout'):
                                dados_visita['croqui_imagem'] = dados['imagens']['croqui_layout']
                                print("✅ Croqui encontrado, salvando...")
                            else:
                                print("⚠️ Croqui não encontrado no payload")

                            if croqui_url:
                                dados_visita['croqui_url'] = croqui_url
                                print(f"✅ URL do croqui salva: {croqui_url}")

                            # ---- DADOS COMUNS ----
                            dados_visita['potencia'] = dados.get('potencia') or dados.get('potencia_kwp') or ''
                            dados_visita['qtd_modulos'] = dados.get('qtd_modulos') or ''
                            dados_visita['inversor'] = dados.get('inversor') or ''
                            investimento = dados.get('investimento') or 0
                            if tipo == 'fast_track' and not investimento:
                                investimento = dados.get('investimento_original') or 0
                            dados_visita['investimento'] = investimento
                            geracao = dados.get('geracao_otimizada') or dados.get('geracao') or dados.get('geracao_estimada') or ''
                            dados_visita['geracao_estimada'] = geracao

                            linhas = dados.get('linhas', [])
                            if linhas and len(linhas) >= 2:
                                dados_visita['projecao'] = linhas[:5]
                                print(f"✅ Projeção salva (primeiras {len(linhas[:5])} linhas)")

                            dados_visita['ultimo_tipo_relatorio'] = tipo

                            # ---- DADOS ESPECÍFICOS ----
                            if tipo == 'sem_adequacao':
                                dados_visita['potencia'] = dados.get('potencia', '')
                                dados_visita['qtd_modulos'] = dados.get('qtd_modulos', '')
                                dados_visita['inversor'] = dados.get('inversor', '')
                                dados_visita['geracao_estimada'] = dados.get('geracao', '')
                                dados_visita['investimento'] = dados.get('investimento', 0)
                                linhas = dados.get('linhas', [])
                                if linhas and len(linhas) >= 2:
                                    dados_visita['projecao'] = linhas[:5]
                                print(f"✅ Dados do relatório 'sem adequação' salvos")

                            elif tipo == 'com_adequacao':
                                dados_visita['geracao_original'] = dados.get('geracao_original', '')
                                dados_visita['geracao_otimizada'] = dados.get('geracao_otimizada', '')
                                dados_visita['valor_adequacoes'] = dados.get('valor_adequacoes', 0)
                                dados_visita['modulos_op1'] = dados.get('modulos_op1', '')
                                dados_visita['inversor_op1'] = dados.get('inversor_op1', '')
                                dados_visita['valor_op1'] = dados.get('valor_op1', 0)
                                dados_visita['geracao_op1'] = dados.get('geracao_op1', '')
                                dados_visita['modulos_op2'] = dados.get('modulos_op2', '')
                                dados_visita['inversor_op2'] = dados.get('inversor_op2', '')
                                dados_visita['valor_op2'] = dados.get('valor_op2', 0)
                                dados_visita['geracao_op2'] = dados.get('geracao_op2', '')
                                dados_visita['desafio1'] = dados.get('desafio1', '')
                                dados_visita['desafio2'] = dados.get('desafio2', '')
                                dados_visita['desafio3'] = dados.get('desafio3', '')
                                dados_visita['recomendacao'] = dados.get('recomendacao', '')
                                dados_visita['adequacao_layout1'] = dados.get('adequacao_layout1', '')
                                dados_visita['adequacao_layout2'] = dados.get('adequacao_layout2', '')
                                dados_visita['local_quadro'] = dados.get('local_quadro', '')
                                dados_visita['reforco_estrutural'] = dados.get('reforco_estrutural', '')
                                dados_visita['adequacao_tec1'] = dados.get('adequacao_tec1', '')
                                dados_visita['adequacao_tec2'] = dados.get('adequacao_tec2', '')
                                dados_visita['adequacao_tec3'] = dados.get('adequacao_tec3', '')
                                dados_visita['adequacoes'] = dados.get('adequacoes', ['geracao', 'homologacao'])

                                # ===== RECALCULA A PROJEÇÃO COM A GERAÇÃO OTIMIZADA =====
                                try:
                                    projecao_original = dados_visita.get('projecao_preproposta', [])

                                    def to_float(valor, padrao=0.0):
                                        if valor is None:
                                            return padrao
                                        if isinstance(valor, (int, float)):
                                            return float(valor)
                                        if isinstance(valor, str):
                                            valor_limpo = valor.strip().replace(',', '.')
                                            if valor_limpo == '':
                                                return padrao
                                            try:
                                                return float(valor_limpo)
                                            except ValueError:
                                                return padrao
                                        return padrao

                                    tarifa = to_float(dados_visita.get('tarifa_preproposta'), 0.75)
                                    hsp = to_float(dados_visita.get('hsp'), 4.35)
                                    investimento = to_float(dados_visita.get('investimento_preproposta'), 0)

                                    consumo_atual = 0
                                    if projecao_original and len(projecao_original) > 0:
                                        primeira_linha = projecao_original[0]
                                        consumo_atual = primeira_linha.get('consumoAtual', 0)
                                        if consumo_atual == 0:
                                            custo_sem = primeira_linha.get('custoSemSolarMes', 0)
                                            if custo_sem > 0 and tarifa > 0:
                                                consumo_atual = custo_sem / tarifa

                                    if consumo_atual == 0 and investimento > 0:
                                        consumo_atual = investimento / (tarifa * 400)

                                    if consumo_atual == 0:
                                        consumo_atual = 300

                                    geracao_otimizada_val = dados.get('geracao_otimizada')
                                    if geracao_otimizada_val is None or str(geracao_otimizada_val).strip() == '':
                                        geracao_otimizada_val = dados_visita.get('geracao_otimizada', '0')
                                    geracao_otimizada_kw = to_float(geracao_otimizada_val, 0)

                                    if geracao_otimizada_kw < 10:
                                        geracao_otimizada_mensal = geracao_otimizada_kw * hsp * 0.8 * 30
                                    else:
                                        geracao_otimizada_mensal = geracao_otimizada_kw

                                    if geracao_otimizada_mensal < 50:
                                        geracao_otimizada_mensal = consumo_atual * 0.7

                                    # === SALVA DADOS PARA A PROPOSTA FINAL ===
                                    dados_visita['geracao_estimada'] = geracao_otimizada_mensal
                                    qtd_modulos_salvar = dados.get('modulos_op1') or dados.get('modulos_op2') or dados.get('qtd_modulos')
                                    if qtd_modulos_salvar:
                                        dados_visita['qtd_modulos'] = qtd_modulos_salvar

                                    print(f"📊 Dados Com Adequação: consumo={consumo_atual:.1f}, tarifa={tarifa:.4f}, geração_otimizada={geracao_otimizada_mensal:.1f}")

                                    nova_projecao = []
                                    for i in range(5):
                                        ano = i + 1
                                        eficiencia = max(1 - i * 0.0055, 0.8)
                                        tarifa_ano = tarifa * (1 + 0.085) ** i
                                        geracao_mensal = geracao_otimizada_mensal * eficiencia

                                        custo_sem_mes = consumo_atual * tarifa_ano * 1.04
                                        consumo_rede = max(0, consumo_atual - geracao_mensal + 30)
                                        injetado = geracao_mensal * 0.3
                                        compensacao = min(injetado, consumo_rede) * tarifa_ano * 0.5
                                        custo_com_mes = max(0, consumo_rede * tarifa_ano * 1.04 - compensacao)
                                        economia_anual = (custo_sem_mes - custo_com_mes) * 12 - 150

                                        nova_projecao.append({
                                            'ano': ano,
                                            'custoSemSolarMes': custo_sem_mes,
                                            'custoComSolarMes': custo_com_mes,
                                            'economiaAnual': max(economia_anual, 0)
                                        })

                                    dados_visita['projecao'] = nova_projecao
                                    print(f"✅ Projeção Com Adequação gerada com sucesso!")

                                except Exception as e:
                                    print(f"⚠️ Erro ao gerar projeção Com Adequação: {e}")
                                    import traceback
                                    traceback.print_exc()

                                print(f"✅ Dados do relatório 'com adequação' salvos")

                            elif tipo == 'fast_track':
                                dados_visita['geracao_original'] = dados.get('geracao_original', '')
                                dados_visita['geracao_otimizada'] = dados.get('geracao_otimizada', '')
                                dados_visita['potencia_inversor'] = dados.get('potencia_inversor', '')
                                dados_visita['local_inversor'] = dados.get('local_inversor', '')

                                # ===== RECALCULA A PROJEÇÃO COM A GERAÇÃO OTIMIZADA =====
                                try:
                                    projecao_original = dados_visita.get('projecao_preproposta', [])

                                    def to_float(valor, padrao=0.0):
                                        if valor is None:
                                            return padrao
                                        if isinstance(valor, (int, float)):
                                            return float(valor)
                                        if isinstance(valor, str):
                                            valor_limpo = valor.strip().replace(',', '.')
                                            if valor_limpo == '':
                                                return padrao
                                            try:
                                                return float(valor_limpo)
                                            except ValueError:
                                                return padrao
                                        return padrao

                                    tarifa = to_float(dados_visita.get('tarifa_preproposta'), 0.75)
                                    hsp = to_float(dados_visita.get('hsp'), 4.35)
                                    investimento_preproposta = to_float(dados_visita.get('investimento_preproposta'), 0)

                                    consumo_atual = 0
                                    if projecao_original and len(projecao_original) > 0:
                                        primeira_linha = projecao_original[0]
                                        consumo_atual = primeira_linha.get('consumoAtual', 0)
                                        if consumo_atual == 0:
                                            custo_sem = primeira_linha.get('custoSemSolarMes', 0)
                                            if custo_sem > 0 and tarifa > 0:
                                                consumo_atual = custo_sem / tarifa

                                    if consumo_atual == 0 and investimento_preproposta > 0:
                                        consumo_atual = investimento_preproposta / (tarifa * 400)

                                    if consumo_atual == 0:
                                        consumo_atual = 300

                                    geracao_otimizada_val = dados.get('geracao_otimizada')
                                    if geracao_otimizada_val is None or str(geracao_otimizada_val).strip() == '':
                                        geracao_otimizada_val = dados_visita.get('geracao_otimizada', '0')
                                    geracao_otimizada_kw = to_float(geracao_otimizada_val, 0)

                                    if geracao_otimizada_kw < 10:
                                        geracao_otimizada_mensal = geracao_otimizada_kw * hsp * 0.8 * 30
                                    else:
                                        geracao_otimizada_mensal = geracao_otimizada_kw

                                    if geracao_otimizada_mensal < 50:
                                        geracao_otimizada_mensal = consumo_atual * 0.7

                                    # === SALVA DADOS PARA A PROPOSTA FINAL ===
                                    dados_visita['geracao_estimada'] = geracao_otimizada_mensal
                                    if not dados_visita.get('qtd_modulos'):
                                        qtd_modulos_salvar = dados.get('qtd_modulos')
                                        if qtd_modulos_salvar:
                                            dados_visita['qtd_modulos'] = qtd_modulos_salvar

                                    print(f"📊 Dados Fast Track: consumo={consumo_atual:.1f}, tarifa={tarifa:.4f}, geração_otimizada={geracao_otimizada_mensal:.1f}")

                                    nova_projecao = []
                                    for i in range(5):
                                        ano = i + 1
                                        eficiencia = max(1 - i * 0.0055, 0.8)
                                        tarifa_ano = tarifa * (1 + 0.085) ** i
                                        geracao_mensal = geracao_otimizada_mensal * eficiencia

                                        custo_sem_mes = consumo_atual * tarifa_ano * 1.04
                                        consumo_rede = max(0, consumo_atual - geracao_mensal + 30)
                                        injetado = geracao_mensal * 0.3
                                        compensacao = min(injetado, consumo_rede) * tarifa_ano * 0.5
                                        custo_com_mes = max(0, consumo_rede * tarifa_ano * 1.04 - compensacao)
                                        economia_anual = (custo_sem_mes - custo_com_mes) * 12 - 150

                                        nova_projecao.append({
                                            'ano': ano,
                                            'custoSemSolarMes': custo_sem_mes,
                                            'custoComSolarMes': custo_com_mes,
                                            'economiaAnual': max(economia_anual, 0)
                                        })

                                    dados_visita['projecao'] = nova_projecao
                                    print(f"✅ Projeção Fast Track gerada com sucesso!")

                                except Exception as e:
                                    print(f"⚠️ Erro ao gerar projeção Fast Track: {e}")
                                    import traceback
                                    traceback.print_exc()

                                print(f"✅ Dados do relatório 'fast track' salvos")

                            # ---- ATUALIZA O CLIENTE ----
                            payload_hash = {
                                "acao": "adminAtualizarCliente",
                                "idCliente": str(cliente_id),
                                "campos": {
                                    "dados_visita": dados_visita
                                },
                                "senhaAdmin": "SoLiVi@64253798@"
                            }
                            requests.post(URL_AREA_CLIENTE, json=payload_hash, timeout=30)
                            print(f"✅ Hash salvo na planilha via Área do Cliente: {hash_documento}")

                    except Exception as e:
                        print(f"⚠️ Erro ao salvar dados via Área do Cliente: {e}")
                        import traceback
                        traceback.print_exc()

                return _cors_response({'success': True, 'url': url})
            else:
                return _cors_response({'success': False, 'error': result.get('error', 'Erro ao salvar no Drive')}, 500)
        else:
            return _cors_response({'success': False, 'error': f'Erro ao comunicar com o Apps Script: {response.status_code}'}, 500)

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return _cors_response({'success': False, 'error': str(e)}, 500)

# ============================================================
# ROTA GERAR PROPOSTA FINAL
# ============================================================
@app.route('/gerar_proposta_final', methods=['POST'])
def gerar_proposta_final():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        cliente_id = dados.get('cliente_id')
        if not cliente_id:
            return jsonify({'success': False, 'error': 'cliente_id não informado'}), 400

        cliente = buscar_cliente_por_id(cliente_id)
        if not cliente:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        # ===== BUSCA CPF/CNPJ DE dados_preproposta =====
        dados_preproposta = cliente.get('dados_preproposta', {})
        cpf_cnpj = dados_preproposta.get('cpf_cnpj', '')
        print(f"🔍 CPF/CNPJ recuperado de dados_preproposta: {cpf_cnpj}")

        dados_visita = cliente.get('dados_visita', {})
        documentos = cliente.get('documentos', {})

        nome_cliente = cliente.get('nome', '')
        email_cliente = cliente.get('email', '')
        telefone_cliente = cliente.get('telefone', '')
        endereco = cliente.get('endereco', '')

        # ===== PRIORIZA DADOS SALVOS (com fallback) =====
        potencia = dados_visita.get('potencia_inversor') or dados_visita.get('potencia') or dados_visita.get('potencia_kwp') or '0'
        qtd_modulos = dados_visita.get('qtd_modulos') or dados_visita.get('modulos') or '0'
        inversor = dados_visita.get('inversor') or 'Microinversor'
        geracao = dados_visita.get('geracao_otimizada') or dados_visita.get('geracao') or dados_visita.get('geracao_estimada') or '0'
        investimento = dados_visita.get('investimento') or 0
        concessionaria = dados_visita.get('concessionaria') or cliente.get('concessionaria') or 'Concessionária local'

        condicao_pagamento = dados.get('condicao_pagamento', 'À vista, cartão de crédito ou financiamento')
        prazo_execucao = dados.get('prazo_execucao', '30 dias úteis')

        num_proposta = f"PF-{datetime.now().strftime('%Y%m%d')}-{cliente_id}"

        beneficios = [
            "💰 Redução de até 95% na conta de luz",
            "🔋 Energia limpa e sustentável",
            "📈 Valorização do imóvel",
            "🔒 Garantia de 25 anos nos painéis",
            "🛡️ Proteção contra aumentos tarifários"
        ]

        inclusos = [
            "Engenharia e Homologação (Gestão completa com a concessionária)",
            "Aquisição e Logística de Equipamentos",
            "Instalação Técnica Especializada",
            "Suporte e Monitoramento pós-instalação",
            "Garantia do Serviço"
        ]
        exclusos = [
            "Obras civis (reformas de telhado ou alvenaria)",
            "Adequação elétrica pesada (fora das normas atuais)"
        ]

        itens_escopo = [
            {'desc': f'Sistema Fotovoltaico {potencia} kWp', 'marca': inversor, 'qtd': qtd_modulos, 'preco': format_moeda_sem_prefixo(investimento)},
            {'desc': 'Estrutura de fixação', 'marca': 'Conforme projeto', 'qtd': '1', 'preco': '0,00'},
            {'desc': 'Cabeamento e conectores', 'marca': 'Conforme projeto', 'qtd': '1', 'preco': '0,00'},
        ]

        # ===== COMPARATIVO FINANCEIRO (VERSÃO SEGURA) =====
        projecao = dados_visita.get('projecao', [])
        if projecao and len(projecao) >= 2:
            comparativo_real = []
            for i, linha in enumerate(projecao[:5]):
                ano = i + 1
                custo_sem = float(linha.get('custoSemSolarMes', 0)) * 12
                custo_com = float(linha.get('custoComSolarMes', 0)) * 12
                economia = float(linha.get('economiaAnual', 0))
                comparativo_real.append({
                    'ano': ano,
                    'custoSem': format_moeda_sem_prefixo(custo_sem),
                    'custoCom': format_moeda_sem_prefixo(custo_com),
                    'economia': format_moeda_sem_prefixo(max(economia, 0))
                })
        else:
            tarifa = float(dados_visita.get('tarifa_preproposta') or 0.75)
            producao_mensal = float(geracao) if geracao and str(geracao).strip() else 0
            invest = float(investimento) if investimento else 0

            if producao_mensal > 0 and invest > 0:
                comparativo_real = []
                for ano in range(1, 6):
                    eficiencia = max(1 - (ano-1) * 0.0055, 0)
                    tarifa_ano = tarifa * (1 + 0.085) ** (ano-1)
                    geracao_mensal = producao_mensal * eficiencia
                    economia_anual = (geracao_mensal * tarifa_ano * 0.8) * 12 - 150
                    if ano <= (dados_visita.get('prazo_financiamento') or 0):
                        economia_anual -= invest / ((dados_visita.get('prazo_financiamento') or 1) * 12) * 12
                    custo_sem = producao_mensal / 0.8 * tarifa_ano * 12 * 1.04
                    custo_com = max(0, (producao_mensal / 0.8 - geracao_mensal + 30) * tarifa_ano * 12)
                    comparativo_real.append({
                        'ano': ano,
                        'custoSem': format_moeda_sem_prefixo(max(0, custo_sem)),
                        'custoCom': format_moeda_sem_prefixo(max(0, custo_com)),
                        'economia': format_moeda_sem_prefixo(max(0, economia_anual))
                    })
            else:
                comparativo_real = [
                    {'ano': 1, 'custoSem': '5.000,00', 'custoCom': '1.200,00', 'economia': '3.800,00'},
                    {'ano': 2, 'custoSem': '5.400,00', 'custoCom': '1.250,00', 'economia': '4.150,00'},
                    {'ano': 3, 'custoSem': '5.800,00', 'custoCom': '1.300,00', 'economia': '4.500,00'},
                    {'ano': 4, 'custoSem': '6.200,00', 'custoCom': '1.350,00', 'economia': '4.850,00'},
                    {'ano': 5, 'custoSem': '6.600,00', 'custoCom': '1.400,00', 'economia': '5.200,00'},
                ]

        hash_input = f"{cliente_id}{datetime.now().isoformat()}"
        hash_documento = hashlib.sha256(hash_input.encode()).hexdigest()
        url_validacao = f"https://script.google.com/macros/s/AKfycbw75sx77HBdie37fqoBg60wWgbb5QxD9uN5-Ee3aemwy8jVP2lqDImO0Brx4iFzsVan/exec?hash={hash_documento}"

        # ===== FOTO DA CAPA =====
        croqui_imagem = dados_visita.get('croqui_imagem')
        croqui_url = dados_visita.get('croqui_url')

        if croqui_imagem:
            foto_capa = f"data:image/png;base64,{croqui_imagem}"
            print(f"📸 Usando base64 do croqui (tamanho: {len(croqui_imagem)} caracteres)")
        elif croqui_url:
            foto_capa = croqui_url
            print(f"📸 Usando URL do croqui: {croqui_url}")
        else:
            foto_capa = 'https://images.unsplash.com/photo-1509391366360-2e959784a276?w=600&h=300&fit=crop'
            print("📸 Usando imagem fallback (Unsplash)")

        context = {
            'RAZAO_SOCIAL': 'SoLivia Engenharia LTDA',
            'NOME_FANTASIA': 'SoLivia Engenharia',
            'CNPJ': '49.972.976/0001-15',
            'TELEFONE': '(11) 5028-2426',
            'EMAIL': 'contato@solivia.com.br',
            'SITE': 'solivia.com.br',
            'ENDERECO_EMPRESA': 'Rua Jerônimo Bueno, 28 - São Paulo/SP',
            'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
            'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
            'SELO_QUALIDADE': 'https://i.imgur.com/hVtSG8M.png',
            'FOTO_CAPA_MIOLO': foto_capa,
            'NUM_PROPOSTA': num_proposta,
            'REVISAO': 'RV00',
            'DATA_EMISSAO': datetime.now().strftime('%d/%m/%Y'),
            'HORA_EMISSAO': datetime.now().strftime('%H:%M'),
            'NOME_CLIENTE': nome_cliente,
            'TELEFONE_CLIENTE': telefone_cliente,
            'CPF_CNPJ': cpf_cnpj,
            'ENDERECO': endereco,
            'NUMERO_ENDERECO': '',
            'FRASE_IMPACTO': 'Energia solar: economia, sustentabilidade e valorização do seu imóvel',
            'RESUMO_SOLUCAO': f'Instalação de sistema fotovoltaico com {potencia} kWp, composto por {qtd_modulos} módulos, garantindo uma geração estimada de {geracao} kWh/mês e economia de até 95% na conta de luz.',
            'BENEFICIOS': beneficios,
            'INCLUSOS': inclusos,
            'EXCLUSOS': exclusos,
            'ITENS_ESCOPO': itens_escopo,
            'VALOR_TOTAL': format_moeda(investimento),
            'CONDICAO_1': 'À vista com 10% de desconto',
            'CONDICAO_2': 'Cartão de crédito',
            'CONDICAO_3': 'Financiamento',
            'OBSERVACOES_COMERCIAIS': f'Condição de pagamento: {condicao_pagamento}. Prazo de execução: {prazo_execucao}.',
            'PRAZO_EXECUCAO': prazo_execucao,
            'VALIDADE_PROPOSTA': '15 dias úteis',
            'COMPARATIVO': comparativo_real,
            'GRAFICO_BASE64': None,
            'HASH_DOCUMENTO': hash_documento,
            'URL_VALIDACAO': url_validacao,
            'NUM_PROTOCOLO': f'PF-{datetime.now().strftime("%Y%m%d")}-{cliente_id}'
        }

        print(f"🔍 Contexto completo: {context.keys()}")
        print(f"🔍 CPF_CNPJ no contexto: {context.get('CPF_CNPJ', '')}")

        html_rendered = render_template('proposta_final.html', **context)
        pdf_bytes = HTML(string=html_rendered).write_pdf()

        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        payload_script = {
            'token': TOKEN,
            'acao': 'salvar_pdf',
            'dados': {
                'nome_cliente': nome_cliente or 'cliente',
                'pdf_base64': pdf_base64,
                'cliente_id': cliente_id,
                'hash_documento': hash_documento,
                'subpasta': 'Documentos',
                'nome_arquivo': f"PropostaFinal_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
            }
        }

        response = requests.post(APPS_SCRIPT_URL, json=payload_script, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                url_pdf = result.get('url')
                try:
                    cliente_atual = buscar_cliente_por_id(cliente_id)
                    if cliente_atual:
                        docs = cliente_atual.get('documentos', {})
                        docs['proposta_final'] = {
                            'url': url_pdf,
                            'data_geracao': datetime.now().isoformat(),
                            'hash': hash_documento
                        }
                        payload_update = {
                            "acao": "adminAtualizarCliente",
                            "idCliente": str(cliente_id),
                            "campos": {
                                "documentos": docs
                            },
                            "senhaAdmin": "SoLiVi@64253798@"
                        }
                        requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                        print(f"✅ Proposta final salva para cliente {cliente_id}")
                except Exception as e:
                    print(f"⚠️ Erro ao atualizar planilha: {e}")

                return jsonify({'success': True, 'url': url_pdf, 'message': 'Proposta final gerada com sucesso!'})
            else:
                return jsonify({'success': False, 'error': result.get('error', 'Erro ao salvar no Drive')}), 500
        else:
            return jsonify({'success': False, 'error': f'Erro no Apps Script: {response.status_code}'}), 500

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTAS ADICIONAIS
# ============================================================

@app.route('/ping', methods=['GET'])
def ping():
    return {'status': 'ok', 'message': 'SoLivia Engenharia - Gerador de Propostas e Relatórios'}

@app.route('/api/atualizar_relatorio_url', methods=['POST'])
def atualizar_relatorio_url():
    try:
        dados = request.get_json()
        cliente_id = dados.get('cliente_id')
        relatorio_url = dados.get('relatorio_url')
        senha_admin = dados.get('senhaAdmin', 'SoLiVi@64253798@')

        if not cliente_id or not relatorio_url:
            return jsonify({'success': False, 'error': 'cliente_id e relatorio_url são obrigatórios'}), 400

        cliente = buscar_cliente_por_id(cliente_id)
        if not cliente:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        campos = {
            'dados_visita': {
                **cliente.get('dados_visita', {}),
                'relatorio_url': relatorio_url
            }
        }

        payload = {
            'acao': 'adminAtualizarCliente',
            'idCliente': str(cliente_id),
            'campos': campos,
            'senhaAdmin': senha_admin
        }
        response = requests.post(URL_AREA_CLIENTE, json=payload, timeout=30)
        resultado = response.json()

        if resultado.get('success'):
            return jsonify({'success': True, 'message': 'URL do relatório atualizada'})
        else:
            return jsonify({'success': False, 'error': resultado.get('error', 'Erro ao atualizar')}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTA: UPLOAD DE DOCUMENTO (CORRIGIDA INDENTAÇÃO)
# ============================================================
@app.route('/api/upload_documento_admin', methods=['POST'])
def upload_documento_admin():
    try:
        cliente_id = request.form.get('cliente_id')
        tipo_doc = request.form.get('tipo_doc')
        arquivo = request.files.get('arquivo')

        if not cliente_id or not tipo_doc or not arquivo:
            return jsonify({'success': False, 'error': 'Dados incompletos'}), 400

        # Determina subpasta (agora tipo_doc já existe)
        if tipo_doc.startswith('instalacao_foto_'):
            subpasta = 'Instalacao'
        elif tipo_doc.startswith('homologacao_foto_'):
            subpasta = 'Homologacao'
        else:
            subpasta = 'Documentos'

        # LOG (agora tipo_doc e subpasta estão definidos)
        print(f"📥 Upload: tipo_doc={tipo_doc}, subpasta={subpasta}")

        base64_content = base64.b64encode(arquivo.read()).decode('utf-8')
        nome_arquivo = arquivo.filename

        cliente = buscar_cliente_por_id(cliente_id)
        if not cliente:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        payload = {
            'acao': 'uploadDocumentoAdmin',
            'senhaAdmin': 'SoLiVi@64253798@',
            'cliente_id': cliente_id,
            'tipo_doc': tipo_doc,
            'nome_arquivo': nome_arquivo,
            'base64': base64_content,
            'subpasta': subpasta
        }

        response = requests.post(URL_AREA_CLIENTE, json=payload, timeout=30)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return jsonify({'success': True, 'url': data.get('url')})
            else:
                return jsonify({'success': False, 'error': data.get('error', 'Erro no Apps Script')}), 500
        else:
            return jsonify({'success': False, 'error': f'Erro no Apps Script: {response.status_code}'}), 500

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTA: GERAR CONTRATO (CLIENTE E PRESTADOR)
# ============================================================

@app.route('/gerar_contrato', methods=['OPTIONS'])
def gerar_contrato_options():
    response = jsonify({'status': 'ok'})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response, 200

@app.route('/gerar_contrato', methods=['POST'])
def gerar_contrato():
    def _cors_response(data, status=200):
        resp = jsonify(data)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return resp, status

    try:
        dados = request.get_json()
        if not dados:
            return _cors_response({'success': False, 'error': 'Dados não fornecidos'}, 400)

        tipo = dados.get('tipo', 'cliente')

        # ===== CONTRATO DO PRESTADOR =====
        if tipo in ('prestador', 'parceiro'):
            # ... (código existente, sem alterações) ...
            pass

        # ===== CONTRATO DO CLIENTE =====
        elif tipo == 'cliente':
            cliente_id = dados.get('cliente_id')
            if not cliente_id:
                return _cors_response({'success': False, 'error': 'cliente_id não informado'}, 400)

            cliente = buscar_cliente_por_id(cliente_id)
            if not cliente:
                return _cors_response({'success': False, 'error': 'Cliente não encontrado'}, 404)

            ## --- Dados do cliente ---
            nome_cliente = cliente.get('nome', '')
            email_cliente = cliente.get('email', '')
            telefone_cliente = cliente.get('telefone', '')
            endereco = cliente.get('endereco', '')
            dados_preproposta = cliente.get('dados_preproposta', {})
            cpf_cnpj = dados_preproposta.get('cpf_cnpj', '')
            print(f"🔍 CPF/CNPJ recuperado de dados_preproposta: {cpf_cnpj}")

            dados_visita = cliente.get('dados_visita', {})

            # ===== DETERMINA OS DADOS DO SISTEMA BASEADO NO TIPO DE RELATÓRIO =====
            tipo_relatorio = dados_visita.get('ultimo_tipo_relatorio', '')

            # Valores padrão
            potencia = '0'
            qtd_modulos = '0'
            inversor = 'Conforme projeto'
            geracao = '0'
            investimento = 0

            if tipo_relatorio == 'sem_adequacao':
                # Tenta pegar a potência do campo específico
                potencia = dados_visita.get('potencia') or '0'
                # Se ainda estiver vazio, tenta usar a potência da pré-proposta
                if not potencia or potencia == '0':
                    potencia = dados_visita.get('potencia_kwp') or '0'
                # Se ainda estiver vazio, tenta estimar pela geração (dividindo por HSP médio ~4.5)
                if not potencia or potencia == '0':
                    geracao_estimada = dados_visita.get('geracao_estimada') or dados_visita.get('geracao') or 0
                    if geracao_estimada and float(geracao_estimada) > 0:
                        # Estima potência = geração mensal / (HSP * 30) ~ 4.5
                        potencia = str(round(float(geracao_estimada) / 4.5, 2))
                # Fallback final
                if not potencia or potencia == '0':
                    potencia = '0'

                qtd_modulos = dados_visita.get('qtd_modulos') or '0'
                inversor = dados_visita.get('inversor') or 'Conforme projeto'
                geracao = dados_visita.get('geracao') or '0'
                investimento = dados_visita.get('investimento', 0)

            elif tipo_relatorio == 'com_adequacao':
                # Usa a opção 1 como padrão
                potencia = '0'  # Não temos kWp para com adequação
                qtd_modulos = dados_visita.get('modulos_op1') or dados_visita.get('modulos_op2') or '0'
                inversor = dados_visita.get('inversor_op1') or dados_visita.get('inversor_op2') or 'Conforme projeto'
                geracao = dados_visita.get('geracao_op1') or dados_visita.get('geracao_op2') or '0'
                investimento = dados_visita.get('valor_op1', 0) or dados_visita.get('valor_op2', 0)

            elif tipo_relatorio == 'fast_track':
                potencia = dados_visita.get('potencia_inversor', '0')
                qtd_modulos = dados_visita.get('qtd_modulos') or '0'
                inversor = 'Conforme projeto'
                geracao = dados_visita.get('geracao_otimizada') or dados_visita.get('geracao_original') or '0'
                investimento = dados_visita.get('investimento', 0)

            else:
                # Fallback
                potencia = dados_visita.get('potencia') or dados_visita.get('potencia_kwp') or '0'
                qtd_modulos = dados_visita.get('qtd_modulos') or dados_visita.get('modulos') or '0'
                inversor = dados_visita.get('inversor') or 'Conforme projeto'
                geracao = dados_visita.get('geracao') or dados_visita.get('geracao_estimada') or '0'
                investimento = (
                    dados_visita.get('investimento') or
                    dados_visita.get('valor_op1') or
                    dados_visita.get('investimento_preproposta') or
                    0
                )

            print(f"🔍 Tipo: {tipo_relatorio}")
            print(f"   Potência: {potencia} kWp | Módulos: {qtd_modulos} | Inversor: {inversor}")
            print(f"   Geração: {geracao} kWh/mês | Investimento: R$ {investimento}")

            concessionaria = dados_visita.get('concessionaria') or cliente.get('concessionaria') or 'Concessionária local'
            condicao_pagamento = dados.get('condicao_pagamento', 'À vista, cartão de crédito ou financiamento')
            prazo_execucao = dados.get('prazo_execucao', '30 dias úteis')

            num_contrato = f"CT-{datetime.now().strftime('%Y%m%d')}-{cliente_id}"

            context = {
                'RAZAO_SOCIAL': 'SoLivia Engenharia LTDA',
                'NOME_FANTASIA': 'SoLivia Engenharia',
                'CNPJ': '49.972.976/0001-15',
                'TELEFONE': '(11) 5028-2426',
                'EMAIL': 'contato@solivia.com.br',
                'ENDERECO_EMPRESA': 'Rua Jerônimo Bueno, 28 - São Paulo/SP',
                'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
                'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
                'SELO_QUALIDADE': 'https://i.imgur.com/hVtSG8M.png',
                'DATA_EMISSAO': datetime.now().strftime('%d/%m/%Y'),
                'NUM_CONTRATO': num_contrato,
                'NUM_PROPOSTA': dados_visita.get('ultimo_protocolo', ''),
                'NOME_CLIENTE': nome_cliente,
                'CPF_CNPJ': cpf_cnpj,
                'ENDERECO': endereco,
                'TELEFONE_CLIENTE': telefone_cliente,
                'REPRESENTANTE_CLIENTE': nome_cliente,
                'CARGO_CLIENTE': 'Proprietário',
                'REPRESENTANTE': 'Nícolas Alves de Sá',
                'CARGO_REPRESENTANTE': 'Sócio-Administrador',
                'TIPO_SERVICO': 'Sistema Fotovoltaico',
                'POTENCIA': potencia,
                'QTD_MODULOS': qtd_modulos,
                'INVERSOR': inversor,
                'GERACAO': geracao,
                'VALOR_FORMATADO': format_moeda(investimento),
                'VALOR_EXTENSO': f"R$ {float(investimento):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
                'COND_PAGAMENTO': condicao_pagamento,
                'PRAZO_EXECUCAO': prazo_execucao,
                'FOTO_CAPA': None,
                'CONCESSIONARIA': concessionaria
            }

            # Gera o PDF
            html_rendered = render_template('contrato_cliente.html', **context)
            pdf_bytes = HTML(string=html_rendered).write_pdf()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

            nome_arquivo = f"Contrato_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

            hash_input = f"{cliente_id}{datetime.now().isoformat()}"
            hash_documento = hashlib.sha256(hash_input.encode()).hexdigest()

            # 1. Salva o PDF no Drive (sempre)
            payload_script = {
                'token': TOKEN,
                'acao': 'salvar_pdf',
                'dados': {
                    'nome_cliente': nome_cliente or 'cliente',
                    'pdf_base64': pdf_base64,
                    'cliente_id': cliente_id,
                    'hash_documento': hash_documento,
                    'subpasta': 'Documentos',
                    'nome_arquivo': nome_arquivo
                }
            }

            response = requests.post(APPS_SCRIPT_URL, json=payload_script, timeout=60)
            if response.status_code != 200:
                return _cors_response({'success': False, 'error': f'Erro ao salvar PDF no Drive: {response.status_code}'}, 500)

            result_save = response.json()
            if not result_save.get('success'):
                return _cors_response({'success': False, 'error': result_save.get('error', 'Erro ao salvar PDF no Drive')}, 500)

            url_pdf = result_save.get('url')

            # 2. Tenta enviar para assinatura (mas não quebra se falhar)
            resultado_assinatura = None
            document_id = None
            link_assinatura = None
            assinatura_ok = False

            try:
                posicao_engenheiro = {
                    "x": "66.0",           # 70% da largura (lado direito)
                    "y": "30.0",           # 65% da altura (ajuste fino)
                    "z": 7,                # página 7 (onde estão as assinaturas agora)
                    "element": "SIGNATURE"
                }
                posicao_cliente = {
                    "x": "15.0",           # 30% da largura (lado esquerdo)
                    "y": "30.0",           # 65% da altura
                    "z": 7,                # página 7
                    "element": "SIGNATURE"
                }

                resultado_assinatura = enviar_para_assinatura_autentique(
                    pdf_bytes=pdf_bytes,
                    nome_documento=nome_arquivo,
                    cliente_email=email_cliente,
                    cliente_nome=nome_cliente,
                    assinante_empresa=ASSINANTE_SOLIVIA,
                    posicao_engenheiro=posicao_engenheiro,
                    posicao_cliente=posicao_cliente
                )

                if resultado_assinatura and resultado_assinatura.get('success'):
                    document_id = resultado_assinatura.get('document_id')
                    link_assinatura = resultado_assinatura.get('link_assinatura')
                    assinatura_ok = True
                    print(f"✅ Envio para assinatura bem-sucedido. Document ID: {document_id}")
                else:
                    print(f"⚠️ Falha no envio para assinatura: {resultado_assinatura.get('error') if resultado_assinatura else 'Erro desconhecido'}")
            except Exception as e:
                print(f"⚠️ Exceção ao enviar para assinatura: {e}")
                import traceback
                traceback.print_exc()

            # 3. Atualiza a planilha com as informações do contrato
            try:
                cliente_atual = buscar_cliente_por_id(cliente_id)
                if cliente_atual:
                    docs = cliente_atual.get('documentos', {})
                    contrato_data = {
                        'url': url_pdf,
                        'data_geracao': datetime.now().isoformat(),
                        'status': 'assinado' if assinatura_ok else 'gerado'
                    }
                    if document_id:
                        contrato_data['document_id'] = document_id
                        contrato_data['link_assinatura'] = link_assinatura
                        if assinatura_ok:
                            contrato_data['status'] = 'enviado'
                            contrato_data['data_envio'] = datetime.now().isoformat()

                    docs['contrato'] = contrato_data

                    payload_update = {
                        "acao": "adminAtualizarCliente",
                        "idCliente": str(cliente_id),
                        "campos": {
                            "documentos": docs,
                            "etapa_atual": "documentos"
                        },
                        "senhaAdmin": "SoLiVi@64253798@"
                    }
                    requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                    print(f"✅ Planilha atualizada para cliente {cliente_id}")
            except Exception as e:
                print(f"⚠️ Erro ao atualizar planilha: {e}")

            # 4. Retorna a resposta final
            if assinatura_ok:
                return _cors_response({
                    'success': True,
                    'message': 'Contrato enviado para assinatura! O cliente receberá o link por e-mail.',
                    'link_assinatura': link_assinatura,
                    'document_id': document_id,
                    'url_pdf': url_pdf
                })
            else:
                # Mesmo sem assinatura, retorna o PDF gerado
                return _cors_response({
                    'success': True,
                    'message': 'Contrato gerado com sucesso, mas ocorreu um problema no envio para assinatura. Entre em contato com o suporte.',
                    'url_pdf': url_pdf,
                    'warning': resultado_assinatura.get('error') if resultado_assinatura else 'Erro desconhecido'
                })

        else:
            return _cors_response({'success': False, 'error': 'Tipo de contrato inválido'}, 400)

    except Exception as e:
        print(f"❌ Exceção em /gerar_contrato: {e}")
        import traceback
        traceback.print_exc()
        return _cors_response({'success': False, 'error': str(e)}, 500)


# ============================================================
# ROTA: GERAR RELATÓRIO DE COMISSIONAMENTO (INSERIDA CORRETAMENTE)
# ============================================================

@app.route('/gerar_relatorio_comissionamento', methods=['OPTIONS'])
def gerar_relatorio_comissionamento_options():
    response = jsonify({'status': 'ok'})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Max-Age'] = '3600'
    return response, 200

@app.route('/gerar_relatorio_comissionamento', methods=['POST'])
def gerar_relatorio_comissionamento():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        cliente_id = dados.get('cliente_id')
        if not cliente_id:
            return jsonify({'success': False, 'error': 'cliente_id não informado'}), 400

        cliente = buscar_cliente_por_id(cliente_id)
        print("🔍 comissionamento recebido:", cliente.get('dados_homologacao', {}).get('comissionamento', {}))
        if not cliente:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

            # ===== LOG DAS FOTOS RECUPERADAS =====
        dados_homologacao = cliente.get('dados_homologacao', {})
        fotos = dados_homologacao.get('fotos', {})
        print("📸 Fotos recuperadas da planilha:", fotos)

        # ===== EXTRAI DADOS DA HOMOLOGAÇÃO E COMISSIONAMENTO =====
        dados_homologacao = cliente.get('dados_homologacao', {})
        fotos = dados_homologacao.get('fotos', {})
        print("📸 Fotos recuperadas da planilha:", fotos)
        comiss = dados_homologacao.get('comissionamento', {})

        # ===== MAPEIA STATUS PARA COR E TEXTO =====
        status_text = comiss.get('status', 'Pendente')
        if status_text == 'Concluído':
            status_classe = 'status-aprovado'
        elif status_text == 'Com falhas':
            status_classe = 'status-reprovado'
        else:
            status_classe = 'status-parcial'

        # ===== DADOS PARA OS ENSAIOS =====
        def safe(valor):
            return valor if valor else '-'

        def resultado_classe(resultado):
            if resultado == 'ok':
                return 'ok'
            elif resultado == 'falha':
                return 'falha'
            return ''

            # ===== GERA HASH E PROTOCOLO UMA ÚNICA VEZ =====
        hash_input = f"{cliente_id}{datetime.now().isoformat()}"
        hash_documento = hashlib.sha256(hash_input.encode()).hexdigest()

# Protocolo automático se não tiver
        protocolo = dados_homologacao.get('protocolo', '')
# Se não tiver protocolo, ou for o antigo fixo, gera novo
        if not protocolo or protocolo == 'PROTO-2026-001':
         protocolo = f"COM-{datetime.now().strftime('%Y%m%d')}-{cliente_id}"

        # ===== CONTEXTO PARA O TEMPLATE =====
        context = {
            'RAZAO_SOCIAL': 'SoLivia Engenharia LTDA',
            'NOME_FANTASIA': 'SoLivia Engenharia',
            'CNPJ': '49.972.976/0001-15',
            'TELEFONE': '(11) 5028-2426',
            'EMAIL': 'contato@solivia.com.br',
            'SITE': 'solivia.com.br',
            'ENDERECO_EMPRESA': 'Rua Jerônimo Bueno, 28 - São Paulo/SP',
            'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
            'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
            'NOME_CLIENTE': cliente.get('nome', ''),
            'CPF_CNPJ': (
    cliente.get('dados_preproposta', {}).get('cpf_cnpj', '') or
    cliente.get('cpf_cnpj', '') or
    ''
),
            'ENDERECO': cliente.get('endereco', ''),
            'ENGENHEIRO_RESPONSAVEL': comiss.get('responsavel', 'Nícolas Alves de Sá'),
            'CREA_NUMERO': '5071237870',
            'DATA_INSTALACAO': dados_homologacao.get('data_vistoria', ''),
            'DATA_COMISSIONAMENTO': comiss.get('data', ''),
            'STATUS': status_text,
            'STATUS_CLASSE': status_classe,
            'POTENCIA_KWP': comiss.get('potencia_kwp', ''),
            'QTD_MODULOS': comiss.get('qtd_modulos', ''),
            'MARCA_MODULOS': comiss.get('marca_modulos', ''),
            'POTENCIA_INVERSOR': comiss.get('potencia_inversor', ''),
            'MARCA_INVERSOR': comiss.get('marca_inversor', ''),
            'TIPO_SISTEMA': comiss.get('tipo_sistema', ''),
            'NUM_STRINGS': comiss.get('num_strings', ''),
            'MODULOS_POR_STRING': comiss.get('modulos_por_string', ''),
            'TENSAO_NOMINAL': comiss.get('tensao_nominal', ''),
            'CORRENTE_NOMINAL': comiss.get('corrente_nominal', ''),
            'FREQUENCIA': comiss.get('frequencia', ''),
            'CLASSE_ISOLAMENTO': comiss.get('classe_isolamento', ''),
            'TENSAO_CC': comiss.get('tensao_cc', ''),
            'CORRENTE_CC': comiss.get('corrente_cc', ''),
            'TENSAO_CA': comiss.get('tensao_ca', ''),
            'FREQUENCIA_REDE': comiss.get('frequencia_rede', ''),
            'TESTE_ISOLAMENTO': comiss.get('teste_isolamento', ''),
            'TESTE_ATERRAMENTO': comiss.get('teste_aterramento', ''),
            'IDENTIFICACAO_POLOS': comiss.get('identificacao_polos', ''),
            'INVERSOR_LIGOU': comiss.get('inversor_ligou', ''),
            'MONITORAMENTO_CONFIGURADO': comiss.get('monitoramento_configurado', ''),
            'COMUNICACAO_APP': comiss.get('comunicacao_app', ''),
            'SISTEMA_GERANDO': comiss.get('sistema_gerando', ''),
            'ENSAIO_VOC': safe(comiss.get('ensaio_voc', '')),
            'ENSAIO_VOC_RESULTADO': resultado_classe(comiss.get('ensaio_voc_resultado', '')),
            'ENSAIO_ISC': safe(comiss.get('ensaio_isc', '')),
            'ENSAIO_ISC_RESULTADO': resultado_classe(comiss.get('ensaio_isc_resultado', '')),
            'ENSAIO_ISOLAMENTO': safe(comiss.get('ensaio_isolamento', '')),
            'ENSAIO_ISOLAMENTO_RESULTADO': resultado_classe(comiss.get('ensaio_isolamento_resultado', '')),
            'ENSAIO_ATERRAMENTO': safe(comiss.get('ensaio_aterramento', '')),
            'ENSAIO_ATERRAMENTO_RESULTADO': resultado_classe(comiss.get('ensaio_aterramento_resultado', '')),
            'ENSAIO_CONTINUIDADE': safe(comiss.get('ensaio_continuidade', '')),
            'ENSAIO_CONTINUIDADE_RESULTADO': resultado_classe(comiss.get('ensaio_continuidade_resultado', '')),
            'ENSAIO_POLARIDADE': safe(comiss.get('ensaio_polaridade', '')),
            'ENSAIO_POLARIDADE_RESULTADO': resultado_classe(comiss.get('ensaio_polaridade_resultado', '')),
            'OBSERVACOES_ENSAIOS': comiss.get('obs_ensaios', ''),
            'OBSERVACOES_FINAIS': comiss.get('obs_finais', ''),
            'RESUMO_COMISSIONAMENTO': f"Sistema de {comiss.get('potencia_kwp', '')} kWp comissionado em {comiss.get('data', '')}.",
            'RESULTADO_GERAL': f"Comissionamento {status_text.lower()}",
            'RESULTADO_FINAL': f"Comissionamento {status_text.lower()}",
            'NUM_RELATORIO': f"RC-{datetime.now().strftime('%Y%m%d')}-{cliente_id}",
            'DATA_EMISSAO': datetime.now().strftime('%d/%m/%Y'),
            'HORA_EMISSAO': datetime.now().strftime('%H:%M'),
            'NUM_PROTOCOLO': protocolo,
            'HASH_DOCUMENTO': hash_documento,
            'URL_VALIDACAO': f"https://script.google.com/macros/s/AKfycbw75sx77HBdie37fqoBg60wWgbb5QxD9uN5-Ee3aemwy8jVP2lqDImO0Brx4iFzsVan/exec?hash={hash_documento}",
            'FOTO_SISTEMA': dados_homologacao.get('fotos', {}).get('sistema', ''),
            'CHECK_ESTRUTURA': comiss.get('check_estrutura', ''),
            'CHECK_MODULOS': comiss.get('check_modulos', ''),
            'CHECK_CONEXOES': comiss.get('check_conexoes', ''),
            'CHECK_ATERRAMENTO': comiss.get('check_aterramento', ''),
            'CHECK_CABEAMENTO': comiss.get('check_cabeamento', ''),
            # Fotos
'FOTO_ESTRUTURA_ANTES': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_estrutura_antes', '')),
'FOTO_ATERRAMENTO_SISTEMA': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_aterramento_sistema', '')),
'FOTO_QUADROS': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_quadros', '')),
'FOTO_CONEXOES': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_conexoes', '')),
'FOTO_QUADRO_REDE': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_quadro_rede', '')),
'FOTO_ATERRAMENTO_CARCACAS': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_aterramento_carcacas', '')),
'FOTO_INSPECAO_LOCAL': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_inspecao_local', '')),
'FOTO_FACHADA': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_fachada', '')),
'FOTO_IDENTIFICACAO_DISJUNTORES': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_identificacao_disjuntores', '')),
'FOTO_ETIQUETAS_CIRCUITOS': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_etiquetas_circuitos', '')),
'FOTO_TENSAO_CIRCUITOS': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_tensao_circuitos', '')),
'FOTO_CORRENTE_CIRCUITOS': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_corrente_circuitos', '')),
'FOTO_EPI': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_epi', '')),
'FOTO_APLICATIVO': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_aplicativo', '')),
'FOTO_SISTEMA': imagem_drive_para_base64(dados_homologacao.get('fotos', {}).get('foto_sistema', '')),
# Quadros e Circuitos
'TIPO_QUADRO': comiss.get('tipo_quadro', ''),
'QTD_CIRCUITOS': comiss.get('qtd_circuitos', ''),
'LOCAL_QUADRO': comiss.get('local_quadro', ''),
'ALTURA_QUADRO': comiss.get('altura_quadro', ''),
'DISTANCIA_PONTOS': comiss.get('distancia_pontos', ''),
'SISTEMA_ATERRADO': comiss.get('sistema_aterrado', ''),
'DUPLO_ISOLAMENTO': comiss.get('duplo_isolamento', ''),
'SEGUIR_DIAGRAMA': comiss.get('seguir_diagrama', ''),
'CIRCUITOS_VERIFICADOS': comiss.get('circuitos_verificados', ''),
# Monitoramento e Segurança
'APLICATIVO_MONITORAMENTO': comiss.get('aplicativo_monitoramento', ''),
'LOGIN_MONITORAMENTO': comiss.get('login_monitoramento', ''),
'SENHA_MONITORAMENTO': comiss.get('senha_monitoramento', ''),
'NF_ENVIADA': comiss.get('nf_enviada', ''),
'PROTECOES_TESTADAS': comiss.get('protecoes_testadas', ''),
'USARAM_EPI': comiss.get('usaram_epi', ''),
'INSPECAO_REALIZADA': comiss.get('inspecao_realizada', ''),
'PONTOS_ATENCAO': comiss.get('pontos_atencao', ''),
        }

                # ===== LOG DAS FOTOS NO CONTEXTO =====
        print("📸 FOTO_ESTRUTURA_ANTES (primeiros 100):", context.get('FOTO_ESTRUTURA_ANTES', '')[:100])
        print("📸 FOTO_ATERRAMENTO_SISTEMA (primeiros 100):", context.get('FOTO_ATERRAMENTO_SISTEMA', '')[:100])

        # ===== GERA O PDF =====
        html_rendered = render_template('relatorio_comissionamento.html', **context)
        pdf_bytes = HTML(string=html_rendered).write_pdf()
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

        # ===== SALVA NO DRIVE =====
        nome_cliente = cliente.get('nome', 'cliente').replace(' ', '_')
        nome_arquivo = f"Relatorio_Comissionamento_{nome_cliente}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

        payload_script = {
            'token': TOKEN,
            'acao': 'salvar_pdf',
            'dados': {
                'nome_cliente': cliente.get('nome', 'cliente'),
                'pdf_base64': pdf_base64,
                'cliente_id': cliente_id,
                'subpasta': 'Homologacao',
                'nome_arquivo': nome_arquivo
            }
        }

        response = requests.post(APPS_SCRIPT_URL, json=payload_script, timeout=60)
        if response.status_code != 200:
            return jsonify({'success': False, 'error': f'Erro ao salvar PDF: {response.status_code}'}), 500

        result = response.json()
        if not result.get('success'):
            return jsonify({'success': False, 'error': result.get('error', 'Erro no Apps Script')}), 500

        url_pdf = result.get('url')

        # ===== ATUALIZA A PLANILHA COM LINK, HASH E PROTOCOLO =====
        try:
            cliente_atual = buscar_cliente_por_id(cliente_id)
            if cliente_atual:
        # Atualiza dados_homologacao
                h = cliente_atual.get('dados_homologacao', {})
                h['laudo_comiss_url'] = url_pdf
                h['hash_documento'] = hash_documento
                h['protocolo'] = protocolo

        # Também salva em dados_visita (compatibilidade com validação existente)
                v = cliente_atual.get('dados_visita', {})
                v['hash_documento'] = hash_documento

                payload_update = {
            "acao": "adminAtualizarCliente",
            "idCliente": str(cliente_id),
            "campos": {
                "dados_homologacao": h,
                "dados_visita": v
            },
            "senhaAdmin": "SoLiVi@64253798@"
        }
                resp_update = requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                if resp_update.status_code == 200:
                    print(f"✅ Hash e protocolo salvos para cliente {cliente_id}")
                else:
                    print(f"❌ Erro ao salvar hash/protocolo: {resp_update.status_code}")
        except Exception as e:
            print(f"⚠️ Erro ao atualizar planilha: {e}")

        # ===== RESPONDE COM CORS =====
        resp = jsonify({'success': True, 'url': url_pdf, 'message': 'Relatório gerado com sucesso!'})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 200

    except Exception as e:
        print(f"❌ Erro em /gerar_relatorio_comissionamento: {e}")
        import traceback
        traceback.print_exc()
        resp = jsonify({'success': False, 'error': str(e)})
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp, 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
