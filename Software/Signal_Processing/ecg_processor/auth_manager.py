"""
ECG 기반 인증 관리자
- 사용자 등록 (ECG 서명 저장)
- 로그인 (ECG 서명 검증)
- 로그아웃
- 세션 관리
"""

import json
import os
import hashlib
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
import uuid


class ECGAuthManager:
    """ECG 기반 사용자 인증 관리자"""
    
    def __init__(self, data_dir: str = None, similarity_threshold: float = 0.85):
        """
        Args:
            data_dir: 사용자 데이터 저장 디렉토리
            similarity_threshold: 인증 유사도 임계값 (0-1, 기본 0.85)
        """
        if data_dir is None:
            # 기본 저장 경로
            data_dir = os.path.join(os.path.dirname(__file__), '..', 'user_data')
        
        self.data_dir = os.path.abspath(data_dir)
        self.users_file = os.path.join(self.data_dir, 'users.json')
        self.similarity_threshold = similarity_threshold
        
        # 세션 관리
        self.active_sessions: Dict[str, dict] = {}  # session_id -> session_info
        self.session_timeout = timedelta(hours=1)  # 세션 만료 시간
        
        # 스레드 안전을 위한 락
        self.lock = threading.Lock()
        
        # 데이터 디렉토리 생성
        os.makedirs(self.data_dir, exist_ok=True)
        
        # 사용자 데이터 로드
        self.users = self._load_users()
        
        print(f"[인증] ECG 인증 관리자 초기화 (등록 사용자: {len(self.users)}명)")
    
    def _load_users(self) -> Dict:
        """저장된 사용자 데이터 로드"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[경고] 사용자 데이터 로드 실패: {e}")
        return {}
    
    def _save_users(self):
        """사용자 데이터 저장"""
        try:
            with open(self.users_file, 'w', encoding='utf-8') as f:
                json.dump(self.users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[에러] 사용자 데이터 저장 실패: {e}")
    
    def register(self, user_id: str, ecg_signature: Dict, user_info: Dict = None) -> Dict:
        """
        새 사용자 등록 (ECG 서명 저장)
        
        Args:
            user_id: 사용자 ID
            ecg_signature: ECG 서명 데이터 (signature_generator 출력)
            user_info: 추가 사용자 정보 (이름 등)
            
        Returns:
            등록 결과
        """
        with self.lock:
            # 입력 검증
            if not user_id or not user_id.strip():
                return {
                    "status": "error",
                    "message": "사용자 ID가 필요합니다."
                }
            
            user_id = user_id.strip().lower()
            
            # 이미 등록된 사용자 확인
            if user_id in self.users:
                return {
                    "status": "error",
                    "message": f"이미 등록된 사용자입니다: {user_id}"
                }
            
            # 서명 데이터 검증
            if not ecg_signature or 'feature_vector' not in ecg_signature:
                return {
                    "status": "error",
                    "message": "유효한 ECG 서명이 필요합니다."
                }
            
            feature_vector = ecg_signature.get('feature_vector', [])
            if len(feature_vector) == 0:
                return {
                    "status": "error",
                    "message": "특징 벡터가 비어있습니다."
                }
            
            # 사용자 데이터 생성
            user_data = {
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "ecg_templates": [
                    {
                        "feature_vector": feature_vector,
                        "normalized_vector": ecg_signature.get('normalized_vector', []),
                        "signature_hash": ecg_signature.get('signature_hex', ''),
                        "registered_at": datetime.now().isoformat()
                    }
                ],
                "info": user_info or {},
                "login_count": 0,
                "last_login": None
            }
            
            # 저장
            self.users[user_id] = user_data
            self._save_users()
            
            return {
                "status": "success",
                "message": f"사용자 등록 완료: {user_id}",
                "user_id": user_id,
                "registered_at": user_data["created_at"]
            }
    
    def login(self, ecg_signature: Dict, user_id: str = None) -> Dict:
        """
        ECG 서명으로 로그인
        
        Args:
            ecg_signature: ECG 서명 데이터
            user_id: 특정 사용자 ID (없으면 전체 검색)
            
        Returns:
            로그인 결과 (세션 정보 포함)
        """
        with self.lock:
            # 서명 데이터 검증
            if not ecg_signature or 'feature_vector' not in ecg_signature:
                return {
                    "status": "error",
                    "message": "유효한 ECG 서명이 필요합니다."
                }
            
            input_vector = np.array(ecg_signature.get('feature_vector', []))
            input_normalized = np.array(ecg_signature.get('normalized_vector', []))
            
            if len(input_vector) == 0:
                return {
                    "status": "error",
                    "message": "특징 벡터가 비어있습니다."
                }
            
            # 특정 사용자 지정된 경우
            if user_id:
                user_id = user_id.strip().lower()
                if user_id not in self.users:
                    return {
                        "status": "error",
                        "message": f"등록되지 않은 사용자: {user_id}"
                    }
                users_to_check = {user_id: self.users[user_id]}
            else:
                users_to_check = self.users
            
            if not users_to_check:
                return {
                    "status": "error",
                    "message": "등록된 사용자가 없습니다."
                }
            
            # 모든 사용자와 비교
            best_match = None
            best_similarity = 0.0
            
            for uid, user_data in users_to_check.items():
                for template in user_data.get('ecg_templates', []):
                    # 원본 특징 벡터 사용 (정규화된 벡터 대신)
                    # Min-Max 정규화는 개인 특성을 제거하므로 원본 사용
                    stored_vector = np.array(template.get('feature_vector', []))
                    
                    if len(stored_vector) == 0:
                        continue
                    
                    # 원본 특징 벡터로 비교
                    compare_input = input_vector
                    
                    # 길이가 다르면 짧은 쪽에 맞춤
                    min_len = min(len(compare_input), len(stored_vector))
                    if min_len == 0:
                        continue
                    
                    v1 = compare_input[:min_len]
                    v2 = stored_vector[:min_len]
                    
                    # 유클리드 거리 기반 유사도 계산 (코사인 유사도보다 구별력 높음)
                    similarity = self._euclidean_similarity(v1, v2)
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = uid
            
            # 임계값 확인
            if best_match and best_similarity >= self.similarity_threshold:
                # 로그인 성공
                session_id = self._create_session(best_match)
                
                # 사용자 정보 업데이트
                self.users[best_match]['login_count'] += 1
                self.users[best_match]['last_login'] = datetime.now().isoformat()
                self._save_users()
                
                return {
                    "status": "success",
                    "message": f"로그인 성공: {best_match}",
                    "user_id": best_match,
                    "session_id": session_id,
                    "similarity": float(best_similarity),
                    "threshold": self.similarity_threshold,
                    "expires_at": (datetime.now() + self.session_timeout).isoformat()
                }
            else:
                # 로그인 실패
                return {
                    "status": "auth_failed",
                    "message": "ECG 인증 실패: 일치하는 사용자가 없습니다.",
                    "best_similarity": float(best_similarity) if best_similarity > 0 else 0.0,
                    "threshold": self.similarity_threshold
                }
    
    def logout(self, session_id: str) -> Dict:
        """
        로그아웃 (세션 종료)
        
        Args:
            session_id: 세션 ID
            
        Returns:
            로그아웃 결과
        """
        with self.lock:
            if session_id in self.active_sessions:
                session = self.active_sessions.pop(session_id)
                return {
                    "status": "success",
                    "message": f"로그아웃 완료: {session['user_id']}",
                    "user_id": session['user_id']
                }
            else:
                return {
                    "status": "error",
                    "message": "유효하지 않은 세션입니다."
                }
    
    def verify_session(self, session_id: str) -> Dict:
        """
        세션 유효성 확인
        
        Args:
            session_id: 세션 ID
            
        Returns:
            세션 정보
        """
        with self.lock:
            if session_id not in self.active_sessions:
                return {
                    "status": "invalid",
                    "message": "유효하지 않은 세션입니다."
                }
            
            session = self.active_sessions[session_id]
            
            # 만료 확인
            expires_at = datetime.fromisoformat(session['expires_at'])
            if datetime.now() > expires_at:
                self.active_sessions.pop(session_id)
                return {
                    "status": "expired",
                    "message": "세션이 만료되었습니다."
                }
            
            return {
                "status": "valid",
                "message": "유효한 세션입니다.",
                "user_id": session['user_id'],
                "expires_at": session['expires_at']
            }
    
    def update_ecg_template(self, user_id: str, ecg_signature: Dict, session_id: str = None) -> Dict:
        """
        사용자 ECG 템플릿 업데이트 (추가 등록)
        
        Args:
            user_id: 사용자 ID
            ecg_signature: 새 ECG 서명
            session_id: 세션 ID (인증용)
            
        Returns:
            업데이트 결과
        """
        with self.lock:
            # 세션 확인 (선택적)
            if session_id:
                session_check = self.verify_session(session_id)
                if session_check['status'] != 'valid':
                    return session_check
                if session_check['user_id'] != user_id:
                    return {
                        "status": "error",
                        "message": "세션 사용자와 일치하지 않습니다."
                    }
            
            user_id = user_id.strip().lower()
            
            if user_id not in self.users:
                return {
                    "status": "error",
                    "message": f"등록되지 않은 사용자: {user_id}"
                }
            
            # 새 템플릿 추가
            new_template = {
                "feature_vector": ecg_signature.get('feature_vector', []),
                "normalized_vector": ecg_signature.get('normalized_vector', []),
                "signature_hash": ecg_signature.get('signature_hex', ''),
                "registered_at": datetime.now().isoformat()
            }
            
            self.users[user_id]['ecg_templates'].append(new_template)
            self.users[user_id]['updated_at'] = datetime.now().isoformat()
            
            # 최대 5개 템플릿 유지
            if len(self.users[user_id]['ecg_templates']) > 5:
                self.users[user_id]['ecg_templates'] = self.users[user_id]['ecg_templates'][-5:]
            
            self._save_users()
            
            return {
                "status": "success",
                "message": f"ECG 템플릿 업데이트 완료: {user_id}",
                "template_count": len(self.users[user_id]['ecg_templates'])
            }
    
    def delete_user(self, user_id: str, session_id: str = None) -> Dict:
        """
        사용자 삭제
        
        Args:
            user_id: 사용자 ID
            session_id: 세션 ID (인증용)
            
        Returns:
            삭제 결과
        """
        with self.lock:
            user_id = user_id.strip().lower()
            
            if user_id not in self.users:
                return {
                    "status": "error",
                    "message": f"등록되지 않은 사용자: {user_id}"
                }
            
            # 사용자 삭제
            del self.users[user_id]
            self._save_users()
            
            # 해당 사용자의 세션 모두 종료
            sessions_to_remove = [
                sid for sid, sess in self.active_sessions.items()
                if sess['user_id'] == user_id
            ]
            for sid in sessions_to_remove:
                del self.active_sessions[sid]
            
            return {
                "status": "success",
                "message": f"사용자 삭제 완료: {user_id}"
            }
    
    def get_user_list(self) -> Dict:
        """등록된 사용자 목록 조회"""
        users_info = []
        for uid, data in self.users.items():
            users_info.append({
                "user_id": uid,
                "created_at": data.get('created_at'),
                "last_login": data.get('last_login'),
                "login_count": data.get('login_count', 0),
                "template_count": len(data.get('ecg_templates', []))
            })
        
        return {
            "status": "success",
            "total_users": len(users_info),
            "users": users_info
        }
    
    def _create_session(self, user_id: str) -> str:
        """새 세션 생성"""
        session_id = str(uuid.uuid4())
        expires_at = datetime.now() + self.session_timeout
        
        self.active_sessions[session_id] = {
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat()
        }
        
        return session_id
    
    def _cosine_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """코사인 유사도 계산"""
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(v1, v2) / (norm1 * norm2))
    
    def _euclidean_similarity(self, v1: np.ndarray, v2: np.ndarray) -> float:
        """
        하이브리드 유사도 계산 (코사인 + 유클리드)
        - 코사인: 패턴의 형태 비교
        - 유클리드: 값의 실제 차이 비교
        """
        # Z-score 정규화
        v1_normalized = (v1 - np.mean(v1)) / (np.std(v1) + 1e-10)
        v2_normalized = (v2 - np.mean(v2)) / (np.std(v2) + 1e-10)
        
        # 1. 코사인 유사도 (패턴 형태)
        norm1 = np.linalg.norm(v1_normalized)
        norm2 = np.linalg.norm(v2_normalized)
        if norm1 > 0 and norm2 > 0:
            cosine_sim = np.dot(v1_normalized, v2_normalized) / (norm1 * norm2)
        else:
            cosine_sim = 0.0
        
        # 2. 유클리드 거리 기반 유사도
        distance = np.linalg.norm(v1_normalized - v2_normalized)
        scale = 15.0  # 더 관대하게 조정 (5 → 15)
        euclidean_sim = 1.0 / (1.0 + distance / scale)
        
        # 3. 하이브리드: 코사인 70% + 유클리드 30%
        # 코사인이 더 중요하지만, 유클리드로 세부 차이 반영
        hybrid_similarity = 0.7 * cosine_sim + 0.3 * euclidean_sim
        
        return float(max(0, min(1, hybrid_similarity)))
    
    def cleanup_expired_sessions(self):
        """만료된 세션 정리"""
        with self.lock:
            now = datetime.now()
            expired = [
                sid for sid, sess in self.active_sessions.items()
                if datetime.fromisoformat(sess['expires_at']) < now
            ]
            for sid in expired:
                del self.active_sessions[sid]
            
            if expired:
                print(f"[세션] 만료된 세션 {len(expired)}개 정리됨")

