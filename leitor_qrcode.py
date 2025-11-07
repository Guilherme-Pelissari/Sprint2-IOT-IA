from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import json
import qrcode
import threading
import time
import cv2
from pyzbar.pyzbar import decode, ZBarSymbol
import requests
from datetime import datetime
import numpy as np

app = FastAPI()

# CORS para permitir chamadas do Thymeleaf (spring em localhost:8080)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# altere se necessário (endpoint do seu backend Java)
BACKEND_URL = "http://localhost:8080/api/movimentacoes"

# ... (código do gerar_qrcode da Fase 1 se mantém) ...
@app.post("/gerar_qrcode")
async def gerar_qrcode(
    idMoto: str = Form(...),
    placa: str = Form(...),
    modelo: str = Form(...)
):
    payload = {
        "idMoto": idMoto,
        "placa": placa,
        "modelo": modelo
    }
    json_str = json.dumps(payload, indent=2)
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=8, border=4)
    qr.add_data(json_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


# =======================================================
#               MUDANÇAS NA LEITURA
# =======================================================

# 1. FUNÇÃO DE ENVIO MODIFICADA
def send_post_request(qr_data: dict, id_ponto: int):
    """
    Combina os dados do QR com o idPonto e a data/hora,
    e envia para o backend Java.
    """
    
    # Validação: qr_data deve ter 'idMoto'
    if "idMoto" not in qr_data:
        print("Erro: JSON do QR Code não contém 'idMoto'.")
        return False, None # Retorna falha

    # Construção do payload final para o Java
    final_payload = {
        "idMovimentacao": None, # O Java deve gerar isso
        "idMoto": qr_data.get("idMoto"),
        "idPonto": id_ponto,
        "dataHora": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    }

    try:
        resp = requests.post(BACKEND_URL, json=final_payload, timeout=5)
        print(f"POST para backend: {resp.status_code} - {resp.text}")
        
        if resp.status_code == 201: # 201 Created (sucesso no Java)
            return True, final_payload
        else:
            return False, final_payload # Falha, mas retorna o que tentou enviar

    except Exception as e:
        print("Erro ao enviar POST para backend:", e)
        return False, final_payload


# 2. ENDPOINT DE UPLOAD MODIFICADO
@app.post("/upload_image_and_decode")
async def upload_image_and_decode(
    file: UploadFile = File(...),
    idPonto: int = Form(...)  # <-- RECEBE O idPonto DO FORMULÁRIO
):
    
    if not idPonto:
        raise HTTPException(status_code=400, detail="idPonto é obrigatório.")

    contents = await file.read()
    nparr = np.frombuffer(contents, dtype='uint8')
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        raise HTTPException(status_code=400, detail="Não foi possível decodificar o arquivo de imagem.")

    qr_codes = decode(img, symbols=[ZBarSymbol.QRCODE])
    
    if not qr_codes:
        return {"found": False}

    data = qr_codes[0].data.decode('utf-8')
    
    try:
        # Tenta decodificar o JSON do QR Code
        qr_json_obj = json.loads(data)
        
        # Envia para o backend Java
        success, payload_sent = send_post_request(qr_json_obj, idPonto)
        
        return {
            "found": True, 
            "data_type": "json",
            "data": qr_json_obj, # O que estava no QR
            "sent_to_backend": success,
            "payload_sent": payload_sent # O que foi enviado ao Java
        }
        
    except json.JSONDecodeError:
        # Se o QR não tiver JSON (talvez só um texto simples)
        return {"found": True, "data_type": "text", "data": data, "sent_to_backend": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno no processamento: {e}")


# 3. LÓGICA /start DEPRECADA (NÃO FUNCIONA COM A NOVA REGRA)
# Recomendo remover ou desabilitar esta parte, pois ela não sabe
# qual 'idPonto' o usuário selecionou no navegador.

is_running = False
thread = None
READ_INTERVAL = 2

def read_qrcode_loop():
    global is_running
    print("AVISO: A função read_qrcode_loop (leitura contínua) foi iniciada.")
    print("AVISO: Esta função não sabe qual 'idPonto' foi selecionado no navegador e falhará ao enviar ao Java.")
    print("Use a captura de imagem pelo navegador (Upload / Abrir Câmera).")
    
    cap = cv2.VideoCapture(0)
    # ... (o resto da função existe, mas vai falhar no send_post_request) ...
    # ... (pois send_post_request agora exige 'id_ponto') ...
    
    # Exemplo de como falharia:
    # qr_codes = decode(frame, ...)
    # for qr in qr_codes:
    #   json_data = json.loads(qr.data.decode("utf-8"))
    #   send_post_request(json_data, ???) # <-- PROBLEMA: Qual idPonto?
    
    cap.release()
    cv2.destroyAllWindows()
    print("Leitor (loop) finalizado")


@app.get("/start")
def start_reader():
    global is_running, thread
    if is_running:
        return JSONResponse({"status": "already_running"}, status_code=400)
    is_running = True
    thread = threading.Thread(target=read_qrcode_loop, daemon=True)
    thread.start()
    return {"status": "started_with_warning", "detail": "Loop de leitura contínua foi iniciado, mas não pode enviar dados ao Java pois não possui 'idPonto'. Use o upload de imagem do navegador."}

@app.get("/stop")
def stop_reader():
    global is_running
    if not is_running:
        return JSONResponse({"status": "not_running"}, status_code=400)
    is_running = False
    return {"status": "stopping"}

@app.get("/status")
def status_reader():
    return {"running": is_running}