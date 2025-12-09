# ECG-SIGN 프로젝트 문서 & 발표 자료

## 1. 프로젝트 개요
- **목표**: ECG(심전도) 파형의 형태학적 특징을 기반으로 한 2차 인증용 디지털 서명 시스템 구현
- **핵심 가치**: 단순 심박수가 아닌 개인 고유의 파형(서명)을 추출하여 높은 보안성 확보
- **구성 요소**: Arduino + AD8232 센서, Android 앱, Python 기반 ECG 처리/인증 서버

## 2. 시스템 구성도
```
AD8232 + Arduino ──(Bluetooth SPP)──▶ Android 앱 ──(TCP/IP)──▶ Python 서버
       │                                     │                        │
       └──────500Hz 샘플링──────▶ 실시간 그래프  │              ECG Signature Pipeline
                                              └──── 명령/응답(JSON) ───▶ Auth Manager
```

## 3. 사용 기술 요약
- **Hardware**: Arduino UNO, AD8232, HC-06 (9600bps), 500Hz 샘플링
- **Android**: Java, Bluetooth Classic API, TCP Socket, MPAndroidChart
- **Python 서버**: `numpy`, `scipy`, `socket`, `threading`, 커스텀 `ecg_processor` 패키지
- **알고리즘**: Baseline wander 제거, Pan-Tompkins R-peak, 비트 정규화, 다중 도메인 특징 추출, SHA-256 서명, 하이브리드 유사도(코사인+유클리드)

## 4. ECG 처리 파이프라인 (서버)
1. **전처리**: 고/저역 & Notch 필터 → 신호 품질 지표 산출(`quality_score`)
2. **R-peak 검출**: Pan-Tompkins → 생리학적 제약(200-2000ms) 적용
3. **비트 정규화**: R-peak 기준 분할 → Z-score 정규화 → 리샘플링 → 이상치 제거
4. **특징 추출**: 형태학적, HRV, 주파수, 통계 영역 30+ 특징
5. **서명 생성**: 가중치 적용 → Min-Max 정규화 → 8비트 이산화 → SHA-256 해시
6. **인증**: `ECGAuthManager`가 저장된 서명과 유사도 비교, 세션 관리

### 알고리즘 세부 설명
1. **전처리 필터 파이프라인**
   - Butterworth High-pass(0.5Hz, 2차) → Low-pass(45Hz, 4차) → IIR Notch(60Hz, Q=30)
   - `remove_baseline_wander`, `remove_high_frequency_noise`, `remove_powerline_noise`가 순차 호출되며 `scipy.signal.butter/iirnotch + filtfilt`로 위상 지연 없는 양방향 필터링 수행
   - 품질 평가는 `SNR = 10 log10(var(signal) / var(diff(signal))/2)`와 포화/평탄성 감지로 스코어링

2. **Pan-Tompkins R-peak 검출**
   - 5~15Hz 밴드패스 + 5점 미분(`(1/8T)(-z^-2-2z^-1+2z+z^2)`) + 제곱 + 150ms 이동 평균 적분
   - 적응형 임계값 = `mean(signal) + 0.5*std(signal)`을 기본으로, 미검출 시 자동 하향
   - `min_rr_interval=0.2s`, `max_rr_interval=2s` 제약을 적용하고, 통과 후보는 원본 신호에서 ±50ms 윈도우 내 재탐색해 정밀 보정

3. **비트 정규화 & 템플릿 생성**
   - R-peak 기준 `[-250ms, +400ms]` 구간을 슬라이스, Z-score 정규화 후 300 샘플로 선형 리샘플링
   - 중앙값 템플릿과의 Modified Z-score(MAD 기반)를 이용해 이상치 제거, 남은 비트를 가중 평균(중앙값에 가까울수록 가중↑)으로 템플릿 생성

4. **특징 추출 자세히**
   - **형태학적**: `P/Q/R/S/T` 진폭, `PR/QRS/QT/ST` 간격(ms 변환), 각 파 면적(적분), R 상승/하강 기울기 등 20여 항목
   - **HRV(Time-domain)**: RR 간격(300~2000ms 필터링)으로 `mean_rr`, `sdnn`, `rmssd`, `pNN50`, `pNN20`, `cv_rr` 산출
   - **주파수**: FFT → 파워 스펙트럼에서 `LF(0-5Hz)/MF(5-15Hz)/HF(15-40Hz)` 비율, `LF/HF`, 스펙트럼 중심·확산, 지배 주파수, 상위 FFT 계수 5개
   - **통계**: `mean/std/var/max/min`, `skew/kurtosis`, `energy`, `RMS`, `zero-crossing-rate`, `entropy`

