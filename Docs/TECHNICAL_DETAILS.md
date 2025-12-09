# ECG-SIGN 프로젝트 기술 상세 문서

## 목차
1. [프로젝트 개요](#1-프로젝트-개요)
2. [시스템 아키텍처](#2-시스템-아키텍처)
3. [하드웨어 구성](#3-하드웨어-구성)
4. [Android 애플리케이션](#4-android-애플리케이션)
5. [Python 서버](#5-python-서버)
6. [ECG 신호 처리 파이프라인](#6-ecg-신호-처리-파이프라인)
7. [인증 시스템](#7-인증-시스템)
8. [데이터 흐름 요약](#8-데이터-흐름-요약)

---

## 1. 프로젝트 개요

### 1.1 프로젝트 목표
ECG(심전도) 신호의 **형태학적 특징**을 추출하여 개인을 식별하는 **2차 인증용 디지털 서명 시스템**을 구현합니다.

### 1.2 왜 ECG인가?
- **고유성**: ECG 파형(P파, QRS 복합체, T파)의 형태, 간격, 진폭은 개인마다 다릅니다.
- **위조 불가**: 지문이나 얼굴과 달리 살아있는 사람에게서만 측정 가능합니다.
- **연속 인증**: 착용형 기기로 지속적인 본인 확인이 가능합니다.

### 1.3 시스템 구성 요소
| 구성 요소 | 역할 |
|-----------|------|
| Arduino + AD8232 | ECG 신호 측정 및 디지털 변환 |
| HC-06 Bluetooth | 무선 데이터 전송 |
| Android 앱 | 데이터 수신, 시각화, 서버 통신 |
| Python 서버 | ECG 처리, 서명 생성, 인증 관리 |

---

## 2. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           전체 시스템 흐름                                │
└─────────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
    │   Arduino    │         │   Android    │         │   Python     │
    │   + AD8232   │────────▶│     App      │────────▶│   Server     │
    │   + HC-06    │Bluetooth│              │  TCP/IP │              │
    └──────────────┘  SPP    └──────────────┘         └──────────────┘
           │                        │                        │
           ▼                        ▼                        ▼
    ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
    │ 500Hz 샘플링  │         │ 실시간 그래프 │         │ ECG Pipeline │
    │ 아날로그→디지털│         │ 명령어 전송   │         │ 특징 추출     │
    │ 정수 문자열    │         │ 응답 처리     │         │ 서명 생성     │
    └──────────────┘         └──────────────┘         │ 사용자 인증   │
                                                      └──────────────┘
```

### 2.1 통신 프로토콜
| 구간 | 프로토콜 | 데이터 형식 | 속도 |
|------|----------|-------------|------|
| Arduino → Android | Bluetooth SPP (Serial Port Profile) | 정수 문자열 + 줄바꿈 (`512\n`) | 9600 bps |
| Android → Python | TCP/IP Socket | 정수 문자열 또는 명령어 (`CMD:REGISTER:user1`) | 로컬 네트워크 |
| Python → Android | TCP/IP Socket | JSON 형식 응답 | 로컬 네트워크 |

---

## 3. 하드웨어 구성

### 3.1 AD8232 ECG 센서 모듈

**AD8232란?**
- Analog Devices에서 제작한 **단일 리드 심박 모니터 IC**입니다.
- 의료용이 아닌 **피트니스/웨어러블 용도**로 설계되었습니다.
- 내부에 계측 증폭기, 필터, 증폭 회로가 통합되어 있습니다.

**동작 원리**
```
피부 전극 → 미세 전압(mV) → AD8232 증폭 → 아날로그 출력(0~3.3V) → Arduino ADC
```

**핀 연결**
| AD8232 핀 | Arduino 핀 | 설명 |
|-----------|------------|------|
| GND | GND | 접지 |
| 3.3V | 3.3V | 전원 공급 |
| OUTPUT | A0 | ECG 아날로그 신호 출력 |
| LO+ | (미사용) | 리드 오프 감지 + |
| LO- | (미사용) | 리드 오프 감지 - |

**전극 배치 (3-리드 구성)**
```
    RA (오른팔)           LA (왼팔)
         ●───────────────────●
                  │
                  │
                  │
                  ●
              RL (오른다리)
              = 기준 전극
```

### 3.2 Arduino UNO

**역할**: AD8232의 아날로그 출력을 디지털로 변환하여 Bluetooth로 전송

**ADC (Analog-to-Digital Converter) 사양**
- 해상도: **10비트** (0~1023 범위)
- 기준 전압: 5V
- 샘플링: `analogRead()` 함수 사용

**코드 핵심 부분**
```cpp
// 샘플링 주기: 2ms = 500Hz
const int SAMPLE_DELAY = 2;

void loop() {
    // ADC 값 읽기 (0~1023)
    int ecgValue = analogRead(A0);
    
    // Bluetooth로 전송 (정수 문자열)
    bluetooth.println(ecgValue);
    
    // 500Hz 유지
    delay(SAMPLE_DELAY);
}
```

**왜 500Hz인가?**
- ECG 신호의 주요 주파수 성분은 0.5~40Hz입니다.
- 나이퀴스트 정리: 최소 **2 × 40Hz = 80Hz** 이상 필요
- 500Hz는 충분한 여유를 두어 **파형 왜곡 없이** 샘플링합니다.
- Pan-Tompkins 알고리즘은 일반적으로 200~500Hz에서 동작합니다.

### 3.3 HC-06 Bluetooth 모듈

**HC-06이란?**
- **Bluetooth 2.0 SPP(Serial Port Profile)** 지원 모듈
- 마스터/슬레이브 중 **슬레이브 전용** (연결 대기만 가능)
- 기본 보드레이트: **9600 bps**
- 페어링 비밀번호: 1234 또는 0000

**Arduino 연결**
```
Arduino 핀 10 (RX) ← HC-06 TX
Arduino 핀 11 (TX) → HC-06 RX
```

**SoftwareSerial 사용 이유**
- Arduino UNO의 하드웨어 시리얼(0, 1번 핀)은 USB 통신에 사용됨
- HC-06과 PC 디버깅을 동시에 하려면 **소프트웨어 시리얼** 필요

```cpp
#include <SoftwareSerial.h>
SoftwareSerial bluetooth(10, 11);  // RX, TX

void setup() {
    Serial.begin(9600);      // PC 디버깅용
    bluetooth.begin(9600);   // HC-06 통신용
}
```

---

## 4. Android 애플리케이션

### 4.1 사용 기술 스택

| 기술 | 용도 | 선택 이유 |
|------|------|-----------|
| Java | 앱 개발 언어 | Android 네이티브, 안정성 |
| Bluetooth Classic API | HC-06 통신 | SPP 프로토콜 지원 |
| TCP Socket | 서버 통신 | 실시간 양방향 통신 |
| MPAndroidChart | ECG 그래프 | 실시간 라인 차트 지원 |
| Handler + Thread | 비동기 처리 | UI 스레드 분리 |

### 4.2 Bluetooth 통신 구현

**SPP UUID**
```java
// Bluetooth Serial Port Profile 표준 UUID
private static final UUID SPP_UUID = 
    UUID.fromString("00001101-0000-1000-8000-00805F9B34FB");
```

**연결 과정**
```java
// 1. 페어링된 장치 목록에서 HC-06 찾기
Set<BluetoothDevice> pairedDevices = bluetoothAdapter.getBondedDevices();
for (BluetoothDevice device : pairedDevices) {
    if ("HC-06".equals(device.getName())) {
        targetDevice = device;
        break;
    }
}

// 2. RFCOMM 소켓 생성 및 연결
bluetoothSocket = targetDevice.createRfcommSocketToServiceRecord(SPP_UUID);
bluetoothSocket.connect();

// 3. 데이터 수신 스레드 시작
connectedThread = new ConnectedThread(bluetoothSocket);
connectedThread.start();
```

**데이터 수신 (ConnectedThread)**
```java
public void run() {
    BufferedReader reader = new BufferedReader(
        new InputStreamReader(socket.getInputStream())
    );
    
    while (true) {
        String line = reader.readLine();  // "512\n" 형태
        int ecgValue = Integer.parseInt(line.trim());
        
        // UI 업데이트 (Handler 사용)
        handler.post(() -> {
            addEntry(ecgValue);  // 그래프에 추가
        });
        
        // TCP 서버로 전송
        if (tcpSender != null && (isRegisterMode || isLoginMode)) {
            tcpSender.sendData(ecgValue);
        }
    }
}
```

### 4.3 TCP 통신 구현

**송신/수신 분리 구조**
```
┌─────────────────────────────────────────┐
│           TcpClientSender               │
├─────────────────────────────────────────┤
│  dataQueue (BlockingQueue)              │
│       ↓                                 │
│  dataSender() ──TCP──▶ Python 서버      │
│                                         │
│  resultReceiver() ◀──TCP── Python 서버  │
│       ↓                                 │
│  handleServerResponse() → UI 업데이트    │
└─────────────────────────────────────────┘
```

**데이터 전송 (비동기 큐)**
```java
private final BlockingQueue<Integer> dataQueue = new LinkedBlockingQueue<>();

public void sendData(int data) {
    dataQueue.offer(data);  // 큐에 추가 (블로킹 없음)
}

private void dataSender() {
    while (isRunning) {
        int dataToSend = dataQueue.take();  // 큐에서 꺼내기 (블로킹)
        out.println(dataToSend);            // 서버로 전송
    }
}
```

**명령어 전송**
```java
public void sendCommand(String command) {
    new Thread(() -> {
        out.println("CMD:" + command);
        // 예: "CMD:REGISTER:user1", "CMD:LOGIN", "CMD:LOGOUT"
    }).start();
}
```

**서버 응답 처리**
```java
private void resultReceiver() {
    while (isRunning) {
        String line = in.readLine();  // JSON 응답
        JSONObject json = new JSONObject(line);
        
        String status = json.optString("status");
        if ("success".equals(status)) {
            // 등록/로그인 성공 처리
        } else if ("auth_failed".equals(status)) {
            // 인증 실패 팝업
        }
    }
}
```

### 4.4 더미 데이터 생성

**실제 센서 없이 테스트하기 위한 ECG 시뮬레이션**

```java
private int generateECGWaveform(double timeSinceBeatStart, double beatDuration) {
    double normalizedTime = timeSinceBeatStart / beatDuration;
    double baseline = 512.0;
    
    // P파 (0.0 ~ 0.15): 심방 수축
    double pWave = 0;
    if (normalizedTime >= 0.0 && normalizedTime < 0.15) {
        double pPhase = normalizedTime / 0.15;
        pWave = 20 * Math.sin(Math.PI * pPhase);
    }
    
    // QRS 복합체 (0.15 ~ 0.25): 심실 수축
    double qrsWave = 0;
    if (normalizedTime >= 0.15 && normalizedTime < 0.25) {
        double qrsPhase = (normalizedTime - 0.15) / 0.1;
        if (qrsPhase < 0.2) {
            qrsWave = -30 * qrsPhase;        // Q파 (하강)
        } else if (qrsPhase < 0.5) {
            qrsWave = 200 * (qrsPhase - 0.2); // R파 (급상승)
        } else {
            qrsWave = 200 * (0.5 - qrsPhase); // S파 (급하강)
        }
    }
    
    // T파 (0.25 ~ 0.7): 심실 재분극
    double tWave = 0;
    if (normalizedTime >= 0.25 && normalizedTime < 0.7) {
        double tPhase = (normalizedTime - 0.25) / 0.45;
        tWave = 40 * Math.sin(Math.PI * tPhase);
    }
    
    // 노이즈 추가 (현실감)
    double noise = (Math.random() - 0.5) * 8;
    
    return (int) (baseline + pWave + qrsWave + tWave + noise);
}
```

**ECG 파형 구성 요소**
```
                    R
                    ▲
                   /│\
                  / │ \
                 /  │  \
           P    /   │   \   T
          ___  /    │    \ ___
         /   \/     │     \/   \
────────/─────Q─────┼─────S─────\────────
       │            │            │
       │   P-R 간격  │   Q-T 간격  │
       │            │            │
```

### 4.5 UI 구성

**주요 UI 요소**
| 요소 | 역할 |
|------|------|
| connectionBadge | 연결 상태 표시 (Bluetooth/TCP) |
| userIdEditText | 사용자 ID 입력 |
| registerButton / loginButton | 등록/로그인 시작 |
| ecgChart (LineChart) | 실시간 ECG 그래프 |
| progressLayout | 진행 상태 표시 (안정화/수집/처리) |
| resultTextView | 서버 응답 결과 표시 |

---

## 5. Python 서버

### 5.1 서버 구조

```
ecg_server.py
├── ECGProcessor        # ECG 데이터 버퍼링 및 파이프라인 실행
├── ClientHandler       # 클라이언트별 스레드 (명령어/데이터 처리)
└── ECGServer          # 메인 TCP 서버

ecg_processor/
├── preprocessing.py    # 전처리 (필터링)
├── r_peak_detector.py  # R-peak 검출 (Pan-Tompkins)
├── beat_processor.py   # 비트 분할 및 템플릿 생성
├── feature_extractor.py # 특징 추출
├── signature_generator.py # 서명 생성 (SHA-256)
├── auth_manager.py     # 사용자 인증 관리
└── pipeline.py         # 통합 파이프라인
```

### 5.2 TCP 서버 동작

**서버 초기화**
```python
HOST = '0.0.0.0'  # 모든 인터페이스에서 수신
PORT = 9999
BUFFER_SIZE = 3000  # 6초 분량 (500Hz × 6초)
SAMPLING_RATE = 500
SIMILARITY_THRESHOLD = 0.80  # 인증 임계값
```

**클라이언트 핸들러**
```python
class ClientHandler(threading.Thread):
    def run(self):
        while self.running:
            line = reader.readline().strip()
            
            if line.startswith("CMD:"):
                self.handle_command(line[4:])  # 명령어 처리
            else:
                self.handle_ecg_data(line)     # ECG 데이터 처리
```

**명령어 종류**
| 명령어 | 동작 |
|--------|------|
| `CMD:REGISTER:<user_id>` | 등록 모드 시작, 버퍼 초기화 |
| `CMD:LOGIN` | 로그인 모드 시작 (전체 사용자 검색) |
| `CMD:LOGIN:<user_id>` | 특정 사용자로 로그인 |
| `CMD:LOGOUT` | 세션 종료 |
| `CMD:USERS` | 등록된 사용자 목록 조회 |
| `CMD:DELETE:<user_id>` | 사용자 삭제 |

**데이터 버퍼링 및 처리**
```python
def handle_ecg_data(self, line):
    ecg_value = int(line)
    
    # 버퍼에 추가
    if self.processor.add_sample(ecg_value):
        # 버퍼가 가득 차면 (3000개) 처리 시작
        result = self.processor.process()
        
        if result["status"] == "success":
            if self.current_mode == "register":
                self.complete_registration(result)
            elif self.current_mode == "login":
                self.complete_login(result)
```

---

## 6. ECG 신호 처리 파이프라인

### 6.1 파이프라인 전체 흐름

```
원본 ECG 신호 (3000 샘플, 6초)
        │
        ▼
┌───────────────────┐
│   1. 전처리       │  Butterworth 필터, Notch 필터
└───────────────────┘
        │
        ▼
┌───────────────────┐
│   2. R-peak 검출  │  Pan-Tompkins 알고리즘
└───────────────────┘
        │
        ▼
┌───────────────────┐
│   3. 비트 처리    │  분할, 정규화, 템플릿 생성
└───────────────────┘
        │
        ▼
┌───────────────────┐
│   4. 특징 추출    │  형태학적, HRV, 주파수, 통계
└───────────────────┘
        │
        ▼
┌───────────────────┐
│   5. 서명 생성    │  벡터화 → 정규화 → 해시
└───────────────────┘
        │
        ▼
디지털 서명 (SHA-256 해시)
```

### 6.2 전처리 (preprocessing.py)

**목적**: ECG 신호에서 노이즈를 제거하고 깨끗한 파형을 얻습니다.

#### 6.2.1 Baseline Wander 제거

**문제**: 호흡이나 움직임으로 인해 ECG 기준선이 천천히 흔들립니다.
**해결**: **High-pass 필터 (0.5Hz)** 적용

```python
def remove_baseline_wander(self, ecg, cutoff=0.5):
    # Butterworth 고역 통과 필터 (2차)
    normalized_cutoff = cutoff / (self.fs / 2)  # 나이퀴스트 주파수로 정규화
    b, a = signal.butter(2, normalized_cutoff, btype='high')
    
    # 양방향 필터링 (위상 지연 없음)
    filtered = signal.filtfilt(b, a, ecg)
    return filtered
```

**Butterworth 필터란?**
- 주파수 응답이 **최대한 평탄**한 필터입니다.
- `signal.butter(order, cutoff, btype)`: 필터 계수 생성
- `signal.filtfilt()`: 양방향 필터링으로 위상 지연 제거

#### 6.2.2 고주파 노이즈 제거

**문제**: 근전도(EMG), 전자기 간섭 등의 고주파 잡음
**해결**: **Low-pass 필터 (45Hz)** 적용

```python
def remove_high_frequency_noise(self, ecg, cutoff=45.0):
    normalized_cutoff = cutoff / (self.fs / 2)
    b, a = signal.butter(4, normalized_cutoff, btype='low')  # 4차 필터
    filtered = signal.filtfilt(b, a, ecg)
    return filtered
```

**왜 45Hz인가?**
- ECG의 유효 주파수 성분: 0.5~40Hz
- 45Hz까지 허용하여 QRS 복합체의 날카로운 부분 보존

#### 6.2.3 전원 노이즈 제거

**문제**: 60Hz(한국) 또는 50Hz(유럽) 전원선 간섭
**해결**: **Notch 필터 (60Hz)** 적용

```python
def remove_powerline_noise(self, ecg, freq=60.0, Q=30.0):
    # IIR Notch 필터: 특정 주파수만 제거
    b, a = signal.iirnotch(freq, Q, self.fs)
    filtered = signal.filtfilt(b, a, ecg)
    return filtered
```

**Q 팩터란?**
- Q = 중심주파수 / 대역폭
- Q=30: 매우 좁은 대역만 제거 (다른 주파수 영향 최소화)

#### 6.2.4 신호 품질 평가

```python
def assess_signal_quality(self, ecg):
    quality = {
        'snr': self._estimate_snr(ecg),      # 신호 대 잡음비
        'is_saturated': self._check_saturation(ecg),  # 클리핑 여부
        'is_flat': self._check_flat_signal(ecg),      # 평탄 신호 여부
        'quality_score': 0.0  # 0~100점
    }
    
    # SNR 기반 점수 계산
    score = 100.0
    if quality['snr'] < 5: score -= 40
    elif quality['snr'] < 10: score -= 20
    
    if quality['is_saturated']: score -= 30
    if quality['is_flat']: score -= 50
    
    quality['quality_score'] = max(0, min(100, score))
    quality['is_acceptable'] = quality['quality_score'] >= 60
    
    return quality
```

### 6.3 R-peak 검출 (r_peak_detector.py)

**Pan-Tompkins 알고리즘**은 1985년에 발표된 **실시간 QRS 검출 알고리즘**입니다.

#### 6.3.1 알고리즘 단계

```
전처리된 ECG
      │
      ▼
┌─────────────────┐
│ 1. 밴드패스 필터 │  5-15Hz (QRS 주파수 대역)
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ 2. 미분 필터    │  기울기 강조
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ 3. 제곱         │  양수화 + 증폭
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ 4. 이동 평균    │  적분 (150ms 윈도우)
└─────────────────┘
      │
      ▼
┌─────────────────┐
│ 5. 피크 검출    │  적응형 임계값
└─────────────────┘
      │
      ▼
R-peak 위치 배열
```

#### 6.3.2 밴드패스 필터 (5-15Hz)

**목적**: QRS 복합체의 주파수 대역만 추출

```python
def _bandpass_filter(self, ecg, lowcut=5.0, highcut=15.0):
    nyquist = self.fs / 2
    low = lowcut / nyquist
    high = highcut / nyquist
    b, a = signal.butter(2, [low, high], btype='band')
    filtered = signal.filtfilt(b, a, ecg)
    return filtered
```

**왜 5-15Hz인가?**
- P파, T파: 0.5~5Hz (제거됨)
- QRS 복합체: 5~15Hz (강조됨)
- 고주파 노이즈: 15Hz 이상 (제거됨)

#### 6.3.3 미분 필터

**목적**: QRS의 급격한 기울기를 강조

```python
def _differentiate(self, ecg):
    # Pan-Tompkins 5점 미분 필터
    # H(z) = (1/8T)(-z^-2 - 2z^-1 + 2z + z^2)
    coefficients = np.array([1, 2, 0, -2, -1]) * (self.fs / 8.0)
    differentiated = np.convolve(ecg, coefficients, mode='same')
    return differentiated
```

#### 6.3.4 제곱

**목적**: 
- 음수 값을 양수로 변환
- 큰 값을 더 크게 증폭 (비선형 강조)

```python
squared = differentiated ** 2
```

#### 6.3.5 이동 평균 (적분)

**목적**: QRS 복합체 전체를 하나의 덩어리로 합침

```python
def _moving_average(self, ecg, window_size):
    # 150ms 윈도우 (500Hz에서 75샘플)
    window = np.ones(window_size) / window_size
    integrated = np.convolve(ecg, window, mode='same')
    return integrated
```

**윈도우 크기 150ms 이유**
- QRS 복합체 지속 시간: 약 80~120ms
- 150ms로 QRS 전체를 포함

#### 6.3.6 피크 검출 및 정제

```python
def _find_peaks(self, integrated, original_ecg):
    # 적응형 임계값
    threshold = np.mean(integrated) + 0.5 * np.std(integrated)
    
    # 로컬 최대값 찾기
    local_max = maximum_filter1d(integrated, size=self.min_rr_interval)
    peak_candidates = np.where((integrated == local_max) & 
                                (integrated > threshold))[0]
    
    # RR 간격 제약 (200ms ~ 2000ms)
    peaks = [peak_candidates[0]]
    for candidate in peak_candidates[1:]:
        if candidate - peaks[-1] >= self.min_rr_interval:  # 최소 200ms
            peaks.append(candidate)
    
    return np.array(peaks)

def _refine_peaks(self, ecg, peaks, search_window=25):
    # 원본 신호에서 정확한 R-peak 위치 찾기
    refined = []
    for peak in peaks:
        start = max(0, peak - search_window)
        end = min(len(ecg), peak + search_window)
        local_max_idx = start + np.argmax(ecg[start:end])
        refined.append(local_max_idx)
    return np.array(refined)
```

### 6.4 비트 처리 (beat_processor.py)

**목적**: 개별 심박을 분할하고 대표 템플릿을 생성합니다.

#### 6.4.1 비트 분할

```python
def extract_beats(self, ecg_signal, r_peaks):
    beats = []
    for r_peak in r_peaks:
        # R-peak 기준 앞뒤로 자르기
        start = r_peak - self.pre_r_samples   # 250ms 전
        end = r_peak + self.post_r_samples    # 400ms 후
        
        if start >= 0 and end <= len(ecg_signal):
            beat = ecg_signal[start:end]
            beats.append(beat)
    
    return np.array(beats)
```

**윈도우 크기 선택 이유**
- 250ms 전: P파 포함
- 400ms 후: T파 포함
- 총 650ms = 완전한 PQRST 파형

```
    ◄────── 250ms ──────┼────────── 400ms ──────────▶
                        R
    ──────P────────────/│\──────────T──────────────
                      Q   S
```

#### 6.4.2 정규화 및 리샘플링

```python
def normalize_beats(self, beats):
    normalized = []
    for beat in beats:
        # Z-score 정규화: 평균 0, 표준편차 1
        mean = np.mean(beat)
        std = np.std(beat)
        if std > 0:
            normalized.append((beat - mean) / std)
    return np.array(normalized)

def resample_beats(self, beats, target_length=300):
    # 모든 비트를 동일한 길이로 리샘플링
    resampled = []
    for beat in beats:
        # 선형 보간
        original_indices = np.linspace(0, 1, len(beat))
        target_indices = np.linspace(0, 1, target_length)
        interpolator = interp1d(original_indices, beat, kind='linear')
        resampled.append(interpolator(target_indices))
    return np.array(resampled)
```

#### 6.4.3 이상치 제거

```python
def remove_outlier_beats(self, beats, threshold=2.0):
    # 중앙값 비트 계산
    median_beat = np.median(beats, axis=0)
    
    # 각 비트와 중앙값의 거리 계산
    distances = [np.sqrt(np.mean((beat - median_beat) ** 2)) for beat in beats]
    
    # Modified Z-score로 이상치 판단
    median_distance = np.median(distances)
    mad = np.median(np.abs(distances - median_distance))
    modified_z_scores = 0.6745 * (distances - median_distance) / mad
    
    # 임계값 초과 비트 제거
    outlier_mask = np.abs(modified_z_scores) > threshold
    clean_beats = beats[~outlier_mask]
    
    return clean_beats
```

#### 6.4.4 대표 템플릿 생성

```python
def create_template(self, beats, method='weighted_mean'):
    if method == 'weighted_mean':
        # 중앙값에 가까운 비트에 더 높은 가중치
        median_beat = np.median(beats, axis=0)
        distances = [np.sqrt(np.mean((beat - median_beat) ** 2)) for beat in beats]
        
        # 거리의 역수를 가중치로
        weights = 1.0 / (np.array(distances) + 1e-8)
        weights = weights / np.sum(weights)
        
        template = np.average(beats, axis=0, weights=weights)
    
    return template
```

### 6.5 특징 추출 (feature_extractor.py)

**4가지 영역에서 총 30개 이상의 특징을 추출합니다.**

#### 6.5.1 형태학적 특징 (Morphological Features)

ECG 파형의 모양에서 추출하는 특징입니다.

```python
def extract_morphological_features(self, template):
    features = {}
    
    # R-peak 위치 찾기
    r_idx = np.argmax(template)
    features['r_amplitude'] = template[r_idx]
    
    # Q파: R-peak 직전 최소값
    q_region = template[max(0, r_idx-50):r_idx]
    q_idx = np.argmin(q_region) + max(0, r_idx-50)
    features['q_amplitude'] = template[q_idx]
    
    # S파: R-peak 직후 최소값
    s_region = template[r_idx:min(len(template), r_idx+50)]
    s_idx = np.argmin(s_region) + r_idx
    features['s_amplitude'] = template[s_idx]
    
    # 간격 계산
    features['qrs_duration'] = (s_idx - q_idx) / self.fs * 1000  # ms
    
    # P파: QRS 이전 최대값
    p_region = template[0:q_idx]
    if len(p_region) > 0:
        p_idx = np.argmax(p_region)
        features['p_amplitude'] = template[p_idx]
        features['pr_interval'] = (r_idx - p_idx) / self.fs * 1000
    
    # T파: QRS 이후 최대값
    t_region = template[s_idx:]
    if len(t_region) > 0:
        t_idx = np.argmax(t_region) + s_idx
        features['t_amplitude'] = template[t_idx]
        features['qt_interval'] = (t_idx - q_idx) / self.fs * 1000
    
    # 비율 특징
    features['p_r_ratio'] = features['p_amplitude'] / features['r_amplitude']
    features['t_r_ratio'] = features['t_amplitude'] / features['r_amplitude']
    
    # 기울기
    features['r_upslope'] = (template[r_idx] - template[q_idx]) / (r_idx - q_idx)
    features['r_downslope'] = (template[s_idx] - template[r_idx]) / (s_idx - r_idx)
    
    # 면적
    features['qrs_area'] = np.trapz(np.abs(template[q_idx:s_idx]))
    
    return features
```

**추출되는 형태학적 특징**
| 특징 | 설명 | 개인차 원인 |
|------|------|-------------|
| R 진폭 | R파 높이 | 심장 크기, 전극 위치 |
| QRS 지속시간 | Q~S 시간 | 심실 전도 속도 |
| PR 간격 | P~R 시간 | 방실 전도 시간 |
| QT 간격 | Q~T 시간 | 심실 탈분극+재분극 |
| P/R 비율 | P파/R파 높이 비 | 심방/심실 상대 크기 |
| R 상승 기울기 | R파 상승 속도 | 탈분극 속도 |

#### 6.5.2 HRV 특징 (Heart Rate Variability)

심박 간격의 변동성에서 추출하는 특징입니다.

```python
def extract_hrv_features(self, r_peaks):
    # RR 간격 계산 (ms)
    rr_intervals = np.diff(r_peaks) / self.fs * 1000
    
    # 이상치 제거 (300ms ~ 2000ms)
    valid_rr = rr_intervals[(rr_intervals > 300) & (rr_intervals < 2000)]
    
    features = {}
    
    # 시간 영역 HRV
    features['mean_rr'] = np.mean(valid_rr)           # 평균 RR 간격
    features['std_rr'] = np.std(valid_rr)             # RR 표준편차
    features['mean_hr'] = 60000.0 / features['mean_rr']  # 평균 심박수
    
    # SDNN: RR 간격의 표준편차 (자율신경 전체 활동)
    features['sdnn'] = np.std(valid_rr)
    
    # RMSSD: 연속 RR 차이의 제곱평균제곱근 (부교감신경 활동)
    rr_diff = np.diff(valid_rr)
    features['rmssd'] = np.sqrt(np.mean(rr_diff ** 2))
    
    # pNN50: 50ms 이상 차이나는 비율
    features['pnn50'] = np.sum(np.abs(rr_diff) > 50) / len(rr_diff) * 100
    
    # 변동계수
    features['cv_rr'] = features['sdnn'] / features['mean_rr']
    
    return features
```

**HRV 특징의 의미**
| 특징 | 의미 | 생리학적 해석 |
|------|------|---------------|
| SDNN | 전체 변동성 | 자율신경계 전체 활동 |
| RMSSD | 단기 변동성 | 부교감신경(미주신경) 활동 |
| pNN50 | 급격한 변화 비율 | 미주신경 톤 |

#### 6.5.3 주파수 영역 특징 (Frequency Domain)

FFT를 사용하여 주파수 성분을 분석합니다.

```python
def extract_frequency_features(self, template):
    # FFT 계산
    n = len(template)
    yf = fft(template)
    xf = fftfreq(n, 1/self.fs)
    
    # 양의 주파수만 사용
    positive_mask = xf >= 0
    xf = xf[positive_mask]
    power = np.abs(yf[positive_mask]) ** 2
    total_power = np.sum(power)
    
    features = {}
    
    # 주파수 대역별 파워
    features['lf_power'] = np.sum(power[(xf >= 0) & (xf < 5)]) / total_power    # P, T파
    features['mf_power'] = np.sum(power[(xf >= 5) & (xf < 15)]) / total_power   # QRS
    features['hf_power'] = np.sum(power[(xf >= 15) & (xf < 40)]) / total_power  # 고주파
    
    # LF/HF 비율
    features['lf_hf_ratio'] = features['lf_power'] / (features['hf_power'] + 1e-10)
    
    # 스펙트럼 중심 (무게 중심 주파수)
    features['spectral_centroid'] = np.sum(xf * power) / total_power
    
    # 지배 주파수 (최대 파워 주파수)
    features['dominant_freq'] = xf[np.argmax(power)]
    
    # 상위 FFT 계수
    top_indices = np.argsort(np.abs(yf))[-5:]
    features['top_fft_coeffs'] = [np.abs(yf[i]) / np.max(np.abs(yf)) for i in top_indices]
    
    return features
```

#### 6.5.4 통계적 특징 (Statistical Features)

신호의 통계적 성질을 분석합니다.

```python
def extract_statistical_features(self, template):
    features = {}
    
    # 기본 통계
    features['mean'] = np.mean(template)
    features['std'] = np.std(template)
    features['var'] = np.var(template)
    features['range'] = np.max(template) - np.min(template)
    
    # 고차 모멘트
    features['skewness'] = skew(template)      # 비대칭도
    features['kurtosis'] = kurtosis(template)  # 첨도
    
    # 에너지
    features['energy'] = np.sum(template ** 2)
    features['rms'] = np.sqrt(np.mean(template ** 2))
    
    # 제로 크로싱 비율
    zero_crossings = np.sum(np.abs(np.diff(np.sign(template))) > 0)
    features['zero_crossing_rate'] = zero_crossings / len(template)
    
    # 엔트로피 (복잡도)
    hist, _ = np.histogram(template, bins=50, density=True)
    hist = hist[hist > 0]
    features['entropy'] = -np.sum(hist * np.log2(hist))
    
    return features
```

**통계적 특징의 의미**
| 특징 | 의미 |
|------|------|
| 왜도 (Skewness) | 분포의 비대칭 정도 |
| 첨도 (Kurtosis) | 분포의 뾰족한 정도 |
| 엔트로피 | 신호의 복잡도/무질서도 |

### 6.6 서명 생성 (signature_generator.py)

#### 6.6.1 특징 벡터화

```python
def features_to_vector(self, features):
    vector_parts = []
    
    # 형태학적 특징 (가중치 1.5 - 가장 중요)
    if 'morphological' in features:
        morph = features['morphological']
        morph_vector = [
            morph['r_amplitude'], morph['q_amplitude'], morph['s_amplitude'],
            morph['p_amplitude'], morph['t_amplitude'],
            morph['qrs_duration'], morph['pr_interval'], morph['qt_interval'],
            # ... 총 16개
        ]
        morph_vector = np.array(morph_vector) * 1.5  # 가중치
        vector_parts.append(morph_vector)
    
    # HRV 특징 (가중치 1.0)
    # 주파수 특징 (가중치 0.8)
    # 통계적 특징 (가중치 0.7)
    
    # 모든 특징 연결
    full_vector = np.concatenate(vector_parts)
    full_vector = np.nan_to_num(full_vector)  # NaN 처리
    
    return full_vector
```

**가중치 설정 이유**
- 형태학적 특징 (1.5): 개인 식별에 가장 중요
- HRV 특징 (1.0): 심박 패턴 반영
- 주파수 특징 (0.8): 보조적 정보
- 통계적 특징 (0.7): 일반적 특성

#### 6.6.2 정규화 및 이산화

```python
def normalize_vector(self, vector, method='minmax'):
    # Min-Max 정규화: 0~1 범위로 변환
    min_val = np.min(vector)
    max_val = np.max(vector)
    normalized = (vector - min_val) / (max_val - min_val)
    return normalized

def discretize_vector(self, vector, bits=8):
    # 0~1 값을 0~255 정수로 변환
    clipped = np.clip(vector, 0, 1)
    max_val = (2 ** bits) - 1  # 255
    discretized = np.round(clipped * max_val).astype(int)
    return discretized
```

#### 6.6.3 SHA-256 해시 생성

```python
def create_hash(self, discretized_vector):
    # 정수 배열을 바이트로 변환
    vector_bytes = discretized_vector.astype(np.uint8).tobytes()
    
    # SHA-256 해시 계산
    hasher = hashlib.sha256()
    hasher.update(vector_bytes)
    
    hex_hash = hasher.hexdigest()  # 64자 16진수 문자열
    
    return hex_hash
```

**SHA-256이란?**
- **Secure Hash Algorithm 256-bit**
- 어떤 크기의 입력이든 256비트(64자 16진수) 고정 출력
- **단방향**: 해시에서 원본 복원 불가능
- **충돌 저항**: 같은 해시를 만드는 다른 입력 찾기 어려움

**서명 생성 전체 과정**
```
특징 딕셔너리 (30+ 특징)
        │
        ▼ 벡터화 + 가중치
가중 특징 벡터 [1.2, 3.4, 0.8, ...]
        │
        ▼ Min-Max 정규화
정규화 벡터 [0.12, 0.45, 0.08, ...]  (0~1 범위)
        │
        ▼ 8비트 이산화
이산 벡터 [31, 115, 20, ...]  (0~255 정수)
        │
        ▼ SHA-256
"a3f2b8c9d1e4f5a6b7c8d9e0f1a2b3c4..."  (64자)
```

---

## 7. 인증 시스템 (auth_manager.py)

### 7.1 사용자 등록

```python
def register(self, user_id, ecg_signature):
    # 중복 확인
    if user_id in self.users:
        return {"status": "error", "message": "이미 등록된 사용자"}
    
    # 사용자 데이터 저장
    user_data = {
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "ecg_templates": [{
            "feature_vector": ecg_signature['feature_vector'],
            "normalized_vector": ecg_signature['normalized_vector'],
            "signature_hash": ecg_signature['signature_hex'],
            "registered_at": datetime.now().isoformat()
        }]
    }
    
    self.users[user_id] = user_data
    self._save_users()  # JSON 파일에 저장
    
    return {"status": "success", "message": "등록 완료"}
```

### 7.2 로그인 (인증)

```python
def login(self, ecg_signature, user_id=None):
    input_vector = np.array(ecg_signature['feature_vector'])
    
    # 모든 등록된 사용자와 비교
    best_match = None
    best_similarity = 0.0
    
    for uid, user_data in self.users.items():
        for template in user_data['ecg_templates']:
            stored_vector = np.array(template['feature_vector'])
            
            # 하이브리드 유사도 계산
            similarity = self._euclidean_similarity(input_vector, stored_vector)
            
            if similarity > best_similarity:
                best_similarity = similarity
                best_match = uid
    
    # 임계값 확인
    if best_similarity >= self.similarity_threshold:  # 0.80
        session_id = self._create_session(best_match)
        return {
            "status": "success",
            "user_id": best_match,
            "similarity": best_similarity,
            "session_id": session_id
        }
    else:
        return {
            "status": "auth_failed",
            "best_similarity": best_similarity
        }
```

### 7.3 하이브리드 유사도 계산

**코사인 유사도 + 유클리드 거리 조합**

```python
def _euclidean_similarity(self, v1, v2):
    # Z-score 정규화
    v1_norm = (v1 - np.mean(v1)) / (np.std(v1) + 1e-10)
    v2_norm = (v2 - np.mean(v2)) / (np.std(v2) + 1e-10)
    
    # 1. 코사인 유사도 (패턴 형태 비교)
    #    cos(θ) = (v1 · v2) / (||v1|| × ||v2||)
    cosine_sim = np.dot(v1_norm, v2_norm) / (
        np.linalg.norm(v1_norm) * np.linalg.norm(v2_norm)
    )
    
    # 2. 유클리드 거리 기반 유사도 (값의 실제 차이)
    distance = np.linalg.norm(v1_norm - v2_norm)
    euclidean_sim = 1.0 / (1.0 + distance / 15.0)
    
    # 3. 하이브리드: 코사인 70% + 유클리드 30%
    hybrid_similarity = 0.7 * cosine_sim + 0.3 * euclidean_sim
    
    return max(0, min(1, hybrid_similarity))
```

**왜 하이브리드인가?**
- **코사인 유사도**: 벡터의 방향(패턴 형태) 비교, 크기에 불변
- **유클리드 거리**: 실제 값의 차이 반영
- 두 가지를 조합하여 더 정확한 비교

### 7.4 세션 관리

```python
def _create_session(self, user_id):
    session_id = str(uuid.uuid4())
    expires_at = datetime.now() + timedelta(hours=1)
    
    self.active_sessions[session_id] = {
        "user_id": user_id,
        "created_at": datetime.now().isoformat(),
        "expires_at": expires_at.isoformat()
    }
    
    return session_id

def logout(self, session_id):
    if session_id in self.active_sessions:
        del self.active_sessions[session_id]
        return {"status": "success"}
```

---

## 8. 데이터 흐름 요약

### 8.1 등록 과정

```
[사용자] ID 입력 + "등록" 클릭
    │
    ▼
[Android] CMD:REGISTER:user1 전송
    │
    ▼
[Python] 등록 모드 시작, 버퍼 초기화
    │
    ▼
[Android] 5초 안정화 카운트다운
    │
    ▼
[Android] ECG 데이터 전송 시작 (500Hz, 6초 = 3000개)
    │
    ▼
[Python] 버퍼가 3000개 차면 파이프라인 실행
    │
    ├── 전처리 (필터링)
    ├── R-peak 검출 (Pan-Tompkins)
    ├── 비트 처리 (템플릿 생성)
    ├── 특징 추출 (30+ 특징)
    └── 서명 생성 (SHA-256)
    │
    ▼
[Python] users.json에 저장
    │
    ▼
[Android] "등록 완료" 메시지 표시
```

### 8.2 로그인 과정

```
[사용자] "로그인" 클릭
    │
    ▼
[Android] CMD:LOGIN 전송
    │
    ▼
[Python] 로그인 모드 시작
    │
    ▼
[Android] 5초 안정화 → ECG 데이터 전송
    │
    ▼
[Python] 파이프라인 실행 → 서명 생성
    │
    ▼
[Python] 저장된 사용자들과 유사도 비교
    │
    ├── 유사도 ≥ 0.80 → 로그인 성공 (session_id 발급)
    │
    └── 유사도 < 0.80 → 인증 실패
    │
    ▼
[Android] 결과 팝업 표시 (성공/실패)
```

### 8.3 JSON 응답 예시

**등록 성공**
```json
{
    "status": "success",
    "message": "사용자 등록 완료: user1",
    "user_id": "user1",
    "registered_at": "2025-12-05T14:30:00"
}
```

**로그인 성공**
```json
{
    "status": "success",
    "message": "로그인 성공: user1",
    "user_id": "user1",
    "similarity": 0.92,
    "session_id": "a3f2b8c9-d1e4-f5a6-b7c8-d9e0f1a2b3c4",
    "threshold": 0.80
}
```

**인증 실패**
```json
{
    "status": "auth_failed",
    "message": "ECG 인증 실패",
    "best_similarity": 0.65,
    "threshold": 0.80
}
```

---

## 부록: 용어 정리

| 용어 | 설명 |
|------|------|
| ECG/EKG | 심전도 (Electrocardiogram) |
| R-peak | QRS 복합체에서 가장 높은 점 |
| QRS 복합체 | 심실 탈분극을 나타내는 파형 |
| HRV | 심박변이도 (Heart Rate Variability) |
| Pan-Tompkins | 실시간 QRS 검출 알고리즘 (1985) |
| FFT | 고속 푸리에 변환 |
| SHA-256 | 256비트 보안 해시 알고리즘 |
| SPP | Serial Port Profile (Bluetooth) |
| ADC | 아날로그-디지털 변환기 |
| Butterworth | 최대 평탄 주파수 응답 필터 |
| Notch 필터 | 특정 주파수만 제거하는 필터 |

---

*이 문서는 ECG-SIGN 프로젝트의 모든 기술적 세부사항을 포함하며, 발표 준비 및 프로젝트 이해에 활용할 수 있습니다.*

