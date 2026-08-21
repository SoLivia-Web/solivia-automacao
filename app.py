from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from jinja2 import Template
from weasyprint import HTML
import io
import os
import base64
import requests
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from datetime import date, datetime
import warnings
warnings.filterwarnings("ignore")

app = Flask(__name__)
CORS(app)

# ============================================================
# CORS MANUAL – GARANTE QUE TODAS AS RESPOSTAS TENHAM HEADERS
# ============================================================
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

@app.route('/gerar_relatorio_conformidade', methods=['OPTIONS'])
def handle_options():
    response = jsonify({'status': 'ok'})
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response, 200

# ============================================================
# CONFIGURAÇÃO DO GOOGLE APPS SCRIPT (salvar PDF)
# ============================================================
APPS_SCRIPT_URL = 'https://script.google.com/macros/s/AKfycbzpiRjXd2ENmkrk5d4bCNEq36deqgCLObVC5L_tyUEFzlP1EMnCzR5R3O_3PEFnlAusSQ/exec'
TOKEN = 'x9K2mP5vR8tY3wL7qZ1nB4fJ6cH5sU9e'

# ============================================================
# CONFIGURAÇÃO: ÁREA DO CLIENTE (criação automática)
# ============================================================
URL_AREA_CLIENTE = 'https://script.google.com/macros/s/AKfycbw75sx77HBdie37fqoBg60wWgbb5QxD9uN5-Ee3aemwy8jVP2lqDImO0Brx4iFzsVan/exec'

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

