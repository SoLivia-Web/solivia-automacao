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

warnings.filterwarnings("ignore")

app = Flask(__name__)

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
    """
    Busca um cliente na planilha pelo document_id salvo em documentos.contrato.document_id
    """
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
        posicao_engenheiro = {"x": 200, "y": 400, "z": 1}
    if posicao_cliente is None:
        posicao_cliente = {"x": 200, "y": 300, "z": 1}

    api_key = assinante_empresa["api_key"]

    query = """
    mutation CreateDocumentMutation($document: DocumentInput!, $signers: [SignerInput!]!, $file: Upload!) {
        createDocument(
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
        if "errors" in dados:
            return {"success": False, "error": dados["errors"]}
        resultado = dados.get("data", {}).get("createDocument", {})
        link_assinatura = None
        signatures = resultado.get("signatures", [])
        if signatures:
            for sig in signatures:
                link = sig.get("link")
                if link and link.get("short_link"):
                    link_assinatura = link["short_link"]
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

    response = requests.post(
        "https://autentique-proxy.ncalves91.workers.dev/v2/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=60,
        proxies={}
    )

    if response.status_code != 200:
        print(f"❌ Erro na requisição GraphQL: {response.status_code}")
        return None

    data = response.json()
    if "errors" in data:
        print(f"❌ Erro GraphQL: {data['errors']}")
        return None

    signed_url = data.get("data", {}).get("document", {}).get("files", {}).get("signed")
    if not signed_url:
        print("❌ Nenhum signed URL encontrado")
        return None

    print(f"📥 Baixando PDF via Worker: {signed_url}")

    pdf_response = requests.get(
        f"https://autentique-proxy.ncalves91.workers.dev/?url={signed_url}",
        timeout=60,
        proxies={}
    )

    if pdf_response.status_code == 200:
        print(f"✅ PDF baixado com sucesso: {len(pdf_response.content)} bytes")
        return pdf_response.content
    else:
        print(f"❌ Erro ao baixar PDF via Worker: {pdf_response.status_code}")
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
            pasta_id_destino = resultado_cliente.get('pastaId')
            senha = resultado_cliente.get('senha_temporaria')
            print(f"✅ Cliente criado: ID {cliente_id}, Pasta {pasta_id_destino}, Senha: {senha}")
        else:
            print(f"⚠️ Cliente não criado: {resultado_cliente.get('error')}")

        # ===== RESTO DA FUNÇÃO (GERAÇÃO DO PDF, SALVAMENTO, ETC.) =====
        # ... (mantenha o restante do código como está)

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

        projecao_20 = []
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
                        resultado = -investimento + max(economia_anual, 0)
                    else:
                        resultado = projecao_20[-1]['resultadoAcumulado'] + max(economia_anual, 0)
                    custo_sem = consumo_atual * tarifa_ano + consumo_atual * tarifa_ano * 0.04
                    custo_com = max(0, (consumo_atual - geracao_mensal + 30) * tarifa_ano)
                    saldo_poupanca = investimento * (1 + 0.0847) ** i
                    saldo_cdb_bruto = investimento * (1 + 0.135) ** i
                    saldo_cdb_liquido = investimento + (saldo_cdb_bruto - investimento) * (1 - 0.15)
                    cor = obter_cor_resultado_suave(resultado)
                    projecao_20.append({
                        'ano': i,
                        'custoSemSolarMes': format_moeda_sem_prefixo(custo_sem),
                        'eficiencia': round(eficiencia_val*100, 1),
                        'tarifa': format_moeda_sem_prefixo(tarifa_ano),
                        'custoComSolarMes': format_moeda_sem_prefixo(custo_com),
                        'economiaAnual': format_moeda_sem_prefixo(max(economia_anual, 0)),
                        'resultadoAcumulado': format_moeda_sem_prefixo(resultado),
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
                'pasta_id': pasta_id_destino
            }
        }

        response = requests.post(APPS_SCRIPT_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
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

@app.route('/webhook/autentique', methods=['POST'])
def webhook_autentique():
    try:
        data = request.json
        print("📥 Webhook Autentique recebido:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        event = data.get('event')
        document_id = data.get('data', {}).get('id')
        document_status = data.get('data', {}).get('status')

        if event == 'document.finished' and document_status == 'signed':
            print(f"✅ Documento {document_id} foi assinado!")

            cliente = buscar_cliente_por_documento_id(document_id)
            if not cliente:
                print(f"⚠️ Cliente com document_id {document_id} não encontrado.")
                return '', 200

            cliente_id = cliente['id']
            print(f"✅ Cliente encontrado: {cliente['nome']} (ID: {cliente_id})")

            api_key = AUTENTIQUE_API_KEY_SOLIVIA
            pdf_assinado_bytes = baixar_pdf_assinado(document_id, api_key)

            if not pdf_assinado_bytes:
                print("❌ Falha ao baixar PDF assinado")
                return '', 200

            print(f"✅ PDF assinado baixado: {len(pdf_assinado_bytes)} bytes")

            nome_arquivo = f"Contrato_Assinado_{cliente['nome'].replace(' ', '_')}.pdf"

            payload = {
                'acao': 'substituirPdfAssinado',
                'senhaAdmin': 'SoLiVi@64253798@',
                'cliente_id': cliente_id,
                'pdf_bytes': base64.b64encode(pdf_assinado_bytes).decode('utf-8'),
                'nome_arquivo': nome_arquivo
            }

            response = requests.post(URL_AREA_CLIENTE, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    nova_url = result.get('url')
                    print(f"✅ PDF assinado salvo no Drive: {nova_url}")

                    cliente_atual = buscar_cliente_por_id(cliente_id)
                    if cliente_atual:
                        docs = cliente_atual.get('documentos', {})
                        if 'contrato' not in docs:
                            docs['contrato'] = {}
                        docs['contrato']['url'] = nova_url
                        docs['contrato']['status'] = 'assinado'
                        docs['contrato']['data_assinatura'] = datetime.now().isoformat()

                        payload_update = {
                            "acao": "adminAtualizarCliente",
                            "idCliente": str(cliente_id),
                            "campos": {
                                "documentos": docs,
                                "etapa_atual": "instalacao",
                                "assinatura_data": datetime.now().isoformat()
                            },
                            "senhaAdmin": "SoLiVi@64253798@"
                        }
                        requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                        print(f"✅ Cliente {cliente_id} atualizado para 'instalacao'")

        return '', 200
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

# ============================================================
# ROTA MANUAL: FORÇAR ATUALIZAÇÃO DE ASSINATURA
# ============================================================
@app.route('/api/forcar_atualizacao_assinatura', methods=['POST'])
def forcar_atualizacao_assinatura():
    try:
        dados = request.get_json()
        document_id = dados.get('document_id')
        print(f"🔍 Document ID recebido: {document_id}")

        if not document_id:
            return jsonify({'success': False, 'error': 'document_id não fornecido'}), 400

        print("🔍 Buscando cliente por document_id...")
        cliente = buscar_cliente_por_documento_id(document_id)
        if not cliente:
            print("❌ Cliente não encontrado")
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        cliente_id = cliente['id']
        print(f"✅ Cliente encontrado: {cliente['nome']} (ID: {cliente_id})")

        print("🔍 Baixando PDF assinado...")
        api_key = AUTENTIQUE_API_KEY_SOLIVIA
        pdf_assinado_bytes = baixar_pdf_assinado(document_id, api_key)

        if not pdf_assinado_bytes:
            print("❌ Falha ao baixar PDF assinado")
            return jsonify({'success': False, 'error': 'Não foi possível baixar o PDF assinado'}), 500

        print(f"✅ PDF assinado baixado: {len(pdf_assinado_bytes)} bytes")

        print("🔍 Salvando PDF assinado no Drive...")
        nome_arquivo = f"Contrato_Assinado_{cliente['nome'].replace(' ', '_')}.pdf"

        payload = {
            'acao': 'substituirPdfAssinado',
            'senhaAdmin': 'SoLiVi@64253798@',
            'cliente_id': cliente_id,
            'pdf_bytes': base64.b64encode(pdf_assinado_bytes).decode('utf-8'),
            'nome_arquivo': nome_arquivo
        }

        response = requests.post(URL_AREA_CLIENTE, json=payload, timeout=30)
        print(f"📡 Status do Apps Script: {response.status_code}")
        print(f"📦 Resposta do Apps Script: {response.text}")

        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                nova_url = result.get('url')
                print(f"✅ PDF assinado salvo no Drive: {nova_url}")

                print("🔍 Atualizando planilha...")
                cliente_atual = buscar_cliente_por_id(cliente_id)
                if cliente_atual:
                    docs = cliente_atual.get('documentos', {})
                    if 'contrato' not in docs:
                        docs['contrato'] = {}
                    docs['contrato']['url'] = nova_url
                    docs['contrato']['status'] = 'assinado'
                    docs['contrato']['data_assinatura'] = datetime.now().isoformat()

                    payload_update = {
                        "acao": "adminAtualizarCliente",
                        "idCliente": str(cliente_id),
                        "campos": {
                            "documentos": docs,
                            "etapa_atual": "instalacao",
                            "assinatura_data": datetime.now().isoformat()
                        },
                        "senhaAdmin": "SoLiVi@64253798@"
                    }
                    update_response = requests.post(URL_AREA_CLIENTE, json=payload_update, timeout=30)
                    print(f"📡 Status da atualização: {update_response.status_code}")
                    print(f"📦 Resposta da atualização: {update_response.text}")

                    if update_response.status_code == 200:
                        update_result = update_response.json()
                        if update_result.get('success'):
                            return jsonify({'success': True, 'message': 'Cliente atualizado com sucesso', 'url': nova_url})

        return jsonify({'success': False, 'error': 'Erro ao processar'}), 500

    except Exception as e:
        print(f"❌ Exceção capturada: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTA PRINCIPAL: GERAR RELATÓRIO DE CONFORMIDADE
# ============================================================
@app.route('/gerar_relatorio_conformidade', methods=['OPTIONS'])
def handle_options_relatorio():
    response = jsonify({'status': 'ok'})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response, 200

@app.route('/gerar_relatorio_conformidade', methods=['POST'])
def gerar_relatorio_conformidade():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        tipo = dados.get('tipo')
        if tipo not in ['sem_adequacao', 'com_adequacao', 'fast_track']:
            return jsonify({'success': False, 'error': 'Tipo de relatório inválido'}), 400

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

                if cliente_id and hash_documento:
                    try:
                        cliente = buscar_cliente_por_id(cliente_id)
                        if cliente:
                            dados_visita = cliente.get('dados_visita', {})
                            dados_visita['hash_documento'] = hash_documento
                            dados_visita['relatorio_url'] = url
                            if protocolo and 'ultimo_protocolo' not in dados_visita:
                                dados_visita['ultimo_protocolo'] = protocolo

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
                        print(f"⚠️ Erro ao salvar hash via Área do Cliente: {e}")

                return jsonify({'success': True, 'url': url})
            else:
                return jsonify({'success': False, 'error': result.get('error', 'Erro ao salvar no Drive')}), 500
        else:
            return jsonify({'success': False, 'error': f'Erro ao comunicar com o Apps Script: {response.status_code}'}), 500

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

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

        dados_visita = cliente.get('dados_visita', {})
        documentos = cliente.get('documentos', {})

        nome_cliente = cliente.get('nome', '')
        email_cliente = cliente.get('email', '')
        telefone_cliente = cliente.get('telefone', '')
        endereco = cliente.get('endereco', '')
        cpf_cnpj = cliente.get('cpf_cnpj', '')

        potencia = dados_visita.get('potencia') or dados_visita.get('potencia_kwp') or '0'
        qtd_modulos = dados_visita.get('qtd_modulos') or dados_visita.get('modulos') or '0'
        inversor = dados_visita.get('inversor') or 'Conforme projeto'
        geracao = dados_visita.get('geracao') or dados_visita.get('geracao_estimada') or '0'
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

        comparativo = [
            {'ano': 1, 'custoSem': '5.000,00', 'custoCom': '1.200,00', 'economia': '3.800,00'},
            {'ano': 2, 'custoSem': '5.400,00', 'custoCom': '1.250,00', 'economia': '4.150,00'},
            {'ano': 3, 'custoSem': '5.800,00', 'custoCom': '1.300,00', 'economia': '4.500,00'},
            {'ano': 4, 'custoSem': '6.200,00', 'custoCom': '1.350,00', 'economia': '4.850,00'},
            {'ano': 5, 'custoSem': '6.600,00', 'custoCom': '1.400,00', 'economia': '5.200,00'},
        ]

        hash_input = f"{cliente_id}{datetime.now().isoformat()}"
        hash_documento = hashlib.sha256(hash_input.encode()).hexdigest()
        url_validacao = f"https://script.google.com/macros/s/AKfycbw75sx77HBdie37fqoBg60wWgbb5QxD9uN5-Ee3aemwy8jVP2lqDImO0Brx4iFzsVan/exec?hash={hash_documento}"

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
            'FOTO_CAPA_MIOLO': 'https://images.unsplash.com/photo-1509391366360-2e959784a276?w=600&h=300&fit=crop',
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
            'COMPARATIVO': comparativo,
            'GRAFICO_BASE64': None,
            'HASH_DOCUMENTO': hash_documento,
            'URL_VALIDACAO': url_validacao,
            'NUM_PROTOCOLO': f'PF-{datetime.now().strftime("%Y%m%d")}-{cliente_id}'
        }

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
# ROTA: GERAR CONTRATO (CLIENTE E PRESTADOR) – CORRIGIDA
# ============================================================
@app.route('/gerar_contrato', methods=['POST', 'OPTIONS'])
def gerar_contrato():
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response, 200

    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        tipo = dados.get('tipo', 'cliente')

        # ============================================================
        # CASO: CONTRATO DO PRESTADOR (com cliente_id)
        # ============================================================
        if tipo == 'prestador' or tipo == 'parceiro':
            prestador = dados.get('dados', {})
            if not prestador:
                return jsonify({'success': False, 'error': 'Dados do prestador não fornecidos'}), 400

            obrigatorios = ['nome', 'cpf', 'especialidade', 'duracao_meses', 'data_inicio', 'valor_combinado']
            faltando = [campo for campo in obrigatorios if not prestador.get(campo)]
            if faltando:
                return jsonify({'success': False, 'error': f'Campos obrigatórios faltando: {", ".join(faltando)}'}), 400

            cliente_id = dados.get('cliente_id')

            context = {
                'RAZAO_SOCIAL': 'SoLivia Engenharia LTDA',
                'NOME_FANTASIA': 'SoLivia Engenharia',
                'CNPJ': '49.972.976/0001-15',
                'TELEFONE': '(11) 5028-2426',
                'EMAIL': 'contato@solivia.com.br',
                'ENDERECO_EMPRESA': 'Rua Jerônimo Bueno, 28 - São Paulo/SP',
                'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
                'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
                'DATA_EMISSAO': datetime.now().strftime('%d/%m/%Y'),
                'NUM_CONTRATO': f'PR-{datetime.now().strftime("%Y%m%d")}-{str(prestador.get("cpf", ""))[-4:]}',
                'REPRESENTANTE': 'Nícolas Alves de Sá',
                'CARGO_REPRESENTANTE': 'Sócio-Administrador',
                'PRESTADOR_NOME': prestador.get('nome', ''),
                'PRESTADOR_CPF': prestador.get('cpf', ''),
                'PRESTADOR_RG': prestador.get('rg', ''),
                'PRESTADOR_NACIONALIDADE': prestador.get('nacionalidade', 'Brasileiro'),
                'PRESTADOR_ESTADO_CIVIL': prestador.get('estado_civil', ''),
                'PRESTADOR_PROFISSAO': prestador.get('profissao', ''),
                'PRESTADOR_ENDERECO': prestador.get('endereco', ''),
                'PRESTADOR_ESPECIALIDADE': prestador.get('especialidade', ''),
                'PRESTADOR_DURACAO_MESES': prestador.get('duracao_meses', '12'),
                'PRESTADOR_DATA_INICIO': prestador.get('data_inicio', datetime.now().strftime('%Y-%m-%d')),
                'PRESTADOR_VALOR_HORA': prestador.get('valor_combinado', ''),
                'PRESTADOR_BANCO': prestador.get('banco', ''),
                'PRESTADOR_AGENCIA': prestador.get('agencia', ''),
                'PRESTADOR_CONTA': prestador.get('conta', ''),
                'PRESTADOR_PIX': prestador.get('pix', '')
            }

            html_rendered = render_template('contrato_prestador.html', **context)
            pdf_bytes = HTML(string=html_rendered).write_pdf()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

            payload_script = {
                'token': TOKEN,
                'acao': 'salvar_pdf',
                'dados': {
                    'nome_cliente': prestador.get('nome', 'prestador'),
                    'pdf_base64': pdf_base64,
                    'cliente_id': cliente_id,
                    'subpasta': 'Instalacao',
                    'nome_arquivo': f"Contrato_Prestador_{prestador.get('nome', '').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"
                }
            }

            response = requests.post(APPS_SCRIPT_URL, json=payload_script, timeout=60)
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return jsonify({'success': True, 'url': result.get('url'), 'message': 'Contrato do prestador gerado com sucesso!'})
                else:
                    return jsonify({'success': False, 'error': result.get('error', 'Erro ao salvar no Drive')}), 500
            else:
                return jsonify({'success': False, 'error': f'Erro no Apps Script: {response.status_code}'}), 500

        # ============================================================
        # CASO: CONTRATO DO CLIENTE (COM ASSINATURA DIGITAL)
        # ============================================================
        elif tipo == 'cliente':
            cliente_id = dados.get('cliente_id')
            if not cliente_id:
                return jsonify({'success': False, 'error': 'cliente_id não informado'}), 400

            cliente = buscar_cliente_por_id(cliente_id)
            if not cliente:
                return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

            # --- Dados do cliente ---
            nome_cliente = cliente.get('nome', '')
            email_cliente = cliente.get('email', '')
            telefone_cliente = cliente.get('telefone', '')
            endereco = cliente.get('endereco', '')
            cpf_cnpj = cliente.get('cpf_cnpj', '')

            dados_visita = cliente.get('dados_visita', {})
            potencia = dados_visita.get('potencia') or dados_visita.get('potencia_kwp') or '0'
            qtd_modulos = dados_visita.get('qtd_modulos') or dados_visita.get('modulos') or '0'
            inversor = dados_visita.get('inversor') or 'Conforme projeto'
            geracao = dados_visita.get('geracao') or dados_visita.get('geracao_estimada') or '0'
            investimento = dados_visita.get('investimento') or 0
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
                'NUM_PROPOSTA': dados_visita.get('num_proposta', ''),
                'NOME_CLIENTE': nome_cliente,
                'CPF_CNPJ': cpf_cnpj,
                'ENDERECO': endereco,
                'TELEFONE_CLIENTE': telefone_cliente,
                'REPRESENTANTE_CLIENTE': nome_cliente,
                'CARGO_CLIENTE': 'Proprietário',
                'REPRESENTANTE': 'Nícolas Alves de Sá',
                'CARGO_REPRESENTANTE': 'Sócio-Administrador',
                'TIPO_SERVICO': 'Sistema Fotovoltaico',
                'VALOR_FORMATADO': format_moeda(investimento),
                'VALOR_EXTENSO': f"R$ {float(investimento):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
                'COND_PAGAMENTO': condicao_pagamento,
                'PRAZO_EXECUCAO': prazo_execucao,
                'FOTO_CAPA': None,
                'POTENCIA': potencia,
                'QTD_MODULOS': qtd_modulos,
                'INVERSOR': inversor,
                'GERACAO': geracao,
                'CONCESSIONARIA': concessionaria
            }

            html_rendered = render_template('contrato_cliente.html', **context)
            pdf_bytes = HTML(string=html_rendered).write_pdf()
            pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

            nome_arquivo = f"Contrato_{nome_cliente.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pdf"

            hash_input = f"{cliente_id}{datetime.now().isoformat()}"
            hash_documento = hashlib.sha256(hash_input.encode()).hexdigest()

            # Salva o PDF no Drive (pasta Documentos)
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
                return jsonify({'success': False, 'error': f'Erro ao salvar PDF no Drive: {response.status_code}'}), 500

            result_save = response.json()
            if not result_save.get('success'):
                return jsonify({'success': False, 'error': result_save.get('error', 'Erro ao salvar PDF no Drive')}), 500

            url_pdf = result_save.get('url')

            # Envia para assinatura via Autentique
            resultado_assinatura = enviar_para_assinatura_autentique(
                pdf_bytes=pdf_bytes,
                nome_documento=nome_arquivo,
                cliente_email=email_cliente,
                cliente_nome=nome_cliente,
                assinante_empresa=ASSINANTE_SOLIVIA
            )

            if not resultado_assinatura.get('success'):
                return jsonify({
                    'success': False,
                    'error': resultado_assinatura.get('error', 'Erro ao enviar para assinatura'),
                    'url_pdf': url_pdf
                }), 500

            document_id = resultado_assinatura.get('document_id')
            link_assinatura = resultado_assinatura.get('link_assinatura')

            # Atualiza a planilha
            try:
                cliente_atual = buscar_cliente_por_id(cliente_id)
                if cliente_atual:
                    docs = cliente_atual.get('documentos', {})
                    docs['contrato'] = {
                        'url': url_pdf,
                        'document_id': document_id,
                        'link_assinatura': link_assinatura,
                        'status': 'enviado',
                        'data_envio': datetime.now().isoformat()
                    }

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
                    print(f"✅ Contrato enviado para assinatura. Document ID: {document_id}")
            except Exception as e:
                print(f"⚠️ Erro ao atualizar planilha: {e}")

            return jsonify({
                'success': True,
                'message': 'Contrato enviado para assinatura! O cliente receberá o link por e-mail.',
                'link_assinatura': link_assinatura,
                'document_id': document_id,
                'url_pdf': url_pdf
            })

        else:
            return jsonify({'success': False, 'error': 'Tipo de contrato inválido'}), 400

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTAS ADICIONAIS
# ============================================================

@app.route('/gerar_relatorio_comissionamento', methods=['POST'])
def gerar_relatorio_comissionamento():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        cliente_id = dados.get('cliente_id')
        if not cliente_id:
            return jsonify({'success': False, 'error': 'cliente_id não informado'}), 400

        cliente_data = buscar_cliente_por_id(cliente_id)
        if not cliente_data:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        return jsonify({'success': True, 'message': 'Relatório de comissionamento gerado'})

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

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

@app.route('/api/upload_documento_admin', methods=['POST'])
def upload_documento_admin():
    try:
        cliente_id = request.form.get('cliente_id')
        tipo_doc = request.form.get('tipo_doc')
        arquivo = request.files.get('arquivo')

        if not cliente_id or not tipo_doc or not arquivo:
            return jsonify({'success': False, 'error': 'Dados incompletos'}), 400

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
            'base64': base64_content
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