5. **디지털 서명 생성**
   - 특징군별 가중치: `morphological 1.5`, `hrv 1.0`, `frequency 0.8`, `statistical 0.7`
   - 전체 벡터를 Min-Max 정규화 → 8비트(0~255) 이산화 → `numpy.ndarray.tobytes()` 후 `hashlib.sha256`으로 해시
   - Base64/Hex 두 형태를 모두 저장해 UI/디버깅에 활용

6. **인증 유사도 계산**
   - `ECGAuthManager`는 저장된 feature vector와 신규 벡터를 각각 Z-score 정규화 후
     - 코사인 유사도(70%) + 유클리드 거리 기반 유사도(30%)의 하이브리드 스코어를 계산
     - `similarity_threshold` 기본 0.80~0.85, 통과 시 세션 발급·JSON 응답

### 파이프라인 실패 처리 (2025-12-05 업데이트)
- 파이프라인 도중 예외 발생 시 **즉시 `status: "error"`** 응답을 반환
- 단순 평균/분산 기반 폴백을 제거하여, 불완전한 데이터가 등록/인증에 사용되지 않도록 보장
- Android 앱은 해당 응답을 수신하면 사용자에게 재측정을 안내

## 5. 발표용 핵심 메시지
| 슬라이드 | 주요 내용 |
| --- | --- |
| 문제 정의 | 비밀번호/OTP는 탈취 위험 → 생체 신호를 활용한 2차 인증 필요 |
| 제안 방식 | ECG 파형의 형태학적 특징을 디지털 서명으로 변환, SHA-256 기반 |
| 시스템 구성 | Hardware → Android → Python Pipeline → Auth Manager 흐름도 |
| 알고리즘 | 전처리, R-peak, 특징 추출, 서명 생성 단계별 시각 자료 |
| 데모 계획 | 센서 ↑ Android 그래프 ↑ 서버 로그/JSON 응답을 순서대로 시연 |
| 결과/한계 | 정상 시 시그니처 생성·로그인 성공, 노이즈 시 재측정 안내, 향후 DB/실시간 모니터링 과제 |

## 6. 데모 시나리오 체크리스트
1. **환경 준비**: `pip install -r requirements.txt`, `python3 ecg_server.py`
2. **Android 설정**: `PYTHON_SERVER_IP`를 서버 IP로 변경 후 빌드/설치
3. **연결 절차**
   - HC-06 페어링 → 앱에서 Bluetooth 연결 → TCP 서버 연결
4. **등록 시연**
   - 사용자 ID 입력 → 확인 다이얼로그 → 5초 안정화 → 6초 수집
   - 서버 로그에서 R-peak/feature count 확인 → 등록 성공 메시지 캡처
5. **로그인 시연**
   - 동일 사용자로 로그인 → 유사도(%) 발표 슬라이드에 표시
6. **실패 시나리오**
   - 전극 분리/노이즈 유발 → `low_quality` 응답 → 앱 팝업으로 재측정 안내

## 7. 기술 세부 요약 (참고용)
- `Hardware/Arduino_Code/main.ino`: 2ms 주기 측정, Bluetooth 전송
- `Software/Android_App/.../MainActivity.java`: Bluetooth/TCP 스레드, 더미 데이터, 진행 UI
- `Software/Signal_Processing/ecg_server.py`: TCP 서버, 버퍼링, 파이프라인 실행, 명령 처리
- `ecg_processor/*`: 모듈화된 전처리·검출·특징·서명·인증 로직

## 8. 향후 발전 아이디어
- JSON → DB 전환, 사용자 데이터 암호화
- 웹 대시보드 및 실시간 스트리밍
- 더 많은 실측 데이터로 임계값 튜닝, 모델 기반 분류기 실험
- ECG + 다른 생체 신호를 결합한 다중 인증

이 문서는 발표 자료 준비 시 바로 슬라이드/대본으로 전환할 수 있도록 구조화되어 있습니다.
