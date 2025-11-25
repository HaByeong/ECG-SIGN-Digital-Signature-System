import socket
import json
import neurokit2 as nk

# 1. 서버 설정
HOST = 'localhost'
PORT = 9999

# 2. 가짜 데이터 생성
fs = 250
temp_signal = nk.ecg_simulate(duration=10, sampling_rate=fs, noise=0.05, heart_rate=70)
string_data = "\n".join(map(str, temp_signal))

print(f">>> 서버({HOST}:{PORT})로 접속 시도...")

# 3. 소켓 연결 및 전송
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    
    # 데이터 전송
    s.sendall(string_data.encode('utf-8'))

    s.shutdown(socket.SHUT_WR)
    
    print(">>> 데이터 전송 완료. 결과 대기 중...")
    
    # 4. 결과 수신
    response_data = b""
    while True:
        chunk = s.recv(4096)
        if not chunk: break
        response_data += chunk
        
    print("\n[결과 수신]")
    print(response_data.decode('utf-8'))