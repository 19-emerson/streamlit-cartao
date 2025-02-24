from __future__ import print_function
import os
import json
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import pickle
import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_option_menu import option_menu
from numerize.numerize import numerize
import numpy as np
import datetime

dotenv_path = os.path.join(os.getcwd(), ".env")
load_dotenv(dotenv_path, override=True)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SAMPLE_SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CLIENT_SECRETS_PATH = os.getenv("CLIENT_SECRETS_PATH", ".secrets/client_secrets.json")
TOKEN_PATH = 'token.json'

if not os.path.exists(CLIENT_SECRETS_PATH):
    st.error("Erro: CLIENT_SECRETS_PATH não foi encontrado.")
    CLIENT_SECRETS_JSON = None
else:
    with open(CLIENT_SECRETS_PATH, "r") as f:
        CLIENT_SECRETS_JSON = f.read()

# Função para obter credenciais do Google

def obter_credenciais():
    creds = None
    
    # Verifica se o token já existe e está válido
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    # Se não houver credenciais válidas, inicia a autenticação
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            try:
                client_secrets = json.loads(CLIENT_SECRETS_JSON)
            except json.JSONDecodeError:
                st.error("Erro ao carregar as credenciais do Google.")
                return None
            
            flow = InstalledAppFlow.from_client_config(client_secrets, SCOPES)
            creds = flow.run_local_server(port=0)
            
            # Salva as credenciais obtidas
            with open(TOKEN_PATH, "w") as token:
                token.write(creds.to_json())
    
    return creds