# ============================================================
# TEMPLATE 1: PROPOSTA COMERCIAL
# ============================================================
template_proposta = """
<html>
<head>
    <style>
        :root {
            --azul-premium: #001f3f;
            --azul-glow: #0b2f5c;
            --amarelo-sol: #ffc400;
            --fundo-conteudo: #f8fafc;
            --azul-corporativo: #0b2f5c;
        }
        @page {
            size: A4;
            margin: 0;
        }
        @page interna {
            margin: 0;
            @bottom-center {
                content: element(footer_geral);
            }
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
        }
        .capa-container {
            width: 210mm;
            height: 297mm;
            background-color: var(--azul-premium);
            color: white;
            position: relative;
            page-break-after: always;
        }
        .fundo-gradiente-capa {
            position: absolute;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 85% 15%, rgba(255,196,0,0.1) 0%, transparent 40%),
                        radial-gradient(circle at 15% 85%, rgba(11,47,92,0.5) 0%, transparent 50%);
        }
        .logo-central-wrapper {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .logo-img-central {
            max-height: 420px;
            max-width: 85%;
            object-fit: contain;
        }
        .titulo-container-capa {
            position: absolute;
            top: 50%;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            transform: translateY(-50%);
        }
        .linha-lateral-capa {
            flex-grow: 1;
            height: 1px;
            background: rgba(255,255,255,0.3);
            margin: 0;
        }
        .titulo-texto-capa {
            font-size: 36px;
            font-weight: bold;
            letter-spacing: 12px;
            margin: 0 15px;
            text-transform: uppercase;
            white-space: nowrap;
            color: var(--amarelo-sol);
        }
        .slogan-superior {
            position: absolute;
            bottom: 145px;
            right: 60px;
            font-size: 16px;
            letter-spacing: 5px;
            opacity: 0.9;
            color: var(--amarelo-sol);
            font-weight: 500;
        }
        .rodape-bloco-capa {
            position: absolute;
            bottom: 0;
            width: 100%;
            height: 135px;
            background: rgba(0,0,0,0.25);
            border-top: 5px solid var(--amarelo-sol);
        }
        .rodape-conteudo-capa {
            position: relative;
            width: 90%;
            margin: 0 auto;
            height: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .linha-divisoria-capa {
            width: 4px;
            height: 60px;
            background: rgba(255,255,255,0.5);
            border-radius: 2px;
        }
        .texto-identidade-capa {
            text-align: center;
            color: white;
        }
        .texto-identidade-capa b {
            font-size: 18px;
            display: block;
            margin-bottom: 5px;
        }
        .texto-identidade-capa span {
            font-size: 13px;
            opacity: 0.8;
            letter-spacing: 1.5px;
            white-space: nowrap;
        }
        .info-proposta-capa {
            text-align: right;
            font-size: 14px;
            color: white;
            line-height: 1.8;
        }
        .info-proposta-capa b {
            font-weight: 600;
        }

        .page-interna {
            page: interna;
            page-break-after: always;
            width: 210mm;
            min-height: 297mm;
            background-color: var(--fundo-conteudo);
            padding: 1.5cm;
            box-sizing: border-box;
            position: relative;
            color: #333;
        }
        #footer_geral {
            position: running(footer_geral);
            text-align: center;
            font-size: 8px;
            color: #64748b;
            padding: 5px 0;
            width: 95%;
            border-top: 2px solid var(--azul-corporativo);
            margin: 0 auto;
        }
        .header-interna {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 3px solid var(--amarelo-sol);
            padding-bottom: 8px;
            margin-bottom: 20px;
        }
        .texto-solivia-topo {
            color: var(--azul-corporativo);
            font-weight: 800;
            font-size: 16px;
        }
        .banner-azul {
            background: var(--azul-corporativo);
            color: white;
            padding: 25px;
            text-align: center;
            border-radius: 10px;
            border-bottom: 8px solid var(--amarelo-sol);
        }
        .foto-cliente {
            width: 100%;
            height: 320px;
            object-fit: cover;
            border-radius: 12px;
            margin: 15px 0;
            border: 4px solid white;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .card {
            background: white;
            padding: 25px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            margin-bottom: 15px;
        }
        .card-diagnostico {
            background: white;
            padding: 30px 25px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            line-height: 1.8;
            white-space: pre-wrap;
            min-height: auto;
            overflow: visible;
        }
        .card-diagnostico .destaque-solivia {
            font-weight: bold;
            color: var(--azul-corporativo);
            font-size: 1.1em;
            display: block;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 2px solid var(--amarelo-sol);
            text-align: center;
        }
        .titulo-faixa {
            background: var(--azul-corporativo);
            color: white;
            padding: 12px 20px;
            font-weight: bold;
            border-left: 8px solid var(--amarelo-sol);
            border-radius: 4px;
            margin: 20px 0;
        }
        .valor-container {
            background: var(--azul-corporativo);
            color: white;
            padding: 40px;
            border-radius: 12px;
            text-align: center;
            border-right: 20px solid var(--amarelo-sol);
        }
        .valor-texto {
            font-size: 48px;
            font-weight: 800;
            color: var(--amarelo-sol);
        }
        .tabela-projecao {
            width: 100%;
            border-collapse: collapse;
            font-size: 10px;
        }
        .tabela-projecao thead th {
            background: var(--azul-corporativo);
            color: white;
            padding: 6px 3px;
            font-weight: 600;
            border-bottom: 2px solid var(--amarelo-sol);
            border: none;
            font-size: 10px;
        }
        .tabela-projecao tbody td {
            padding: 5px 3px;
            border: none;
            border-bottom: 1px solid #e9edf2;
            text-align: center;
            font-size: 10px;
        }
        .tabela-projecao tbody tr:last-child td {
            border-bottom: none;
        }
        .celula-resultado {
            border-radius: 3px;
            padding: 2px 4px;
            font-weight: 700;
        }
        .pagina-especificacao table {
            width: 100%;
            border-collapse: collapse;
            font-size: 10px;
            border: 1px solid #cbd5e1;
        }
        .pagina-especificacao th {
            background: var(--azul-corporativo);
            color: white;
            padding: 8px 6px;
            font-weight: 600;
            border: 1px solid #cbd5e1;
            text-align: center;
        }
        .pagina-especificacao td {
            padding: 6px 4px;
            border: 1px solid #cbd5e1;
            text-align: center;
            font-size: 10px;
        }
        .container-grafico {
            max-height: 550px;
            overflow: hidden;
            text-align: center;
            margin-top: 10px;
        }
        .imagem-grafico {
            max-width: 100%;
            max-height: 500px;
            border-radius: 12px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            object-fit: contain;
        }
        .frase-compromisso {
            text-align: center;
            font-size: 12px;
            color: #666;
            margin-top: 20px;
            font-style: italic;
        }
        .assinatura-container {
            display: flex;
            justify-content: space-between;
            margin-top: 80px;
        }
        .assinatura {
            width: 40%;
            text-align: center;
        }
        .linha-assinatura {
            width: 100%;
            border-top: 1.5px solid #333;
            margin-bottom: 5px;
        }
        .nome-assinatura {
            font-size: 13px;
            font-weight: bold;
            margin-top: 5px;
        }
        .cargo-assinatura {
            font-size: 11px;
            color: #555;
        }
        .icone-condicao {
            display: inline-block;
            width: 20px;
            text-align: center;
            margin-right: 8px;
        }
        .lista-inclusos {
            list-style: none;
            padding: 0;
            font-size: 12px;
            line-height: 1.8;
        }
        .lista-inclusos li::before {
            content: "✔ ";
            color: #10b981;
            font-weight: bold;
        }
        .lista-exclusos {
            list-style: none;
            padding: 0;
            font-size: 12px;
            line-height: 1.8;
        }
        .lista-exclusos li::before {
            content: "✘ ";
            color: #e11d48;
            font-weight: bold;
        }
        .beneficio-item {
            font-size: 1.0em;
            line-height: 2.2;
        }
        .solucao-texto {
            font-size: 1.0em;
            line-height: 1.8;
            margin-bottom: 15px;
        }
        .destaque-pre-proposta {
            font-weight: 600;
            color: var(--azul-corporativo);
            background: #eef2f7;
            padding: 2px 6px;
            border-radius: 4px;
        }
        .passo-container {
            width: 100%;
            text-align: center;
            background: white;
            padding: 28px 15px;
            border-radius: 12px;
            border: 1px solid #e2e8f0;
            margin-bottom: 10px;
            box-sizing: border-box;
        }
        .passo-container .icone-passo {
            font-size: 28px;
            margin-bottom: 5px;
            display: block;
        }
        .passo-container .titulo-passo {
            font-weight: bold;
            font-size: 14px;
            color: var(--azul-corporativo);
            margin-bottom: 3px;
        }
        .passo-container .desc-passo {
            font-size: 12px;
            color: #555;
            margin: 0;
        }
        .galeria-equipamentos {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            justify-content: center;
            margin-top: 15px;
        }
        .item-equipamento {
            flex: 1 1 110px;
            max-width: 120px;
            text-align: center;
            background: #f8fafc;
            border-radius: 10px;
            padding: 8px 5px;
            border: 1px solid #e2e8f0;
        }
        .item-equipamento .img-placeholder {
            width: 100%;
            height: 190px;
            background: #e2e8f0;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            color: #64748b;
            margin-bottom: 4px;
        }
        .item-equipamento .legenda {
            font-size: 10px;
            color: #555;
            font-weight: 500;
        }
    </style>
</head>
<body>
    <div id="footer_geral">SoLivia ENGENHARIA | CNPJ: 49.972.976/0001-15 | {{ CONTATOS }}</div>

    <!-- CAPA -->
    <div class="capa-container">
        <div class="fundo-gradiente-capa"></div>
        <div class="logo-central-wrapper">
            {% if LOGO_CENTRAL %}<img src="{{ LOGO_CENTRAL }}" class="logo-img-central">{% endif %}
        </div>
        <div class="titulo-container-capa">
            <div class="linha-lateral-capa"></div>
            <div class="titulo-texto-capa">PROPOSTA COMERCIAL</div>
            <div class="linha-lateral-capa"></div>
        </div>
        <div class="slogan-superior">SoLivia ENGENHARIA LTDA</div>
        <div class="rodape-bloco-capa">
            <div class="rodape-conteudo-capa">
                <div style="display: flex; align-items: center; gap: 25px;">
                    {% if LOGO_RODAPE %}<img src="{{ LOGO_RODAPE }}" style="max-height: 100px;">{% endif %}
                    <div class="linha-divisoria-capa"></div>
                    <div class="texto-identidade-capa">
                        <b>SoLivia ENGENHARIA</b>
                        <span>{{ TIPO_PROJETO }}</span>
                    </div>
                </div>
                <div class="info-proposta-capa">
                    <b>Nº DA PROPOSTA:</b> {{ NUM_PROPOSTA }}<br>
                    <b>REVISÃO:</b> {{ REVISAO }}<br>
                    <b>DATA:</b> {{ DATA_EMISSAO }}
                </div>
            </div>
        </div>
    </div>

    <!-- PÁGINA 2: IDENTIFICAÇÃO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">SoLivia ENGENHARIA</div>
            <div>Pág. 02</div>
        </div>
        <div class="banner-azul">
            <h1 style="margin:0; font-size: 28px;">{{ TIPO_PROJETO }}</h1>
        </div>
        {% if FOTO_CAPA_MIOLO %}
        <img src="{{ FOTO_CAPA_MIOLO }}" class="foto-cliente">
        {% endif %}
        <div class="titulo-faixa">Identificação do Cliente</div>
        <div class="card">
            <p>
                <b>CLIENTE:</b> {{ NOME_CLIENTE }}<br>
                <b>CPF/CNPJ:</b> {{ CPF_CNPJ }}<br>
                <b>TELEFONE:</b> {{ TELEFONE_CLIENTE }}<br>
                <b>LOCAL:</b> {{ ENDERECO }}{% if NUMERO_ENDERECO %}, {{ NUMERO_ENDERECO }}{% endif %}
            </p>
        </div>
        <p style="text-align: center; font-style: italic; margin-top: 30px; font-size: 16px; color: #0b2f5c;">
            "{{ FRASE_IMPACTO }}"
        </p>
    </div>

    <!-- PÁGINA 3: DIAGNÓSTICO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">SoLivia ENGENHARIA</div>
            <div>Pág. 03</div>
        </div>
        <div class="titulo-faixa">Diagnóstico Técnico</div>
        <div class="card-diagnostico">
            {{ DIAGNOSTICO }}
            <span class="destaque-solivia">{{ DESTAQUE_FINAL }} </span>
        </div>
    </div>

    <!-- PÁGINA 4: SOLUÇÃO E BENEFÍCIOS -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">SoLivia ENGENHARIA</div>
            <div>Pág. 04</div>
        </div>
        <div class="titulo-faixa">Solução Proposta e Benefícios</div>
        <div class="card">
            <div class="solucao-texto">
                {{ SOLUCAO_TEXTO }}
            </div>
            <ul style="list-style: none; padding: 0; font-size: 1.0em; line-height: 2.2;">
                {% for beneficio in BENEFICIOS %}
                <li class="beneficio-item">★ {{ beneficio }}</li>
                {% endfor %}
            </ul>
        </div>
        {% if FOTO_PROVA %}
        <div class="container-grafico">
            <img src="{{ FOTO_PROVA }}" class="imagem-grafico">
        </div>
        {% endif %}
    </div>

    <!-- PÁGINA 5: COMO FUNCIONA O SISTEMA -->
    <div class="page-interna" style="padding:1.2cm 1.5cm; display:flex; flex-direction:column; height:100%; box-sizing:border-box;">
        <div class="header-interna" style="flex-shrink:0;">
            <div class="texto-solivia-topo">SoLivia ENGENHARIA</div>
            <div>Pág. 05</div>
        </div>
        <div class="titulo-faixa" style="flex-shrink:0; margin: 8px 0 12px 0;">Como Funciona o Sistema Solar?</div>

        <div style="flex:1; display:flex; flex-direction:column; gap:10px; min-height:0;">

            <!-- Card 1: Geração -->
            <div class="passo-container" style="flex:1; padding:10px 15px; border-radius:12px; border:1px solid #e2e8f0; background:white; display:flex; align-items:center; gap:15px; min-height:0;">
                <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/1.%20Gera%C3%A7%C3%A3o.png" style="width:50%; height:160px; object-fit:cover; object-position:top center; border-radius:8px; flex-shrink:0;">
                <div style="flex:1; text-align:left;">
                    <p class="titulo-passo" style="margin:0 0 2px 0; font-weight:bold; font-size:14px; color:var(--azul-corporativo);">1. Geração</p>
                    <p class="desc-passo" style="margin:0; font-size:12px; color:#555;">Os módulos captam a luz solar e geram energia em corrente contínua (CC).</p>
                </div>
            </div>

            <!-- Card 2: Conversão -->
            <div class="passo-container" style="flex:1; padding:10px 15px; border-radius:12px; border:1px solid #e2e8f0; background:white; display:flex; align-items:center; gap:15px; min-height:0;">
                <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/2.%20Convers%C3%A3o.png" style="width:50%; height:160px; object-fit:cover; object-position:center center; border-radius:8px; flex-shrink:0;">
                <div style="flex:1; text-align:left;">
                    <p class="titulo-passo" style="margin:0 0 2px 0; font-weight:bold; font-size:14px; color:var(--azul-corporativo);">2. Conversão</p>
                    <p class="desc-passo" style="margin:0; font-size:12px; color:#555;">O inversor transforma a corrente contínua (CC) em corrente alternada (CA).</p>
                </div>
            </div>

            <!-- Card 3: Distribuição -->
            <div class="passo-container" style="flex:1; padding:10px 15px; border-radius:12px; border:1px solid #e2e8f0; background:white; display:flex; align-items:center; gap:15px; min-height:0;">
                <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/3.%20Distribui%C3%A7%C3%A3o.png" style="width:50%; height:160px; object-fit:cover; object-position:center center; border-radius:8px; flex-shrink:0;">
                <div style="flex:1; text-align:left;">
                    <p class="titulo-passo" style="margin:0 0 2px 0; font-weight:bold; font-size:14px; color:var(--azul-corporativo);">3. Distribuição</p>
                    <p class="desc-passo" style="margin:0; font-size:12px; color:#555;">A energia gerada abastece os eletrodomésticos e a iluminação do imóvel.</p>
                </div>
            </div>

            <!-- Card 4: Excedente -->
            <div class="passo-container" style="flex:1; padding:10px 15px; border-radius:12px; border:1px solid #e2e8f0; background:white; display:flex; align-items:center; gap:15px; min-height:0;">
                <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/4.%20Excedente.png" style="width:50%; height:160px; object-fit:cover; object-position:center center; border-radius:8px; flex-shrink:0;">
                <div style="flex:1; text-align:left;">
                    <p class="titulo-passo" style="margin:0 0 2px 0; font-weight:bold; font-size:14px; color:var(--azul-corporativo);">4. Excedente</p>
                    <p class="desc-passo" style="margin:0; font-size:12px; color:#555;">O excedente vai para a rede elétrica, gerando créditos de energia para você.</p>
                </div>
            </div>

        </div>
    </div>

    <!-- PÁGINA 6: PROJEÇÃO 20 MARCOS + GRÁFICO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">SoLivia ENGENHARIA</div>
            <div>Pág. 06</div>
        </div>
        <div class="titulo-faixa">Projeção Financeira – Marcos (20 anos)</div>
        <table class="tabela-projecao">
            <thead>
                <tr>
                    <th>ANO</th>
                    <th>Custo s/ solar (Mês)</th>
                    <th>Eficiência</th>
                    <th>Tarifa</th>
                    <th>Custo c/ solar</th>
                    <th>Economia anual</th>
                    <th>Resultado Solar</th>
                    <th>Resultado Poupança</th>
                    <th>Resultado CDB (líq.)</th>
                </tr>
            </thead>
            <tbody>
                {% for item in PROJECAO_20 %}
                <tr>
                    <td>{{ item.ano }}</td>
                    <td>R$ {{ item.custoSemSolarMes }}</td>
                    <td>{{ item.eficiencia }}%</td>
                    <td>R$ {{ item.tarifa }}</td>
                    <td>R$ {{ item.custoComSolarMes }}</td>
                    <td>R$ {{ item.economiaAnual }}</td>
                    <td class="col-resultado">
                        <span class="celula-resultado" style="background-color:{{ item.cor_fundo }}; color:{{ item.cor_texto }}; padding: 2px 6px; border-radius: 3px;">
                            R$ {{ item.resultadoAcumulado }}
                        </span>
                    </td>
                    <td>R$ {{ item.saldoPoupanca }}</td>
                    <td>R$ {{ item.saldoCDB }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% if GRAFICO_BASE64 %}
        <div class="container-grafico">
            <img src="data:image/png;base64,{{ GRAFICO_BASE64 }}" class="imagem-grafico">
        </div>
        {% endif %}
    </div>

    <!-- PÁGINA 7: ESPECIFICAÇÕES + GALERIA DE EQUIPAMENTOS -->
    <div class="page-interna pagina-especificacao">
        <div class="header-interna">
            <div class="texto-solivia-topo">SoLivia ENGENHARIA</div>
            <div>Pág. 07</div>
        </div>
        <div class="titulo-faixa">Especificações do Sistema</div>
        <table>
            <thead>
                <tr>
                    <th>Descrição</th>
                    <th>Marca</th>
                    <th>Quantidade</th>
                    <th>Preço Unitário</th>
                </tr>
            </thead>
            <tbody>
                {% for item in ITENS_ESCOPO %}
                <tr>
                    <td>{{ item.desc }}</td>
                    <td>{{ item.marca }}</td>
                    <td>{{ item.qtd }}</td>
                    <td>R$ {{ item.preco }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        <div style="display: flex; gap: 20px; margin-top: 30px;">
            <div style="flex: 1;">
                <p style="font-weight: bold; color: #10b981; font-size: 12px;">✔ INCLUSO:</p>
                <ul class="lista-inclusos">
                    {% for i in INCLUSOS %}
                    <li>{{ i }}</li>
                    {% endfor %}
                </ul>
            </div>
            <div style="flex: 1;">
                <p style="font-weight: bold; color: #e11d48; font-size: 12px;">✘ NÃO INCLUSO:</p>
                <ul class="lista-exclusos">
                    {% for i in EXCLUSOS %}
                    <li>{{ i }}</li>
                    {% endfor %}
                </ul>
            </div>
        </div>
        <!-- GALERIA DE EQUIPAMENTOS -->
        <div style="margin-top: 25px;">
            <p style="font-weight: bold; color: var(--azul-corporativo); font-size: 12px; margin-bottom: 8px;">🔧 Componentes do Sistema</p>
            <div class="galeria-equipamentos">
                <div class="item-equipamento">
                    <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/M%C3%B3dulo%20Solar.png" style="width:100%; height:120px; object-fit:cover; border-radius:8px;">
                    <span class="legenda">Módulo Solar</span>
                </div>
                <div class="item-equipamento">
                    <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/Inversor.jpg" style="width:100%; height:120px; object-fit:cover; border-radius:8px;">
                    <span class="legenda">Inversor</span>
                </div>
                <div class="item-equipamento">
                    <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/Microinversor.png" style="width:100%; height:120px; object-fit:cover; border-radius:8px;">
                    <span class="legenda">Microinversor</span>
                </div>
                <div class="item-equipamento">
                    <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/String%20Box.jpg" style="width:100%; height:120px; object-fit:cover; border-radius:8px;">
                    <span class="legenda">String Box</span>
                </div>
                <div class="item-equipamento">
                    <img src="https://raw.githubusercontent.com/SoLivia-Web/termos-solivia/main/assets/img/Estrutura.jpg" style="width:100%; height:120px; object-fit:cover; border-radius:8px;">
                    <span class="legenda">Estrutura</span>
                </div>
            </div>
        </div>
        <p style="font-size: 9px; color: #64748b; text-align: center; margin-top: 8px; font-style: italic;">
            * Imagens ilustrativas dos principais equipamentos do sistema.
        </p>
    </div>

    <!-- PÁGINA 8: INVESTIMENTO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">SoLivia ENGENHARIA</div>
            <div>Pág. 08</div>
        </div>
        <div class="titulo-faixa">Investimento Final</div>
        <div class="valor-container" style="margin-top: 20px;">
            <span style="font-size: 14px; opacity: 0.8; letter-spacing: 2px; margin-bottom: 25px; display: block;">
                INVESTIMENTO TOTAL
            </span>
            <div class="valor-texto">{{ VALOR_TOTAL }}</div>
        </div>
        <div class="card" style="margin-top: 30px; padding: 25px;">
            <p>
                <span class="icone-condicao">💰</span>
                <b>FORMA DE INVESTIMENTO:</b> {{ CONDICAO_1 }} / {{ CONDICAO_2 }} / {{ CONDICAO_3 }}
            </p>
            <p>
                <span class="icone-condicao">⏱️</span>
                <b>PRAZO DE EXECUÇÃO:</b> {{ PRAZO_EXECUCAO }}
            </p>
            <p>
                <span class="icone-condicao">📅</span>
                <b>VALIDADE DA PROPOSTA:</b> {{ VALIDADE_PROPOSTA }}
            </p>
        </div>

        <!-- BLOCO DA VISITA TÉCNICA -->
        <div class="card" style="margin-top: 20px; padding: 20px; background: #f8fafc; border-left: 6px solid var(--amarelo-sol);">
            <p>
                <span class="icone-condicao">📍</span>
                <b>VISITA TÉCNICA:</b> Distância: {{ DISTANCIA_VISITA }} | Custo: {{ CUSTO_VISITA }}
            </p>
            <p style="font-size: 11px; color: #555; margin-top: 8px; font-style: italic;">
                * Este é um valor estimado da visita técnica, baseado na distância entre o CEP da empresa e o CEP do cliente.
                Caso o projeto seja fechado conosco, o valor da visita será integralmente abatido do investimento total.
            </p>
        </div>

        <div style="margin-top: 40px; text-align: center;">
            {% if SELO_QUALIDADE %}<img src="{{ SELO_QUALIDADE }}" style="width: 140px;">{% endif %}
            <p class="frase-compromisso">Compromisso com Excelência e Sustentabilidade</p>
        </div>
        <div class="assinatura-container">
            <div class="assinatura">
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">{{ NOME_CLIENTE }}</div>
                <div class="cargo-assinatura"><b>CLIENTE</b></div>
            </div>
            <div class="assinatura">
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">SoLivia ENGENHARIA</div>
                <div class="cargo-assinatura"><b>GESTOR DE SOLUÇÕES</b></div>
            </div>
        </div>
    </div>
</body>
</html>
"""

