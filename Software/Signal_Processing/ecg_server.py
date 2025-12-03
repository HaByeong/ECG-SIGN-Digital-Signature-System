#!/usr/bin/env python3
"""
ECG 디지털 서명 인증 서버
- Android 앱에서 TCP로 ECG 데이터(정수 문자열)를 받음
- ECG 서명 생성 파이프라인으로 처리
- 사용자 등록/로그인/로그아웃 기능
- 처리 결과를 JSON 형태로 응답

사용법:
    python ecg_server.py

필요 패키지:
    pip install numpy scipy
"""

import socket
import threading
import json
import numpy as np
from collections import deque
from datetime import datetime
import sys
import os

# ecg_processor 패키지 경로 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ECG 서명 파이프라인 및 인증 관리자 임포트
try:
    from ecg_processor import ECGSignaturePipeline, ECGAuthManager
    PIPELINE_AVAILABLE = True
    print("[초기화] ECG 서명 파이프라인 로드 성공")
except ImportError as e:
    PIPELINE_AVAILABLE = False
    print(f"[경고] ECG 서명 파이프라인 로드 실패: {e}")
    print("[경고] 기본 처리 모드로 동작합니다.")

# ============ 설정 ============
HOST = '0.0.0.0'  # 모든 네트워크 인터페이스에서 수신
PORT = 9999       # Android 앱의 PYTHON_SERVER_PORT와 동일해야 함
BUFFER_SIZE = 1500  # 처리할 ECG 샘플 개수 (3초 분량, 500Hz 기준) - 최소 3개 R-peak 검출을 위해 1500개 필요
SAMPLING_RATE = 500  # 샘플링 주파수 (Hz) - 아두이노 설정과 일치해야 함
SIMILARITY_THRESHOLD = 0.85  # ECG 인증 유사도 임계값 (0-1) - 보안 강화: 0.75에서 0.85로 상향 조정
# ==============================


class ECGProcessor:
    """ECG 신호 처리 클래스 (파이프라인 통합)"""
    
    def __init__(self, buffer_size=BUFFER_SIZE, sampling_rate=SAMPLING_RATE):
        self.buffer_size = buffer_size
        self.sampling_rate = sampling_rate
        self.data_buffer = deque(maxlen=buffer_size * 2)
        
        # 파이프라인 초기화
        if PIPELINE_AVAILABLE:
            self.pipeline = ECGSignaturePipeline(sampling_rate)
            print(f"[초기화] ECG 파이프라인 생성 (샘플링: {sampling_rate}Hz)")
        else:
            self.pipeline = None
    
    def add_sample(self, value: int) -> bool:
        """샘플 추가. 버퍼가 가득 차면 True 반환"""
        self.data_buffer.append(value)
        return len(self.data_buffer) >= self.buffer_size
    
    def process(self, min_samples: int = None) -> dict:
        """버퍼에 있는 ECG 데이터 처리
        
        Args:
            min_samples: 최소 필요 샘플 수 (None이면 buffer_size 사용)
        """
        min_required = min_samples if min_samples is not None else self.buffer_size
        
        if len(self.data_buffer) < min_required:
            return {
                "status": "error",
                "message": f"데이터 부족: {len(self.data_buffer)}/{min_required}"
            }
        
        # 사용할 샘플 수 결정 (버퍼 크기 또는 실제 버퍼 크기 중 작은 값)
        samples_to_use = min(len(self.data_buffer), self.buffer_size)
        ecg_data = np.array(list(self.data_buffer)[:samples_to_use], dtype=np.float64)
        
        # 버퍼에서 처리한 데이터 제거
        for _ in range(samples_to_use):
            if self.data_buffer:
                self.data_buffer.popleft()
        
        if self.pipeline is not None:
            return self._process_with_pipeline(ecg_data)
        else:
            return self._process_basic(ecg_data)
    
    def _process_with_pipeline(self, ecg_data: np.ndarray) -> dict:
        """파이프라인을 사용한 전체 ECG 처리"""
        try:
            result = self.pipeline.process(ecg_data)
            
            response = {
                "status": result["status"],
                "message": result["message"],
                "timestamp": result["timestamp"],
                "sample_count": len(ecg_data),
                "quality_score": result.get("quality_score", 0),
            }
            
            if result["status"] == "success":
                response["feature_vector"] = result["feature_vector"]
                response["signature_hash"] = result["signature_hash"]
                response["signature"] = result.get("signature", {})
                
                summary = self.pipeline.get_summary(result)
                response["summary"] = {
                    "heart_rate": summary.get("heart_rate", 0),
                    "num_beats": summary.get("num_beats", 0),
                    "feature_count": summary.get("feature_count", 0),
                }
            
            return response
            
        except Exception as e:
            print(f"[에러] 파이프라인 처리 실패: {e}")
            import traceback
            traceback.print_exc()
            return self._process_basic(ecg_data)
    
    def _process_basic(self, ecg_data: np.ndarray) -> dict:
        """기본 ECG 처리 (파이프라인 실패 시 폴백)"""
        normalized = (ecg_data - np.mean(ecg_data)) / (np.std(ecg_data) + 1e-8)
        
        features = {
            "mean": float(np.mean(ecg_data)),
            "std": float(np.std(ecg_data)),
            "max": float(np.max(ecg_data)),
            "min": float(np.min(ecg_data)),
            "range": float(np.max(ecg_data) - np.min(ecg_data)),
        }
        
        feature_vector = list(features.values())
        
        return {
            "status": "success",
            "message": "ECG 기본 처리 완료",
            "feature_vector": feature_vector,
            "signature": {"normalized_vector": normalized.tolist()[:50]},
            "sample_count": len(ecg_data),
            "timestamp": datetime.now().isoformat()
        }
    
    def get_buffer_status(self) -> str:
        return f"{len(self.data_buffer)}/{self.buffer_size}"
    
    def clear_buffer(self):
        """버퍼 초기화"""
        self.data_buffer.clear()


