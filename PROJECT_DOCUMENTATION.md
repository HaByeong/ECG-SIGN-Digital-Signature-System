# 🫀 ECG-SIGN 디지털 서명 시스템 - 프로젝트 종합 문서

## 📋 목차
1. [프로젝트 개요](#프로젝트-개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [프로젝트 구조](#프로젝트-구조)
4. [각 모듈 상세 설명](#각-모듈-상세-설명)
5. [데이터 흐름](#데이터-흐름)
6. [주요 기능](#주요-기능)
7. [설정 및 사용법](#설정-및-사용법)
8. [기술 스택](#기술-스택)
9. [ECG 처리 파이프라인](#ecg-처리-파이프라인)

---

## 프로젝트 개요

### 목적
ECG(심전도) 신호의 고유한 파형 특성을 추출하여 개인을 식별하는 디지털 서명 시스템을 구현합니다. 단순한 심박수가 아닌, **ECG 파형 자체를 '서명(Signature)'으로 활용**하여 사용자 인증을 수행합니다.

### 핵심 개념
- **ECG 파형의 고유성**: P파, QRS 복합체(R-peak), T파 등 주요 파형의 진폭과 간격 정보는 개인마다 고유합니다.
- **디지털 서명 생성**: ECG 신호에서 특징을 추출하고 벡터화하여 SHA-256 해시 기반 서명을 생성합니다.
- **생체 인증**: 사용자 등록 시 ECG 서명을 저장하고, 로그인 시 비교하여 인증합니다.

---

## 시스템 아키텍처

```
┌─────────────────┐
│   Arduino       │
│  (ECG 센서)     │
│  AD8232         │
└────────┬────────┘
         │ Bluetooth (SPP)
         │ (정수 문자열)
         ▼
┌─────────────────┐
│  Android App     │
│  (MainActivity)  │
│  - 데이터 수신   │
│  - 그래프 표시   │
│  - UI 제어       │
└────────┬────────┘
         │ TCP/IP (Socket)
         │ (정수 문자열)
         ▼
┌─────────────────┐
│  Python Server   │
│  (ecg_server.py) │
│  - 데이터 수집   │
│  - ECG 처리      │
│  - 인증 관리     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ECG Processor   │
│  Pipeline        │
│  - 전처리        │
│  - R-peak 검출   │
│  - 특징 추출     │
│  - 서명 생성     │
└─────────────────┘
```

### 통신 프로토콜
1. **Arduino → Android**: Bluetooth Classic (SPP)
   - 데이터 형식: 한 줄에 하나의 정수 (예: `512\n`)
   - 샘플링 레이트: 500Hz (2ms 간격)
   - 데이터 범위: 0-1023 (또는 0-4095, ADC 해상도에 따라)

2. **Android → Python Server**: TCP/IP Socket
   - 데이터 형식: 한 줄에 하나의 정수 문자열
   - 명령어 형식: `CMD:REGISTER:<user_id>`, `CMD:LOGIN`, `CMD:LOGOUT` 등
   - 응답 형식: JSON

---

## 프로젝트 구조

```
ECG-SIGN-Digital-Signature-System/
│
├── Hardware/
│   └── Arduino_Code/
│       └── main.ino              # 아두이노 ECG 센서 읽기 및 블루투스 전송
│
├── Software/
│   ├── Android_App/              # Android 애플리케이션
│   │   └── app/
│   │       └── src/
│   │           └── main/
│   │               ├── AndroidManifest.xml    # 권한 및 액티비티 선언
│   │               ├── java/
│   │               │   └── com/example/ecgapp/
│   │               │       └── MainActivity.java  # 메인 액티비티 (UI + 통신)
│   │               └── res/
│   │                   ├── layout/
│   │                   │   └── activity_main.xml  # UI 레이아웃
│   │                   ├── values/
│   │                   │   └── colors.xml          # 색상 정의
│   │                   └── drawable/               # 버튼, 카드 등 스타일
│   │
│   └── Signal_Processing/        # Python ECG 처리 서버
│       ├── ecg_server.py          # TCP 서버 메인
│       ├── requirements.txt       # Python 의존성
│       ├── user_data/
│       │   └── users.json         # 등록된 사용자 데이터 (ECG 서명 저장)
│       └── ecg_processor/         # ECG 처리 모듈 패키지
│           ├── __init__.py
│           ├── preprocessing.py      # 1. 전처리 (필터링, 노이즈 제거)
│           ├── r_peak_detector.py    # 2. R-peak 검출 (Pan-Tompkins)
│           ├── beat_processor.py   # 3. 비트 처리 (템플릿 생성)
│           ├── feature_extractor.py # 4. 특징 추출 (형태학적, 시간, 주파수, 통계)
│           ├── signature_generator.py # 5. 서명 생성 (벡터화, 해시)
│           ├── pipeline.py          # 통합 파이프라인
│           └── auth_manager.py      # 인증 관리 (등록/로그인/로그아웃)
│
└── Docs/
    └── README.md
```

---

## 각 모듈 상세 설명

### 1. Hardware (Arduino)

#### `Hardware/Arduino_Code/main.ino`
**역할**: AD8232 ECG 센서에서 아날로그 데이터를 읽어 Bluetooth로 전송

**주요 기능**:
- AD8232 센서의 OUTPUT 핀(A0)에서 아날로그 값 읽기
- 500Hz 샘플링 (2ms 간격)
- HC-06 Bluetooth 모듈을 통해 데이터 전송
- 각 샘플을 한 줄에 하나씩 전송 (예: `512\n`)

**설정**:
- `SAMPLE_DELAY = 2` (500Hz)
- `ECG_OUTPUT = A0`
- Bluetooth: 9600 baud

---

### 2. Android App

#### `MainActivity.java`
**역할**: 사용자 인터페이스, Bluetooth/TCP 통신, ECG 데이터 시각화

**주요 클래스/메서드**:

1. **Bluetooth 통신**
   - `initBluetooth()`: Bluetooth 어댑터 초기화
   - `connectToPairedDevice()`: 페어링된 HC-06 장치 연결
   - `ConnectedThread`: Bluetooth 데이터 수신 스레드
     - `readLine()`으로 한 줄씩 읽기
     - 정수로 파싱하여 그래프에 표시
     - TCP 서버로 전송

2. **TCP 통신**
   - `TcpClientSender`: Python 서버와 TCP 통신
     - `sendData(int value)`: ECG 데이터 전송
     - `sendCommand(String cmd)`: 명령어 전송 (REGISTER, LOGIN, LOGOUT 등)
     - `resultReceiver()`: 서버 응답 수신 및 처리

3. **인증 기능**
   - `startRegister()`: 사용자 등록 시작
   - `startLogin()`: 로그인 시작
   - `doLogout()`: 로그아웃
   - `handleAuthResponse()`: 서버 응답 처리

4. **더미 데이터 생성**
   - `toggleDummyData()`: 더미 ECG 데이터 생성/중지
   - `generateDummyECGData()`: 테스트용 ECG 파형 시뮬레이션

5. **UI 관리**
   - `initChart()`: ECG 그래프 초기화
   - `addEntry()`: 그래프에 데이터 포인트 추가
   - `updateProgress()`: 진행 상태 표시
   - `showProgress()`, `hideProgress()`: 진행 바 표시/숨김

**설정 상수**:
```java
private final String PYTHON_SERVER_IP = "192.168.219.59";  // 서버 IP 주소
private final int PYTHON_SERVER_PORT = 9999;
private static final String TARGET_DEVICE_NAME = "HC-06";
private static final UUID SPP_UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
```

#### `activity_main.xml`
**역할**: 앱 UI 레이아웃 정의

**주요 UI 요소**:
- 연결 상태 배지 (`connectionBadge`)
- 블루투스/TCP 연결 버튼
- 사용자 ID 입력 필드 (`userIdEditText`)
- 등록/로그인/로그아웃 버튼
- 더미 데이터 생성 버튼
- 사용자 목록/삭제 버튼
- ECG 그래프 (`LineChart`)
- 진행 상태 표시 (`ProgressBar`, `TextView`)

---

### 3. Python Server

#### `ecg_server.py`
**역할**: TCP 서버로 ECG 데이터 수신, 처리, 인증 관리

**주요 클래스**:

1. **ECGProcessor**
   - `add_sample(value)`: 샘플 추가, 버퍼가 가득 차면 True 반환
   - `process()`: 버퍼의 ECG 데이터를 파이프라인으로 처리
   - `clear_buffer()`: 버퍼 초기화

2. **ClientHandler** (Thread)
   - 각 클라이언트 연결을 별도 스레드로 처리
   - `handle_command()`: 명령어 파싱 및 처리
     - `CMD:REGISTER:<user_id>`: 등록 모드 시작
     - `CMD:LOGIN` 또는 `CMD:LOGIN:<user_id>`: 로그인 모드 시작
     - `CMD:LOGOUT`: 로그아웃
     - `CMD:STATUS`: 상태 확인
     - `CMD:USERS`: 사용자 목록
     - `CMD:DELETE:<user_id>`: 사용자 삭제
   - `handle_ecg_data()`: ECG 데이터 수신 및 버퍼에 추가
   - `complete_registration()`: 등록 완료 처리
   - `complete_login()`: 로그인 완료 처리

3. **ECGServer**
   - TCP 서버 시작/종료
   - 클라이언트 연결 수락 및 `ClientHandler` 생성

**설정 상수**:
```python
HOST = '0.0.0.0'              # 모든 인터페이스에서 수신
PORT = 9999                   # 서버 포트
BUFFER_SIZE = 10000           # 처리할 샘플 수 (20초, 500Hz 기준)
SAMPLING_RATE = 500           # 샘플링 주파수 (Hz)
SIMILARITY_THRESHOLD = 0.75   # 인증 유사도 임계값
```

---

### 4. ECG Processor Modules

#### `preprocessing.py` - 전처리
**역할**: ECG 신호의 노이즈 제거 및 품질 향상

**주요 기능**:
- `ECGPreprocessor` 클래스
  - `process()`: 전체 전처리 파이프라인 실행
  - `remove_baseline_wander()`: 고주파 필터로 baseline wander 제거
  - `remove_high_frequency_noise()`: 저주파 필터로 고주파 노이즈 제거
  - `remove_powerline_interference()`: Notch 필터로 60Hz 전원 노이즈 제거
  - `assess_quality()`: 신호 품질 평가 (SNR, 변동성 등)

**필터 설정**:
- Baseline wander 제거: 고주파 필터 (cutoff: 0.5Hz)
- 고주파 노이즈 제거: 저주파 필터 (cutoff: 40Hz)
- 전원 노이즈 제거: Notch 필터 (60Hz)

---

#### `r_peak_detector.py` - R-peak 검출
**역할**: Pan-Tompkins 알고리즘으로 R-peak 검출

**주요 기능**:
- `PanTompkinsDetector` 클래스
  - `detect()`: R-peak 검출 실행
  - `_bandpass_filter()`: 밴드패스 필터 (5-15Hz) - QRS 복합체 강조
  - `_differentiate()`: 5점 미분 필터 - 기울기 강조
  - `_moving_average()`: 이동 평균 (150ms 윈도우) - 적분
  - `_find_peaks()`: 적응형 임계값으로 피크 검출
  - `_refine_peaks()`: 원본 신호에서 정확한 R-peak 위치 재검색
  - `_calculate_heart_rate()`: 평균 심박수 계산

**Pan-Tompkins 알고리즘 단계**:
1. 밴드패스 필터 (5-15Hz)
2. 미분 필터: `H(z) = (1/8T)(-z^-2 - 2z^-1 + 2z + z^2)`
3. 제곱 (양수화 및 증폭)
4. 이동 평균 적분 (150ms)
5. 적응형 임계값 피크 검출
6. RR 간격 제약 조건 적용 (200ms ~ 2000ms)

---

#### `beat_processor.py` - 비트 처리
**역할**: R-peak 기준으로 비트 분할 및 대표 템플릿 생성

**주요 기능**:
- `BeatProcessor` 클래스
  - `process_beats()`: 비트 처리 실행
  - `segment_beats()`: R-peak 기준으로 비트 분할
    - R-peak 이전 250ms, 이후 400ms
  - `resample_beats()`: 모든 비트를 동일한 길이로 리샘플링
  - `normalize_amplitude()`: 진폭 정규화
  - `reject_outliers()`: 이상치 비트 제거 (Z-score 기반)
  - `generate_template()`: 유효한 비트들의 평균 템플릿 생성

**처리 과정**:
1. 각 R-peak 주변으로 비트 분할
2. 리샘플링으로 길이 통일
3. 진폭 정규화
4. 이상치 제거
5. 평균 템플릿 계산

---

#### `feature_extractor.py` - 특징 추출
**역할**: ECG 템플릿에서 다양한 특징 추출

**주요 기능**:
- `FeatureExtractor` 클래스
  - `extract_all_features()`: 모든 특징 추출
  - `extract_morphological_features()`: 형태학적 특징
    - P, Q, R, S, T 파의 진폭
    - QRS 지속 시간, PR 간격, QT 간격
    - ST 세그먼트 높이
    - P/R, T/R 비율
    - R 파 기울기 (상승/하강)
    - 각 파형의 면적
  - `extract_hrv_features()`: 시간 영역 HRV 특징
    - 평균 RR 간격, 표준편차 (SDNN)
    - RMSSD, pNN50
    - 변동계수 (CV)
  - `extract_frequency_features()`: 주파수 영역 특징
    - FFT 변환
    - LF, MF, HF 파워
    - LF/HF 비율
    - 스펙트럼 중심, 확산
    - 주요 주파수
    - 상위 FFT 계수
  - `extract_statistical_features()`: 통계적 특징
    - 평균, 표준편차
    - 왜도 (skewness), 첨도 (kurtosis)
    - 에너지, RMS
    - 제로 크로싱 비율
    - 엔트로피

---

#### `signature_generator.py` - 서명 생성
**역할**: 추출된 특징을 디지털 서명으로 변환

**주요 기능**:
- `SignatureGenerator` 클래스
  - `generate_signature()`: 서명 생성 파이프라인
  - `features_to_vector()`: 특징 딕셔너리를 벡터로 변환
    - 형태학적 특징 (가중치: 1.5)
    - HRV 특징 (가중치: 1.0)
    - 주파수 특징 (가중치: 0.8)
    - 통계적 특징 (가중치: 0.7)
  - `normalize_vector()`: 벡터 정규화 (Min-Max, Z-score, L2)
  - `discretize_vector()`: 연속 벡터를 이산 값으로 변환 (8비트)
  - `create_hash()`: SHA-256 해시 생성
    - 이산화된 벡터를 바이트로 변환
    - SHA-256 해시 계산
    - 16진수 및 Base64 인코딩
  - `compare_signatures()`: 두 서명 비교 (코사인 유사도)

**서명 생성 과정**:
1. 특징 벡터화 (가중치 적용)
2. 정규화 (Min-Max: 0-1 범위)
3. 이산화 (0-255 정수)
4. SHA-256 해시 생성
5. 16진수 문자열로 변환

---

#### `pipeline.py` - 통합 파이프라인
**역할**: 모든 모듈을 연결하여 end-to-end 처리

**주요 기능**:
- `ECGSignaturePipeline` 클래스
  - `process()`: 전체 ECG 처리 파이프라인 실행
    1. 전처리
    2. R-peak 검출
    3. 비트 처리
    4. 특징 추출
    5. 서명 생성
  - `process_streaming()`: 스트리밍 데이터 처리
  - `get_summary()`: 처리 결과 요약
  - `compare_ecg()`: 두 ECG 신호 비교

**처리 흐름**:
```
ECG 신호 입력
    ↓
[1] 전처리 (노이즈 제거)
    ↓
[2] R-peak 검출 (Pan-Tompkins)
    ↓
[3] 비트 처리 (템플릿 생성)
    ↓
[4] 특징 추출 (형태학적, 시간, 주파수, 통계)
    ↓
[5] 서명 생성 (벡터화 → 정규화 → 이산화 → 해시)
    ↓
디지털 서명 (SHA-256 해시)
```

---

#### `auth_manager.py` - 인증 관리
**역할**: 사용자 등록, 로그인, 로그아웃, 세션 관리

**주요 기능**:
- `ECGAuthManager` 클래스
  - `register(user_id, ecg_signature)`: 사용자 등록
    - ECG 서명을 `user_data/users.json`에 저장
    - 사용자 ID는 소문자로 변환하여 저장
  - `login(ecg_signature, user_id=None)`: 로그인
    - `user_id`가 제공되면 해당 사용자와만 비교
    - 제공되지 않으면 모든 등록된 사용자와 비교
    - 코사인 유사도로 비교 (임계값: 0.75)
  - `logout(session_id)`: 로그아웃 (세션 무효화)
  - `get_user_list()`: 등록된 사용자 목록 반환
  - `delete_user(user_id, session_id)`: 사용자 삭제
  - `_load_users()`, `_save_users()`: JSON 파일로 사용자 데이터 영구 저장

**데이터 저장 형식** (`users.json`):
```json
{
  "user_id": {
    "signature_hex": "abc123...",
    "feature_vector": [...],
    "registered_at": "2025-11-26T10:00:00",
    "last_login": "2025-11-26T10:05:00"
  }
}
```

---

## 데이터 흐름

### 1. 등록 프로세스

```
[사용자] Android 앱에서 사용자 ID 입력 + "등록" 버튼 클릭
    ↓
[Android] TCP 서버로 "CMD:REGISTER:<user_id>" 전송
    ↓
[Python Server] 등록 모드 시작, 버퍼 초기화, "ready" 응답 전송
    ↓
[Android] "ready" 응답 수신 → 진행 바 표시, 더미 데이터 생성 시작
    ↓
[Android] ECG 데이터를 TCP로 전송 (10000개 샘플)
    ↓
[Python Server] 데이터 수신 및 버퍼에 저장
    ↓
[Python Server] 버퍼가 가득 차면 (10000개) ECG 처리 시작
    ↓
[Python Server] ECG 파이프라인 실행:
    - 전처리 → R-peak 검출 → 비트 처리 → 특징 추출 → 서명 생성
    ↓
[Python Server] ECG 서명을 users.json에 저장
    ↓
[Python Server] "등록 완료" JSON 응답 전송
    ↓
[Android] 응답 수신 → 진행 바 숨김, "등록 완료" 메시지 표시
```

### 2. 로그인 프로세스

```
[사용자] Android 앱에서 "로그인" 버튼 클릭 (선택적으로 사용자 ID 입력)
    ↓
[Android] TCP 서버로 "CMD:LOGIN" 또는 "CMD:LOGIN:<user_id>" 전송
    ↓
[Python Server] 로그인 모드 시작, 버퍼 초기화, "ready" 응답 전송
    ↓
[Android] "ready" 응답 수신 → 진행 바 표시, 더미 데이터 생성 시작
    ↓
[Android] ECG 데이터를 TCP로 전송 (10000개 샘플)
    ↓
[Python Server] 데이터 수신 및 버퍼에 저장
    ↓
[Python Server] 버퍼가 가득 차면 ECG 처리 시작
    ↓
[Python Server] ECG 파이프라인 실행하여 서명 생성
    ↓
[Python Server] 저장된 사용자 서명과 비교 (코사인 유사도)
    ↓
[Python Server] 유사도가 임계값(0.75) 이상이면 "로그인 성공" 응답
    ↓
[Android] 응답 수신 → 진행 바 숨김, "로그인 완료" 메시지 표시
```

### 3. ECG 데이터 전송 형식

**Bluetooth (Arduino → Android)**:
```
512\n
513\n
514\n
...
```

**TCP (Android → Python Server)**:
```
512
513
514
...
```

**서버 명령어 형식**:
```
CMD:REGISTER:user123
CMD:LOGIN
CMD:LOGIN:user123
CMD:LOGOUT
CMD:STATUS
CMD:USERS
CMD:DELETE:user123
```

**서버 응답 형식 (JSON)**:
```json
{
  "type": "ready",
  "message": "등록 모드 시작",
  "required_samples": 10000
}
```

```json
{
  "type": "register_success",
  "message": "등록 완료",
  "user_id": "user123",
  "signature_hash": "abc123..."
}
```

```json
{
  "type": "login_success",
  "message": "로그인 성공",
  "user_id": "user123",
  "similarity": 0.85,
  "session_id": "session_abc123"
}
```

---

## 주요 기능

### 1. 사용자 등록
- 사용자 ID 입력
- ECG 데이터 수집 (10000 샘플, 약 20초)
- ECG 서명 생성 및 저장
- 중복 등록 방지 (이미 등록된 사용자 ID 체크)

### 2. 로그인
- ECG 데이터 수집 (10000 샘플)
- 저장된 서명과 비교
- 유사도 임계값(0.75) 이상이면 성공
- 특정 사용자 ID로 로그인 또는 전체 검색

### 3. 로그아웃
- 현재 세션 무효화
- 로그인 상태 해제

### 4. 사용자 관리
- 등록된 사용자 목록 조회
- 사용자 삭제

### 5. 더미 데이터 생성
- 실제 센서 없이 테스트 가능
- ECG 파형 시뮬레이션
- 등록/로그인 테스트용

### 6. 실시간 ECG 그래프
- 수신된 ECG 데이터를 실시간으로 그래프에 표시
- 최대 500개 포인트 유지 (슬라이딩 윈도우)

---

## 설정 및 사용법

### 1. Python 서버 실행

**필요 패키지 설치**:
```bash
cd Software/Signal_Processing
pip3 install -r requirements.txt
```

**서버 실행**:
```bash
python3 ecg_server.py
```

**서버 출력 예시**:
```
============================================================
  🫀 ECG 디지털 서명 인증 서버
============================================================
  호스트: 0.0.0.0
  포트: 9999
  로컬 IP: 192.168.219.59
  샘플링 레이트: 500 Hz
  버퍼 크기: 10000 샘플 (20.0초)
  인증 임계값: 0.75
  파이프라인: ✅ 활성화
============================================================

📱 Android 앱 설정:
   PYTHON_SERVER_IP = "192.168.219.59"
   PYTHON_SERVER_PORT = 9999
```

### 2. Android 앱 설정

**서버 IP 주소 설정** (`MainActivity.java`):
```java
private final String PYTHON_SERVER_IP = "192.168.219.59";  // 서버 IP로 변경
private final int PYTHON_SERVER_PORT = 9999;
```

**서버 IP 확인 방법**:
- 서버 실행 시 출력된 "로컬 IP" 사용
- 또는 터미널에서:
  ```bash
  ifconfig | grep "inet " | grep -v 127.0.0.1
  ```

### 3. Arduino 설정

**샘플링 레이트** (`main.ino`):
```cpp
const int SAMPLE_DELAY = 2;  // 500Hz (2ms 간격)
```

**Bluetooth 모듈**:
- HC-06 모듈 사용
- 페어링 이름: "HC-06" (또는 `TARGET_DEVICE_NAME` 수정)
- 통신 속도: 9600 baud

### 4. 사용 순서

1. **Python 서버 실행**
   ```bash
   cd Software/Signal_Processing
   python3 ecg_server.py
   ```

2. **Android 앱 실행**
   - 서버 IP 주소 확인 및 설정
   - 앱 빌드 및 설치

3. **블루투스 연결** (선택사항, 테스트 모드에서는 생략 가능)
   - HC-06 모듈 페어링
   - 앱에서 "📶 블루투스" 버튼 클릭

4. **TCP 서버 연결**
   - 앱에서 "TCP 서버 연결" 버튼 클릭

5. **등록/로그인**
   - 사용자 ID 입력 (등록 시)
   - "등록" 또는 "로그인" 버튼 클릭
   - 더미 데이터 생성 또는 실제 센서 데이터 수집
   - 진행 상태 확인

---

## 기술 스택

### Hardware
- **Arduino**: ECG 센서 데이터 읽기
- **AD8232**: ECG 센서 모듈
- **HC-06**: Bluetooth 모듈 (SPP)

### Android
- **언어**: Java
- **최소 SDK**: Android API 21 (Android 5.0)
- **주요 라이브러리**:
  - MPAndroidChart: ECG 그래프 표시
  - Android Bluetooth API: Bluetooth 통신
  - Java Socket: TCP 통신

### Python Server
- **언어**: Python 3
- **주요 라이브러리**:
  - `numpy`: 수치 계산
  - `scipy`: 신호 처리 (필터, FFT 등)
  - `socket`: TCP 서버
  - `threading`: 멀티 클라이언트 처리
  - `json`: 데이터 직렬화

### 알고리즘
- **Pan-Tompkins 알고리즘**: R-peak 검출
- **디지털 필터링**: Butterworth 필터 (고주파, 저주파, Notch)
- **특징 추출**: 형태학적, 시간 영역, 주파수 영역, 통계적 특징
- **서명 생성**: 벡터화 → 정규화 → 이산화 → SHA-256 해시
- **인증**: 코사인 유사도 기반 비교

---

## ECG 처리 파이프라인

### 상세 처리 단계

#### 1단계: 전처리 (`preprocessing.py`)
```
원본 ECG 신호
    ↓
Baseline Wander 제거 (고주파 필터, 0.5Hz)
    ↓
고주파 노이즈 제거 (저주파 필터, 40Hz)
    ↓
전원 노이즈 제거 (Notch 필터, 60Hz)
    ↓
신호 품질 평가 (SNR, 변동성)
    ↓
전처리된 ECG 신호
```

#### 2단계: R-peak 검출 (`r_peak_detector.py`)
```
전처리된 ECG
    ↓
밴드패스 필터 (5-15Hz) → QRS 복합체 강조
    ↓
미분 필터 (5점) → 기울기 강조
    ↓
제곱 → 양수화 및 증폭
    ↓
이동 평균 (150ms) → 적분
    ↓
적응형 임계값 피크 검출
    ↓
RR 간격 제약 조건 적용 (200ms ~ 2000ms)
    ↓
원본 신호에서 정확한 위치 재검색
    ↓
R-peak 위치 배열
```

#### 3단계: 비트 처리 (`beat_processor.py`)
```
R-peak 위치 + 전처리된 ECG
    ↓
각 R-peak 주변으로 비트 분할 (이전 250ms, 이후 400ms)
    ↓
리샘플링으로 길이 통일
    ↓
진폭 정규화
    ↓
이상치 제거 (Z-score 기반)
    ↓
평균 템플릿 계산
    ↓
대표 템플릿 (평균 비트)
```

#### 4단계: 특징 추출 (`feature_extractor.py`)
```
대표 템플릿 + R-peak 위치
    ↓
┌─────────────────────────────────────┐
│ 형태학적 특징                        │
│ - P, Q, R, S, T 파 진폭             │
│ - QRS 지속 시간, PR/QT 간격          │
│ - ST 세그먼트, 파형 비율             │
│ - 기울기, 면적                       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 시간 영역 특징 (HRV)                 │
│ - 평균 RR 간격, SDNN                │
│ - RMSSD, pNN50                      │
│ - 변동계수                          │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 주파수 영역 특징                      │
│ - FFT 변환                           │
│ - LF, MF, HF 파워                    │
│ - 스펙트럼 중심, 확산                │
│ - 주요 주파수, 상위 FFT 계수         │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 통계적 특징                          │
│ - 평균, 표준편차                     │
│ - 왜도, 첨도                         │
│ - 에너지, RMS                        │
│ - 제로 크로싱 비율, 엔트로피         │
└─────────────────────────────────────┘
    ↓
특징 딕셔너리
```

#### 5단계: 서명 생성 (`signature_generator.py`)
```
특징 딕셔너리
    ↓
특징 벡터화 (가중치 적용)
    - 형태학적: 1.5
    - HRV: 1.0
    - 주파수: 0.8
    - 통계적: 0.7
    ↓
정규화 (Min-Max: 0-1 범위)
    ↓
이산화 (0-255 정수, 8비트)
    ↓
SHA-256 해시 생성
    ↓
16진수 문자열 변환
    ↓
디지털 서명 (64자 16진수)
```

### 특징 벡터 구성

전체 특징 벡터는 다음과 같이 구성됩니다:

1. **형태학적 특징** (16개 × 1.5 가중치)
   - R, Q, S, P, T 진폭
   - QRS 지속 시간, PR 간격, QT 간격
   - ST 세그먼트, P/R 비율, T/R 비율
   - R 상승/하강 기울기
   - QRS, P, T 면적

2. **HRV 특징** (6개 × 1.0 가중치)
   - 평균 RR, 표준편차 RR
   - SDNN, RMSSD, pNN50
   - 변동계수

3. **주파수 특징** (7개 + 상위 FFT 계수 × 0.8 가중치)
   - LF, MF, HF 파워
   - LF/HF 비율
   - 스펙트럼 중심, 확산
   - 주요 주파수
   - 상위 FFT 계수 (일반적으로 10개)

4. **통계적 특징** (8개 × 0.7 가중치)
   - 평균, 표준편차
   - 왜도, 첨도
   - 에너지, RMS
   - 제로 크로싱 비율, 엔트로피

**총 특징 벡터 크기**: 약 37-47개 (FFT 계수 개수에 따라 변동)

---

## 파일별 상세 정보

### Android App 파일

#### `MainActivity.java` 주요 메서드

**Bluetooth 관련**:
- `initBluetooth()`: Bluetooth 어댑터 초기화
- `connectToPairedDevice()`: 페어링된 장치 연결
- `ConnectedThread.run()`: 데이터 수신 루프

**TCP 통신 관련**:
- `startTcpClient()`: TCP 클라이언트 시작
- `TcpClientSender.sendData()`: ECG 데이터 전송
- `TcpClientSender.sendCommand()`: 명령어 전송
- `TcpClientSender.resultReceiver()`: 서버 응답 수신

**인증 관련**:
- `startRegister()`: 등록 시작
- `startLogin()`: 로그인 시작
- `doLogout()`: 로그아웃
- `handleAuthResponse()`: 서버 응답 처리
- `handleUserListResponse()`: 사용자 목록 응답 처리
- `handleUserDeleteResponse()`: 사용자 삭제 응답 처리

**더미 데이터**:
- `toggleDummyData()`: 더미 데이터 토글
- `generateDummyECGData()`: 더미 ECG 파형 생성

**UI 관련**:
- `initChart()`: 그래프 초기화
- `addEntry()`: 그래프에 데이터 추가
- `showProgress()`, `hideProgress()`: 진행 바 표시/숨김
- `updateProgress()`: 진행 상태 업데이트

### Python Server 파일

#### `ecg_server.py` 주요 메서드

**ECGProcessor**:
- `add_sample(value)`: 샘플 추가, 버퍼 가득 차면 True
- `process()`: 버퍼 데이터 처리
- `clear_buffer()`: 버퍼 초기화

**ClientHandler**:
- `handle_command()`: 명령어 처리
- `start_register_mode()`: 등록 모드 시작
- `start_login_mode()`: 로그인 모드 시작
- `handle_ecg_data()`: ECG 데이터 수신
- `complete_registration()`: 등록 완료
- `complete_login()`: 로그인 완료
- `do_logout()`: 로그아웃
- `send_user_list()`: 사용자 목록 전송
- `delete_user()`: 사용자 삭제
- `send_response()`: JSON 응답 전송

**ECGServer**:
- `start()`: 서버 시작
- `get_local_ip()`: 로컬 IP 주소 가져오기
- `stop()`: 서버 종료

---

## 문제 해결 (Troubleshooting)

### 1. TCP 연결 실패
- **원인**: 서버 IP 주소가 잘못되었거나 방화벽 차단
- **해결**: 
  - 서버 실행 시 출력된 "로컬 IP" 확인
  - Android 앱의 `PYTHON_SERVER_IP` 수정
  - 같은 네트워크(WiFi)에 연결되어 있는지 확인

### 2. 블루투스 연결 실패
- **원인**: HC-06 모듈이 꺼져 있거나 이미 다른 장치에 연결됨
- **해결**:
  - HC-06 전원 확인
  - 다른 장치에서 연결 해제
  - 거리 확인 (너무 멀면 안 됨)
  - 재페어링

### 3. "이미 등록된 사용자" 오류
- **원인**: 동일한 사용자 ID로 이미 등록됨
- **해결**: 다른 사용자 ID 사용 또는 기존 사용자 삭제

### 4. 로그인 실패
- **원인**: ECG 서명이 임계값(0.75) 미만
- **해결**:
  - 더 많은 샘플 수집 (현재 10000개)
  - 신호 품질 확인
  - 등록 시와 동일한 조건에서 측정

### 5. 서버 포트 이미 사용 중
- **원인**: 이전 서버 프로세스가 종료되지 않음
- **해결**:
  ```bash
  # 포트 사용 중인 프로세스 확인
  lsof -i :9999
  
  # 프로세스 종료
  kill -9 <PID>
  ```

---

## 개발 참고사항

### 코드 수정 시 주의사항

1. **서버 IP 주소**: Android 앱과 Python 서버의 IP/포트 일치 확인
2. **샘플링 레이트**: Arduino, Android, Python 서버 모두 500Hz로 통일
3. **버퍼 크기**: 서버의 `BUFFER_SIZE`와 Android의 `requiredSamples` 일치
4. **네트워크 스레드**: Android에서 네트워크 작업은 별도 스레드에서 수행
5. **JSON 응답 형식**: 서버 응답 형식 변경 시 Android의 파싱 코드도 수정 필요

### 확장 가능성

1. **다중 사용자 동시 접속**: 현재 구현되어 있음 (스레드 기반)
2. **데이터베이스 연동**: `users.json` 대신 SQLite/PostgreSQL 사용 가능
3. **암호화**: ECG 서명 저장 시 추가 암호화 적용 가능
4. **웹 대시보드**: Flask/FastAPI로 웹 인터페이스 추가 가능
5. **실시간 스트리밍**: WebSocket으로 실시간 ECG 모니터링 가능

---

## 작성일
2025-11-26


---

**이 문서는 프로젝트의 전체 구조와 동작 방식을 이해하기 위한 종합 가이드입니다.**
**추가 질문이나 수정 사항이 있으면 언제든지 문의하세요.**

