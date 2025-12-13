#include <SoftwareSerial.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ========== 핀 설정 ==========
// 블루투스 모듈 설정 (10번 핀=RX, 11번 핀=TX)
SoftwareSerial bluetooth(10, 11); // RX, TX

// AD8232 ECG 센서 핀 설정
const int ECG_OUTPUT = A0;  // ECG 신호 출력 (OUTPUT 핀)

// I2C LCD 설정 (주소: 0x27 또는 0x3F, 16칸 x 2줄)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// ========== 샘플링 설정 ==========
const int SAMPLE_DELAY = 2;  // 2ms = 500Hz 샘플링

// ========== LCD 업데이트 설정 ==========
unsigned long lastLcdUpdate = 0;
const int LCD_UPDATE_INTERVAL = 100;  // LCD는 100ms마다 업데이트 (너무 빠르면 깜빡임)
int minValue = 1023;
int maxValue = 0;

void setup() {
  // 시리얼 통신 시작
  Serial.begin(9600);
  bluetooth.begin(9600);  // HC-06 기본 보드레이트
  
  // 핀 모드 설정
  pinMode(ECG_OUTPUT, INPUT);
  
  // LCD 초기화
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("ECG Monitor");
  lcd.setCursor(0, 1);
  lcd.print("Starting...");
  
  // 시작 메시지
  Serial.println("AD8232 ECG Monitor Started");
  bluetooth.println("AD8232 ECG Monitor Started");
  
  delay(1000);
  
  // LCD 초기 화면
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ECG:");
}

void loop() {
  // ECG 데이터 읽기
  int ecgValue = analogRead(ECG_OUTPUT);
  
  // 블루투스로 데이터 전송
  bluetooth.println(ecgValue);
  
  // PC 시리얼 모니터로도 출력 (디버깅용)
  Serial.println(ecgValue);
  
  // 최소/최대값 추적 (심박 범위 표시용)
  if (ecgValue < minValue) minValue = ecgValue;
  if (ecgValue > maxValue) maxValue = ecgValue;
  
  // LCD 업데이트 (100ms마다)
  unsigned long currentTime = millis();
  if (currentTime - lastLcdUpdate >= LCD_UPDATE_INTERVAL) {
    lastLcdUpdate = currentTime;
    
    // 첫째 줄: ECG 값
    lcd.setCursor(0, 0);
    lcd.print("ECG: ");
    lcd.print(ecgValue);
    lcd.print("     ");  // 이전 값 지우기
    
    // 둘째 줄: 범위 (Min ~ Max)
    lcd.setCursor(0, 1);
    lcd.print(minValue);
    lcd.print("-");
    lcd.print(maxValue);
    lcd.print("      ");
    
    // 5초마다 min/max 리셋
    static unsigned long lastReset = 0;
    if (currentTime - lastReset >= 5000) {
      lastReset = currentTime;
      minValue = 1023;
      maxValue = 0;
    }
  }
  
  // 샘플링 주기 유지 (500Hz = 2ms 간격)
  delay(SAMPLE_DELAY);
}