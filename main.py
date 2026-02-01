from fastapi import FastAPI
from pydantic import BaseModel

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

@app.post("/sincronizar/{numero_serie}")
def sincronizar(numero_serie: str, body: SincronizarBody):
    return {
        "numero_serie": numero_serie,
        "senha_sincronizar": body.senha_sincronizar
    }