# ============================================================
# TEMPLATE 2: RELATÓRIO SEM ADEQUAÇÃO (VT)
# ============================================================
template_sem_adequacao = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>RELATÓRIO DE CONFORMIDADE TÉCNICA - SoLivia ENGENHARIA</title>
    <style>
        :root {
            --azul-premium: #001f3f;
            --azul-glow: #0b2f5c;
            --amarelo-sol: #ffc400;
            --fundo-conteudo: #f8fafc;
            --azul-corporativo: #0b2f5c;
        }
        @page {
            size: A4;
            margin: 0;
        }
        @page interna {
            margin: 0;
            @bottom-center {
                content: element(footer_geral);
            }
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
        }
        .capa-container {
            width: 210mm;
            height: 297mm;
            background-color: var(--azul-premium);
            color: white;
            position: relative;
            page-break-after: always;
        }
        .fundo-gradiente-capa {
            position: absolute;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 85% 15%, rgba(255,196,0,0.1) 0%, transparent 40%),
                        radial-gradient(circle at 15% 85%, rgba(11,47,92,0.5) 0%, transparent 50%);
        }
        .logo-central-wrapper {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .logo-img-central {
            max-height: 420px;
            max-width: 85%;
            object-fit: contain;
        }
        .titulo-container-capa {
            position: absolute;
            top: 50%;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            transform: translateY(-50%);
        }
        .linha-lateral-capa {
            flex-grow: 1;
            height: 1px;
            background: rgba(255,255,255,0.3);
            margin: 0;
        }
        .titulo-texto-capa {
            font-size: 36px;
            font-weight: bold;
            letter-spacing: 12px;
            margin: 0 15px;
            text-transform: uppercase;
            white-space: nowrap;
            color: var(--amarelo-sol);
        }
        .rodape-bloco-capa {
            position: absolute;
            bottom: 0;
            width: 100%;
            height: 135px;
            background: rgba(0,0,0,0.25);
            border-top: 5px solid var(--amarelo-sol);
        }
        .rodape-conteudo-capa {
            position: relative;
            width: 90%;
            margin: 0 auto;
            height: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .linha-divisoria-capa {
            width: 4px;
            height: 60px;
            background: rgba(255,255,255,0.5);
            border-radius: 2px;
        }
        .texto-identidade-capa {
            text-align: center;
            color: white;
        }
        .texto-identidade-capa b {
            font-size: 18px;
            display: block;
            margin-bottom: 5px;
        }
        .texto-identidade-capa span {
            font-size: 13px;
            opacity: 0.8;
            letter-spacing: 1.5px;
            white-space: nowrap;
        }
        .info-proposta-capa {
            text-align: right;
            font-size: 14px;
            color: white;
            line-height: 1.8;
        }
        .info-proposta-capa b {
            font-weight: 600;
        }

        /* PÁGINAS INTERNAS */
        .page-interna {
            page: interna;
            page-break-after: always;
            width: 210mm;
            min-height: 297mm;
            background-color: var(--fundo-conteudo);
            padding: 1.5cm;
            box-sizing: border-box;
            position: relative;
            color: #333;
            font-size: 12px;
            line-height: 1.6;
        }
        #footer_geral {
            position: running(footer_geral);
            text-align: center;
            font-size: 8px;
            color: #64748b;
            padding: 5px 0;
            width: 95%;
            border-top: 2px solid var(--azul-corporativo);
            margin: 0 auto;
        }
        .header-interna {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 3px solid var(--amarelo-sol);
            padding-bottom: 8px;
            margin-bottom: 20px;
        }
        .texto-solivia-topo {
            color: var(--azul-corporativo);
            font-weight: 800;
            font-size: 16px;
        }
        .titulo-faixa {
            background: var(--azul-corporativo);
            color: white;
            padding: 10px 18px;
            font-weight: bold;
            border-left: 8px solid var(--amarelo-sol);
            border-radius: 4px;
            margin: 16px 0;
            font-size: 14px;
        }
        .clausula-titulo {
            font-weight: bold;
            margin-top: 15px;
            color: var(--azul-corporativo);
            font-size: 14px;
        }
        .clausula-conteudo {
            text-align: justify;
            line-height: 1.6;
            margin-bottom: 10px;
            font-size: 12px;
        }
        .negrito {
            font-weight: bold;
        }
        .item-lista {
            margin-left: 20px;
            margin-bottom: 6px;
            font-size: 12px;
        }
        .assinatura-container {
            display: flex;
            justify-content: space-between;
            margin-top: 110px;
            page-break-inside: avoid;
        }
        .assinatura {
            width: 40%;
            text-align: center;
        }
        .linha-assinatura {
            width: 100%;
            border-top: 1.5px solid #333;
            margin-bottom: 5px;
        }
        .nome-assinatura {
            font-size: 13px;
            font-weight: bold;
            margin-top: 5px;
        }
        .cargo-assinatura {
            font-size: 11px;
            color: #555;
        }
        .destaque-azul {
            background-color: rgba(11, 47, 92, 0.1);
            padding: 15px;
            border-left: 4px solid var(--azul-corporativo);
            margin: 15px 0;
            border-radius: 4px;
        }
        .destaque-verde {
            background-color: rgba(76, 175, 80, 0.1);
            padding: 20px;
            border-left: 6px solid #4CAF50;
            margin: 20px 0;
            border-radius: 6px;
            text-align: center;
        }
        .container-geracao {
            display: flex;
            justify-content: space-around;
            align-items: stretch;
            margin: 15px 0 10px 0;
            gap: 12px;
        }
        .box-geracao {
            background: white;
            border: 2px solid var(--azul-corporativo);
            padding: 10px 8px;
            border-radius: 8px;
            text-align: center;
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            min-height: 80px;
        }
        .valor-geracao {
            font-size: 24px;
            font-weight: bold;
            color: var(--azul-corporativo);
            margin: 2px 0;
        }
        .label-geracao {
            font-size: 11px;
            color: #666;
            font-weight: 600;
            letter-spacing: 0.5px;
        }
        .sub-label {
            font-size: 10px;
            color: #555;
            margin-top: 2px;
        }
        .emoji-grande {
            font-size: 56px;
            margin-bottom: 10px;
        }
        .moldura-imagem {
            border: 4px solid var(--azul-corporativo);
            border-radius: 12px;
            padding: 8px;
            background: white;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            margin: 15px 0;
            text-align: center;
        }
        .moldura-imagem img {
            max-width: 100%;
            max-height: 300px;
            border-radius: 8px;
            display: block;
            margin: 0 auto;
        }
        .clausula-conteudo, .item-lista, .destaque-azul p, .destaque-verde p {
            font-size: 12px;
        }
        .destaque-azul .negrito, .destaque-verde .negrito {
            font-size: 13px;
        }
        .selo-contato {
            margin-top: 25px;
            text-align: center;
        }
    </style>
</head>
<body>
    <div id="footer_geral">{{ RAZAO_SOCIAL }} | CNPJ: {{ CNPJ }} | Telefone: {{ TELEFONE }} | WhatsApp: (11) 91686-6075 | {{ EMAIL }}</div>

    <!-- CAPA -->
    <div class="capa-container">
        <div class="fundo-gradiente-capa"></div>
        <div class="logo-central-wrapper">
            <img src="{{ LOGO_CENTRAL }}" class="logo-img-central">
        </div>
        <div class="titulo-container-capa">
            <div class="linha-lateral-capa"></div>
            <div class="titulo-texto-capa">RELATÓRIO TÉCNICO</div>
            <div class="linha-lateral-capa"></div>
        </div>
        <div class="rodape-bloco-capa">
            <div class="rodape-conteudo-capa">
                <div style="display: flex; align-items: center; gap: 25px;">
                    <img src="{{ LOGO_RODAPE }}" style="max-height: 100px;">
                    <div class="linha-divisoria-capa"></div>
                    <div class="texto-identidade-capa">
                        <b>{{ NOME_FANTASIA }}</b>
                        <span>ENGENHARIA E INSTALAÇÕES SOLARES</span>
                    </div>
                </div>
                <div class="info-proposta-capa">
                    <b>Nº DO RELATÓRIO:</b> {{ NUM_RELATORIO }}<br>
                    <b>DATA:</b> {{ DATA_EMISSAO }}<br>
                    <b>CLIENTE:</b> {{ NOME_CLIENTE }}
                </div>
            </div>
        </div>
    </div>

    <!-- PÁGINA 1 -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 01</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            <span class="negrito">Cliente:</span> {{ NOME_CLIENTE }}<br>
            <span class="negrito">Endereço:</span> {{ ENDERECO }}
        </div>

        <div class="destaque-verde">
            <div class="emoji-grande">🎉</div>
            <p class="negrito" style="font-size: 18px; color: #2E7D32;">
                ANÁLISE CONCLUÍDA: NENHUM AJUSTE NECESSÁRIO!
            </p>
            <p style="font-size: 13px; margin-top: 10px;">
                Sua instalação está pronta para prosseguir conforme planejado!
            </p>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            Este relatório técnico apresenta o layout definido para sua instalação fotovoltaica. Concluímos a análise da visita técnica com ótimas notícias: <span class="negrito">seu projeto não requer adequações adicionais</span> e está pronto para homologação junto à concessionária.
        </div>

        <div class="destaque-azul">
            <p class="negrito">SOBRE SUA CONCESSIONÁRIA</p>
            <p style="font-size: 11px; margin: 5px 0;">
                A {{ CONCESSIONARIA }} possui normativas específicas para instalações fotovoltaicas. Nossa equipe técnica analisou seu imóvel e confirmou que o projeto atende integralmente às exigências técnicas.
            </p>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Objetivo deste relatório:</span>
            <div class="item-lista">• Apresentar o layout técnico otimizado para seu imóvel</div>
            <div class="item-lista">• Garantir conformidade com as normativas da {{ CONCESSIONARIA }}</div>
            <div class="item-lista">• Estabelecer os próximos passos para instalação</div>
            <div class="item-lista">• Orientar sobre procedimentos importantes</div>
        </div>

        <div style="margin-top: 60px; text-align: center;">
            <p style="font-style: italic; color: var(--azul-corporativo);">
                "Soluções energéticas com excelência técnica e segurança"
            </p>
            <div style="margin-top: 40px;">
                <div class="linha-assinatura" style="width: 60%; margin: 0 auto;"></div>
                <div class="nome-assinatura">{{ NOME_CLIENTE }}</div>
                <div class="cargo-assinatura">CLIENTE / PROPRIETÁRIO</div>
            </div>
        </div>
    </div>

    <!-- PÁGINA 2 -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 02</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-titulo">LAYOUT DEFINIDO PARA INSTALAÇÃO</div>

        <div class="clausula-conteudo">
            Após análise detalhada das imagens e dados coletados na visita técnica, confirmamos que o projeto está <span class="negrito">totalmente adequado</span> para instalação imediata. Estamos entusiasmados com esta parceria e confiantes de que alcançaremos resultados excepcionais juntos!
        </div>

        <div class="container-geracao">
            <div class="box-geracao">
                <div class="label-geracao">SISTEMA DEFINIDO</div>
                <div class="valor-geracao">{{ QTD_MODULOS }} MÓDULOS</div>
                <div class="sub-label">+ {{ INVERSOR }}</div>
            </div>
            <div class="box-geracao">
                <div class="label-geracao">GERAÇÃO ESTIMADA</div>
                <div class="valor-geracao">{{ GERACAO }} kWh/mês</div>
                <div class="sub-label">MÉDIA MENSAL</div>
            </div>
            <div class="box-geracao">
                <div class="label-geracao">INVESTIMENTO TOTAL</div>
                <div class="valor-geracao">R$ {{ INVESTIMENTO }}</div>
                <div class="sub-label">PROJETO CHAVE NA MÃO</div>
            </div>
        </div>

        <div class="moldura-imagem">
            {% if CROQUI_LAYOUT %}
            <img src="data:image/png;base64,{{ CROQUI_LAYOUT }}" alt="Layout do sistema fotovoltaico">
            {% else %}
            <img src="https://i.imgur.com/014AgLG.png" alt="Layout do sistema fotovoltaico">
            {% endif %}
        </div>

        <div class="clausula-conteudo" style="margin-top: 10px;">
            <span class="negrito">Especificações do sistema:</span>
            <div class="item-lista">• {{ QTD_MODULOS }} módulos fotovoltaicos de alta eficiência</div>
            <div class="item-lista">• {{ INVERSOR }} com tecnologia MPPT</div>
            <div class="item-lista">• Sistema de monitoramento remoto incluído</div>
            <div class="item-lista">• Estrutura de fixação compatível com seu telhado</div>
            <div class="item-lista">• Cabos e conectores específicos para energia solar</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 10px;">
            <span class="negrito">Vantagens do layout definido:</span>
            <div class="item-lista">• Máxima eficiência energética para seu consumo</div>
            <div class="item-lista">• Instalação rápida e sem adequações adicionais</div>
            <div class="item-lista">• Homologação simplificada junto à concessionária</div>
            <div class="item-lista">• Retorno do investimento otimizado</div>
        </div>

        <div style="margin-top: 15px; text-align: center;">
            <p style="font-style: italic; color: var(--azul-corporativo); font-size: 12px;">
                "Energia solar com tecnologia de ponta e tranquilidade"
            </p>
        </div>
    </div>

    <!-- PÁGINA 3 -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 03</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-titulo">LOCAL DE INSTALAÇÃO DOS INVERSORES</div>

        <div class="clausula-conteudo">
            <span class="negrito">Local definido para instalação dos inversores:</span>
            <div class="item-lista" style="margin-top: 10px;">• Instalados diretamente <span class="negrito">embaixo dos módulos fotovoltaicos</span></div>
            <div class="item-lista">• Protegidos contra chuva e radiação UV (IP67)</div>
            <div class="item-lista">• Ventilação natural adequada (convecção)</div>
            <div class="item-lista">• Fácil acesso para manutenção quando necessário</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Requisitos técnicos atendidos:</span>
            <div class="item-lista">• Estrutura do telhado em boas condições para fixação</div>
            <div class="item-lista">• Espaço mínimo para circulação de ar</div>
            <div class="item-lista">• Temperatura ambiente dentro da faixa recomendada</div>
            <div class="item-lista">• Conexões elétricas devidamente protegidas</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Considerações importantes:</span>
            <div class="item-lista">• Os inversores possuem Wi-Fi integrado para monitoramento direto</div>
            <div class="item-lista">• Recomendamos garantir acesso à rede Wi-Fi para monitoramento</div>
            <div class="item-lista">• Cada inversor conecta até 4 módulos</div>
        </div>

        <div class="selo-contato">
            <img src="{{ SELO_QUALIDADE }}" style="width: 100px; opacity: 0.8;">
            <p style="font-size: 11px; color: #666; margin-top: 8px;">
                {{ SITE }}<br>
                {{ TELEFONE }} | {{ EMAIL }}
            </p>
        </div>
    </div>

    <!-- PÁGINA 4 -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 04</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            Para garantir que sua instalação ocorra de forma tranquila, segura e dentro dos prazos estabelecidos, destacamos os seguintes pontos importantes:
        </div>

        <div class="clausula-titulo">RECEBIMENTO DOS EQUIPAMENTOS</div>
        <div class="item-lista">• <span class="negrito">Confira imediatamente</span> a quantidade de volumes entregues, comparando com a nota fiscal</div>
        <div class="item-lista">• <span class="negrito">Verifique a integridade física</span> dos módulos fotovoltaicos (painéis solares)</div>
        <div class="item-lista">• Em caso de avaria ou divergência, <span class="negrito">registre fotos e entre em contato imediatamente</span></div>

        <div class="clausula-titulo" style="margin-top: 15px;">ARMAZENAMENTO TEMPORÁRIO</div>
        <div class="item-lista">• <span class="negrito">Reserve uma área adequada</span> para armazenamento (os equipamentos ocupam espaço considerável)</div>
        <div class="item-lista">• Módulos podem ficar expostos ao tempo, mas <span class="negrito">REMOVA o papelão de proteção</span> se houver chuva</div>
        <div class="item-lista">• Inversores e outros equipamentos eletrônicos <span class="negrito">DEVEM ficar em locais cobertos e secos</span></div>

        <div class="clausula-titulo" style="margin-top: 15px;">PRESENÇA NO LOCAL</div>
        <div class="item-lista">• É <span class="negrito">obrigatória a presença do cliente ou pessoa autorizada</span> durante a entrega dos equipamentos</div>
        <div class="item-lista">• Durante a instalação, é necessário que <span class="negrito">alguém de confiança esteja presente</span> para acesso e esclarecimento de dúvidas</div>

        <div class="clausula-titulo" style="margin-top: 15px;">CONEXÃO E MONITORAMENTO</div>
        <div class="item-lista">• Para funcionamento do monitoramento remoto (aplicativo), é necessário <span class="negrito">internet de qualidade no local</span></div>
        <div class="item-lista">• Se não houver internet no momento da instalação, o <span class="negrito">retorno do técnico para configuração será cobrado adicionalmente</span></div>

        <div class="clausula-titulo" style="margin-top: 15px;">ALTERAÇÕES NO PROJETO</div>
        <div class="item-lista">• Caso o cliente realize adequações por conta própria, este relatório torna-se <span class="negrito">apenas consultivo</span></div>
        <div class="item-lista">• A {{ RAZAO_SOCIAL }} não se responsabiliza por <span class="negrito">atrasos ou reprovações</span> junto à concessionária decorrentes de alterações não autorizadas</div>
    </div>

    <!-- PÁGINA 5 -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 05</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            <span class="negrito">Reformas e alterações pós-assinatura:</span>
            <div class="item-lista">• Qualquer reforma no imóvel após a assinatura deste relatório exigirá <span class="negrito">nova visita técnica para validação</span></div>
            <div class="item-lista">• O custo da nova visita técnica será de <span class="negrito">responsabilidade integral do cliente</span></div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Alterações cadastrais:</span>
            <div class="item-lista">• Mudanças no cadastro junto à concessionária durante o processo de instalação <span class="negrito">podem estender os prazos</span></div>
            <div class="item-lista">• A {{ RAZAO_SOCIAL }} não se responsabiliza por <span class="negrito">atrasos decorrentes de alterações cadastrais</span> feitas pelo cliente</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Garantia e pós-venda:</span>
            <div class="item-lista">• Garantia dos equipamentos conforme fabricante (certificados serão entregues após instalação)</div>
            <div class="item-lista">• Garantia da instalação: 90 dias para vícios aparentes, 5 anos para vícios ocultos</div>
            <div class="item-lista">• Suporte técnico disponível durante todo o período de garantia</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Próximos passos:</span>
            <div class="item-lista">1. Aprovação deste relatório pelo cliente</div>
            <div class="item-lista">2. Início do processo de homologação junto à concessionária ({{ CONCESSIONARIA }})</div>
            <div class="item-lista">3. Agendamento da entrega dos equipamentos</div>
            <div class="item-lista">4. Instalação e comissionamento do sistema</div>
            <div class="item-lista">5. Ativação e monitoramento contínuo</div>
        </div>

        <div style="margin-top: 35px;">
            <p style="text-align: center; font-size: 14px; color: var(--azul-corporativo);">
                Em caso de dúvidas, estamos à sua disposição!
            </p>
        </div>

        <div style="text-align: center; margin-top: 25px;">
            <p style="font-size: 16px; font-weight: bold; color: var(--amarelo-sol);">
                Junte-se à revolução da energia solar!
            </p>
            <p style="font-size: 12px; color: #666; margin-top: 8px;">
                {{ NOME_CLIENTE }}<br>
                {{ DATA_EMISSAO }}
            </p>
        </div>
    </div>

    <!-- PÁGINA 6 -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 06</div>
        </div>

        <div class="titulo-faixa">VALIDAÇÃO E ASSINATURAS</div>

        <div class="clausula-conteudo">
            Este documento foi elaborado com base na visita técnica realizada e nas normas técnicas aplicáveis. A assinatura abaixo indica ciência e concordância com todas as informações técnicas apresentadas.
        </div>

        <div class="assinatura-container" style="margin-top: 130px;">
            <div class="assinatura">
                <p style="font-size: 12px; margin-bottom: 15px;">
                    <span class="negrito">CLIENTE</span><br>
                    Declaro ter lido e compreendido todas as informações deste relatório técnico.
                </p>
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">{{ NOME_CLIENTE }}</div>
                <div class="cargo-assinatura">CPF/CNPJ: {{ CPF_CNPJ }}</div>
            </div>

            <div class="assinatura">
                <p style="font-size: 12px; margin-bottom: 15px;">
                    <span class="negrito">ENGENHEIRO RESPONSÁVEL</span><br>
                    Certifico a veracidade das informações técnicas contidas neste relatório.
                </p>
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">{{ ENGENHEIRO_RESPONSAVEL }}</div>
                <div class="cargo-assinatura">CREA: {{ CREA_NUMERO }}</div>
            </div>
        </div>

        <div style="margin-top: 60px; font-size: 10px; color: #666; text-align: center;">
            <p>Documento gerado eletronicamente por {{ RAZAO_SOCIAL }}</p>
            <p>Data de emissão: {{ DATA_EMISSAO }} às {{ HORA_EMISSAO }}</p>
            <p>Protocolo: {{ NUM_PROTOCOLO }}</p>

            <div style="margin-top: 25px; padding: 10px; background: #f5f5f5; border-radius: 4px;">
                <p class="negrito">AUTENTICIDADE DO DOCUMENTO</p>
                <p>Hash SHA256: {{ HASH_DOCUMENTO }}</p>
                <p>Verifique a autenticidade em: {{ URL_VALIDACAO }}</p>
            </div>
        </div>

        <div style="margin-top: 30px; text-align: center;">
            <p style="font-size: 9px; color: #999;">
                {{ RAZAO_SOCIAL }} | CNPJ: {{ CNPJ }}<br>
                {{ ENDERECO_EMPRESA }}<br>
                {{ TELEFONE }} | {{ EMAIL }} | {{ SITE }}
            </p>
        </div>
    </div>
</body>
</html>
"""

# ============================================================
# TEMPLATE 3: RELATÓRIO COM ADEQUAÇÃO (VT)
# ============================================================
template_com_adequacao = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>RELATÓRIO DE CONFORMIDADE TÉCNICA - SoLivia ENGENHARIA</title>
    <style>
        :root {
            --azul-premium: #001f3f;
            --azul-glow: #0b2f5c;
            --amarelo-sol: #ffc400;
            --fundo-conteudo: #f8fafc;
            --azul-corporativo: #0b2f5c;
        }
        @page {
            size: A4;
            margin: 0;
        }
        @page interna {
            margin: 0;
            @bottom-center {
                content: element(footer_geral);
            }
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
        }

        /* CAPA - MESMO DESIGN DOS CONTRATOS */
        .capa-container {
            width: 210mm;
            height: 297mm;
            background-color: var(--azul-premium);
            color: white;
            position: relative;
            page-break-after: always;
        }
        .fundo-gradiente-capa {
            position: absolute;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 85% 15%, rgba(255,196,0,0.1) 0%, transparent 40%),
                        radial-gradient(circle at 15% 85%, rgba(11,47,92,0.5) 0%, transparent 50%);
        }
        .logo-central-wrapper {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .logo-img-central {
            max-height: 420px;
            max-width: 85%;
            object-fit: contain;
        }
        .titulo-container-capa {
            position: absolute;
            top: 50%;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            transform: translateY(-50%);
        }
        .linha-lateral-capa {
            flex-grow: 1;
            height: 1px;
            background: rgba(255,255,255,0.3);
            margin: 0;
        }
        .titulo-texto-capa {
            font-size: 36px;
            font-weight: bold;
            letter-spacing: 12px;
            margin: 0 15px;
            text-transform: uppercase;
            white-space: nowrap;
            color: var(--amarelo-sol);
        }
        .slogan-superior {
            position: absolute;
            bottom: 145px;
            right: 60px;
            font-size: 16px;
            letter-spacing: 5px;
            opacity: 0.9;
            color: var(--amarelo-sol);
            font-weight: 500;
        }
        .rodape-bloco-capa {
            position: absolute;
            bottom: 0;
            width: 100%;
            height: 135px;
            background: rgba(0,0,0,0.25);
            border-top: 5px solid var(--amarelo-sol);
        }
        .rodape-conteudo-capa {
            position: relative;
            width: 90%;
            margin: 0 auto;
            height: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .linha-divisoria-capa {
            width: 4px;
            height: 60px;
            background: rgba(255,255,255,0.5);
            border-radius: 2px;
        }
        .texto-identidade-capa {
            text-align: center;
            color: white;
        }
        .texto-identidade-capa b {
            font-size: 18px;
            display: block;
            margin-bottom: 5px;
        }
        .texto-identidade-capa span {
            font-size: 13px;
            opacity: 0.8;
            letter-spacing: 1.5px;
            white-space: nowrap;
        }
        .info-proposta-capa {
            text-align: right;
            font-size: 14px;
            color: white;
            line-height: 1.8;
        }
        .info-proposta-capa b {
            font-weight: 600;
        }

        /* PÁGINAS INTERNAS */
        .page-interna {
            page: interna;
            page-break-after: always;
            width: 210mm;
            min-height: 297mm;
            background-color: var(--fundo-conteudo);
            padding: 1.5cm;
            box-sizing: border-box;
            position: relative;
            color: #333;
        }
        #footer_geral {
            position: running(footer_geral);
            text-align: center;
            font-size: 10px;
            color: #64748b;
            padding: 10px 0;
            width: 90%;
            border-top: 2px solid var(--azul-corporativo);
            margin: 0 auto;
        }
        .header-interna {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 3px solid var(--amarelo-sol);
            padding-bottom: 8px;
            margin-bottom: 20px;
        }
        .texto-solivia-topo {
            color: var(--azul-corporativo);
            font-weight: 800;
            font-size: 16px;
        }
        .titulo-faixa {
            background: var(--azul-corporativo);
            color: white;
            padding: 12px 20px;
            font-weight: bold;
            border-left: 8px solid var(--amarelo-sol);
            border-radius: 4px;
            margin: 20px 0;
        }
        .clausula-titulo {
            font-weight: bold;
            margin-top: 15px;
            color: var(--azul-corporativo);
            font-size: 14px;
        }
        .clausula-conteudo {
            text-align: justify;
            line-height: 1.6;
            margin-bottom: 10px;
            font-size: 12px;
        }
        .negrito {
            font-weight: bold;
        }
        .item-lista {
            margin-left: 20px;
            margin-bottom: 8px;
        }
        .assinatura-container {
            display: flex;
            justify-content: space-between;
            margin-top: 80px;
            page-break-inside: avoid;
        }
        .assinatura {
            width: 40%;
            text-align: center;
        }
        .linha-assinatura {
            width: 100%;
            border-top: 1.5px solid #333;
            margin-bottom: 5px;
        }
        .nome-assinatura {
            font-size: 13px;
            font-weight: bold;
            margin-top: 5px;
        }
        .cargo-assinatura {
            font-size: 11px;
            color: #555;
        }
        .destaque-azul {
            background-color: rgba(11, 47, 92, 0.1);
            padding: 15px;
            border-left: 4px solid var(--azul-corporativo);
            margin: 15px 0;
            border-radius: 4px;
        }
        .tabela-proposta {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 11px;
        }
        .tabela-proposta th {
            background-color: var(--azul-corporativo);
            color: white;
            padding: 10px;
            text-align: center;
            border: 1px solid #ddd;
        }
        .tabela-proposta td {
            padding: 10px;
            border: 1px solid #ddd;
            text-align: center;
        }
        .tabela-proposta tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .box-adequacao {
            background: white;
            border: 2px solid var(--amarelo-sol);
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }
        .valor-adequacao {
            font-size: 24px;
            font-weight: bold;
            color: var(--azul-corporativo);
            text-align: center;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div id="footer_geral">{{ RAZAO_SOCIAL }} | CNPJ: {{ CNPJ }} | {{ TELEFONE }} | {{ EMAIL }} | {{ SITE }}</div>

    <!-- CAPA DO RELATÓRIO -->
    <div class="capa-container">
        <div class="fundo-gradiente-capa"></div>
        <div class="logo-central-wrapper">
            {% if LOGO_CENTRAL %}<img src="{{ LOGO_CENTRAL }}" class="logo-img-central">{% endif %}
        </div>
        <div class="titulo-container-capa">
            <div class="linha-lateral-capa"></div>
            <div class="titulo-texto-capa">RELATÓRIO TÉCNICO</div>
            <div class="linha-lateral-capa"></div>
        </div>
        <div class="slogan-superior">{{ RAZAO_SOCIAL }}</div>
        <div class="rodape-bloco-capa">
            <div class="rodape-conteudo-capa">
                <div style="display: flex; align-items: center; gap: 25px;">
                    {% if LOGO_RODAPE %}<img src="{{ LOGO_RODAPE }}" style="max-height: 100px;">{% endif %}
                    <div class="linha-divisoria-capa"></div>
                    <div class="texto-identidade-capa">
                        <b>{{ NOME_FANTASIA }}</b>
                        <span>ENGENHARIA E INSTALAÇÕES SOLARES</span>
                    </div>
                </div>
                <div class="info-proposta-capa">
                    <b>Nº DO RELATÓRIO:</b> {{ NUM_RELATORIO }}<br>
                    <b>DATA:</b> {{ DATA_EMISSAO }}<br>
                    <b>PROPOSTA:</b> {{ NUM_PROPOSTA }}
                </div>
            </div>
        </div>
    </div>

    <!-- PÁGINA 1: APRESENTAÇÃO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 01</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            <span class="negrito">Cliente:</span> {{ NOME_CLIENTE }}<br>
            <span class="negrito">Endereço:</span> {{ ENDERECO }}
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            Este relatório técnico apresenta as adequações necessárias para prosseguirmos com a instalação do seu sistema fotovoltaico. Sua cidade é atendida pela concessionária <span class="negrito">{{ CONCESSIONARIA }}</span>, e a seguir detalhamos o layout proposto e as adequações solicitadas para homologação do projeto.
        </div>

        <div class="destaque-azul">
            <p class="negrito">CONSIDERAÇÕES DA CONCESSIONÁRIA</p>
            <p style="font-size: 11px; margin: 5px 0;">
                Cada concessionária possui normativas específicas para instalações fotovoltaicas. A <span class="negrito">{{ CONCESSIONARIA }}</span> exige que todos os projetos atendam rigorosamente às suas diretrizes técnicas para garantir a segurança da rede e dos usuários.
            </p>
            <p style="font-size: 11px; margin: 5px 0;">
                Nossa equipe técnica analisou minuciosamente seu imóvel para propor a melhor solução dentro dos parâmetros exigidos.
            </p>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Objetivo do relatório:</span>
            <div class="item-lista">• Apresentar as adequações técnicas necessárias</div>
            <div class="item-lista">• Otimizar a geração de energia do sistema</div>
            <div class="item-lista">• Garantir conformidade com as normativas da {{ CONCESSIONARIA }}</div>
            <div class="item-lista">• Estabelecer os próximos passos do processo</div>
        </div>

        <div style="margin-top: 40px; text-align: center;">
            <p style="font-style: italic; color: var(--azul-corporativo);">
                "Soluções energéticas com excelência técnica e segurança"
            </p>

            <div style="margin-top: 30px;">
                <div class="linha-assinatura" style="width: 60%; margin: 0 auto;"></div>
                <div class="nome-assinatura">{{ NOME_CLIENTE }}</div>
                <div class="cargo-assinatura">CLIENTE / PROPRIETÁRIO</div>
            </div>
        </div>
    </div>

    <!-- PÁGINA 2: NOVA PROPOSTA DE LAYOUT -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 02</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-titulo">NOVA PROPOSTA DE LAYOUT</div>

        <div class="clausula-conteudo">
            Após análise detalhada das imagens e dados coletados na visita técnica, identificamos oportunidades para otimizar a performance do seu sistema fotovoltaico. Estamos comprometidos em entregar a melhor solução técnica possível!
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Desafios técnicos identificados:</span>
            <div class="item-lista">• {{ DESAFIO_1 }}</div>
            <div class="item-lista">• {{ DESAFIO_2 }}</div>
            <div class="item-lista">• {{ DESAFIO_3 }}</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            Sua geração originalmente proposta foi de <span class="negrito">{{ GERACAO_ORIGINAL }} kWh/mês</span>. Na nova proposta, com o intuito de otimizarmos a geração de energia solar, o sistema contará com as seguintes adequações:
            <div class="item-lista">• {{ ADEQUACAO_LAYOUT_1 }}</div>
            <div class="item-lista">• {{ ADEQUACAO_LAYOUT_2 }}</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            Modificando o layout conforme as especificações técnicas e otimizando o uso dos espaços disponíveis, temos as seguintes opções de composição:
        </div>

        <table class="tabela-proposta">
            <thead>
                <tr>
                    <th>QTDE DE MÓDULOS</th>
                    <th>INVERSOR</th>
                    <th>VALOR TOTAL DO PROJETO</th>
                    <th>GERAÇÃO (média mensal)</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{{ QTD_MODULOS_OPCAO1 }}</td>
                    <td>{{ INVERSOR_OPCAO1 }}</td>
                    <td>{{ VALOR_OPCAO1 }}</td>
                    <td>{{ GERACAO_OPCAO1 }} kWh/mês</td>
                </tr>
                <tr>
                    <td>{{ QTD_MODULOS_OPCAO2 }}</td>
                    <td>{{ INVERSOR_OPCAO2 }}</td>
                    <td>{{ VALOR_OPCAO2 }}</td>
                    <td>{{ GERACAO_OPCAO2 }} kWh/mês</td>
                </tr>
            </tbody>
        </table>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Recomendação técnica:</span>
            <div class="item-lista">• {{ RECOMENDACAO_TECNICA }}</div>
            <div class="item-lista">• Considerar o custo-benefício de cada opção</div>
            <div class="item-lista">• Avaliar a expansão futura do sistema</div>
        </div>

        <div style="margin-top: 30px; text-align: center;">
            <p style="font-style: italic; color: var(--azul-corporativo);">
                "Eficiência energética com tecnologia de ponta"
            </p>
        </div>
    </div>

    <!-- PÁGINA 3: LOCAL DO QUADRO ELÉTRICO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 03</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-titulo">LOCAL DO QUADRO ELÉTRICO DO SISTEMA</div>

        <div class="clausula-conteudo">
            <span class="negrito">Cômodo definido para instalação do quadro elétrico:</span>
            <div class="item-lista" style="margin-top: 10px;">• {{ LOCAL_QUADRO }}</div>
            <div class="item-lista">• Próximo ao quadro elétrico geral do imóvel</div>
            <div class="item-lista">• Área coberta e protegida</div>
            <div class="item-lista">• Acesso facilitado para manutenção</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Especificações técnicas do local:</span>
            <div class="item-lista">• Parede sólida para fixação do quadro</div>
            <div class="item-lista">• Distância mínima de 1m de fontes de calor ou umidade</div>
            <div class="item-lista">• Espaço para passagem de cabos e dutos</div>
            <div class="item-lista">• Iluminação adequada para trabalhos de manutenção</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Componentes do quadro elétrico:</span>
            <div class="item-lista">• Disjuntor geral de proteção</div>
            <div class="item-lista">• DPS (Dispositivo de Proteção contra Surtos)</div>
            <div class="item-lista">• Relé de interface com a rede</div>
            <div class="item-lista">• Barramentos de distribuição</div>
            <div class="item-lista">• Sistema de aterramento</div>
        </div>

        <div style="margin-top: 40px; text-align: center;">
            {% if SELO_QUALIDADE %}<img src="{{ SELO_QUALIDADE }}" style="width: 100px; opacity: 0.8;">{% endif %}
            <p style="font-size: 11px; color: #666; margin-top: 10px;">
                {{ SITE }}<br>
                {{ TELEFONE }} | {{ EMAIL }}
            </p>
        </div>
    </div>

    <!-- PÁGINA 4: ADEQUAÇÕES OBRIGATÓRIAS -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 04</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-titulo">ADEQUAÇÕES OBRIGATÓRIAS PARA HOMOLOGAÇÃO</div>

        <div class="clausula-conteudo">
            Após a visita técnica, identificamos oportunidades para melhorar o padrão de entrada de energia, garantindo total conformidade com as normativas da concessionária <span class="negrito">{{ CONCESSIONARIA }}</span>. Para atender a todos os requisitos técnicos, serão realizadas as seguintes adequações:
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Adequações técnicas necessárias:</span>
            <div class="item-lista">• {{ ADEQUACAO_TECNICA_1 }}</div>
            <div class="item-lista">• {{ ADEQUACAO_TECNICA_2 }}</div>
            <div class="item-lista">• {{ ADEQUACAO_TECNICA_3 }}</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Normativa aplicável:</span> {{ CONCESSIONARIA }}
        </div>

        <div class="box-adequacao">
            <p style="text-align: center; font-size: 14px; margin-bottom: 10px;">
                <span class="negrito">INVESTIMENTO EM ADEQUAÇÕES</span><br>
                Valor adicional para atender todas as exigências técnicas
            </p>
            <div class="valor-adequacao">{{ VALOR_ADEQUACOES }}</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">A SoLivia está com você!</span> Nossa equipe técnica está preparada para esclarecer todas as dúvidas e auxiliá-lo em cada etapa do processo. Essas adequações garantem a segurança da sua instalação e a conformidade com as regulamentações vigentes.
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Benefícios das adequações:</span>
            <div class="item-lista">• Maior segurança elétrica para seu imóvel</div>
            <div class="item-lista">• Conformidade total com as normativas</div>
            <div class="item-lista">• Agilidade no processo de homologação</div>
            <div class="item-lista">• Proteção adicional para seus equipamentos</div>
        </div>
    </div>

    <!-- PÁGINA 5: ORIENTAÇÕES FINAIS -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 05</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            Para garantir uma instalação segura, eficiente e dentro dos prazos estabelecidos, destacamos os seguintes pontos importantes:
        </div>

        <div class="clausula-titulo">RECEBIMENTO DOS EQUIPAMENTOS</div>
        <div class="item-lista">• Confira imediatamente a quantidade de volumes entregues, comparando com a nota fiscal</div>
        <div class="item-lista">• Verifique a integridade física dos módulos fotovoltaicos (painéis solares)</div>
        <div class="item-lista">• Em caso de avaria ou divergência, registre fotos e entre em contato imediatamente</div>

        <div class="clausula-titulo" style="margin-top: 15px;">ARMAZENAMENTO TEMPORÁRIO</div>
        <div class="item-lista">• Reserve uma área adequada para armazenamento (os equipamentos ocupam espaço considerável)</div>
        <div class="item-lista">• Módulos podem ficar expostos ao tempo, mas REMOVA o papelão de proteção se houver chuva</div>
        <div class="item-lista">• Inversores e outros equipamentos eletrônicos DEVEM ficar em locais cobertos e secos</div>

        <div class="clausula-titulo" style="margin-top: 15px;">PRESENÇA NO LOCAL</div>
        <div class="item-lista">• É obrigatória a presença do cliente ou pessoa autorizada durante a entrega dos equipamentos</div>
        <div class="item-lista">• Durante a instalação, é necessário que alguém de confiança esteja presente para acesso e dúvidas</div>

        <div class="clausula-titulo" style="margin-top: 15px;">MONITORAMENTO DO SISTEMA</div>
        <div class="item-lista">• Para funcionamento do monitoramento remoto (aplicativo), é necessário internet de qualidade no local do inversor</div>
        <div class="item-lista">• Se não houver internet no momento da instalação, o retorno técnico para configuração será cobrado adicionalmente</div>

        <div class="clausula-titulo" style="margin-top: 15px;">RESPONSABILIDADES</div>
        <div class="item-lista">• Caso o cliente realize adequações por conta própria, este relatório torna-se apenas consultivo</div>
        <div class="item-lista">• A SoLivia não se responsabiliza por atrasos ou reprovações junto à concessionária decorrentes de alterações não autorizadas</div>

        <div style="margin-top: 30px;">
            <p style="text-align: center; font-size: 14px; color: var(--azul-corporativo);">
                Em caso de dúvidas, estamos à sua disposição!
            </p>
        </div>

        <div style="text-align: center; margin-top: 30px;">
            <p style="font-size: 16px; font-weight: bold; color: var(--amarelo-sol);">
                Junte-se à revolução da energia solar!
            </p>
            <p style="font-size: 12px; color: #666; margin-top: 10px;">
                {{ NOME_CLIENTE }}<br>
                {{ DATA_EMISSAO }}
            </p>
        </div>
    </div>

    <!-- PÁGINA 6: ASSINATURAS -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 06</div>
        </div>

        <div class="titulo-faixa">VALIDAÇÃO E ASSINATURAS</div>

        <div class="clausula-conteudo">
            Este documento foi elaborado com base na visita técnica realizada e nas normas técnicas aplicáveis. A assinatura abaixo indica ciência e concordância com todas as informações técnicas apresentadas.
        </div>

        <div class="assinatura-container">
            <div class="assinatura">
                <p style="font-size: 12px; margin-bottom: 15px;">
                    <span class="negrito">CLIENTE</span><br>
                    Declaro ter lido e compreendido todas as informações deste relatório técnico.
                </p>
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">{{ NOME_CLIENTE }}</div>
                <div class="cargo-assinatura">CPF/CNPJ: {{ CPF_CNPJ }}</div>
            </div>

            <div class="assinatura">
                <p style="font-size: 12px; margin-bottom: 15px;">
                    <span class="negrito">ENGENHEIRO RESPONSÁVEL</span><br>
                    Certifico a veracidade das informações técnicas contidas neste relatório.
                </p>
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">{{ ENGENHEIRO_RESPONSAVEL }}</div>
                <div class="cargo-assinatura">CREA: {{ CREA_NUMERO }}</div>
            </div>
        </div>

        <div style="margin-top: 60px; font-size: 10px; color: #666; text-align: center;">
            <p>Documento gerado eletronicamente por {{ RAZAO_SOCIAL }}</p>
            <p>Data de emissão: {{ DATA_EMISSAO }} às {{ HORA_EMISSAO }}</p>
            <p>Protocolo: {{ NUM_PROTOCOLO }}</p>

            <div style="margin-top: 20px; padding: 10px; background: #f5f5f5; border-radius: 4px;">
                <p class="negrito">AUTENTICIDADE DO DOCUMENTO</p>
                <p>Hash SHA256: {{ HASH_DOCUMENTO }}</p>
                <p>Verifique a autenticidade em: {{ URL_VALIDACAO }}</p>
            </div>
        </div>

        <div style="margin-top: 30px; text-align: center;">
            <p style="font-size: 9px; color: #999;">
                {{ RAZAO_SOCIAL }} | CNPJ: {{ CNPJ }}<br>
                {{ ENDERECO_EMPRESA }}<br>
                {{ TELEFONE }} | {{ EMAIL }} | {{ SITE }}
            </p>
        </div>
    </div>
</body>
</html>
"""

# ============================================================
# TEMPLATE 4: RELATÓRIO FAST TRACK (VT)
# ============================================================
template_fast_track = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>RELATÓRIO DE CONFORMIDADE TÉCNICA - SoLivia ENGENHARIA</title>
    <style>
        :root {
            --azul-premium: #001f3f;
            --azul-glow: #0b2f5c;
            --amarelo-sol: #ffc400;
            --fundo-conteudo: #f8fafc;
            --azul-corporativo: #0b2f5c;
        }
        @page {
            size: A4;
            margin: 0;
        }
        @page interna {
            margin: 0;
            @bottom-center {
                content: element(footer_geral);
            }
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 0;
        }

        /* CAPA - MESMO DESIGN DOS CONTRATOS */
        .capa-container {
            width: 210mm;
            height: 297mm;
            background-color: var(--azul-premium);
            color: white;
            position: relative;
            page-break-after: always;
        }
        .fundo-gradiente-capa {
            position: absolute;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 85% 15%, rgba(255,196,0,0.1) 0%, transparent 40%),
                        radial-gradient(circle at 15% 85%, rgba(11,47,92,0.5) 0%, transparent 50%);
        }
        .logo-central-wrapper {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .logo-img-central {
            max-height: 420px;
            max-width: 85%;
            object-fit: contain;
        }
        .titulo-container-capa {
            position: absolute;
            top: 50%;
            width: 100%;
            display: flex;
            align-items: center;
            justify-content: center;
            transform: translateY(-50%);
        }
        .linha-lateral-capa {
            flex-grow: 1;
            height: 1px;
            background: rgba(255,255,255,0.3);
            margin: 0;
        }
        .titulo-texto-capa {
            font-size: 36px;
            font-weight: bold;
            letter-spacing: 12px;
            margin: 0 15px;
            text-transform: uppercase;
            white-space: nowrap;
            color: var(--amarelo-sol);
        }
        .slogan-superior {
            position: absolute;
            bottom: 145px;
            right: 60px;
            font-size: 16px;
            letter-spacing: 5px;
            opacity: 0.9;
            color: var(--amarelo-sol);
            font-weight: 500;
        }
        .rodape-bloco-capa {
            position: absolute;
            bottom: 0;
            width: 100%;
            height: 135px;
            background: rgba(0,0,0,0.25);
            border-top: 5px solid var(--amarelo-sol);
        }
        .rodape-conteudo-capa {
            position: relative;
            width: 90%;
            margin: 0 auto;
            height: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .linha-divisoria-capa {
            width: 4px;
            height: 60px;
            background: rgba(255,255,255,0.5);
            border-radius: 2px;
        }
        .texto-identidade-capa {
            text-align: center;
            color: white;
        }
        .texto-identidade-capa b {
            font-size: 18px;
            display: block;
            margin-bottom: 5px;
        }
        .texto-identidade-capa span {
            font-size: 13px;
            opacity: 0.8;
            letter-spacing: 1.5px;
            white-space: nowrap;
        }
        .info-proposta-capa {
            text-align: right;
            font-size: 14px;
            color: white;
            line-height: 1.8;
        }
        .info-proposta-capa b {
            font-weight: 600;
        }

        /* PÁGINAS INTERNAS */
        .page-interna {
            page: interna;
            page-break-after: always;
            width: 210mm;
            min-height: 297mm;
            background-color: var(--fundo-conteudo);
            padding: 1.5cm;
            box-sizing: border-box;
            position: relative;
            color: #333;
        }
        #footer_geral {
            position: running(footer_geral);
            text-align: center;
            font-size: 10px;
            color: #64748b;
            padding: 10px 0;
            width: 90%;
            border-top: 2px solid var(--azul-corporativo);
            margin: 0 auto;
        }
        .header-interna {
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 3px solid var(--amarelo-sol);
            padding-bottom: 8px;
            margin-bottom: 20px;
        }
        .texto-solivia-topo {
            color: var(--azul-corporativo);
            font-weight: 800;
            font-size: 16px;
        }
        .titulo-faixa {
            background: var(--azul-corporativo);
            color: white;
            padding: 12px 20px;
            font-weight: bold;
            border-left: 8px solid var(--amarelo-sol);
            border-radius: 4px;
            margin: 20px 0;
        }
        .clausula-titulo {
            font-weight: bold;
            margin-top: 15px;
            color: var(--azul-corporativo);
            font-size: 14px;
        }
        .clausula-conteudo {
            text-align: justify;
            line-height: 1.6;
            margin-bottom: 10px;
            font-size: 12px;
        }
        .negrito {
            font-weight: bold;
        }
        .item-lista {
            margin-left: 20px;
            margin-bottom: 8px;
        }
        .assinatura-container {
            display: flex;
            justify-content: space-between;
            margin-top: 80px;
            page-break-inside: avoid;
        }
        .assinatura {
            width: 40%;
            text-align: center;
        }
        .linha-assinatura {
            width: 100%;
            border-top: 1.5px solid #333;
            margin-bottom: 5px;
        }
        .nome-assinatura {
            font-size: 13px;
            font-weight: bold;
            margin-top: 5px;
        }
        .cargo-assinatura {
            font-size: 11px;
            color: #555;
        }
        .destaque-amarelo {
            background-color: rgba(255, 196, 0, 0.1);
            padding: 15px;
            border-left: 4px solid var(--amarelo-sol);
            margin: 15px 0;
            border-radius: 4px;
        }
        .container-geracao {
            display: flex;
            justify-content: space-between;
            margin: 20px 0;
        }
        .box-geracao {
            background: white;
            border: 2px solid var(--azul-corporativo);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            width: 48%;
        }
        .valor-geracao {
            font-size: 24px;
            font-weight: bold;
            color: var(--azul-corporativo);
        }
        .label-geracao {
            font-size: 12px;
            color: #666;
        }
    </style>
</head>
<body>
    <div id="footer_geral">{{ RAZAO_SOCIAL }} | CNPJ: {{ CNPJ }} | {{ TELEFONE }} | {{ EMAIL }} | {{ SITE }}</div>

    <!-- CAPA DO RELATÓRIO -->
    <div class="capa-container">
        <div class="fundo-gradiente-capa"></div>
        <div class="logo-central-wrapper">
            {% if LOGO_CENTRAL %}<img src="{{ LOGO_CENTRAL }}" class="logo-img-central">{% endif %}
        </div>
        <div class="titulo-container-capa">
            <div class="linha-lateral-capa"></div>
            <div class="titulo-texto-capa">RELATÓRIO TÉCNICO</div>
            <div class="linha-lateral-capa"></div>
        </div>
        <div class="slogan-superior">{{ RAZAO_SOCIAL }}</div>
        <div class="rodape-bloco-capa">
            <div class="rodape-conteudo-capa">
                <div style="display: flex; align-items: center; gap: 25px;">
                    {% if LOGO_RODAPE %}<img src="{{ LOGO_RODAPE }}" style="max-height: 100px;">{% endif %}
                    <div class="linha-divisoria-capa"></div>
                    <div class="texto-identidade-capa">
                        <b>{{ NOME_FANTASIA }}</b>
                        <span>ENGENHARIA E INSTALAÇÕES SOLARES</span>
                    </div>
                </div>
                <div class="info-proposta-capa">
                    <b>Nº DO RELATÓRIO:</b> {{ NUM_RELATORIO }}<br>
                    <b>DATA:</b> {{ DATA_EMISSAO }}<br>
                    <b>PROPOSTA:</b> {{ NUM_PROPOSTA }}
                </div>
            </div>
        </div>
    </div>

    <!-- PÁGINA 1: APRESENTAÇÃO E CONTEXTO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 01</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            <span class="negrito">Cliente:</span> {{ NOME_CLIENTE }}<br>
            <span class="negrito">Endereço:</span> {{ ENDERECO }}
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            Este relatório técnico tem como objetivo apresentar as análises e recomendações de engenharia para garantir o sucesso da sua instalação fotovoltaica. A seguir, detalhamos o layout otimizado e as considerações técnicas necessárias para homologação junto à concessionária.
        </div>

        <div class="destaque-amarelo">
            <p class="negrito">PROCEDIMENTO FAST TRACK</p>
            <p style="font-size: 11px; margin: 5px 0;">
                Em algumas regiões, as concessionárias de energia têm solicitado redução da potência de sistemas fotovoltaicos devido ao fenômeno de <span class="negrito">inversão de fluxo</span>, que ocorre quando a geração de energia excede a demanda local, causando distúrbios na rede de distribuição.
            </p>
            <p style="font-size: 11px; margin: 5px 0;">
                Para sistemas com potência inferior a 7,5 kWp, temos a opção do <span class="negrito">FAST TRACK</span>, que agiliza o processo de homologação, porém com as seguintes considerações importantes:
            </p>
            <ul style="font-size: 11px; margin: 5px 0 0 15px;">
                <li>Não há análise de inversão de fluxo</li>
                <li>Processo de homologação simplificado</li>
                <li><span class="negrito">NÃO haverá possibilidade de roteamento de créditos excedentes para outras unidades, nem agora nem no futuro</span></li>
            </ul>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            Para garantir transparência e evitar surpresas durante o processo, a SoLivia Energia inicia com antecedência o parecer de acesso junto à concessionária. Esta etapa permite identificar previamente qualquer necessidade de ajuste no projeto.
        </div>

        <div class="clausula-conteudo">
            <span class="negrito">Nota importante para financiamentos:</span> Devido ao prazo curto de validade das simulações financeiras, pode ser necessária uma nova tentativa de financiamento após a validação técnica do projeto.
        </div>

        <div style="margin-top: 40px; text-align: center;">
            <p class="negrito">DECLARAÇÃO DE CIÊNCIA</p>
            <p style="font-size: 12px;">
                Declaro estar ciente e de acordo com a opção FAST TRACK, compreendendo todos os aspectos técnicos e regulatórios envolvidos.
            </p>

            <div style="margin-top: 30px;">
                <div class="linha-assinatura" style="width: 60%; margin: 0 auto;"></div>
                <div class="nome-assinatura">{{ NOME_CLIENTE }}</div>
                <div class="cargo-assinatura">CLIENTE / PROPRIETÁRIO</div>
            </div>
        </div>
    </div>

    <!-- PÁGINA 2: ANÁLISE TÉCNICA E LAYOUT -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 02</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-titulo">NOVA PROPOSTA DE LAYOUT</div>

        <div class="clausula-conteudo">
            Após análise detalhada das imagens e dados coletados na visita técnica, identificamos considerações importantes que otimizam a performance do seu sistema fotovoltaico. Estamos comprometidos em entregar a melhor solução técnica possível!
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Observações técnicas identificadas:</span>
            <div class="item-lista">• Orientação do telhado: A área disponível está voltada para noroeste, o que impacta na eficiência da geração solar durante o dia.</div>
            <div class="item-lista">• Sombreamento: Verificamos possíveis interferências que podem reduzir a produção energética.</div>
            <div class="item-lista">• Estrutura do telhado: Foram avaliadas as condições de suporte para os módulos fotovoltaicos.</div>
        </div>

        <div class="container-geracao">
            <div class="box-geracao">
                <div class="label-geracao">GERAÇÃO ORIGINALMENTE PROPOSTA</div>
                <div class="valor-geracao">{{ GERACAO_ORIGINAL }} kWh/mês</div>
            </div>
            <div class="box-geracao">
                <div class="label-geracao">GERAÇÃO OTIMIZADA</div>
                <div class="valor-geracao">{{ GERACAO_OTIMIZADA }} kWh/mês</div>
            </div>
        </div>

        <div class="clausula-conteudo">
            <span class="negrito">Sistema proposto:</span>
            <div class="item-lista">• {{ QTD_MODULOS }} módulos fotovoltaicos de alta eficiência</div>
            <div class="item-lista">• 1 inversor central string de {{ POTENCIA_INVERSOR }}</div>
            <div class="item-lista">• Sistema de monitoramento remoto incluído</div>
            <div class="item-lista">• Estrutura de fixação em alumínio anodizado</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Próximos passos:</span>
            <div class="item-lista">1. Aprovação deste layout pelo cliente</div>
            <div class="item-lista">2. Início do processo de homologação junto à concessionária</div>
            <div class="item-lista">3. Agendamento da instalação</div>
            <div class="item-lista">4. Comissionamento e ativação do sistema</div>
        </div>

        <div style="margin-top: 30px; text-align: center;">
            <p style="font-style: italic; color: var(--azul-corporativo);">
                "Energia solar com excelência técnica e transparência"
            </p>
        </div>
    </div>

    <!-- PÁGINA 3: LOCAL DE INSTALAÇÃO DO INVERSOR -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 03</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-titulo">LOCAL DE INSTALAÇÃO DO INVERSOR CENTRAL</div>

        <div class="clausula-conteudo">
            <span class="negrito">Cômodo definido para instalação do inversor:</span>
            <div class="item-lista" style="margin-top: 10px;">• {{ LOCAL_INVERSOR }}</div>
            <div class="item-lista">• Área coberta e protegida das intempéries</div>
            <div class="item-lista">• Acesso facilitado para manutenção</div>
            <div class="item-lista">• Distância otimizada dos módulos fotovoltaicos</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Requisitos técnicos do local:</span>
            <div class="item-lista">• Parede sólida para fixação do inversor</div>
            <div class="item-lista">• Altura recomendada: 1,5m do chão</div>
            <div class="item-lista">• Espaço para circulação de ar (mínimo 50cm em todas as laterais)</div>
            <div class="item-lista">• Temperatura ambiente entre 0°C e 40°C</div>
            <div class="item-lista">• Proteção contra incidência direta de sol e umidade excessiva</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 20px;">
            <span class="negrito">Considerações importantes:</span>
            <div class="item-lista">• O inversor deve ficar afastado de fontes de calor excessivo</div>
            <div class="item-lista">• Evitar locais com poeira excessiva ou vapores corrosivos</div>
            <div class="item-lista">• Garantir acesso à rede Wi-Fi para monitoramento remoto</div>
            <div class="item-lista">• Tomada elétrica próxima (se aplicável ao modelo)</div>
        </div>

        <div style="margin-top: 40px; text-align: center;">
            {% if SELO_QUALIDADE %}<img src="{{ SELO_QUALIDADE }}" style="width: 100px; opacity: 0.8;">{% endif %}
            <p style="font-size: 11px; color: #666; margin-top: 10px;">
                {{ SITE }}<br>
                {{ TELEFONE }} | {{ EMAIL }}
            </p>
        </div>
    </div>

    <!-- PÁGINA 4: ORIENTAÇÕES PARA INSTALAÇÃO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 04</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            Para garantir uma instalação segura, eficiente e dentro dos prazos estabelecidos, destacamos os seguintes pontos importantes:
        </div>

        <div class="clausula-titulo">RECEBIMENTO DOS EQUIPAMENTOS</div>
        <div class="item-lista">• Confira imediatamente a quantidade de volumes entregues, comparando com a nota fiscal</div>
        <div class="item-lista">• Verifique a integridade física dos módulos fotovoltaicos (painéis solares)</div>
        <div class="item-lista">• Em caso de avaria ou divergência, registre fotos e entre em contato imediatamente</div>

        <div class="clausula-titulo" style="margin-top: 20px;">ARMAZENAMENTO TEMPORÁRIO</div>
        <div class="item-lista">• Reserve uma área adequada para armazenamento (os equipamentos ocupam espaço considerável)</div>
        <div class="item-lista">• Módulos podem ficar expostos ao tempo, mas REMOVA o papelão de proteção se houver chuva</div>
        <div class="item-lista">• Inversores e outros equipamentos eletrônicos DEVEM ficar em locais cobertos e secos</div>

        <div class="clausula-titulo" style="margin-top: 20px;">PRESENÇA NO LOCAL</div>
        <div class="item-lista">• É obrigatória a presença do cliente ou pessoa autorizada durante a entrega dos equipamentos</div>
        <div class="item-lista">• Durante a instalação, é necessário que alguém de confiança esteja presente para acesso e dúvidas</div>

        <div class="clausula-titulo" style="margin-top: 20px;">CONEXÃO E MONITORAMENTO</div>
        <div class="item-lista">• Para funcionamento do monitoramento remoto (aplicativo), é necessário internet de qualidade no local do inversor</div>
        <div class="item-lista">• Se não houver internet no momento da instalação, o retorno técnico para configuração será cobrado adicionalmente</div>

        <div class="clausula-titulo" style="margin-top: 20px;">ALTERAÇÕES NO PROJETO</div>
        <div class="item-lista">• Caso o cliente realize adequações por conta própria, este relatório torna-se apenas consultivo</div>
        <div class="item-lista">• A SoLivia não se responsabiliza por atrasos ou reprovações junto à concessionária decorrentes de alterações não autorizadas</div>
    </div>

    <!-- PÁGINA 5: CONSIDERAÇÕES FINAIS -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 05</div>
        </div>

        <div class="titulo-faixa">RELATÓRIO DE CONFORMIDADE TÉCNICA</div>
        <div class="clausula-titulo">CHECK DE ENGENHARIA</div>

        <div class="clausula-conteudo">
            <span class="negrito">Reformas e alterações pós-assinatura:</span>
            <div class="item-lista">• Qualquer reforma no imóvel após a assinatura deste relatório exigirá nova visita técnica para validação</div>
            <div class="item-lista">• O custo da nova visita técnica será de responsabilidade integral do cliente</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Alterações cadastrais:</span>
            <div class="item-lista">• Mudanças no cadastro junto à concessionária durante o processo de instalação podem estender os prazos</div>
            <div class="item-lista">• A SoLivia não se responsabiliza por atrasos decorrentes de alterações cadastrais feitas pelo cliente</div>
        </div>

        <div class="clausula-conteudo" style="margin-top: 15px;">
            <span class="negrito">Garantia e pós-venda:</span>
            <div class="item-lista">• Garantia dos equipamentos conforme fabricante (certificados serão entregues após instalação)</div>
            <div class="item-lista">• Garantia da instalação: 90 dias para vícios aparentes, 5 anos para vícios ocultos</div>
            <div class="item-lista">• Suporte técnico disponível durante todo o período de garantia</div>
        </div>

        <div style="margin-top: 40px;">
            <p style="text-align: center; font-size: 14px; color: var(--azul-corporativo);">
                Estamos à disposição para esclarecer qualquer dúvida!
            </p>
        </div>

        <div style="text-align: center; margin-top: 30px;">
            <p style="font-size: 16px; font-weight: bold; color: var(--amarelo-sol);">
                Junte-se à revolução da energia solar!
            </p>
            <p style="font-size: 12px; color: #666; margin-top: 10px;">
                {{ NOME_CLIENTE }}<br>
                {{ DATA_EMISSAO }}
            </p>
        </div>
    </div>

    <!-- PÁGINA 6: ASSINATURAS E VALIDAÇÃO -->
    <div class="page-interna">
        <div class="header-interna">
            <div class="texto-solivia-topo">{{ NOME_FANTASIA }}</div>
            <div>Pág. 06</div>
        </div>

        <div class="titulo-faixa">VALIDACÃO E ASSINATURAS</div>

        <div class="clausula-conteudo">
            Este documento foi elaborado com base na visita técnica realizada e nas normas técnicas aplicáveis. A assinatura abaixo indica ciência e concordância com todas as informações técnicas apresentadas.
        </div>

        <div class="assinatura-container">
            <div class="assinatura">
                <p style="font-size: 12px; margin-bottom: 15px;">
                    <span class="negrito">CLIENTE</span><br>
                    Declaro ter lido e compreendido todas as informações deste relatório técnico.
                </p>
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">{{ NOME_CLIENTE }}</div>
                <div class="cargo-assinatura">CPF/CNPJ: {{ CPF_CNPJ }}</div>
            </div>

            <div class="assinatura">
                <p style="font-size: 12px; margin-bottom: 15px;">
                    <span class="negrito">ENGENHEIRO RESPONSÁVEL</span><br>
                    Certifico a veracidade das informações técnicas contidas neste relatório.
                </p>
                <div class="linha-assinatura"></div>
                <div class="nome-assinatura">{{ ENGENHEIRO_RESPONSAVEL }}</div>
                <div class="cargo-assinatura">CREA: {{ CREA_NUMERO }}</div>
            </div>
        </div>

        <div style="margin-top: 60px; font-size: 10px; color: #666; text-align: center;">
            <p>Documento gerado eletronicamente por {{ RAZAO_SOCIAL }}</p>
            <p>Data de emissão: {{ DATA_EMISSAO }} às {{ HORA_EMISSAO }}</p>
            <p>Protocolo: {{ NUM_PROTOCOLO }}</p>

            <div style="margin-top: 20px; padding: 10px; background: #f5f5f5; border-radius: 4px;">
                <p class="negrito">AUTENTICIDADE DO DOCUMENTO</p>
                <p>Hash SHA256: {{ HASH_DOCUMENTO }}</p>
                <p>Verifique a autenticidade em: {{ URL_VALIDACAO }}</p>
            </div>
        </div>

        <div style="margin-top: 30px; text-align: center;">
            <p style="font-size: 9px; color: #999;">
                {{ RAZAO_SOCIAL }} | CNPJ: {{ CNPJ }}<br>
                {{ ENDERECO_EMPRESA }}<br>
                {{ TELEFONE }} | {{ EMAIL }} | {{ SITE }}
            </p>
        </div>
    </div>
</body>
</html>
"""

# ============================================================
# ROTA: GERAR PROPOSTA
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

        # Extrair dados
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

        # Processar itens
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

        # Gráfico
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

        # Projeção 20 marcos
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
            # Fallback
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

        # Diagnóstico, solução, benefícios, inclusos/exclusos
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

        # Imagens
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

        # Renderizar PDF
        html_content = Template(template_proposta).render(dados_template)
        pdf_bytes = HTML(string=html_content).write_pdf()

        # Enviar para o Google Apps Script
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        payload = {
            'token': TOKEN,
            'acao': 'salvar_pdf',
            'dados': {
                'nome_cliente': nome_cliente or 'cliente',
                'pdf_base64': pdf_base64,
                'nome_arquivo': f"PreProposta_{nome_cliente or 'cliente'}_{date.today().strftime('%Y%m%d')}.pdf"
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
# ROTA: UPLOAD DE DOCUMENTO (ADMIN)
# ============================================================
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

# ============================================================
# ROTA: GERAR RELATÓRIO DE CONFORMIDADE (VT)
# ============================================================
@app.route('/gerar_relatorio_conformidade', methods=['POST'])
def gerar_relatorio_conformidade_api():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({'error': 'Dados não fornecidos'}), 400

        tipo = dados.get('tipo')
        if not tipo:
            return jsonify({'error': 'Tipo de relatório não especificado'}), 400

        # Dados comuns
        cliente_id = dados.get('cliente_id')
        if not cliente_id:
            return jsonify({'error': 'cliente_id é obrigatório'}), 400

        # Buscar cliente para preencher dados
        cliente = buscar_cliente_por_id(cliente_id)
        if not cliente:
            return jsonify({'error': 'Cliente não encontrado'}), 404

        # Dados do cliente
        nome_cliente = cliente.get('nome', '')
        email_cliente = cliente.get('email', '')
        endereco = cliente.get('endereco', '')
        cep = cliente.get('cep', '')
        cpf_cnpj = cliente.get('cpf_cnpj', '')

        # Dados do relatório
        concessionaria = dados.get('concessionaria', '')
        engenheiro = dados.get('engenheiro', 'Nícolas Alves de Sá')
        crea = dados.get('crea', '5071237870')
        data_visita = dados.get('data_visita', date.today().strftime("%d/%m/%Y"))
        observacoes_gerais = dados.get('observacoes_gerais', '')

        # Imagens (base64)
        imagens = dados.get('imagens', {})
        croqui_layout = imagens.get('croqui_layout', None)
        foto_panoramica = imagens.get('foto_panoramica', None)
        foto_telhado = imagens.get('foto_telhado', None)
        foto_local_inversor = imagens.get('foto_local_inversor', None)
        foto_padrao_entrada = imagens.get('foto_padrao_entrada', None)
        foto_quadro_eletrico = imagens.get('foto_quadro_eletrico', None)

        # Dados específicos
        if tipo == 'sem_adequacao':
            potencia = dados.get('potencia', 0)
            qtd_modulos = dados.get('qtd_modulos', 0)
            inversor = dados.get('inversor', '')
            geracao = dados.get('geracao', 0)
            investimento = dados.get('investimento', 0)
            observacoes = dados.get('observacoes', '')

            dados_template = {
                'RAZAO_SOCIAL': 'SoLivia Engenharia',
                'NOME_FANTASIA': 'SoLivia Engenharia',
                'CNPJ': '49.972.976/0001-15',
                'TELEFONE': '(19) 99681-0219',
                'EMAIL': 'contato@solivia.com.br',
                'SITE': 'www.solivia.com.br',
                'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
                'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
                'SELO_QUALIDADE': 'https://i.imgur.com/hVtSG8M.png',
                'NUM_RELATORIO': f"VT-{date.today().strftime('%Y%m%d')}-001",
                'DATA_EMISSAO': data_visita,
                'NOME_CLIENTE': nome_cliente,
                'CPF_CNPJ': cpf_cnpj,
                'ENDERECO': endereco,
                'CONCESSIONARIA': concessionaria,
                'ENGENHEIRO_RESPONSAVEL': engenheiro,
                'CREA_NUMERO': crea,
                'QTD_MODULOS': qtd_modulos,
                'INVERSOR': inversor,
                'GERACAO': geracao,
                'INVESTIMENTO': investimento,
                'CROQUI_LAYOUT': croqui_layout,
                'OBSERVACOES': observacoes,
                'ENDERECO_EMPRESA': 'Rua Exemplo, 123 - Campinas/SP',
                'HORA_EMISSAO': datetime.now().strftime("%H:%M"),
                'NUM_PROTOCOLO': f"PROT-{date.today().strftime('%Y%m%d')}-001",
                'HASH_DOCUMENTO': 'a'*64,  # placeholder
                'URL_VALIDACAO': 'https://solivia.com.br/validar'
            }

            html_content = Template(template_sem_adequacao).render(dados_template)

        elif tipo == 'com_adequacao':
            # Coleta dados específicos
            desafio1 = dados.get('desafio1', '')
            desafio2 = dados.get('desafio2', '')
            desafio3 = dados.get('desafio3', '')
            adequacao_layout1 = dados.get('adequacao_layout1', '')
            adequacao_layout2 = dados.get('adequacao_layout2', '')
            modulos_op1 = dados.get('modulos_op1', 0)
            inversor_op1 = dados.get('inversor_op1', '')
            valor_op1 = dados.get('valor_op1', 0)
            geracao_op1 = dados.get('geracao_op1', 0)
            modulos_op2 = dados.get('modulos_op2', '')
            inversor_op2 = dados.get('inversor_op2', '')
            valor_op2 = dados.get('valor_op2', '')
            geracao_op2 = dados.get('geracao_op2', '')
            recomendacao = dados.get('recomendacao', '')
            local_quadro = dados.get('local_quadro', '')
            adequacao_tec1 = dados.get('adequacao_tec1', '')
            adequacao_tec2 = dados.get('adequacao_tec2', '')
            adequacao_tec3 = dados.get('adequacao_tec3', '')
            valor_adequacoes = dados.get('valor_adequacoes', 0)
            geracao_original = dados.get('geracao_original', 0)
            geracao_otimizada = dados.get('geracao_otimizada', 0)
            reforco_estrutural = dados.get('reforco_estrutural', '')

            dados_template = {
                'RAZAO_SOCIAL': 'SoLivia Engenharia',
                'NOME_FANTASIA': 'SoLivia Engenharia',
                'CNPJ': '49.972.976/0001-15',
                'TELEFONE': '(19) 99681-0219',
                'EMAIL': 'contato@solivia.com.br',
                'SITE': 'www.solivia.com.br',
                'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
                'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
                'SELO_QUALIDADE': 'https://i.imgur.com/hVtSG8M.png',
                'NUM_RELATORIO': f"VT-{date.today().strftime('%Y%m%d')}-001",
                'NUM_PROPOSTA': f"PROP-{date.today().strftime('%Y%m%d')}-001",
                'DATA_EMISSAO': data_visita,
                'NOME_CLIENTE': nome_cliente,
                'CPF_CNPJ': cpf_cnpj,
                'ENDERECO': endereco,
                'CONCESSIONARIA': concessionaria,
                'ENGENHEIRO_RESPONSAVEL': engenheiro,
                'CREA_NUMERO': crea,
                'ENDERECO_EMPRESA': 'Rua Exemplo, 123 - Campinas/SP',
                'HORA_EMISSAO': datetime.now().strftime("%H:%M"),
                'NUM_PROTOCOLO': f"PROT-{date.today().strftime('%Y%m%d')}-001",
                'HASH_DOCUMENTO': 'a'*64,
                'URL_VALIDACAO': 'https://solivia.com.br/validar',
                'DESAFIO_1': desafio1,
                'DESAFIO_2': desafio2,
                'DESAFIO_3': desafio3,
                'ADEQUACAO_LAYOUT_1': adequacao_layout1,
                'ADEQUACAO_LAYOUT_2': adequacao_layout2,
                'QTD_MODULOS_OPCAO1': modulos_op1,
                'INVERSOR_OPCAO1': inversor_op1,
                'VALOR_OPCAO1': format_moeda(valor_op1),
                'GERACAO_OPCAO1': geracao_op1,
                'QTD_MODULOS_OPCAO2': modulos_op2,
                'INVERSOR_OPCAO2': inversor_op2,
                'VALOR_OPCAO2': format_moeda(valor_op2),
                'GERACAO_OPCAO2': geracao_op2,
                'RECOMENDACAO_TECNICA': recomendacao,
                'LOCAL_QUADRO': local_quadro,
                'ADEQUACAO_TECNICA_1': adequacao_tec1,
                'ADEQUACAO_TECNICA_2': adequacao_tec2,
                'ADEQUACAO_TECNICA_3': adequacao_tec3,
                'VALOR_ADEQUACOES': format_moeda(valor_adequacoes),
                'GERACAO_ORIGINAL': geracao_original,
                'GERACAO_OTIMIZADA': geracao_otimizada,
                'REFORCO_ESTRUTURAL': reforco_estrutural
            }

            html_content = Template(template_com_adequacao).render(dados_template)

        elif tipo == 'fast_track':
            geracao_original = dados.get('geracao_original', 0)
            geracao_otimizada = dados.get('geracao_otimizada', 0)
            qtd_modulos = dados.get('qtd_modulos', 0)
            potencia_inversor = dados.get('potencia_inversor', '')
            local_inversor = dados.get('local_inversor', '')
            observacoes = dados.get('observacoes', '')

            dados_template = {
                'RAZAO_SOCIAL': 'SoLivia Engenharia',
                'NOME_FANTASIA': 'SoLivia Engenharia',
                'CNPJ': '49.972.976/0001-15',
                'TELEFONE': '(19) 99681-0219',
                'EMAIL': 'contato@solivia.com.br',
                'SITE': 'www.solivia.com.br',
                'LOGO_CENTRAL': 'https://i.imgur.com/HkYPKmQ.png',
                'LOGO_RODAPE': 'https://i.imgur.com/gdnq1ok.png',
                'SELO_QUALIDADE': 'https://i.imgur.com/hVtSG8M.png',
                'NUM_RELATORIO': f"VT-{date.today().strftime('%Y%m%d')}-001",
                'NUM_PROPOSTA': f"PROP-{date.today().strftime('%Y%m%d')}-001",
                'DATA_EMISSAO': data_visita,
                'NOME_CLIENTE': nome_cliente,
                'CPF_CNPJ': cpf_cnpj,
                'ENDERECO': endereco,
                'CONCESSIONARIA': concessionaria,
                'ENGENHEIRO_RESPONSAVEL': engenheiro,
                'CREA_NUMERO': crea,
                'ENDERECO_EMPRESA': 'Rua Exemplo, 123 - Campinas/SP',
                'HORA_EMISSAO': datetime.now().strftime("%H:%M"),
                'NUM_PROTOCOLO': f"PROT-{date.today().strftime('%Y%m%d')}-001",
                'HASH_DOCUMENTO': 'a'*64,
                'URL_VALIDACAO': 'https://solivia.com.br/validar',
                'GERACAO_ORIGINAL': geracao_original,
                'GERACAO_OTIMIZADA': geracao_otimizada,
                'QTD_MODULOS': qtd_modulos,
                'POTENCIA_INVERSOR': potencia_inversor,
                'LOCAL_INVERSOR': local_inversor,
                'OBSERVACOES': observacoes
            }

            html_content = Template(template_fast_track).render(dados_template)

        else:
            return jsonify({'error': 'Tipo de relatório inválido'}), 400

        # Gerar PDF
        pdf_bytes = HTML(string=html_content).write_pdf()

        # Salvar no Google Drive via Apps Script
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8')
        nome_arquivo = f"Relatorio_VT_{nome_cliente}_{date.today().strftime('%Y%m%d')}.pdf"
        payload = {
            'token': TOKEN,
            'acao': 'salvar_pdf',
            'dados': {
                'nome_cliente': nome_cliente or 'cliente',
                'pdf_base64': pdf_base64,
                'nome_arquivo': nome_arquivo
            }
        }

        response = requests.post(APPS_SCRIPT_URL, json=payload)
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return jsonify({'success': True, 'url': result.get('url'), 'message': 'Relatório salvo com sucesso'})
            else:
                return jsonify({'success': False, 'error': result.get('error', 'Erro ao salvar no Drive')}), 500
        else:
            return jsonify({'success': False, 'error': f'Erro ao comunicar com o Apps Script: {response.status_code}'}), 500

    except Exception as e:
        print(f"❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ============================================================
# ROTA: PING
# ============================================================
@app.route('/ping', methods=['GET'])
def ping():
    return {'status': 'ok', 'message': 'SoLivia Engenharia - Gerador de Propostas e Relatórios'}

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