class ClientHandler(threading.Thread):
    """클라이언트 연결 처리 스레드"""
    
    def __init__(self, client_socket: socket.socket, client_address: tuple, 
                 auth_manager: 'ECGAuthManager'):
        super().__init__()
        self.client_socket = client_socket
        self.client_address = client_address
        self.processor = ECGProcessor()
        self.auth_manager = auth_manager
        self.running = True
        self.sample_count = 0
        
        # 현재 모드 및 세션
        self.current_mode = "idle"  # idle, collecting, register, login
        self.pending_user_id = None
        self.session_id = None
        self.logged_in_user = None
    
    def run(self):
        print(f"[연결] 클라이언트 접속: {self.client_address}")
        self.send_welcome_message()
        
        try:
            with self.client_socket.makefile('r', encoding='utf-8') as reader:
                while self.running:
                    line = reader.readline()
                    
                    if not line:
                        print(f"[종료] 클라이언트 연결 종료: {self.client_address}")
                        break
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 명령어 처리
                    if line.startswith("CMD:"):
                        self.handle_command(line[4:])
                    else:
                        # ECG 데이터 처리
                        self.handle_ecg_data(line)
                        
        except Exception as e:
            print(f"[에러] 클라이언트 처리 중 오류: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.client_socket.close()
            print(f"[정리] 소켓 닫음: {self.client_address}")
    
    def send_welcome_message(self):
        """연결 시 환영 메시지 전송"""
        welcome = {
            "status": "connected",
            "message": "ECG 인증 서버에 연결되었습니다.",
            "commands": [
                "CMD:REGISTER:<user_id> - 사용자 등록 모드",
                "CMD:LOGIN - 로그인 모드 (ECG 데이터 전송)",
                "CMD:LOGIN:<user_id> - 특정 사용자로 로그인",
                "CMD:LOGOUT - 로그아웃",
                "CMD:STATUS - 현재 상태 확인",
                "CMD:USERS - 등록된 사용자 목록",
                "CMD:DELETE:<user_id> - 사용자 삭제",
                "CMD:CANCEL - 현재 작업 취소"
            ],
            "session": self.session_id,
            "logged_in_user": self.logged_in_user
        }
        self.send_response(welcome)
    
    def handle_command(self, command: str):
        """명령어 처리"""
        parts = command.strip().split(":", 1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else None
        
        print(f"[명령] {cmd} (인자: {arg})")
        
        if cmd == "REGISTER":
            self.start_register_mode(arg)
        elif cmd == "LOGIN":
            self.start_login_mode(arg)
        elif cmd == "LOGOUT":
            self.do_logout()
        elif cmd == "STATUS":
            self.send_status()
        elif cmd == "USERS":
            self.send_user_list()
        elif cmd == "DELETE":
            self.delete_user(arg)
        elif cmd == "CANCEL":
            self.cancel_current_mode()
        elif cmd == "VERIFY":
            self.verify_session()
        elif cmd == "COMPLETE":
            self.handle_complete_command()
        else:
            self.send_response({
                "status": "error",
                "message": f"알 수 없는 명령어: {cmd}"
            })
    
    def start_register_mode(self, user_id: str):
        """사용자 등록 모드 시작"""
        if not user_id:
            self.send_response({
                "status": "error",
                "message": "사용자 ID가 필요합니다. 형식: CMD:REGISTER:<user_id>"
            })
            return
        
        user_id = user_id.strip()
        
        # 이미 등록된 사용자인지 확인 (등록 모드 시작 시점에 확인)
        # auth_manager.register()에서 user_id.strip().lower()로 저장하므로 동일하게 비교
        if self.auth_manager and hasattr(self.auth_manager, 'users'):
            # 사용자 데이터를 다시 로드하여 최신 상태 확인
            self.auth_manager.users = self.auth_manager._load_users()
            user_id_lower = user_id.lower()
            if user_id_lower in self.auth_manager.users:
                self.send_response({
                    "status": "error",
                    "message": f"이미 등록된 사용자입니다: {user_id} (등록일: {self.auth_manager.users[user_id_lower].get('created_at', '알 수 없음')})"
                })
                return
        
        self.current_mode = "register"
        self.pending_user_id = user_id
        self.processor.clear_buffer()
        self.sample_count = 0
        
        self.send_response({
            "status": "ready",
            "message": f"등록 모드 시작. ECG 데이터를 전송하세요. (사용자: {self.pending_user_id})",
            "mode": "register",
            "user_id": self.pending_user_id,
            "required_samples": self.processor.buffer_size
        })
    
    def start_login_mode(self, user_id: str = None):
        """로그인 모드 시작"""
        self.current_mode = "login"
        self.pending_user_id = user_id.strip() if user_id else None
        self.processor.clear_buffer()
        self.sample_count = 0
        
        msg = f"로그인 모드 시작 (사용자: {self.pending_user_id})" if self.pending_user_id else "로그인 모드 시작 (전체 검색)"
        
        self.send_response({
            "status": "ready",
            "message": f"{msg}. ECG 데이터를 전송하세요.",
            "mode": "login",
            "user_id": self.pending_user_id,
            "required_samples": self.processor.buffer_size
        })
    
    def do_logout(self):
        """로그아웃 처리"""
        if self.session_id:
            result = self.auth_manager.logout(self.session_id)
            self.session_id = None
            self.logged_in_user = None
            self.send_response(result)
        else:
            self.send_response({
                "status": "error",
                "message": "로그인 상태가 아닙니다."
            })
    
    def send_status(self):
        """현재 상태 전송"""
        status = {
            "status": "info",
            "mode": self.current_mode,
            "logged_in": self.logged_in_user is not None,
            "user_id": self.logged_in_user,
            "session_id": self.session_id,
            "buffer_status": self.processor.get_buffer_status(),
            "total_samples_received": self.sample_count
        }
        
        if self.session_id:
            session_check = self.auth_manager.verify_session(self.session_id)
            status["session_valid"] = session_check["status"] == "valid"
            status["session_expires"] = session_check.get("expires_at")
        
        self.send_response(status)
    
    def send_user_list(self):
        """등록된 사용자 목록 전송"""
        result = self.auth_manager.get_user_list()
        self.send_response(result)
    
    def delete_user(self, user_id: str):
        """사용자 삭제"""
        if not user_id:
            self.send_response({
                "status": "error",
                "message": "사용자 ID가 필요합니다."
            })
            return
        
        result = self.auth_manager.delete_user(user_id, self.session_id)
        self.send_response(result)
    
    def cancel_current_mode(self):
        """현재 모드 취소"""
        self.current_mode = "idle"
        self.pending_user_id = None
        self.processor.clear_buffer()
        
        self.send_response({
            "status": "cancelled",
            "message": "현재 작업이 취소되었습니다."
        })
    
    def verify_session(self):
        """세션 유효성 확인"""
        if self.session_id:
            result = self.auth_manager.verify_session(self.session_id)
            self.send_response(result)
        else:
            self.send_response({
                "status": "error",
                "message": "활성 세션이 없습니다."
            })
    
    def handle_complete_command(self):
        """데이터 수집 완료 신호 처리"""
        if self.current_mode not in ["register", "login"]:
            self.send_response({
                "status": "error",
                "message": "등록/로그인 모드가 아닙니다."
            })
            return
        
        buffer_status = self.processor.get_buffer_status()
        buffer_count = len(self.processor.data_buffer)
        
        print(f"[완료 신호] 모드: {self.current_mode}, 버퍼: {buffer_status}, 총 샘플: {self.sample_count}")
        
        # 최소 버퍼 크기 체크
        # 파이프라인이 최소 1500개(3초)를 요구하므로, 정확히 1500개 필요
        min_required = 1500
        
        if buffer_count < min_required:
            self.send_response({
                "status": "error",
                "message": f"데이터가 부족합니다. (버퍼: {buffer_count}/{self.processor.buffer_size}, 최소 {min_required}개 필요)"
            })
            return
        
        # 버퍼가 가득 차지 않았어도 처리 진행
        # 충분한 데이터가 있으면 처리 가능
        print(f"[강제 처리] 버퍼 데이터로 처리 시작 ({buffer_count}개 샘플, 최소 {min_required}개 요구)")
        
        # ECG 처리 (최소 샘플 수로 처리 허용)
        result = self.processor.process(min_samples=min_required)
        
        if result["status"] == "success":
            # 모드에 따른 처리
            if self.current_mode == "register":
                self.complete_registration(result)
            elif self.current_mode == "login":
                self.complete_login(result)
        else:
            self.send_response(result)
    
    def handle_ecg_data(self, line: str):
        """ECG 데이터 처리"""
        try:
            ecg_value = int(line)
            self.sample_count += 1
            
            # 100개마다 상태 출력
            if self.sample_count % 100 == 0:
                print(f"[수신] 샘플 #{self.sample_count}, 버퍼: {self.processor.get_buffer_status()}, 모드: {self.current_mode}")
            
            # 버퍼에 추가
            if self.processor.add_sample(ecg_value):
                print(f"\n[처리] 버퍼 가득 참. 모드: {self.current_mode}")
                
                # ECG 처리
                result = self.processor.process()
                
                if result["status"] == "success":
                    # 모드에 따른 처리
                    if self.current_mode == "register":
                        self.complete_registration(result)
                    elif self.current_mode == "login":
                        self.complete_login(result)
                    else:
                        # 일반 처리 (서명만 생성)
                        self.send_response(result)
                else:
                    self.send_response(result)
                    
        except ValueError:
            # 숫자가 아닌 데이터는 무시
            pass
    
    def complete_registration(self, ecg_result: dict):
        """등록 완료 처리"""
        signature = {
            "feature_vector": ecg_result.get("feature_vector", []),
            "normalized_vector": ecg_result.get("signature", {}).get("normalized_vector", []),
            "signature_hex": ecg_result.get("signature_hash", "")
        }
        
        result = self.auth_manager.register(self.pending_user_id, signature)
        
        # 등록 성공 시 자동 로그인 제거 (사용자가 직접 로그인하도록)
        # if result["status"] == "success":
        #     login_result = self.auth_manager.login(signature, self.pending_user_id)
        #     if login_result["status"] == "success":
        #         self.session_id = login_result["session_id"]
        #         self.logged_in_user = login_result["user_id"]
        #         result["auto_login"] = True
        #         result["session_id"] = self.session_id
        
        self.current_mode = "idle"
        self.pending_user_id = None
        
        self.send_response(result)
    
    def complete_login(self, ecg_result: dict):
        """로그인 완료 처리"""
        signature = {
            "feature_vector": ecg_result.get("feature_vector", []),
            "normalized_vector": ecg_result.get("signature", {}).get("normalized_vector", []),
            "signature_hex": ecg_result.get("signature_hash", "")
        }
        
        result = self.auth_manager.login(signature, self.pending_user_id)
        
        if result["status"] == "success":
            self.session_id = result["session_id"]
            self.logged_in_user = result["user_id"]
        
        self.current_mode = "idle"
        self.pending_user_id = None
        
        self.send_response(result)
    
    def send_response(self, data: dict):
        """JSON 응답 전송"""
        try:
            json_str = json.dumps(data, ensure_ascii=False)
            self.client_socket.sendall((json_str + '\n').encode('utf-8'))
            print(f"[전송] {data.get('status', 'unknown')}: {data.get('message', '')[:50]}")
        except Exception as e:
            print(f"[에러] 응답 전송 실패: {e}")
    
    def stop(self):
        self.running = False


class ECGServer:
    """메인 TCP 서버"""
    
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.server_socket = None
        self.clients = []
        self.running = False
        
        # 인증 관리자 초기화
        if PIPELINE_AVAILABLE:
            self.auth_manager = ECGAuthManager(similarity_threshold=SIMILARITY_THRESHOLD)
        else:
            self.auth_manager = None
    
    def get_local_ip(self):
        """실제 네트워크 IP 주소 가져오기"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def start(self):
        """서버 시작"""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        self.running = True
        
        local_ip = self.get_local_ip()
        
        print()
        print("=" * 60)
        print("  🫀 ECG 디지털 서명 인증 서버")
        print("=" * 60)
        print(f"  호스트: {self.host}")
        print(f"  포트: {self.port}")
        print(f"  로컬 IP: {local_ip}")
        print(f"  샘플링 레이트: {SAMPLING_RATE} Hz")
        print(f"  버퍼 크기: {BUFFER_SIZE} 샘플 ({BUFFER_SIZE/SAMPLING_RATE:.1f}초)")
        print(f"  인증 임계값: {SIMILARITY_THRESHOLD}")
        print(f"  파이프라인: {'✅ 활성화' if PIPELINE_AVAILABLE else '❌ 비활성화'}")
        print("=" * 60)
        print()
        print("📱 Android 앱 설정:")
        print(f"   PYTHON_SERVER_IP = \"{local_ip}\"")
        print(f"   PYTHON_SERVER_PORT = {self.port}")
        print()
        print("📋 사용 가능한 명령어:")
        print("   CMD:REGISTER:<user_id>  - 사용자 등록")
        print("   CMD:LOGIN               - 로그인 (전체 검색)")
        print("   CMD:LOGIN:<user_id>     - 특정 사용자 로그인")
        print("   CMD:LOGOUT              - 로그아웃")
        print("   CMD:STATUS              - 상태 확인")
        print("   CMD:USERS               - 사용자 목록")
        print()
        print("⏳ 클라이언트 연결 대기 중...")
        print("-" * 60)
        
        try:
            while self.running:
                client_socket, client_address = self.server_socket.accept()
                handler = ClientHandler(client_socket, client_address, self.auth_manager)
                handler.start()
                self.clients.append(handler)
                
        except KeyboardInterrupt:
            print("\n[종료] 서버 종료 요청...")
        finally:
            self.stop()
    
    def stop(self):
        """서버 종료"""
        self.running = False
        for client in self.clients:
            client.stop()
        if self.server_socket:
            self.server_socket.close()
        print("[완료] 서버가 종료되었습니다.")


if __name__ == "__main__":
    server = ECGServer()
    server.start()
