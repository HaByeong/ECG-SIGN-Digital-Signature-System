"""
ECG 서명 생성 모듈
- 특징 벡터화
- 정규화 및 이산화
- 해싱/암호화를 통한 서명 생성
"""

import numpy as np
import hashlib
import json
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class SignatureGenerator:
    """ECG 기반 디지털 서명 생성 클래스"""
    
    def __init__(self):
        """초기화"""
        # 특징 가중치 (중요도에 따른 가중치)
        # TODO: 실제 데이터로 최적 가중치 찾아보기
        self.feature_weights = {
            'morphological': 1.5,  # 형태학적 특징 (가장 중요)
            'hrv': 1.0,            # HRV 특징
            'frequency': 0.8,      # 주파수 특징
            'statistical': 0.7    # 통계적 특징
        }
        
        # 이산화 비트 수 (8비트 = 0-255)
        self.discretization_bits = 8
        
    def generate_signature(self, features: Dict) -> Dict:
        """
        특징에서 디지털 서명 생성
        
        Args:
            features: 추출된 특징 딕셔너리
            
        Returns:
            서명 정보 딕셔너리
        """
        result = {
            'feature_vector': [],
            'normalized_vector': [],
            'discretized_vector': [],
            'signature_hash': '',
            'signature_hex': '',
            'timestamp': datetime.now().isoformat(),
            'success': False
        }
        
        # 1. 특징 벡터화
        feature_vector = self.features_to_vector(features)
        if len(feature_vector) == 0:
            return result
        result['feature_vector'] = feature_vector.tolist()
        
        # 2. 정규화
        normalized = self.normalize_vector(feature_vector)
        result['normalized_vector'] = normalized.tolist()
        
        # 3. 이산화
        discretized = self.discretize_vector(normalized)
        result['discretized_vector'] = discretized.tolist()
        
        # 4. 해시 생성 (서명)
        signature_hash, signature_hex = self.create_hash(discretized)
        result['signature_hash'] = signature_hash
        result['signature_hex'] = signature_hex
        
        result['success'] = True
        return result
    
    def features_to_vector(self, features: Dict) -> np.ndarray:
        """
        특징 딕셔너리를 벡터로 변환
        
        Args:
            features: 특징 딕셔너리
            
        Returns:
            특징 벡터 (numpy array)
        """
        vector_parts = []
        
        # 형태학적 특징
        if 'morphological' in features:
            morph = features['morphological']
            morph_vector = [
                morph.get('r_amplitude', 0),
                morph.get('q_amplitude', 0),
                morph.get('s_amplitude', 0),
                morph.get('p_amplitude', 0),
                morph.get('t_amplitude', 0),
                morph.get('qrs_duration', 0),
                morph.get('pr_interval', 0),
                morph.get('qt_interval', 0),
                morph.get('st_segment', 0),
                morph.get('p_r_ratio', 0),
                morph.get('t_r_ratio', 0),
                morph.get('r_upslope', 0),
                morph.get('r_downslope', 0),
                morph.get('qrs_area', 0),
                morph.get('p_area', 0),
                morph.get('t_area', 0),
            ]
            # 가중치 적용
            morph_vector = np.array(morph_vector) * self.feature_weights['morphological']
            vector_parts.append(morph_vector)
        
        # HRV 특징
        if 'hrv' in features:
            hrv = features['hrv']
            hrv_vector = [
                hrv.get('mean_rr', 0),
                hrv.get('std_rr', 0),
                hrv.get('sdnn', 0),
                hrv.get('rmssd', 0),
                hrv.get('pnn50', 0),
                hrv.get('cv_rr', 0),
            ]
            hrv_vector = np.array(hrv_vector) * self.feature_weights['hrv']
            vector_parts.append(hrv_vector)
        
        # 주파수 특징
        if 'frequency' in features:
            freq = features['frequency']
            freq_vector = [
                freq.get('lf_power', 0),
                freq.get('mf_power', 0),
                freq.get('hf_power', 0),
                freq.get('lf_hf_ratio', 0),
                freq.get('spectral_centroid', 0),
                freq.get('spectral_spread', 0),
                freq.get('dominant_freq', 0),
            ]
            # top_fft_coeffs 추가
            if 'top_fft_coeffs' in freq:
                freq_vector.extend(freq['top_fft_coeffs'])
            freq_vector = np.array(freq_vector) * self.feature_weights['frequency']
            vector_parts.append(freq_vector)
        
        # 통계적 특징
        if 'statistical' in features:
            stat = features['statistical']
            stat_vector = [
                stat.get('mean', 0),
                stat.get('std', 0),
                stat.get('skewness', 0),
                stat.get('kurtosis', 0),
                stat.get('energy', 0),
                stat.get('rms', 0),
                stat.get('zero_crossing_rate', 0),
                stat.get('entropy', 0),
            ]
            stat_vector = np.array(stat_vector) * self.feature_weights['statistical']
            vector_parts.append(stat_vector)
        
        if len(vector_parts) == 0:
            return np.array([])
        
        # 모든 특징 연결
        full_vector = np.concatenate(vector_parts)
        
        # NaN, Inf 처리
        full_vector = np.nan_to_num(full_vector, nan=0.0, posinf=0.0, neginf=0.0)
        
        return full_vector
    
    def normalize_vector(self, vector: np.ndarray, method: str = 'minmax') -> np.ndarray:
        """
        특징 벡터 정규화
        
        Args:
            vector: 특징 벡터
            method: 'minmax', 'zscore', 'l2'
            
        Returns:
            정규화된 벡터
        """
        if len(vector) == 0:
            return vector
        
        if method == 'minmax':
            # Min-Max 정규화 (0-1)
            min_val = np.min(vector)
            max_val = np.max(vector)
            if max_val - min_val > 0:
                normalized = (vector - min_val) / (max_val - min_val)
            else:
                normalized = np.zeros_like(vector)
                
        elif method == 'zscore':
            # Z-score 정규화
            mean = np.mean(vector)
            std = np.std(vector)
            if std > 0:
                normalized = (vector - mean) / std
            else:
                normalized = vector - mean
                
        elif method == 'l2':
            # L2 정규화 (단위 벡터)
            norm = np.linalg.norm(vector)
            if norm > 0:
                normalized = vector / norm
            else:
                normalized = vector
        else:
            normalized = vector
            
        return normalized
    
    def discretize_vector(self, vector: np.ndarray, bits: int = None) -> np.ndarray:
        """
        연속 벡터를 이산 값으로 변환
        
        Args:
            vector: 정규화된 벡터 (0-1 범위 가정)
            bits: 이산화 비트 수
            
        Returns:
            이산화된 벡터 (정수)
        """
        if len(vector) == 0:
            return vector
            
        if bits is None:
            bits = self.discretization_bits
        
        # 0-1 범위로 클리핑
        clipped = np.clip(vector, 0, 1)
        
        # 이산화 (0 ~ 2^bits - 1)
        max_val = (2 ** bits) - 1
        discretized = np.round(clipped * max_val).astype(int)
        
        return discretized
    
    def create_hash(self, discretized_vector: np.ndarray, algorithm: str = 'sha256') -> Tuple[str, str]:
        """
        이산화된 벡터에서 해시 생성
        
        Args:
            discretized_vector: 이산화된 특징 벡터
            algorithm: 해시 알고리즘 ('sha256', 'sha512', 'md5')
            
        Returns:
            (base64_hash, hex_hash) 튜플
        """
        # 벡터를 바이트로 변환
        vector_bytes = discretized_vector.astype(np.uint8).tobytes()
        
        # 해시 생성
        if algorithm == 'sha256':
            hasher = hashlib.sha256()
        elif algorithm == 'sha512':
            hasher = hashlib.sha512()
        elif algorithm == 'md5':
            hasher = hashlib.md5()
        else:
            hasher = hashlib.sha256()
        
        hasher.update(vector_bytes)
        
        # 결과
        hex_hash = hasher.hexdigest()
        
        # Base64 인코딩
        import base64
        base64_hash = base64.b64encode(hasher.digest()).decode('utf-8')
        
        return base64_hash, hex_hash
    
    def compare_signatures(self, sig1: Dict, sig2: Dict, threshold: float = 0.85) -> Dict:
        """
        두 서명 비교
        
        Args:
            sig1: 첫 번째 서명
            sig2: 두 번째 서명
            threshold: 일치 판단 임계값 (0-1)
            
        Returns:
            비교 결과 딕셔너리
        """
        result = {
            'is_match': False,
            'similarity': 0.0,
            'vector_distance': 0.0,
            'hash_match': False
        }
        
        # 해시 직접 비교
        result['hash_match'] = sig1.get('signature_hex') == sig2.get('signature_hex')
        
        # 벡터 유사도 계산
        vec1 = np.array(sig1.get('normalized_vector', []))
        vec2 = np.array(sig2.get('normalized_vector', []))
        
        if len(vec1) == len(vec2) and len(vec1) > 0:
            # 코사인 유사도
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 > 0 and norm2 > 0:
                result['similarity'] = float(dot_product / (norm1 * norm2))
            
            # 유클리드 거리
            result['vector_distance'] = float(np.linalg.norm(vec1 - vec2))
        
        # 일치 판단
        result['is_match'] = result['similarity'] >= threshold
        
        return result
    
    def serialize_signature(self, signature: Dict) -> str:
        """서명을 JSON 문자열로 직렬화"""
        return json.dumps(signature, ensure_ascii=False)
    
    def deserialize_signature(self, signature_json: str) -> Dict:
        """JSON 문자열에서 서명 복원"""
        return json.loads(signature_json)