def main():
    creds = obter_credenciais()
    if not creds:
        return
    
    try:
        service = build("sheets", "v4", credentials=creds)
        sheet = service.spreadsheets()

        # Buscar valores na planilha
        result_mes = sheet.values().get(
            spreadsheetId=SAMPLE_SPREADSHEET_ID, 
            range='Fev'
        ).execute()
        valores_mes = result_mes.get("values", [])

        result_diario = sheet.values().get(
            spreadsheetId=SAMPLE_SPREADSHEET_ID, 
            range='DIÁRIO!C7:K21'
        ).execute()
        valores_diario = result_diario.get("values", [])

        if valores_mes:
            st.cache_data.clear()
            df = pd.DataFrame(valores_mes[1:], columns=valores_mes[0])
            print("Colunas disponíveis:", df.columns.tolist())

            dias_passados = int(df.loc[0, 'Ajuda'])
            dias_uteis = int(df.loc[1, 'Ajuda'])
            dias_restante = int(df.loc[2, 'Ajuda'])
            df['Resultado_Status'] = df['Status'].apply(lambda x: 'ACEITE' if x in ['PAGO', 'AG. INSS', 'BLOQUEADO'] else 'PEND. ACEITE')

            df_selection = df[df["Status"].isin(["PAGO", "AG. INSS", "BLOQUEADO", "PENDENTE", "CANCELADO"])]
            df_selection['Valor'] = df_selection['Valor'].str.replace('R$ ', '').str.replace('.', '').str.replace(',', '.').str.replace(' ', '')
            df_selection['Valor'] = pd.to_numeric(df_selection['Valor'], errors='coerce')
            df_selection['Valor'] = df_selection['Valor'].fillna(0)
            df_selection['Data'] = pd.to_datetime(df_selection['Data'], dayfirst=True, errors='coerce')
            data_corte = pd.to_datetime('2025-01-30')
            df_selection.loc[df_selection['Data'] <= data_corte, 'Data'] = pd.to_datetime('2025-01-31')
            data_min = df_selection['Data'].min().date()
            data_max = df_selection['Data'].max().date()

            pago_qtde_sem_saque = ((df_selection['Status'] == 'PAGO') & (df_selection['Produto'] == 'Cartão sem Saque')).sum()
            pago_qtde_com_saque = ((df_selection['Status'] == 'PAGO') & (df_selection['Produto'] == 'Cartão com Saque')).sum()
            ag_qtde_sem_saque = ((df_selection['Status'] == 'AG. INSS') & (df_selection['Produto'] == 'Cartão sem Saque')).sum()
            ag_qtde_com_saque = ((df_selection['Status'] == 'AG. INSS') & (df_selection['Produto'] == 'Cartão com Saque')).sum()
            bloqueado_qtde_sem_saque = ((df_selection['Status'] == 'BLOQUEADO') & (df_selection['Produto'] == 'Cartão sem Saque')).sum()
            bloqueado_qtde_com_saque = ((df_selection['Status'] == 'BLOQUEADO') & (df_selection['Produto'] == 'Cartão com Saque')).sum()       

            soma_cartao_pago = df_selection[(df_selection['Status'] == 'PAGO') & (df_selection['Produto'] == 'Cartão com Saque')]['Valor'].sum()
            soma_cartao_aguardando = df_selection[(df_selection['Status'] == 'PAGO') & (df_selection['Produto'] == 'Cartão com Saque')]['Valor'].sum()
            soma_cartao_bloqueado = df_selection[(df_selection['Status'] == 'BLOQUEADO') & (df_selection['Produto'] == 'Cartão com Saque')]['Valor'].sum()
            soma_novo_pago = df_selection[(df_selection['Status'] == 'PAGO_') & (df_selection['Produto'] == 'Margem Livre')]['Valor'].sum()
            soma_saque_pago = df_selection[(df_selection['Status'] == 'PAGO_') & (df_selection['Produto'] == 'Saque Complementar')]['Valor'].sum()
            soma_novo_aguardando = df_selection[(df_selection['Status'] == 'AG. INSS_') & (df_selection['Produto'] == 'Margem Livre')]['Valor'].sum()
            soma_saque_aguardando = df_selection[(df_selection['Status'] == 'AG. INSS_') & (df_selection['Produto'] == 'Saque Complementar')]['Valor'].sum()

            total_emitido = pago_qtde_sem_saque + pago_qtde_com_saque
            total_saque_autorizado = soma_cartao_pago
            total_saque_complementar = soma_saque_pago
            total_novo = soma_novo_pago

            cms_total_emitido = total_emitido * 300
            cms_total_saque_autorizado = total_saque_autorizado * 0.1
            cms_total_saque_complementar = total_saque_complementar * 0.1
            cms_total_novo = total_novo * 0.07
            cms_subtotal1 = cms_total_emitido+ cms_total_saque_autorizado + cms_total_saque_complementar + cms_total_novo

            aguardando_emissao = ag_qtde_sem_saque + ag_qtde_com_saque
            aguardando_saque_autorizado = soma_cartao_aguardando
            aguardando_desbloquear_emissao = bloqueado_qtde_sem_saque + bloqueado_qtde_com_saque
            aguardando_desbloquear_saque_autorizado = soma_cartao_bloqueado
            aguardando_saque_complementar = soma_saque_aguardando
            aguardando_novo = soma_novo_aguardando
            expectativa_ativacao = total_emitido * 0.2

            cms_aguardando_emissao = aguardando_emissao * 300
            cms_aguardando_saque_autorizado = aguardando_saque_autorizado * 0.1
            cms_aguardando_desbloquear_emissao = aguardando_desbloquear_emissao * 300
            cms_aguardando_desbloquear_saque_autorizado = aguardando_desbloquear_saque_autorizado * 0.1
            cms_aguardando_saque_complementar = aguardando_saque_complementar * 0.1
            cms_aguardando_novo = aguardando_novo * 0.07
            cms_expectativa_ativacao = expectativa_ativacao * 100
            cms_subtotal2 = (
                cms_aguardando_emissao + cms_aguardando_saque_autorizado +
                cms_aguardando_desbloquear_emissao + cms_aguardando_desbloquear_saque_autorizado +
                cms_aguardando_saque_complementar + cms_aguardando_novo + cms_expectativa_ativacao
            )
            total = cms_subtotal1 + cms_subtotal2

            projecao_receita_bruta = total
            imposto = total * -0.16
            premiacao_funcionario = total * -0.15 
            campanha = -500
            despesas_adm = -18535
            despesas_pessoal = -51782
            desbloqueio_beneficio = -1805 -2436 -570 -285 -522 -7650

            projecao_receita_liquida = (
                total + imposto + premiacao_funcionario + campanha +
                despesas_adm + despesas_pessoal + desbloqueio_beneficio
            )
            projecao_receita_liquida = f'{projecao_receita_liquida:,.0f}'.replace(",", "X").replace(".", ",").replace("X", ".")

            def painel_custo():
              st.write('')
              st.write('')
              st.write('')
              data = {
                  "PROJEÇÕES": [
                      "Emitido", "Saque autorizado", "Saque complementar", "Consignado", "Ativado", 
                      "Subtotal¹", "Aguardando averbação - Emissão", "Aguardando averbação - Saque autorizado",
                      "Bloqueado: Aguardando averbação - Emissão", "Bloqueado: Aguardando averbação - Saque autorizado", 
                      "Aguardando averbação - Saque complementar", "Aguardando averbação - Consignado",
                      "Expectativa de ativação", "Subtotal²", "TOTAL"
                  ],
                  "Qtde/Valor": [
                      total_emitido, total_saque_autorizado, total_saque_complementar, total_novo, 0, '',
                      aguardando_emissao, aguardando_saque_autorizado, aguardando_desbloquear_emissao,
                      aguardando_desbloquear_saque_autorizado, aguardando_saque_complementar, aguardando_novo,
                      expectativa_ativacao, '', ''
                  ],
                  "Cms": [
                      cms_total_emitido, cms_total_saque_autorizado, cms_total_saque_complementar, cms_total_novo, 0,
                      cms_subtotal1,
                      cms_aguardando_emissao, cms_aguardando_saque_autorizado, cms_aguardando_desbloquear_emissao,
                      cms_aguardando_desbloquear_saque_autorizado, cms_aguardando_saque_complementar, cms_aguardando_novo,
                      cms_expectativa_ativacao, cms_subtotal2, total
                  ],
                  "% referência": [
                      "R$ 300", "10%", "10%", "7%", "20%", "", # <-- subtotal¹
                      "R$ 300", "10%", "R$ 300", "10%", "10%", "7%", "20%", "", # <-- subtotal²
                      ""  # <-- TOTAL
                  ]
              }

              data2 = {
                  'DEDUÇÃO DE CUSTOS E DESPESAS': [
                      'PROJEÇÃO DE RECEITA BRUTA', 'IMPOSTO', 'PREMIAÇÃO FUNCIONÁRIO', 'CAMPANHAS', 'DESPESAS ADMINISTRATIVAS',
                      'DESPESAS COM PESSOAL', 'DISPAROS SMS', 'DISPAROS WHATSAPP', 'DESBLOQUEIO BENEFÍCIO'
                  ],
                  'Valor': [
                      projecao_receita_bruta, imposto, premiacao_funcionario, campanha, despesas_adm, despesas_pessoal, 0, 0, desbloqueio_beneficio
                  ],
                  "% referência": [
                      "", "16%", "15%", "", "", "", "", "", ""
                  ]
              }

              custo = pd.DataFrame(data)
              receita = pd.DataFrame(data2)
              colunas_numericas = ["Qtde/Valor", "Cms"]
              custo[colunas_numericas] = custo[colunas_numericas].apply(pd.to_numeric, errors='coerce')
              custo[colunas_numericas] = custo[colunas_numericas].applymap(
                  lambda x: f"{x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
              )

              coluna_numerica = ["Valor"]
              receita[coluna_numerica] = receita[coluna_numerica].apply(pd.to_numeric, errors='coerce')
              receita[coluna_numerica] = receita[coluna_numerica].applymap(
                  lambda x: f"{x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".") if pd.notna(x) else ""
              )

              st.markdown("<h3 style='text-align: center;'>📊 PROJEÇÃO DE RESULTADO</h3>", unsafe_allow_html=True)
              st.dataframe(custo, use_container_width=True, height=562, hide_index=True)
              st.dataframe(receita, use_container_width=True, hide_index=True)

              st.markdown("""
                  <style>
                      .info-box {
                          background-color: #e6f3ff;  /* Cor de fundo azul claro */
                          padding: 12px 20px;  /* Espaçamento interno */
                          border-radius: 8px;  /* Bordas arredondadas */
                          color: #000;  /* Cor do texto */
                          font-size: 16px;  /* Tamanho da fonte */
                          font-weight: bold;  /* Texto em negrito */
                          text-align: center;  /* Centralização do texto */
                          display: flex;
                          align-items: center;
                          justify-content: center;
                          position: relative;
                      }
                      .info-box::before {
                          content: "";
                          position: absolute;
                          left: 0;
                          width: 6px;  /* Largura da faixa azul */
                          height: 100%;
                          background-color: #007bff;  /* Azul forte */
                          border-top-left-radius: 8px;
                          border-bottom-left-radius: 8px;
                      }
                  </style>
              """, unsafe_allow_html=True)

              st.markdown(F'<div class="info-box">PROJEÇÃO DE RECEITA LÍQUIDA: R$ {projecao_receita_liquida}</div>', unsafe_allow_html=True)

            st.set_page_config(page_title="Painel de Vendas", page_icon="🌍", layout="wide")
            st.markdown("""
                <style>
                    [data-testid="stSidebar"] {
                        background-color: #FEF8F4;
                        width: 256px !important;
                    }
                </style>
            """, unsafe_allow_html=True)

            st.sidebar.image("Sorfcred.png", caption="Call Center")

            def sidebar_data():
              if not df_selection['Data'].isna().all():
                data_min = df_selection['Data'].min().date()
                data_max = df_selection['Data'].max().date()
              else:
                st.error('Nenhuma data valida encontrada no DF')
                data_min = datetime.date.today()
                data_max = datetime.date.today()

              st.sidebar.header('Filtrar por período')
              data_inicial = st.sidebar.date_input('Data inicial', data_min, format='DD/MM/YYYY', help='Propostas com data de 31/01/2025 vieram do estoque de Janeiro.')
              data_final = st.sidebar.date_input('Data final', data_max, format='DD/MM/YYYY')

              st.session_state.data = (data_inicial, data_final)
              df_filtrado = df_selection[(df_selection['Data'].dt.date >= data_inicial) & (df_selection['Data'].dt.date <= data_final)]
              st.sidebar.write("")

            def sidebar_filtros():

                st.sidebar.header('Filtrar por status')
                status = st.sidebar.multiselect(
                    'Selecione o status',
                    options=df['Status'].unique(),
                    default=df['Status'].unique()
                )

                st.session_state.status = status
                st.sidebar.write("")

            def sidebar_origem():
                st.sidebar.header('Filtrar por origem')
                origem = st.sidebar.multiselect(
                    'Selecione a origem',
                    options=df['Origem'].unique(),
                    default=df['Origem'].unique()
                )

                st.session_state.origem = origem
                st.sidebar.write("")

            def sidebar_parceiros():
                st.sidebar.write("")
                st.sidebar.write("")
                st.sidebar.markdown('**Parceiros**')

                col1, col2, col3 = st.sidebar.columns(3)
                col1.image("bmg.png", width=60)
                col2.image("amigoz.jpg", width=60)
                col3.image("facta.png", width=60)

            def Home1():
                total_pago = df_selection[df_selection['Status'] == 'PAGO'].shape[0]
                total_aguardando = df_selection[df_selection['Status'] == 'AG. INSS'].shape[0]
                total_projetado = int(round(((total_pago + total_aguardando) / dias_passados) * dias_uteis))
                total_meta = sum([60,	45,	45,	60,	45,	20,	20,	30,	20,	20,	30,	30,	7, 0])
                total_atingimento = (total_projetado / total_meta) * 100
                total_atingimento = str(int(round(total_atingimento))) + '%'
                total_valor = df_selection[df_selection['Status'] == 'PAGO']['Valor'].sum()
                total_bloqueado = df_selection[df_selection['Status'] == 'BLOQUEADO'].shape[0]
                total_pendente = df_selection[
                    (df_selection['Status'] == 'PENDENTE') & (df_selection['Perfil'] == 'ATUAL')
                ].shape[0] + df_selection[
                    (df_selection['Status'] == 'CANCELADO')
                ].shape[0]
                total_conversao = ((total_pago + total_aguardando + total_bloqueado) / (total_pago + total_aguardando + total_bloqueado + total_pendente)) * 100
                total_conversao = str(int(round(total_conversao))) + '%'

                col1, col2, col3, col4 = st.columns(4, gap='medium')
                with col1:
                    st.info(f'{total_pago}')
                    st.markdown('<p style="font-size:18px; color:gray;">💳 Pago</p>', unsafe_allow_html=True)

                with col2:
                    st.info(f'{total_aguardando}')
                    st.markdown('<p style="font-size:18px; color:gray;">⏳ Ag. Inss</p>', unsafe_allow_html=True)

                with col3:
                    st.info(f'{total_projetado:,.0f}')
                    st.markdown('<p style="font-size:18px; color:gray;">📊 Projeção</p>', unsafe_allow_html=True)

                with col4:
                    st.info(f'{total_atingimento}')
                    st.markdown('<p style="font-size:18px; color:gray;">🎯 Proj. de Atingimento</p>', unsafe_allow_html=True)

                col5, col6, col7, col8 = st.columns(4, gap='medium')
                with col5:
                    st.info(f'R$ {total_valor:,.0f}')
                    st.markdown('<p style="font-size:18px; color:gray;">💰 Valor Pago</p>', unsafe_allow_html=True)

                with col6:
                    st.info(f'{total_bloqueado}')
                    st.markdown('<p style="font-size:18px; color:gray;">🚫 Bloqueado</p>', unsafe_allow_html=True)

                with col7:
                    st.info(f'{total_conversao}')
                    st.markdown('<p style="font-size:18px; color:gray;">📉 Conv. sobre digitação</p>', unsafe_allow_html=True)

                with col8:
                    st.info(f'{total_pendente}')
                    st.markdown('<p style="font-size:18px; color:gray;">🛒 Pendente</p>', unsafe_allow_html=True)

                    st.markdown("""---""")

            Home1()

            def painel_mensal():
                dados_vendedores = {
                    'Vendedor': [
                    'ROSIMERY', 'ELLEN', 'ISABEL', 'ANTONIO', 'DANILO', 'DANIEL', 'VICTOR SILVA',
                    'VICTOR', 'CALL CENTER - SAIU', 'LARISSA', 'JOAO', 'ANNA', 'CALL CENTER - TESTE'
                    ],
                    'Meta Cartões': [
                      60, 45, 60, 45, 45, 20, 20, 20, 20, 30, 30, 20, 0
                    ],
                    'Meta Saque': [
                      20000, 15000, 20000, 15000, 15000, 0, 0, 0, 0, 0, 0, 0, 0
                    ],
                    'Início': [
                    '14/08/2024', '08/01/2025', '26/08/2024', '09/01/2025', '09/01/2025', '04/12/2024',
                    '06/11/2024', '09/10/2024', '-', '04/02/2024', '04/02/2024', '04/12/2024', '-'
                    ]
                }
                df_vendedores = pd.DataFrame(dados_vendedores)
                
                painel = df.groupby('Vendedor').agg(
                    Pago=('Status', lambda x: (x == 'PAGO').sum()),
                    Ag_Inss=('Status', lambda x: (x == 'AG. INSS').sum()),
                    Valor_Pago=('Valor', lambda x: pd.to_numeric(df.loc[x.index, 'Valor'], errors='coerce').fillna(0).sum()),
                    Bloqueado=('Status', lambda x: (x == 'BLOQUEADO').sum()),
                    Pendente=('Status', lambda x: ((df.loc[x.index, 'Perfil'] == 'ATUAL') & (x.isin(['PENDENTE']))).sum() + (x == 'CANCELADO').sum())
                ).reset_index()

                painel = painel.merge(df_vendedores, on='Vendedor', how='left')

                painel['Digitado'] = painel['Pago'] + painel['Ag_Inss'] + painel['Bloqueado'] + painel['Pendente']
                painel['Conversão'] = ((painel['Pago'] + painel['Ag_Inss'] + painel['Bloqueado']) / painel['Digitado']) * 100
                painel['Conversão'] = painel['Conversão'].fillna(0).replace([float('inf'), -float('inf')], 0).round().astype(int).astype(str) + '%'
                painel['Projetado'] = (((painel['Pago'] + painel['Ag_Inss']) / dias_passados) * dias_uteis).round().astype(int)
                painel['Proj. Ating.'] = (painel['Projetado'] / painel['Meta Cartões']) * 100
                painel['Proj. Ating.'] = painel['Proj. Ating.'].fillna(0).replace([float('inf'), -float('inf')], 0).round().astype(int).astype(str) + '%'
                painel['Meta Saque'] = painel['Meta Saque'].fillna(0).round().astype(int)
                painel['Meta Saque'] = painel['Meta Saque'].apply(lambda x: f'R$ {x:,}'.replace(',', '.'))

                painel['Soma'] = painel['Pago'] + painel['Ag_Inss']
                painel = painel.sort_values(by='Soma', ascending=False)
                painel = painel.drop(columns=['Soma'])

                total = painel[['Meta Cartões', 'Meta Saque', 'Projetado', 'Digitado', 'Pago', 'Ag_Inss', 'Valor_Pago', 'Bloqueado', 'Pendente']].sum()
                total['Vendedor'] = 'Total'
                total['Conversão'] = (total['Pago'] + total['Ag_Inss'] + total['Bloqueado']) / total['Digitado'] * 100
                total['Conversão'] = str(int(round(total['Conversão']))) + '%'
                total['Proj. Ating.'] = (total['Projetado'] / total['Meta Cartões']) * 100
                total['Proj. Ating.'] = str(int(round(total['Proj. Ating.']))) + '%'
                total['Projetado'] = int(round(painel['Projetado'].sum()))
                total['Meta Saque'] = f'R$ {painel['Meta Saque'].str.replace("R$ ", "").str.replace(".", "").round().astype(int).sum():,}'.replace(',', '.')

                painel = pd.concat([painel, total.to_frame().T], ignore_index=True)
                painel = painel.reindex(columns=['Vendedor', 'Meta Cartões', 'Meta Saque', 'Projetado',	'Proj. Ating.', 'Digitado', 'Pago', 'Ag_Inss', 'Valor_Pago', 'Bloqueado', 'Conversão', 'Pendente'])
                painel = painel.reset_index(drop=True)

          #      st.subheader("📌 PAINEL MENSAL")
                st.markdown("<h3 style='text-align: center;'>📌 PAINEL MENSAL</h3>", unsafe_allow_html=True)
          #      st.markdown("##")
                st.dataframe(painel, use_container_width=True, height=528, hide_index=True)

                st.markdown("""
                      <p style="text-align: center; font-size: 16px; font-weight: bold;">
                          A atualização do painel ocorre às 9h
                      </p>
                  """, unsafe_allow_html=True)
                st.write("")

                painel_sem_total = painel[~painel['Vendedor'].isin(['Total', 'CALL CENTER - SAIU', 'CALL CENTER - TESTE'])]
                painel_sem_total['Total_Aceites'] = painel_sem_total[['Pago', 'Ag_Inss', 'Bloqueado']].sum(axis=1)
                mais_aceites_vendedor = painel_sem_total.loc[painel_sem_total['Total_Aceites'].idxmax(), 'Vendedor']
                mais_aceites_qtde = painel_sem_total['Total_Aceites'].max()

                vendedores_ordenados = painel_sem_total.sort_values(by='Total_Aceites', ascending=False)
                vendedores_com_aceites_validos = vendedores_ordenados[vendedores_ordenados['Total_Aceites'] >= (dias_passados * 2)]

                if not vendedores_com_aceites_validos.empty:
                    melhor_conversao_idx = vendedores_com_aceites_validos['Conversão'].str.replace('%', '').round().astype(int).idxmax()
                else:
                    melhor_conversao_idx = painel_sem_total['Conversão'].str.replace('%', '').round().astype(int).idxmax()

                melhor_conversao_vendedor = painel_sem_total.loc[melhor_conversao_idx, 'Vendedor']
                melhor_conversao_valor = painel_sem_total.loc[melhor_conversao_idx, 'Conversão']

                melhor_projecao_valor = painel_sem_total['Proj. Ating.'].str.replace('%', '').round().astype(int).max()
                melhor_projecao_vendedores = painel_sem_total[painel_sem_total['Proj. Ating.'].str.replace('%', '').round().astype(int) == melhor_projecao_valor]['Vendedor'].tolist()

                st.write("")
                quantidade_vendedores = painel_sem_total['Vendedor'].nunique()
                meta_dia = int(round((total['Meta Cartões'] - (total['Pago'] + total['Ag_Inss'])) / dias_restante))
                quantidade_por_vendedor = round(meta_dia / quantidade_vendedores, 2)
                st.markdown("""
                    <style>
                    .info-box {
                        background-color: #e0f3ff;
                        padding: 15px;
                        border-radius: 5px;
                        border-left: 6px solid #1f77b4;
                        text-align: center;
                        font-weight: bold;
                    }
                    </style>
                """, unsafe_allow_html=True)

                col1, col2 = st.columns(2, gap='medium')
                with col1:
                    st.markdown(f'<div class="info-box">Meta do dia: {meta_dia} cartões</div>', unsafe_allow_html=True)
                with col2:
                    st.markdown(f'<div class="info-box">Quantidade por vendedor: {quantidade_por_vendedor} cartões</div>', unsafe_allow_html=True)

                st.write("")
                st.write("")
                st.write("")
                st.write("")
                st.markdown("<p style='text-align: center; font-size: 20px;'><strong>🏆 Destaques do mês</strong></p>", unsafe_allow_html=True)
                if mais_aceites_qtde > 0:
                  st.markdown(f"<p style='text-align: center;<st>'>Maior quantidade de aceites: <strong>{mais_aceites_vendedor}</strong> com <strong>{mais_aceites_qtde}</strong> aceites</p>", unsafe_allow_html=True)
                else:
                  st.write('')
                if melhor_conversao_valor == '0%':
                  st.write('')
                else:
      #             st.markdown(f"<p style='text-align: center;'>Melhor conversão sobre digitação: <strong>{melhor_conversao_vendedor}</strong> com <strong>{melhor_conversao_valor}</strong> de conversão</p>", unsafe_allow_html=True)
                  st.markdown(f"""
                        <p style='text-align: center;'>
                            Melhor conversão sobre digitação: 
                            <strong>{melhor_conversao_vendedor}</strong> com 
                            <strong>{melhor_conversao_valor}</strong> de conversão
                            <span title="Considerado quem tem, no mínimo, média de 2 aceites dia" style="cursor: help; color: blue;">[?]</span>
                        </p>
                    """, unsafe_allow_html=True)
                if len(melhor_projecao_vendedores) > 1:
                  st.markdown(f"<p style='text-align: center;'>Maiores em projeção de atingimento sobre a meta: <strong>{', '.join(melhor_projecao_vendedores)}</strong> com <strong>{melhor_projecao_valor}%</strong> de projeção</p>", unsafe_allow_html=True)
                elif melhor_projecao_valor <= 0:
                  st.write('')
                else:
                  st.markdown(f"<p style='text-align: center;'>Maior projeção de atingimento sobre a meta: <strong>{melhor_projecao_vendedores[0]}</strong> com <strong>{melhor_projecao_valor}%</strong> de projeção</p>", unsafe_allow_html=True)

            st.write("")
            st.write("")

            st.write("")
      #      def graficos(df_filtrado):
            def graficos():
                st.write("")
                st.write("")
                st.write("")
                if 'resultado' not in st.session_state or st.session_state.resultado is None:
                  st.session_state.resultado = ['ACEITE', 'PEND. ACEITE']
                status = st.session_state.status
                origem = st.session_state.origem
                resultado = st.session_state.resultado
                data = st.session_state.data
                data_inicial, data_final = st.session_state.data
                df_filtrado = df_selection[(df_selection['Status'].isin(status)) &
                                          (df_selection['Origem'].isin(origem)) &
                                          (df_selection['Resultado_Status'].isin(resultado)) &
                                          (df_selection['Data'].dt.date) &
                                          (df_selection['Data'].dt.date >= data_inicial) &
                                          (df_selection['Data'].dt.date <= data_final)]
                if df_filtrado.empty:
                    st.warning("Nenhum dado disponível. Por favor, selecione algum status.")
                    return
                origem = df_filtrado['Origem'].value_counts().sort_values(ascending=True)
                produto = df_filtrado['Produto'].value_counts().sort_values(ascending=True)
                especie = df_filtrado['Espécie'].value_counts().sort_values(ascending=True)
                banco = df_filtrado['Banco'].value_counts().sort_values(ascending=True)
                resultado = df_filtrado['Resultado_Status'].value_counts()
                data_resultado_count = df_filtrado.groupby(['Data', 'Resultado_Status']).size().reset_index(name='Quantidade')

                fig_produto = px.bar(
                    x=produto.values,
                    y=produto.index,
                    orientation='h',
                    title='<b>Distribuição por:  Produto</b>',
                    color_discrete_sequence=['#FFC000'] * len(produto),
                    template='plotly_white'
                )

                fig_produto.update_layout(
                    plot_bgcolor='rgba(0, 0, 0, 0)',
                    xaxis=dict(showgrid=False, title='', showticklabels=False),
                    yaxis=dict(title='')
                )

                fig_origem = px.bar(
                    x=origem.values,
                    y=origem.index,
                    orientation='h',
                    title='<b>                    Origem</b>',
                    color_discrete_sequence=['#FFC000'] * len(origem),
                    template='plotly_white'
                )

                fig_origem.update_layout(
                    plot_bgcolor='rgba(0, 0, 0, 0)',
                    xaxis=dict(showgrid=False, title='', showticklabels=False),
                    yaxis=dict(title=''),
                    xaxis_title='Quantidade Vendas'
                )

                fig_especie = px.bar(
                    x=especie.values,
                    y=especie.index,
                    orientation='h',
                    title='<b>                    Espécie</b>',
                    color_discrete_sequence=['#FFC000'] * len(especie),
                    template='plotly_white'
                )

                fig_especie.update_layout(
                    plot_bgcolor='rgba(0, 0, 0, 0)',
                    xaxis=dict(showgrid=False, title='', showticklabels=False),
                    yaxis=dict(title='')
                )

                fig_banco = px.bar(
                    x=banco.values,
                    y=banco.index,
                    orientation='h',
                    title='<b>                    Banco</b>',
                    color=banco.index,
                    color_discrete_map={
                      'BMG': '#FFC000',
                      'Pine': '#D9E1F2',
                      'FACTA': '#305496',
                    },
                    template='plotly_white'
                )

                fig_banco.update_layout(
                    plot_bgcolor='rgba(0, 0, 0, 0)',
                    xaxis=dict(showgrid=False, title='', showticklabels=False),
                    yaxis=dict(title='')
                )

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                  st.plotly_chart(fig_produto, use_container_width=True)
                with col2:
                  st.plotly_chart(fig_origem, use_container_width=True)
                with col3:
                  st.plotly_chart(fig_especie, use_container_width=True)
                with col4:
                  st.plotly_chart(fig_banco, use_container_width=True)

                fig_resultado = px.bar(
                    data_resultado_count,
                    x='Data',
                    y='Quantidade',
                    color='Resultado_Status',
                    title='<b>Acompanhamento de aceite diário</b>',
                    template='plotly_white',
                    #color_discrete_sequence=px.colors.qualitative.Set1
                    color_discrete_map={
                      'ACEITE': '#A9D08E',
                      'PEND. ACEITE': '#FF7D7D',
                    },
                )

                fig_resultado.update_layout(
                    xaxis=dict(
                        showgrid=False,
                        title='Quantidade de Vendas',
                        tickmode='array',
                        tickvals=data_resultado_count['Data'].unique(),
                        tickformat='%b %d'
                    ),
                    yaxis=dict(
                        title='',
                        showgrid=False,
                        zeroline=False,
                        gridcolor='rgba(0,0,0,0)'
                    ),
                    plot_bgcolor='rgba(0, 0, 0, 0)'
                )
                st.plotly_chart(fig_resultado, use_container_width=True)
              
                df_filtrado = df[df['Status'].isin(status)]
                df_filtrado = df_filtrado[df_filtrado['Origem'].isin(['DISCADOR', 'URA', 'INDICAÇÃO', 'SMS', 'REVERSAO', 'REDE'])]
                df_filtrado = df_filtrado[df_filtrado['Produto'].isin(['Cartão sem Saque', 'Cartão com Saque', 'Margem Livre', 'Saque Complementar'])]

            def aceite_diario():
                st.write("")
                st.write("")
                st.write("")
                if 'resultado' not in st.session_state or st.session_state.resultado is None:
                  st.session_state.resultado = ['ACEITE', 'PEND. ACEITE']
                resultado = st.session_state.resultado
                df_filtrado = df_selection[(df_selection['Resultado_Status'].isin(resultado)) &
                                          (df_selection['Data'].dt.date)]

      #          data = st.session_state.data
      #          resultado = df_filtrado['Resultado_Status'].value_counts()
                data_resultado_count = df_filtrado.groupby(['Data', 'Resultado_Status']).size().reset_index(name='Quantidade')

                fig_resultado = px.bar(
                    data_resultado_count,
                    x='Data',
                    y='Quantidade',
                    color='Resultado_Status',
                    title='<b>Acompanhamento de aceite diário</b>',
                    template='plotly_white',
                    #color_discrete_sequence=px.colors.qualitative.Set1
                    color_discrete_map={
                      'ACEITE': '#A9D08E',
                      'PEND. ACEITE': '#FF7D7D',
                    },
                )

                fig_resultado.update_layout(
                    xaxis=dict(
                        showgrid=False,
                        title='Quantidade de Vendas',
                        tickmode='array',
                        tickvals=data_resultado_count['Data'].unique(),
                        tickformat='%b %d'
                    ),
                    yaxis=dict(
                        title='',
                        showgrid=False,
                        zeroline=False,
                        gridcolor='rgba(0,0,0,0)'
                    ),
                    plot_bgcolor='rgba(0, 0, 0, 0)'
                )
                st.plotly_chart(fig_resultado, use_container_width=True)

            def painel_recuperacao():
                dados_vendedores2 = {
                    'Vendedor': [
                    'ROSIMERY', 'ELLEN', 'ISABEL', 'ANTONIO', 'DANILO', 'DANIEL', 'VICTOR SILVA',
                    'VICTOR', 'LARISSA', 'JOAO', 'ANNA'
                    ],
                    'Meta Cartões': [
                      60, 45, 60, 45, 45, 20, 20, 20, 30, 30, 20
                    ],
                    'Meta Saque': [
                      20000, 15000, 20000, 15000, 15000, 0, 0, 0, 0, 0, 0
                    ],
                    'Início': [
                    '14/08/2024', '08/01/2025', '26/08/2024', '09/01/2025', '09/01/2025', '04/12/2024',
                    '06/11/2024', '09/10/2024', '04/02/2024', '04/02/2024', '04/12/2024'
                    ]
                }
                df_vendedores2 = pd.DataFrame(dados_vendedores2)

                dados_painel_recuperacao = {
                  'Conversão s/ Digitação': ['> 70%', 'De 40% à 69%', '< 39%'],
                  'Plano Recuperação': ['Satisfatório', 'Em Desenvolvimento', 'À Desenvolver']
                }
                df_recuperacao = pd.DataFrame(dados_painel_recuperacao)

                painel2 = df.groupby('Vendedor').agg(
                    Pago=('Status', lambda x: (x == 'PAGO').sum()),
                    Ag_Inss=('Status', lambda x: (x == 'AG. INSS').sum()),
                    Valor_Pago=('Valor', lambda x: pd.to_numeric(df.loc[x.index, 'Valor'], errors='coerce').fillna(0).sum()),
                    Bloqueado=('Status', lambda x: (x == 'BLOQUEADO').sum()),
                    Pendente=('Status', lambda x: ((df.loc[x.index, 'Perfil'] == 'ATUAL') & (x.isin(['PENDENTE']))).sum() + (x == 'CANCELADO').sum())
                ).reset_index()

                painel2 = painel2.merge(df_vendedores2, on='Vendedor', how='inner')
                vendedor_pendente = painel2.loc[painel2['Pendente'].idxmax(), 'Vendedor']
                cartoes_pendentes = painel2['Pendente'].max()
                total_pendente = painel2['Pendente'].sum()
                media_pend_dia = round(total_pendente / dias_passados)
                media_cartoes_pend_dia = round(cartoes_pendentes / dias_passados)

                projecao_meta = (((painel2['Pago'] + painel2['Ag_Inss']) / dias_passados) * dias_uteis).round()
                vendedores_fora_meta = painel2.loc[projecao_meta < painel2['Meta Cartões'], 'Vendedor'].tolist()

                painel2['Total Digitado'] = painel2['Pago'] + painel2['Ag_Inss'] + painel2['Bloqueado'] + painel2['Pendente']
                painel2['Total Aceite'] = painel2['Pago'] + painel2['Ag_Inss'] + painel2['Bloqueado']
                painel2['Conv. s/ Digitação'] = ((painel2['Pago'] + painel2['Ag_Inss'] + painel2['Bloqueado']) / painel2['Total Digitado']) * 100
                painel2['Conv. s/ Digitação'] = painel2['Conv. s/ Digitação'].fillna(0).replace([float('inf'), -float('inf')], 0)
                menor_conversao = painel2['Conv. s/ Digitação'].min()
                
                def definir_plano(conversao):
                  if conversao <= 39.99:
                      return 'À Desenvolver'
                  elif 40 <= conversao <= 69.99:
                      return 'Em Desenvolvimento'
                  elif conversao >= 70:
                      return 'Satisfatório'
                  else:
                      return 'Verifique a conversão'
                  
                painel2['Plano'] = painel2['Conv. s/ Digitação'].apply(definir_plano)
                painel2['Conv. s/ Digitação'] = painel2['Conv. s/ Digitação'].round().astype(int).astype(str) + '%'
                painel2 = painel2.sort_values(by='Total Aceite', ascending=False)
                
                total2 = painel2[['Total Digitado', 'Total Aceite']].sum()
                total2['Vendedor'] = 'Total'
                total2['Início'] = ''
                total2['Conv. s/ Digitação'] = (total2['Total Aceite'] / total2['Total Digitado']) * 100
                total2['Conv. s/ Digitação'] = str(int(round(total2['Conv. s/ Digitação']))) + '%'
                total2['Plano'] = ''

                painel2 = pd.concat([painel2, total2.to_frame().T], ignore_index=True)
                painel2 = painel2.reindex(columns=['Vendedor', 'Início', 'Total Digitado', 'Total Aceite', 'Conv. s/ Digitação',	'Plano']).reset_index(drop=True)

                painel_regra = df_recuperacao.copy()
                painel_regra = painel_regra.reindex(columns=['Conversão s/ Digitação', 'Plano Recuperação']).reset_index(drop=True)

                media_aceite_dia = round((painel2['Total Aceite'] / dias_passados).min(), 2)
                vendedor_media_aceite = painel2.loc[(painel2['Total Aceite'] / dias_passados).idxmin(), 'Vendedor']

                vendedor_menor_conversao = painel2.loc[painel2['Conv. s/ Digitação'].idxmin(), 'Vendedor']
                porcentagem_conversao = painel2['Conv. s/ Digitação'].min()

                st.text('')
                st.text('')
                st.markdown("<p style='text-align: center; font-size: 20px;'><strong>📝 Pontos de atenção:</strong></p>", unsafe_allow_html=True)
                if cartoes_pendentes > 0:
                  st.markdown(f"""
                      <p style='text-align: center;'>
                          Quantidade total de cartões pendentes: 
                          <strong>{total_pendente}</strong>. Em média 
                          <strong>{media_pend_dia}</strong> cartões pendentes por dia
                          <span title="Não incluído as pendências dos operadores que estão em teste ou saíram" style="cursor: help; color: blue;">[?]</span>
                      </p>
                  """, unsafe_allow_html=True)
                else:
                  st.write('')
                if cartoes_pendentes > 0:
                  st.markdown(f"""
                      <p style='text-align: center;'>
                          Conversão sobre digitação abaixo do mínimo esperado: 
                          <strong>{vendedor_menor_conversao}</strong> com  
                          <strong>{porcentagem_conversao}</strong> de conversão
                          <span title="Objetivo: 50%. Mínimo: 30%" style="cursor: help; color: blue;">[?]</span>
                      </p>
                  """, unsafe_allow_html=True)
                else:
                  st.write('')
                if cartoes_pendentes > 0:
                  st.markdown(f"<p style='text-align: center;'>Maior quantidade de cartões pendentes no mês: <strong>{vendedor_pendente}</strong> com <strong>{cartoes_pendentes}</strong> cartões. Em média <strong>{media_cartoes_pend_dia}</strong> cartões pendentes por dia</p>", unsafe_allow_html=True)
                else:
                  st.write('')
                if cartoes_pendentes > 0:
                  st.markdown(f"<p style='text-align: center;<st>'>Menor média de aceite dia: <strong>{vendedor_media_aceite}</strong> com <strong>{media_aceite_dia}</strong> aceites em média por dia</p>", unsafe_allow_html=True)
                else:
                  st.write('')
                if len(vendedores_fora_meta) > 1:
                  st.markdown(f"<p style='text-align: center;'>Vendedores que não estão projetando meta: <strong>{', '.join(vendedores_fora_meta)}</strong></p>", unsafe_allow_html=True)
                else:
                  st.markdown(f"<p style='text-align: center;'>Vendedor que não está projetando meta: <strong>{vendedores_fora_meta[0]}</strong></p>", unsafe_allow_html=True)

                st.text('')
                st.text('')
                st.text('')

                st.markdown("<h2 style='text-align: left;'>🚥 PLANO DE RECUPERAÇÃO</h2>", unsafe_allow_html=True)
                st.dataframe(painel_regra, hide_index=True)
                st.text('')

                painel_satisfatorio = painel2[painel2['Plano'] == 'Satisfatório']
                painel_desenvolvimento = painel2[painel2['Plano'] == 'Em Desenvolvimento']
                painel_a_desenvolver = painel2[painel2['Plano'] == 'À Desenvolver']

                st.text('')
                if not painel_satisfatorio.empty:
                    st.markdown("<p style='text-align: left; font-size: 20px;'><strong>✅ Satisfatório</strong></p>", unsafe_allow_html=True)
                    st.dataframe(painel_satisfatorio, hide_index=True)

                if not painel_desenvolvimento.empty:
                    st.markdown("<p style='text-align: left; font-size: 20px;'><strong>⚠ Em Desenvolvimento</strong></p>", unsafe_allow_html=True)
                    st.dataframe(painel_desenvolvimento, hide_index=True)

                if not painel_a_desenvolver.empty:
                    st.markdown("<p style='text-align: left; font-size: 20px;'><strong>🚨 À Desenvolver</strong></p>", unsafe_allow_html=True)
                    st.dataframe(painel_a_desenvolver, hide_index=True)

                print()

        else:
          print("Nenhum dado encontrado na planilha.")

        if valores_diario:
          st.cache_data.clear()
          df_diario = pd.DataFrame(valores_diario [1:], columns=valores_diario[0])
          colunas_final = ['Vendedor', ' Meta Dia ', 'Valor', ' Aceite Dia ', ' Aceite Anterior ', ' Total ', 'Ligações', 'TMA']
          df_diario = df_diario[colunas_final]

          def painel_diario():
              st.write('')
              st.markdown("<h3 style='text-align: center;'>💳 PAINEL DIÁRIO</h3>", unsafe_allow_html=True)
              st.dataframe(df_diario, use_container_width=True, height=493, hide_index=True)
              meta_do_dia = int(df_diario.loc[len(df_diario) - 1, ' Meta Dia '])
              vendido_no_dia = int(df_diario.loc[len(df_diario) - 1, ' Total '])
              diferenca = vendido_no_dia - meta_do_dia
              resultado = diferenca - (diferenca * 2)
              df_sem_total = df_diario.iloc[:-1].copy()
              df_sem_total[' Total '] = pd.to_numeric(df_sem_total[' Total '], errors='coerce')
              maior_aceite_dia = int(df_sem_total[' Total '].max())
              destaque_dia = df_sem_total.loc[df_sem_total[' Total '] == maior_aceite_dia, 'Vendedor'].tolist()
              
              st.markdown("""
                    <p style="text-align: center; font-size: 16px; font-weight: bold;">
                        As atualizações do painel acontecem às 11h, 14h, 16h e 18h
                    </p>
                """, unsafe_allow_html=True)
              st.write("")
              st.markdown("""
                    <style>
                    .info-box {
                        background-color: #e0f3ff;
                        padding: 15px;
                        border-radius: 5px;
                        border-left: 6px solid #1f77b4;
                        text-align: center;
                        font-weight: bold;
                    }
                    </style>
                """, unsafe_allow_html=True)
              
              col1, col2 = st.columns(2, gap='medium')
              with col1:
                    st.markdown(f'<div class="info-box">Meta do dia: {meta_do_dia} cartões</div>', unsafe_allow_html=True)
                
              with col2:
                    if diferenca > 0:
                      st.markdown(f'<div class="info-box">Parabéns!👏👏👏 Meta do dia superada em {diferenca} cartões.</div>', unsafe_allow_html=True)
                    elif diferenca == 0:
                      st.markdown(f'<div class="info-box">Objetivo cumprido! Meta do dia atingida com sucesso 🚀</div>', unsafe_allow_html=True)
                    elif diferenca < 0:
                      st.markdown(f'<div class="info-box">🚨 Faltam {resultado} cartões para batermos a meta do dia</div>', unsafe_allow_html=True)
                    else:
                      st.markdown(f'<div class="info-box">Verifique!</div>', unsafe_allow_html=True)

              st.write("")
              st.write("")
              st.write("")
              st.write("")
              if maior_aceite_dia > 0:
                if len(destaque_dia) == 1:
                    destaque_str = destaque_dia[0]
                    st.markdown("<p style='text-align: center; font-size: 20px;'><strong>🥇 Destaque do dia</strong></p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='text-align: center;<st>'>Maior quantidade de aceites do dia: <strong>{destaque_str}</strong> com <strong>{maior_aceite_dia} </strong> aceites</p>", unsafe_allow_html=True)
                elif len(destaque_dia) > 1:
                    destaque_str = ", ".join(destaque_dia)
                    st.markdown("<p style='text-align: center; font-size: 20px;'><strong>🥇 Destaque do dia</strong></p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='text-align: center;<st>'>Maior quantidade de aceites do dia: <strong>{destaque_str}</strong> com <strong>{maior_aceite_dia} </strong> aceites</p>", unsafe_allow_html=True)
              else:
                st.write('')

        def navegacao():
            senha_supervisao = os.getenv("SENHA_SUPERVISAO")
            senha_gerente = os.getenv("SENHA_GERENTE")

            if senha_supervisao is not None:
                senha_supervisao = int(senha_supervisao)
            if senha_gerente is not None:
                senha_gerente = int(senha_gerente)

            selected = option_menu(
              menu_title='Página Principal',
              options=['Home', 'Vendas do Dia', 'Indicadores'],
              icons=['house', 'credit-card', 'graph-up arrow'],
              menu_icon='cast',
              default_index=0,
              orientation='horizontal'
            )
          
            if selected == 'Home':
              sidebar_parceiros()
              painel_mensal()

            if selected == 'Vendas do Dia':
              sidebar_parceiros()
              painel_diario()

            if selected == 'Indicadores':
              senha_digitada = st.text_input('Digite o pin: ', type='password')
              if senha_digitada.isdigit() and int(senha_digitada) == senha_gerente:
                  sidebar_data()
                  sidebar_filtros()
                  sidebar_origem()
                  sidebar_parceiros()
                  painel_recuperacao()
                  graficos()
                  painel_custo()

              elif senha_digitada.isdigit() and int(senha_digitada) == senha_supervisao:
                  sidebar_parceiros()
                  painel_recuperacao()
                  aceite_diario()
              else:
                  st.write('Não foi possível exibir nenhuma análise')

        navegacao()
        st.write("")
        st.write("")
        st.write("")
        st.write("")
        st.write("")
        st.write("")
        st.write("")
        st.markdown("""
            <hr>
            <p style="text-align:center; font-size:14px; color:gray;">
                © 2025 - Desenvolvido por <b>Inteligência da Informação</b>
            </p>
        """, unsafe_allow_html=True)

    except HttpError as err:
      print(err)

if __name__ == "__main__":
  main()
