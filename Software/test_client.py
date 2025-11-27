import requests
import neurokit2 as nk
import numpy as np

# 1. 서버 주소 (fs 파라미터 포함)
url = "http://localhost:9999/process_ecg?fs=250"

# 2.데이터 생성 (10초)
print(">>> 가상 데이터 생성 중...")
fs = 250
temp_signal = nk.ecg_simulate(duration=10, sampling_rate=fs, noise=0.05, heart_rate=70)

# \n
string_data = "\n".join(map(str, temp_signal))

# 4. 전송 (헤더를 text/plain으로 설정)
headers = {'Content-Type': 'text/plain'}

print(f">>> 서버({url})로 데이터 전송 시도...")
print(f"    (데이터 길이: {len(string_data)} 글자)")

try:
    # [중요] json=... 대신 data=... 를 사용해야 합니다.
    response = requests.post(url, data=string_data, headers=headers)
    
    print("\n[결과 수신]")
    print(f"상태 코드: {response.status_code}")
    
    if response.status_code == 200:
        print(f"응답 본문: {response.json()}")
    else:
        print(f"에러 메시지: {response.text}")
    
except Exception as e:
    print(f"\n[에러 발생] 연결 실패: {e}")