#include <SoftwareSerial.h>

// 블루투스 모듈 설정 (10번 핀=RX, 11번 핀=TX)
SoftwareSerial bluetooth(10, 11); // RX, TX

// AD8232 ECG 센서 핀 설정
const int ECG_OUTPUT = A0;  // ECG 신호 출력 (OUTPUT 핀)

// 샘플링 설정
const int SAMPLE_DELAY = 2;  // 2ms = 500Hz 샘플링

void setup() {
  // 시리얼 통신 시작
  // 참고: HC-06 모듈 기본 보드레이트는 9600
  // 500Hz 샘플링에는 부족하지만, 우선 기본값으로 동작 확인
  Serial.begin(9600);
  bluetooth.begin(9600);  // HC-06 기본 보드레이트
  
  // 핀 모드 설정
  pinMode(ECG_OUTPUT, INPUT);
  
  // 시작 메시지
  Serial.println("AD8232 ECG Monitor Started");
  bluetooth.println("AD8232 ECG Monitor Started");
  
  delay(1000);
}

void loop() {
  // ECG 데이터 읽기
  int ecgValue = analogRead(ECG_OUTPUT);
  
  // 블루투스로 데이터 전송
  bluetooth.println(ecgValue);
  
  // PC 시리얼 모니터로도 출력 (디버깅용)
  // Serial Plotter에서 그래프로 보려면 숫자만 출력 (현재 형식)
  Serial.println(ecgValue);
  
  // 샘플링 주기 유지 (500Hz = 2ms 간격)
  // 블루투스 전송이 느려도 샘플링 주기는 유지 (데이터 손실 가능성 있음)
  delay(SAMPLE_DELAY);
}