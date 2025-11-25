import socket
import json
import numpy as np
import neurokit2 as nk
import threading


# [핵심 로직] ECG 신호 처리 함수 

def process_ecg_signal(raw_data_list, fs=250):
    """
    try:
        # [수정 1] 데이터 길이 체크
        if not raw_data_list or len(raw_data_list) < fs * 2: 
            return None, "데이터 길이가 너무 짧습니다."

        # [수정 2] NaN/Inf 안전 처리
        raw_ecg_signal = np.array(raw_data_list).astype(float)
        if np.any(np.isnan(raw_ecg_signal)) or np.any(np.isinf(raw_ecg_signal)):
            raw_ecg_signal = np.nan_to_num(raw_ecg_signal)
        
        # 1. 필터링 & R-peak 검출
        ecg_cleaned = nk.ecg_clean(raw_ecg_signal, sampling_rate=fs, method="neurokit")
        peaks_result = nk.ecg_peaks(ecg_cleaned, sampling_rate=fs, method="neurokit")
        
        if peaks_result is None: return None, "R-peak 검출 실패"
        _, info = peaks_result
        r_peaks = info["ECG_R_Peaks"]

        if len(r_peaks) < 2: return None, f"R-peak 개수 부족 ({len(r_peaks)}개)"

        # 2. 템플릿 생성 (1.0초 구간)
        before_samples = int(0.4 * fs)
        after_samples = int(0.6 * fs)
        processed_epochs = []

        for r_idx in r_peaks:
            r_idx = int(r_idx)
            start = r_idx - before_samples
            end = r_idx + after_samples
            
            if start < 0 or end > len(ecg_cleaned): continue
            
            segment = ecg_cleaned[start:end]
            seg_max = np.nanmax(segment)
            if seg_max <= 0 or np.isnan(seg_max): continue
            
            processed_epochs.append(segment / seg_max)

        if not processed_epochs: return None, "유효한 템플릿 생성 실패"
            
        processed_epochs = np.array(processed_epochs)
        representative_template = np.nanmean(processed_epochs, axis=0)
        representative_template = np.nan_to_num(representative_template)

        # 3. 특징 추출 (수동 로직)
        r_idx = np.argmax(representative_template)
        r_amp = representative_template[r_idx]
        
        search_qs = int(0.05 * fs)
        search_t_start = int(0.1 * fs)

        # Q, S, P, T 점 찾기
        q_region = representative_template[r_idx - search_qs : r_idx]
        q_idx = (r_idx - search_qs) + np.argmin(q_region) if len(q_region) > 0 else r_idx - 5
        
        s_region = representative_template[r_idx : r_idx + search_qs]
        s_idx = r_idx + np.argmin(s_region) if len(s_region) > 0 else r_idx + 5

        p_region = representative_template[:q_idx]
        p_idx = np.argmax(p_region) if len(p_region) > 0 else 0
        p_amp = representative_template[p_idx]

        t_search_start = r_idx + search_t_start
        if t_search_start < len(representative_template):
            t_region = representative_template[t_search_start:]
            t_idx = t_search_start + np.argmax(t_region) if len(t_region) > 0 else len(representative_template)-1
            t_amp = representative_template[t_idx]
        else:
            t_idx, t_amp = len(representative_template)-1, 0.001

        if t_amp == 0: t_amp = 0.001

        # 4. 결과 벡터 생성 (일반 float)
        feature_vector = [
            float(abs(s_idx - q_idx) * (1000 / fs)),
            float(abs(q_idx - p_idx) * (1000 / fs)),
            float(abs(t_idx - q_idx) * (1000 / fs)),
            float(t_amp),
            float(p_amp),
            float(r_amp / t_amp)
        ]
        return feature_vector, "Success"

    except Exception as e:
        print(f" 분석 중 에러: {e}")
        return None, f"분석 로직 에러: {str(e)}"
        """


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
    print("   (이 서버는 HTTP가 아닌 Raw TCP 통신을 사용합니다)")
    
    while True:
        client_sock, addr = server.accept()
        client_handler = threading.Thread(target=handle_client, args=(client_sock, addr))
        client_handler.start()