class FuzzyExtractor:
    """
    Fuzzy Extractor for biometric key generation
    생체 정보의 변동성을 허용하면서 안정적인 키 생성
    """
    
    def __init__(self, error_tolerance: float = 0.1):
        """
        Args:
            error_tolerance: 허용 오차 비율 (0-1)
        """
        self.error_tolerance = error_tolerance
        
    def generate(self, feature_vector: np.ndarray) -> Tuple[str, np.ndarray]:
        """
        특징 벡터에서 키와 헬퍼 데이터 생성
        
        Args:
            feature_vector: 정규화된 특징 벡터
            
        Returns:
            (key, helper_data) 튜플
        """
        # 양자화
        quantized = self._quantize(feature_vector)
        
        # 랜덤 노이즈 생성 (헬퍼 데이터)
        np.random.seed(42)  # 재현성을 위해 고정 시드 (실제로는 제거)
        helper_data = np.random.randint(0, 256, size=len(quantized))
        
        # XOR로 키 생성
        key_bytes = quantized ^ helper_data
        
        # 해시하여 최종 키 생성
        key = hashlib.sha256(key_bytes.tobytes()).hexdigest()
        
        return key, helper_data
    
    def reproduce(self, feature_vector: np.ndarray, helper_data: np.ndarray) -> str:
        """
        헬퍼 데이터를 사용하여 키 재생성
        
        Args:
            feature_vector: 새로운 특징 벡터
            helper_data: 저장된 헬퍼 데이터
            
        Returns:
            재생성된 키
        """
        # 양자화
        quantized = self._quantize(feature_vector)
        
        # 길이 맞추기
        if len(quantized) != len(helper_data):
            min_len = min(len(quantized), len(helper_data))
            quantized = quantized[:min_len]
            helper_data = helper_data[:min_len]
        
        # XOR로 키 복원
        key_bytes = quantized ^ helper_data
        
        # 해시
        key = hashlib.sha256(key_bytes.tobytes()).hexdigest()
        
        return key
    
    def _quantize(self, vector: np.ndarray, levels: int = 256) -> np.ndarray:
        """벡터 양자화"""
        # 0-1 범위로 클리핑
        clipped = np.clip(vector, 0, 1)
        # 양자화
        quantized = np.floor(clipped * (levels - 1)).astype(np.uint8)
        return quantized

