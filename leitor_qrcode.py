import cv2
import json
import requests
import time
from pyzbar.pyzbar import decode, ZBarSymbol

# URL do backend Java
BACKEND_URL = "http://localhost:8080/api/movimentacoes"

def send_post_request(json_data):
    try:
        response = requests.post(BACKEND_URL, json=json_data)
        print(f"Resposta do backend: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Erro ao enviar POST: {e}")

def main():
    cap = cv2.VideoCapture(0)
    print("Aponte a câmera do celular para um QR Code")

    last_read_time = 0
    read_interval = 5
    qr_info = None
    tracker = None

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Erro ao capturar vídeo.")
            break

        current_time = time.time()

        # --- Detecta QR Code a cada X segundos
        if current_time - last_read_time >= read_interval:
            qr_codes = decode(frame, symbols=[ZBarSymbol.QRCODE])

            for qr_code in qr_codes:
                try:
                    qr_data = qr_code.data.decode('utf-8')
                    print(f"QR Code detectado: {qr_data}")

                    try:
                        json_data = json.loads(qr_data)
                        qr_info = {
                            "idMoto": json_data.get("idMoto", ""),
                            "idPonto": json_data.get("idPonto", ""),
                            "dataHora": json_data.get("dataHora", "")
                        }
                        print("JSON válido detectado")
                        send_post_request(json_data)
                    except json.JSONDecodeError:
                        print("QR Code não contém JSON válido")
                        qr_info = None

                    # inicia tracker no QR Code detectado
                    (x, y, w, h) = qr_code.rect
                    tracker = cv2.TrackerKCF_create()
                    tracker.init(frame, (x, y, w, h))

                except Exception as e:
                    print(f"Erro ao processar QR Code: {e}")

            last_read_time = current_time

        # --- Usa tracker se já tiver inicializado
        if tracker is not None:
            success, box = tracker.update(frame)
            if success:
                (x, y, w, h) = [int(v) for v in box]
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                if qr_info:
                    cv2.putText(frame, f"Moto: {qr_info['idMoto']}", (x, y - 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(frame, f"Ponto: {qr_info['idPonto']}", (x, y - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(frame, f"Data: {qr_info['dataHora']}", (x, y - 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        cv2.imshow("QR Code + Tracking", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
