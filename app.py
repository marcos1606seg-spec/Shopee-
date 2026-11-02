import streamlit as st
import pandas as pd
import json
import sqlite3
import bcrypt
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# 1. CONEXÃO COM A API DE IA (GEMINI)
# -----------------------------------------------------------------------------
try:
    client = genai.Client()
    api_disponivel = True
except Exception:
    api_disponivel = False

st.set_page_config(page_title="Caçador de Margens Shopee", layout="wide", page_icon="🛍️")

# -----------------------------------------------------------------------------
# 2. ESTRUTURAÇÃO DO BANCO DE DADOS PERMANENTE (SQLITE)
# -----------------------------------------------------------------------------
def conectar_banco():
    conn = sqlite3.connect('cacador_margens.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            senha_hash TEXT NOT NULL,
            custo_embalagem REAL DEFAULT 2.00,
            frete_entrada REAL DEFAULT 1.00,
            frete_gratis INTEGER DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos_fornecedor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            custo REAL NOT NULL,
            preco_shopee_mercado REAL NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
        )
    """)
    conn.commit()
    return conn

# Inicialização imediata das tabelas
conectar_banco().close()

# -----------------------------------------------------------------------------
# 3. CONTROLADORES E LOGICA DE NEGÓCIO
# -----------------------------------------------------------------------------
def criar_usuario(email, senha):
    conn = conectar_banco()
    cursor = conn.cursor()
    senha_hash = bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    try:
        cursor.execute("INSERT INTO usuarios (email, senha_hash) VALUES (?, ?)", (email, senha_hash))
        conn.commit()
        cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
        user_id = cursor.fetchone()[0]
        
        # Carga padrão de dados de demonstração para novos usuários
        produtos_originais = [
            (user_id, "Garrafa Térmica Inox 500ml", "Cozinha e Utensílios", 18.00, 39.90),
            (user_id, "Fone de Ouvido Bluetooth Y50", "Eletrônicos", 22.50, 49.99),
            (user_id, "Organizador de Maquiagem Acrílico", "Beleza e Cosméticos", 14.00, 29.90),
            (user_id, "Cabo USB-C Turbo 2 Metros", "Celulares e Acessórios", 8.00, 14.90),
            (user_id, "Suporte de Celular Automotivo Magnético", "Automotivo", 9.50, 24.90)
        ]
        cursor.executemany("""
            INSERT INTO produtos_fornecedor (usuario_id, nome, categoria, custo, preco_shopee_mercado)
            VALUES (?, ?, ?, ?, ?)
        """, produtos_originais)
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def verificar_login(email, senha):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT id, senha_hash FROM usuarios WHERE email = ?", (email,))
    resultado = cursor.fetchone()
    conn.close()
    if resultado and bcrypt.checkpw(senha.encode('utf-8'), resultado[1].encode('utf-8')):
        return resultado[0]
    return None

def salvar_configuracoes_usuario(user_id, custo_emb, frete_ent, frete_gratis):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE usuarios SET custo_embalagem = ?, frete_entrada = ?, frete_gratis = ? WHERE id = ?
    """, (custo_emb, frete_ent, 1 if frete_gratis else 0, user_id))
    conn.commit()
    conn.close()

def carregar_configuracoes_usuario(user_id):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("SELECT custo_embalagem, frete_entrada, frete_gratis, email FROM usuarios WHERE id = ?", (user_id,))
    resultado = cursor.fetchone()
    conn.close()
    return resultado

def carregar_produtos_usuario(user_id):
    conn = conectar_banco()
    df = pd.read_sql_query("SELECT * FROM produtos_fornecedor WHERE usuario_id = ?", conn, params=(user_id,))
    conn.close()
    return df.to_dict(orient='records')

def inserir_produto_usuario(user_id, nome, categoria, custo, preco_shopee):
    conn = conectar_banco()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO produtos_fornecedor (usuario_id, nome, categoria, custo, preco_shopee_mercado)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, nome, categoria, custo, preco_shopee))
    conn.commit()
    conn.close()

def chamar_ia_gerar_anuncio(nome_produto, categoria, preco_venda):
    if not api_disponivel:
        return {
            "titulo_seo": f"{nome_produto} Pronta Entrega Envio Rápido Nfe",
            "descricao_estrategica": f"Compre agora seu {nome_produto}! Estoque disponível no Brasil com envio imediato em até 24h úteis. Produto de alta qualidade na categoria {categoria} por apenas R$ {preco_venda}."
        }
    prompt = f"Gere um anúncio de alta conversão para a Shopee do produto '{nome_produto}' da categoria '{categoria}' vendido por R$ {preco_venda}. Retorne estritamente em JSON válido com as chaves 'titulo_seo' e 'descricao_estrategica'."
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
        )
        return json.loads(response.text)
    except Exception as e:
        return {"titulo_seo": "Erro na Geração", "descricao_estrategica": f"Falha na API: {str(e)}"}

