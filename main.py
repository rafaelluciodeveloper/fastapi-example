from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime

import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
import ftplib
from typing import Optional
import io
import zipfile
from datetime import datetime

load_dotenv()

app = FastAPI()

@app.get("/")
async def root():
    return RedirectResponse(url="/admin/upload")

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
                "versaoContabil": row.get("versao_contabil"),
                "arquivoFolha": row.get("arquivo_folha"),
                "arquivoFiscal": row.get("arquivo_fiscal"),
                "arquivoContabil": row.get("arquivo_contabil")
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
        "versaoContabil": None,
        "arquivoFolha": None,
        "arquivoFiscal": None,
        "arquivoContabil": None
    }
    
    return {**autorizacao, **atualizacao}

class SincronizarBody(BaseModel):
    senha_sincronizar: str
    folha_encontrado: bool
    fiscal_encontrado: bool
    contabil_encontrado: bool
    documento:str

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
        (numero_serie_atualizacao, autoriza_folha, autoriza_fiscal, autoriza_contabil, documento)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        autoriza_folha = VALUES(autoriza_folha),
        autoriza_fiscal = VALUES(autoriza_fiscal),
        autoriza_contabil = VALUES(autoriza_contabil),
        documento = VALUES(documento)
        """
        cursor.execute(query, (
            numero_serie, 
            body.folha_encontrado, 
            body.fiscal_encontrado, 
            body.contabil_encontrado,
            body.documento
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
            "autoriza_contabil": body.contabil_encontrado,
            "documento": body.documento
        }
    }

templates = Jinja2Templates(directory="templates")

@app.get("/admin/upload", response_class=HTMLResponse)
async def get_upload_page(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/admin/verify-password")
async def verify_password(password: str = Form(...)):
    expected_password = os.getenv("UPLOAD_PASSWORD")
    if password == expected_password:
        return {"status": "success"}
    raise HTTPException(status_code=401, detail="Senha incorreta")

async def process_file_upload_ftp(file: UploadFile, timestamp_int: int, ftp_config: dict):
    # Convert timestamp to formatting objects
    # timestamp_int is from browser (milliseconds)
    dt_obj = datetime.fromtimestamp(timestamp_int / 1000.0)
    
    # Filename suffix: .yyyy.mm.dd.hh.mm.ss
    ts_suffix = dt_obj.strftime(".%Y.%m.%d.%H.%M.%S")
    
    # DB Version string: yyyy.mm.dd.hh:mm:ss
    db_version = dt_obj.strftime("%Y.%m.%d.%H:%M:%S")

    filename = file.filename
    name_part, ext_part = os.path.splitext(filename)
    ext_lower = ext_part.lower()
    
    file_content = await file.read()
    file_to_upload = io.BytesIO(file_content)
    final_filename = ""

    if ext_lower == ".exe":
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(filename, file_content)
        
        zip_buffer.seek(0)
        file_to_upload = zip_buffer
        final_filename = f"{name_part}{ts_suffix}.zip"
    else:
        final_filename = f"{name_part}{ts_suffix}{ext_part}"

    final_filename =  final_filename.lower()

    # FTP Upload
    try:
        ftp = ftplib.FTP(ftp_config['host'])
        ftp.login(ftp_config['user'], ftp_config['pass'])
        
        if ftp_config['dir']:
            try:
                ftp.cwd(ftp_config['dir'])
            except ftplib.error_perm:
                pass 
        
        ftp.storbinary(f"STOR {final_filename}", file_to_upload)
        ftp.quit()
    except Exception as e:
        raise Exception(f"FTP Error for {filename}: {str(e)}")

    return db_version, final_filename

@app.post("/admin/upload-files-sync")
async def upload_files_sync(
    password: str = Form(...),
    file_folha: Optional[UploadFile] = File(None),
    ts_folha: Optional[int] = Form(None),
    file_fiscal: Optional[UploadFile] = File(None),
    ts_fiscal: Optional[int] = Form(None),
    file_contabil: Optional[UploadFile] = File(None),
    ts_contabil: Optional[int] = Form(None)
):
    expected_password = os.getenv("UPLOAD_PASSWORD")
    if password != expected_password:
        raise HTTPException(status_code=401, detail="Não autorizado")
    
    # FTP Config
    ftp_config = {
        'host': os.getenv("FTP_HOST"),
        'user': os.getenv("FTP_USER"),
        'pass': os.getenv("FTP_PASSWORD"),
        'dir': os.getenv("FTP_DIR")
    }
    
    if not all([ftp_config['host'], ftp_config['user'], ftp_config['pass']]):
         raise HTTPException(status_code=500, detail="Configuração de FTP incompleta no .env")

    # Fetch current versions to preserve if not updating
    current_data = fetch_atualizacao() or {}
    
    versao_folha = current_data.get("versaoFolha")
    versao_fiscal = current_data.get("versaoFiscal")
    versao_contabil = current_data.get("versaoContabil")
    arquivo_folha = current_data.get("arquivoFolha")
    arquivo_fiscal = current_data.get("arquivoFiscal")
    arquivo_contabil = current_data.get("arquivoContabil")

    # Process Uploads
    try:
        if file_folha and ts_folha:
            if "folha" not in file_folha.filename.lower():
                raise HTTPException(status_code=400, detail=f"Erro: O arquivo '{file_folha.filename}' selecionado para o campo Módulo Folha parece incorreto. Verifique se selecionou o arquivo certo.")
            versao_folha, arquivo_folha = await process_file_upload_ftp(file_folha, ts_folha, ftp_config)
            
        if file_fiscal and ts_fiscal:
            if "fiscal" not in file_fiscal.filename.lower():
                raise HTTPException(status_code=400, detail=f"Erro: O arquivo '{file_fiscal.filename}' selecionado para o campo Módulo Fiscal parece incorreto. Verifique se selecionou o arquivo certo.")
            versao_fiscal, arquivo_fiscal = await process_file_upload_ftp(file_fiscal, ts_fiscal, ftp_config)
            
        if file_contabil and ts_contabil:
            name_lower = file_contabil.filename.lower()
            if "contabil" not in name_lower and "contábil" not in name_lower:
                raise HTTPException(status_code=400, detail=f"Erro: O arquivo '{file_contabil.filename}' selecionado para o campo Módulo Contábil parece incorreto. Verifique se selecionou o arquivo certo.")
            versao_contabil, arquivo_contabil = await process_file_upload_ftp(file_contabil, ts_contabil, ftp_config)
            
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Insert into Database
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Using NOW() for data_publicacao
        query = """
        INSERT INTO atualizacao 
        (versao_folha, versao_fiscal, versao_contabil, 
         arquivo_folha, arquivo_fiscal, arquivo_contabil, 
         data_publicacao)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """
        cursor.execute(query, (
            versao_folha, versao_fiscal, versao_contabil,
            arquivo_folha, arquivo_fiscal, arquivo_contabil
        ))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro banco de dados: {str(e)}")
    finally:
        cursor.close()
        conn.close()

    return {
        "message": "Arquivos processados e banco de dados atualizado com sucesso!",
        "versoes": {
            "folha": versao_folha,
            "fiscal": versao_fiscal,
            "contabil": versao_contabil
        },
        "arquivos": {
            "folha": arquivo_folha,
            "fiscal": arquivo_fiscal,
            "contabil": arquivo_contabil
        }
    }
