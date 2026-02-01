from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime

import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Database configuration - Loaded from environment variables
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'test_db')
}

def get_db_connection():
    import mysql.connector
    return mysql.connector.connect(**DB_CONFIG)

def fetch_atualizacao():
    """
    Executes SELECT * FROM atualizacao ORDER BY data_publicacao DESC LIMIT 1
    Returns properties map with keys: versaoFolha, versaoFiscal, versaoContabil
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM atualizacao ORDER BY data_publicacao DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return {
                "versaoFolha": row.get("versao_folha"),
                "versaoFiscal": row.get("versao_fiscal"),
                "versaoContabil": row.get("versao_contabil")
            }
        return None
    finally:
        cursor.close()
        conn.close()

def fetch_autorizacao(serie_atualizacao: str):
    """
    Executes SELECT * FROM atualizacao_autorizacao WHERE serie_atualizacao = ?
    Returns properties: autorizaFiscal, autorizaContabil, autorizaFolha, numeroSerieAutualizacao
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Note: mysql-connector-python uses %s for placeholders
        query = "SELECT * FROM atualizacao_autorizacao WHERE numero_serie_atualizacao = %s LIMIT 1"
        cursor.execute(query, (serie_atualizacao,))
        row = cursor.fetchone()
        if row:
            return {
                "autorizaFiscal": bool(row.get("autoriza_fiscal")),
                "autorizaContabil": bool(row.get("autoriza_contabil")),
                "autorizaFolha": bool(row.get("autoriza_folha")),
                "numeroSerieAutualizacao": row.get("numero_serie_atualizacao")
            }
        return None
    finally:
        cursor.close()
        conn.close()

@app.get("/atualizacao/{numero_serie}")
def get_atualizacao(numero_serie: str):
    autorizacao = fetch_autorizacao(numero_serie) or {
        "autorizaFolha": False,
        "autorizaFiscal": False,
        "autorizaContabil": False,
        "numeroSerieAutualizacao": None
    }
    
    atualizacao = fetch_atualizacao() or {
        "versaoFolha": None,
        "versaoFiscal": None,
        "versaoContabil": None
    }
    
    return {**autorizacao, **atualizacao}

class SincronizarBody(BaseModel):
    senha_sincronizar: str
    folha_encontrado: bool
    fiscal_encontrado: bool
    contabil_encontrado: bool

@app.post("/sincronizar/{numero_serie}")
def sincronizar(numero_serie: str, body: SincronizarBody):
    # Logica de decodificacao da senha
    # Formato: d r d r m r m r y r y r (12 caracteres)
    if len(body.senha_sincronizar) != 12:
        raise HTTPException(status_code=400, detail="Senha formato inválido")
    
    decoded_date = ""
    for i in range(0, 12, 2):
        decoded_date += body.senha_sincronizar[i]
    
    current_date = datetime.now().strftime("%d%m%y")
    
    if decoded_date != current_date:
        raise HTTPException(status_code=400, detail=f"Senha inválida. Esperado data atual ({current_date}), recebido {decoded_date}")

    # Inserir no banco
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Usando INSERT ON DUPLICATE KEY UPDATE para garantir que atualize se ja existir
        query = """
        INSERT INTO atualizacao_autorizacao 
        (numero_serie_atualizacao, autoriza_folha, autoriza_fiscal, autoriza_contabil)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        autoriza_folha = VALUES(autoriza_folha),
        autoriza_fiscal = VALUES(autoriza_fiscal),
        autoriza_contabil = VALUES(autoriza_contabil)
        """
        cursor.execute(query, (
            numero_serie, 
            body.folha_encontrado, 
            body.fiscal_encontrado, 
            body.contabil_encontrado
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

    return {
        "status": "sucesso",
        "messagem": "Sincronização realizada com sucesso",
        "dados_atualizados": {
            "numero_serie": numero_serie,
            "autoriza_folha": body.folha_encontrado,
            "autoriza_fiscal": body.fiscal_encontrado,
            "autoriza_contabil": body.contabil_encontrado
        }
    }
