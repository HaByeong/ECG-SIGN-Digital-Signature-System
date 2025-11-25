import socket
import json
import numpy as np
import neurokit2 as nk
import threading

# 입력 포맷 : 숫자\n숫자\n
# 반환 포맷 : {"status": "success", "feature_vector": [123.0, 456.0, 789.0, 0.5, 0.1, 5.0]}

# ECG 신호 처리 함수(임시)
def process_ecg_signal(raw_data_list, fs=250):
    print(f"   [Logic] process_ecg_signal 호출됨!")
    print(f"   [Logic] 받은 데이터 샘플 수: {len(raw_data_list)}개")
    # 테스트용 결과
    dummy_vector = [123.0, 456.0, 789.0, 0.5, 0.1, 5.0]
    return dummy_vector, "Success"

# [TCP 서버 핸들러]
def handle_client(client_socket, addr):
    print(f"[{addr}] 연결됨")
    received_data = b""
    try:
        # 1. 데이터 수신 Loop
        while True:
            chunk = client_socket.recv(4096)
            if not chunk: break # 클라이언트 전송 종료
            received_data += chunk
            
        print(f"[{addr}] 데이터 수신 완료 ({len(received_data)} bytes)")
        
        # 2. 데이터 파싱
        if not received_data: raise ValueError("빈 데이터")
        
        raw_string = received_data.decode('utf-8')
        raw_data = [float(x) for x in raw_string.strip().split('\n') if x.strip()]
        
        # 3. 분석 실행
        vector, msg = process_ecg_signal(raw_data, fs=250)
        
        # 4. 결과 전송
        if vector:
            response = {"status": "success", "feature_vector": vector}
            print(f"[{addr}]  결과:   {vector}")
        else:
            response = {"status": "error", "message": msg}
            
        client_socket.sendall(json.dumps(response).encode('utf-8'))
        
        print(f"[{addr}] 결과 전송 완료")
        
    except Exception as e:
        print(f"[{addr}] 에러: {e}")
        error_resp = {"status": "error", "message": str(e)}
        client_socket.sendall(json.dumps(error_resp).encode('utf-8'))
        
    finally:
        client_socket.close()
        print(f"[{addr}] 연결 종료")

# [메인 실행]

if __name__ == '__main__':
    HOST = '0.0.0.0'
    PORT = 9999
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # 포트 재사용 허용
    server.bind((HOST, PORT))
    server.listen(5)
    
    print(f" TCP 소켓 서버가 시작되었습니다. (Port: {PORT})")
    
    while True:
        client_sock, addr = server.accept()
        client_handler = threading.Thread(target=handle_client, args=(client_sock, addr))
        client_handler.start()
