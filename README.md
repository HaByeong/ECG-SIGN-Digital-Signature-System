# ECG-SIGN-Digital-Signature-System
ECG 형태학적 특징 기반 2차 인증 디지털 서명 시스템

## 프로젝트 소개
ECG(심전도) 신호의 고유한 파형 특성을 이용하여 개인을 식별하는 디지털 서명 시스템입니다.
단순한 심박수가 아닌, ECG 파형 자체를 '서명(Signature)'으로 활용하여 사용자 인증을 수행합니다.

## 주요 기능
- ECG 신호 수집 (Arduino + AD8232 센서)
- Pan-Tompkins 알고리즘을 이용한 R-peak 검출
- 형태학적 특징 추출 및 디지털 서명 생성
- 사용자 등록/로그인 기능

## 기술 스택
- **Hardware**: Arduino, AD8232 ECG 센서, HC-06 Bluetooth 모듈
- **Android**: Java, Bluetooth Classic, TCP Socket
- **Python**: NumPy, SciPy, Pan-Tompkins 알고리즘

## 사용 방법
자세한 내용은 `PROJECT_DOCUMENTATION.md` 파일을 참조하세요.

## 참고사항
- 실제 ECG 센서 없이도 더미 데이터로 테스트 가능합니다
- Python 서버 실행 시 로컬 IP 주소를 Android 앱에 설정해야 합니다
- 사용자 데이터는 `Software/Signal_Processing/user_data/users.json`에 저장됩니다

## 개선 필요 사항
- [ ] 데이터베이스 연동 (현재는 JSON 파일 사용)
- [ ] 웹 대시보드 추가
- [ ] 실시간 ECG 모니터링 기능
- [ ] 더 정확한 인증을 위한 알고리즘 개선
