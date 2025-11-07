from fastapi import FastAPI, UploadFile, File, Form
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

is_running = False
thread = None
READ_INTERVAL = 2  # segundos entre leituras

def send_post_request(json_data):
    try:
        resp = requests.post(BACKEND_URL, json=json_data, timeout=5)
        print(f"POST para backend: {resp.status_code} - {resp.text}")
    except Exception as e:
        print("Erro ao enviar POST para backend:", e)

def read_qrcode_loop():
    global is_running
    cap = cv2.VideoCapture(0)
    last_read_time = 0
    qr_info = None
    tracker = None

    while is_running:
        ret, frame = cap.read()
        if not ret:
            print("Erro ao capturar frame")
            break

        now = time.time()
        if now - last_read_time >= READ_INTERVAL:
            qr_codes = decode(frame, symbols=[ZBarSymbol.QRCODE])
            for qr in qr_codes:
                try:
                    data = qr.data.decode("utf-8")
                    print("QR detectado:", data)
                    try:
                        json_data = json.loads(data)
                        send_post_request(json_data)
                        qr_info = json_data
                    except json.JSONDecodeError:
                        print("QR não contém JSON")

                    (x, y, w, h) = qr.rect
                    tracker = cv2.TrackerKCF_create()
                    tracker.init(frame, (x, y, w, h))
                except Exception as e:
                    print("Erro processamento QR:", e)
            last_read_time = now

        if tracker is not None:
            ok, box = tracker.update(frame)
            if ok:
                (x, y, w, h) = [int(v) for v in box]
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                if qr_info:
                    cv2.putText(frame, f"Moto: {qr_info.get('idMoto','')}", (x, y - 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)

        cv2.imshow("QR Code - Leitor", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            is_running = False
            break

    cap.release()
    cv2.destroyAllWindows()
    print("Leitor finalizado")

@app.post("/gerar_qrcode")
async def gerar_qrcode(
    idMovimentacao: int = Form(None),
    idMoto: str = Form(None),
    idPonto: int = Form(None),
    dataHora: str = Form(None)
):
    if not dataHora:
        dataHora = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    payload = {
        "idMovimentacao": idMovimentacao,
        "idMoto": idMoto,
        "idPonto": idPonto,
        "dataHora": dataHora
    }

    json_str = json.dumps(payload)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=4,
    )
    qr.add_data(json_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")

@app.get("/start")
def start_reader():
    global is_running, thread
    if is_running:
        return JSONResponse({"status": "already_running"}, status_code=400)
    is_running = True
    thread = threading.Thread(target=read_qrcode_loop, daemon=True)
    thread.start()
    return {"status": "started"}

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

@app.post("/upload_image_and_decode")
async def upload_image_and_decode(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, dtype='uint8')
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    qr_codes = decode(img, symbols=[ZBarSymbol.QRCODE])
    if not qr_codes:
        return {"found": False}
    data = qr_codes[0].data.decode('utf-8')
    try:
        json_obj = json.loads(data)
        # opcional: envia para backend
        send_post_request(json_obj)
        return {"found": True, "data": json_obj}
    except json.JSONDecodeError:
        return {"found": True, "data": data}