# -----------------------------------------------------------------------------
# 4. CONTROLE DE INTERFACE GRAFICA (STREAMLIT)
# -----------------------------------------------------------------------------
if 'logado' not in st.session_state:
    st.session_state.logado = False
if 'usuario_id' not in st.session_state:
    st.session_state.usuario_id = None

# TELA 1: AUTENTICAÇÃO DE SEGURANÇA
if not st.session_state.logado:
    st.title("🛍️ Acesso ao Sistema - Inteligência Operacional Shopee")
    tab_log, tab_cad = st.tabs(["🔐 Entrar", "📝 Cadastrar"])
    
    with tab_log:
        with st.form("f_login"):
            em_log = st.text_input("E-mail:")
            se_log = st.text_input("Senha:", type="password")
            if st.form_submit_button("Entrar no Painel"):
                uid = verificar_login(em_log, se_log)
                if uid:
                    st.session_state.logado = True
                    st.session_state.usuario_id = uid
                    st.rerun()
                else:
                    st.error("Credenciais inválidas.")

    with tab_cad:
        with st.form("f_cad"):
            em_cad = st.text_input("Definir E-mail:")
            se_cad = st.text_input("Definir Senha (mínimo 6 caracteres):", type="password")
            if st.form_submit_button("Confirmar Cadastro Permanente"):
                if em_cad and len(se_cad) >= 6:
                    if criar_usuario(em_cad, se_cad):
                        st.success("Conta configurada! Faça o login na aba ao lado.")
                    else:
                        st.error("E-mail já registrado.")
                else:
                    st.error("Insira dados válidos.")

# TELA 2: DASHBOARD OPERACIONAL COMPLETO
else:
    uid = st.session_state.usuario_id
    c_emb, f_ent, f_gratis, email_user = carregar_configuracoes_usuario(uid)
    
    # Barra lateral de controle
    st.sidebar.markdown(f"👤 Operador: **{email_user}**")
    if st.sidebar.button("🚪 Sair do App"):
        st.session_state.logado = False
        st.session_state.usuario_id = None
        st.rerun()
        
    st.sidebar.divider()
    st.sidebar.header("⚙️ Variáveis de Custo")
    custo_emb_atual = st.sidebar.number_input("Custo de Embalagem (R$)", value=float(c_emb), step=0.5)
    frete_ent_atual = st.sidebar.number_input("Frete de Entrada (R$)", value=float(f_ent), step=0.5)
    gratis_atual = st.sidebar.checkbox("Programa Frete Grátis (+6% Taxa)", value=bool(f_gratis))
    
    salvar_configuracoes_usuario(uid, custo_emb_atual, frete_ent_atual, gratis_atual)
    
    taxa_shopee = 0.20 if gratis_atual else 0.14
    TAXA_FIXA = 4.00
    LUCRO_CORTE = 0.10
    
    st.sidebar.divider()
    st.sidebar.subheader("➕ Adicionar Produto")
    with st.sidebar.form("f_add", clear_on_submit=True):
        n_p = st.text_input("Nome:")
        c_p = str(st.selectbox("Categoria:", ["Eletrônicos", "Cozinha e Utensílios", "Beleza e Cosméticos", "Celulares e Acessórios", "Automotivo", "Outros"]))
        cust_p = st.number_input("Custo Fornecedor (R$):", min_value=0.0, step=1.0)
        merc_p = st.number_input("Preço Shopee (R$):", min_value=0.0, step=1.0)
        if st.form_submit_button("Cadastrar"):
            if n_p and cust_p > 0 and merc_p > 0:
                inserir_produto_usuario(uid, n_p, c_p, cust_p, merc_p)
                st.rerun()

    st.sidebar.divider()
    st.sidebar.subheader("📁 Importar Lote (CSV)")
    csv_file = st.sidebar.file_uploader("Arquivo CSV (delimitador ';'):", type=["csv"])
    if csv_file is not None:
        try:
            df = pd.read_csv(csv_file, sep=";")
            if {"nome", "categoria", "custo", "preco_shopee_mercado"}.issubset(df.columns):
                for _, r in df.iterrows():
                    inserir_produto_usuario(uid, str(r["nome"]), str(r["categoria"]), float(r["custo"]), float(r["preco_shopee_mercado"]))
                st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erro: {e}")

    # Processamento logístico matemático
    