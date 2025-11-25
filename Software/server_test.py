from flask import Flask, request, jsonify
import numpy as np
import neurokit2 as nk

app = Flask(__name__)

def process_ecg_signal(raw_data_list, fs):


@app.route('/process_ecg', methods=['POST'])
def handle_request():

    fs = request.args.get('fs', default=250, type=int)
    raw_bytes = request.data 
    if not raw_bytes:
        return jsonify({"status": "error", "message": "데이터가 없습니다."}), 400

    try:
        raw_string = raw_bytes.decode('utf-8') # 바이트 -> 문자열 변환
        
        str_values = raw_string.strip().split('\n')
        
        raw_data = [float(x) for x in str_values if x.strip()]
        
        print(f" 요청 수신: 데이터 길이 {len(raw_data)}개, fs={fs}Hz")

    except ValueError:
        return jsonify({"status": "error", "message": "데이터 파싱 실패: 숫자가 아닌 값이 포함되어 있습니다."}), 400

    # 처리 로직 
    vector, msg = process_ecg_signal(raw_data, fs)

    # 결과 
    if vector:
        response = {
            "status": "success",
            "feature_vector": vector,
            "message": "서명 생성 성공"
        }
        print(f"처리 성공: {vector}")
        return jsonify(response), 200
    else:
        print(f"처리 실패: {msg}")
        return jsonify({"status": "error", "message": msg}), 500

# 서버 실행 9999번 포트

if __name__ == '__main__':
    # host='0.0.0.0' : 외부(안드로이드 폰)
    # port=9999 : 포트 번호 설정
    print(" ECG 분석 서버가 시작되었습니다. (Port: 9999)")
    app.run(host='0.0.0.0', port=9999)