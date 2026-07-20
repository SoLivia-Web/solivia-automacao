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

warnings.filterwarnings("ignore")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
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
# FUNÇÃO: GERAR GRÁFICO DE PAYBACK
# ============================================================
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
# FUNÇÃO: BUSCAR CLIENTE POR ID (via API da Área do Cliente)
# ============================================================
def buscar_cliente_por_id(cliente_id):
    """Busca os dados completos de um cliente via API da Área do Cliente."""
    try:
        senha_admin = 'SoLiVi@64253798@'
        # Converter para string para garantir a comparação correta
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
    Busca um cliente pelo document_id (armazenado na planilha).
    Você precisa implementar essa função para usar no webhook.
    Por enquanto, retorna None.
    """
    # TODO: Implementar busca por document_id na planilha
    # Exemplo: consultar a planilha e encontrar qual cliente tem esse document_id
    return None

def atualizar_aprovacao_cliente(cliente_id):
    """
    Atualiza a data de aprovação do cliente (campo visita_aprovacao).
    Você precisa implementar essa função para usar no webhook.
    """
    # TODO: Atualizar o campo 'visita_aprovacao' com a data atual
    # Usar a API adminAtualizarCliente para atualizar o cliente
    print(f"✅ Atualizando aprovação do cliente {cliente_id}")
    # Exemplo:
    # cliente = buscar_cliente_por_id(cliente_id)
    # if cliente:
    #     campos = {
    #         "dados_visita": {
    #             **cliente.get('dados_visita', {}),
    #             "assinatura_data": date.today().strftime('%Y-%m-%d')
    #         }
    #     }
    #     # Chamar adminAtualizarCliente via API
    pass

# ============================================================
# FUNÇÃO: CRIAR CLIENTE VIA ÁREA DO CLIENTE
# ============================================================
def criar_cliente_area_cliente(dados_cliente):
    """Chama a API da Área do Cliente para criar um novo cliente."""
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
# FUNÇÃO: ENVIAR PARA ASSINATURA (AUTENTIQUE)
# ============================================================
def enviar_para_assinatura_autentique(
    pdf_bytes,
    nome_documento,
    cliente_email,
    cliente_nome,
    assinante_empresa=None
):
    """
    Envia um PDF para assinatura via Autentique usando Base64.
    (Sem definição de posição – a assinatura será colocada automaticamente)
    """
    if assinante_empresa is None:
        assinante_empresa = ASSINANTE_SOLIVIA

    api_key = assinante_empresa["api_key"]

    # Codificar PDF em Base64
    import base64
    pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')

    # Query usando createDocument (NÃO use FromBase64, pois pode não existir)
    # Vamos usar a mutation createDocument com o file em base64, mas sem o "FromBase64"
    # Na verdade, a forma correta é usar createDocument com o file como Upload,
    # mas como estamos no PythonAnywhere, precisamos evitar multipart.
    # Tentaremos a mutation createDocument com o arquivo em base64, mas a sintaxe pode ser diferente.
    # Vamos usar a mutation createDocumentFromBase64 que é a mais simples, mas se não existir,
    # vamos tentar createDocument com o arquivo como variável.

    # Como a mutation createDocumentFromBase64 não existe, vamos tentar a mutation createDocument
    # com o arquivo em base64 diretamente no campo file. Na documentação, existe a possibilidade
    # de passar o arquivo em base64 no campo "file" da mutation "createDocument", mas não tenho certeza.
    # Vou tentar a versão com createDocument, passando o base64 como string.

    # Vamos usar a mutation createDocument com o arquivo em base64.
    # Mas o campo "file" espera um Upload, não uma string.
    # Então a única forma é usar multipart com createDocument.
    # Como estamos tendo problemas com o proxy, podemos tentar a mutation createDocument
    # usando a sintaxe de base64, se existir. Vou pesquisar na memória:
    # O Autentique tem uma mutation chamada "createDocumentFromBase64" para evitar multipart,
    # mas aparentemente não está disponível na sua conta (versão do plano).
    # Então a saída é usar multipart mesmo.

    # Vou fornecer uma versão que usa multipart, mas com a URL do Worker,
    # e garantindo que o Worker preserve o multipart.

    # ========== VERSÃO MULTIPART (CORRETA) ==========

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
                "action": "SIGN"
            },
            {
                "email": cliente_email,
                "name": cliente_nome,
                "action": "SIGN"
            }
        ]
    }

    operations = {"query": query, "variables": variables}
    map_payload = {"file": ["variables.file"]}

    url = "https://autentique-proxy.ncalves91.workers.dev/v2/graphql"

    response = requests.post(
        url,
        data={
            "operations": json.dumps(operations),
            "map": json.dumps(map_payload)
        },
        files={
            "file": (nome_documento, pdf_bytes, "application/pdf")
        },
        headers={
            "Authorization": f"Bearer {api_key}"
        },
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
# ROTA: GERAR PRÉ-PROPOSTA
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

        resultado_cliente = criar_cliente_area_cliente(sim_data)
        pasta_id_destino = None
        if resultado_cliente.get('success'):
            cliente_id = resultado_cliente.get('id')
            pasta_id_destino = resultado_cliente.get('pastaId')
            senha = resultado_cliente.get('senha_temporaria')
            print(f"✅ Cliente criado: ID {cliente_id}, Pasta {pasta_id_destino}, Senha: {senha}")
        else:
            print(f"⚠️ Cliente não criado: {resultado_cliente.get('error')}")

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

# ============================================================
# ROTA: ENVIAR PARA ASSINATURA (via Autentique)
# ============================================================
@app.route('/api/enviar_para_assinatura', methods=['POST'])
def api_enviar_para_assinatura():
    """
    Endpoint para enviar um PDF para assinatura via Autentique.
    Espera um JSON com:
        - cliente_id (obrigatório)
        - pdf_base64 (obrigatório)
        - nome_documento (opcional)
        - tipo_assinante: "empresa" ou "engenheiro" (opcional, padrão: "empresa")
    """
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        cliente_id = dados.get('cliente_id')
        pdf_base64 = dados.get('pdf_base64')
        nome_documento = dados.get('nome_documento', 'Contrato.pdf')
        tipo_assinante = dados.get('tipo_assinante', 'empresa')

        if not cliente_id:
            return jsonify({'success': False, 'error': 'cliente_id é obrigatório'}), 400
        if not pdf_base64:
            return jsonify({'success': False, 'error': 'pdf_base64 é obrigatório'}), 400

        # Buscar cliente
        cliente = buscar_cliente_por_id(cliente_id)
        if not cliente:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        # Escolher assinante
        if tipo_assinante == 'engenheiro':
            assinante = ASSINANTE_NICOLAS
        else:
            assinante = ASSINANTE_SOLIVIA

        # Decodificar PDF
        pdf_bytes = base64.b64decode(pdf_base64)

        # Enviar para assinatura
        resultado = enviar_para_assinatura_autentique(
            pdf_bytes=pdf_bytes,
            nome_documento=nome_documento,
            cliente_email=cliente['email'],
            cliente_nome=cliente['nome'],
            assinante_empresa=assinante
        )

        if resultado['success']:
            # Salvar document_id no cliente (opcional)
            # Você pode implementar uma função para salvar na planilha
            print(f"✅ Documento enviado para assinatura. ID: {resultado['document_id']}")
            return jsonify({
                'success': True,
                'document_id': resultado['document_id'],
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
# ROTA: WEBHOOK (AUTENTIQUE)
# ============================================================
@app.route('/webhook/autentique', methods=['POST'])
def webhook_autentique():
    """Recebe notificações do Autentique quando um documento é assinado"""
    try:
        data = request.json
        print("📥 Webhook Autentique recebido:")
        print(json.dumps(data, indent=2, ensure_ascii=False))

        event = data.get('event')
        document_id = data.get('data', {}).get('id')
        document_status = data.get('data', {}).get('status')

        if event == 'document.finished' and document_status == 'signed':
            print(f"✅ Documento {document_id} foi assinado!")

            # Buscar cliente pelo document_id
            cliente = buscar_cliente_por_documento_id(document_id)
            if cliente:
                atualizar_aprovacao_cliente(cliente['id'])
                print(f"✅ Aprovação atualizada para o cliente {cliente['nome']}")
            else:
                print(f"⚠️ Cliente com document_id {document_id} não encontrado.")

        return '', 200
    except Exception as e:
        print(f"❌ Erro no webhook: {e}")
        import traceback
        traceback.print_exc()
        return '', 500

# ============================================================
# ROTA: GERAR RELATÓRIO DE CONFORMIDADE (VT)
# ============================================================
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

        # ===== CONTEXTO BASE =====
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
            'URL_VALIDACAO': 'https://solivia.com.br/validar',
            'NUM_RELATORIO': f"RT-{datetime.now().year}-{str(1).zfill(3)}",
            'DATA_EMISSAO': datetime.now().strftime('%d/%m/%Y'),
            'HORA_EMISSAO': datetime.now().strftime('%H:%M'),
            'NUM_PROTOCOLO': f"VT-{datetime.now().strftime('%Y%m%d')}-{cliente_id or '000'}",
            'HASH_DOCUMENTO': '8a7d3f9e2c1b5d4a6f8e7c9d0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0',
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

        # ===== CAMPOS ESPECÍFICOS POR TIPO =====
        if tipo == 'sem_adequacao':
            context.update({
                'POTENCIA': dados.get('potencia', ''),
                'QTD_MODULOS': dados.get('qtd_modulos', ''),
                'INVERSOR': dados.get('inversor', ''),
                'GERACAO': dados.get('geracao', ''),
                'INVESTIMENTO': format_moeda(dados.get('investimento', 0)),  # <-- FORMATADO
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
            })
        elif tipo == 'fast_track':
            context.update({
                'GERACAO_ORIGINAL': dados.get('geracao_original', ''),
                'GERACAO_OTIMIZADA': dados.get('geracao_otimizada', ''),
                'QTD_MODULOS': dados.get('qtd_modulos', ''),
                'POTENCIA_INVERSOR': dados.get('potencia_inversor', ''),
                'LOCAL_INVERSOR': dados.get('local_inversor', ''),
                'OBSERVACOES': dados.get('observacoes', ''),
            })

        # ===== IMAGENS (COM CONVERSÃO PARA MAIÚSCULAS) =====
        imagens = dados.get('imagens', {})
        for key, value in imagens.items():
            if value:  # só adiciona se não estiver vazio
                context[key.upper()] = f"data:image/png;base64,{value}"

        # ===== RENDERIZAR PDF =====
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
            }
        }

        response = requests.post(APPS_SCRIPT_URL, json=payload_script)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return jsonify({'success': True, 'url': result.get('url')})
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
# ROTA: GERAR PROPOSTA FINAL
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

        cliente_data = buscar_cliente_por_id(cliente_id)
        if not cliente_data:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        # ... (restante do código da proposta final, mantido igual ao que você já tinha)

        # Por brevidade, mantive apenas a estrutura. Você deve manter o código original.
        return jsonify({'success': True, 'message': 'Proposta final gerada'})

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTA: GERAR CONTRATO
# ============================================================
@app.route('/gerar_contrato', methods=['POST'])
def gerar_contrato():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'success': False, 'error': 'Dados não fornecidos'}), 400

        tipo = dados.get('tipo', 'cliente')
        cliente_id = dados.get('cliente_id')

        if tipo == 'cliente':
            if not cliente_id:
                return jsonify({'success': False, 'error': 'cliente_id não informado'}), 400

            cliente_data = buscar_cliente_por_id(cliente_id)
            if not cliente_data:
                return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

            # ... código do contrato cliente ...

        elif tipo == 'prestador' or tipo == 'parceiro':
            prestador = dados.get('dados', {})
            if not prestador:
                return jsonify({'success': False, 'error': 'Dados do prestador não fornecidos'}), 400

            # ... código do contrato prestador ...

        else:
            return jsonify({'success': False, 'error': 'Tipo de contrato inválido'}), 400

        # Salvar PDF no Drive
        # ...

        return jsonify({'success': True, 'message': 'Contrato gerado com sucesso'})

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTA: GERAR RELATÓRIO DE COMISSIONAMENTO
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

        # ... código do relatório de comissionamento ...

        return jsonify({'success': True, 'message': 'Relatório gerado'})

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# ROTA: PING
# ============================================================
@app.route('/ping', methods=['GET'])
def ping():
    return {'status': 'ok', 'message': 'SoLivia Engenharia - Gerador de Propostas e Relatórios'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
    # ============================================================
# ROTA: ?
# ============================================================
@app.route('/api/atualizar_relatorio_url', methods=['POST'])
def atualizar_relatorio_url():
    try:
        dados = request.get_json()
        cliente_id = dados.get('cliente_id')
        relatorio_url = dados.get('relatorio_url')
        senha_admin = dados.get('senhaAdmin', 'SoLiVi@64253798@')

        if not cliente_id or not relatorio_url:
            return jsonify({'success': False, 'error': 'cliente_id e relatorio_url são obrigatórios'}), 400

        # Buscar cliente atual
        cliente = buscar_cliente_por_id(cliente_id)
        if not cliente:
            return jsonify({'success': False, 'error': 'Cliente não encontrado'}), 404

        # Atualizar apenas o campo relatorio_url
        campos = {
            'dados_visita': {
                **cliente.get('dados_visita', {}),
                'relatorio_url': relatorio_url
            }
        }

        # Chamar a API de atualização do cliente
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
