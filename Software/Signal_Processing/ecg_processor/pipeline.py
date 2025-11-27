"""
ECG 서명 생성 통합 파이프라인
모든 모듈을 연결하여 end-to-end 처리
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .preprocessing import ECGPreprocessor
from .r_peak_detector import PanTompkinsDetector
from .beat_processor import BeatProcessor
from .feature_extractor import FeatureExtractor
from .signature_generator import SignatureGenerator


class ECGSignaturePipeline:
    """ECG 서명 생성 통합 파이프라인"""
    
    def __init__(self, sampling_rate: int = 500):
        """
        Args:
            sampling_rate: 샘플링 주파수 (Hz)
        """
        self.fs = sampling_rate
        
        # 모듈 초기화
        self.preprocessor = ECGPreprocessor(sampling_rate)
        self.r_peak_detector = PanTompkinsDetector(sampling_rate)
        self.beat_processor = BeatProcessor(sampling_rate)
        self.feature_extractor = FeatureExtractor(sampling_rate)
        self.signature_generator = SignatureGenerator()
        
        # 최소 필요 샘플 수 (최소 3개의 비트를 위해)
        self.min_samples = int(3 * sampling_rate)  # 3초
        
    def process(self, ecg_signal: np.ndarray) -> Dict:
        """
        ECG 신호에서 디지털 서명 생성
        
        Args:
            ecg_signal: 원본 ECG 신호 (1D numpy array 또는 list)
            
        Returns:
            처리 결과 딕셔너리
        """
        result = {
            'status': 'error',
            'message': '',
            'timestamp': datetime.now().isoformat(),
            
            # 처리 단계별 결과
            'preprocessing': {},
            'r_peak_detection': {},
            'beat_processing': {},
            'features': {},
            'signature': {},
            
            # 최종 출력
            'feature_vector': [],
            'signature_hash': '',
            'quality_score': 0.0
        }
        
        try:
            # 입력 검증
            ecg = np.array(ecg_signal, dtype=np.float64)
            
            if len(ecg) < self.min_samples:
                result['message'] = f'신호가 너무 짧습니다. 최소 {self.min_samples} 샘플 필요 (현재: {len(ecg)})'
                return result
            
            # ========== 1. 전처리 ==========
            preprocessed_ecg, quality_info = self.preprocessor.process(ecg)
            result['preprocessing'] = {
                'quality': quality_info,
                'signal_length': len(preprocessed_ecg)
            }
            result['quality_score'] = quality_info['quality_score']
            
            # 품질 검사
            if not quality_info['is_acceptable']:
                result['message'] = f"신호 품질이 낮습니다 (점수: {quality_info['quality_score']:.1f})"
                result['status'] = 'low_quality'
                return result
            
            # ========== 2. R-peak 검출 ==========
            r_peaks, detection_info = self.r_peak_detector.detect(preprocessed_ecg)
            result['r_peak_detection'] = {
                'num_peaks': len(r_peaks),
                'mean_hr': detection_info['mean_hr'],
                'r_peak_positions': r_peaks.tolist() if len(r_peaks) > 0 else []
            }
            
            if len(r_peaks) < 3:
                result['message'] = f'R-peak가 부족합니다 (검출: {len(r_peaks)}개, 최소 3개 필요)'
                result['status'] = 'insufficient_peaks'
                return result
            
            # ========== 3. 비트 처리 ==========
            beat_result = self.beat_processor.process_beats(preprocessed_ecg, r_peaks)
            result['beat_processing'] = {
                'num_total_beats': beat_result['num_total_beats'],
                'num_valid_beats': beat_result['num_valid_beats'],
                'num_outliers': beat_result['num_outliers']
            }
            
            if not beat_result['success'] or beat_result['template'] is None:
                result['message'] = '비트 처리 실패: 유효한 비트가 없습니다'
                result['status'] = 'beat_processing_failed'
                return result
            
            template = beat_result['template']
            
            # ========== 4. 특징 추출 ==========
            features = self.feature_extractor.extract_all_features(
                template=template,
                r_peaks=r_peaks,
                ecg_signal=preprocessed_ecg
            )
            result['features'] = features
            
            # ========== 5. 서명 생성 ==========
            signature = self.signature_generator.generate_signature(features)
            result['signature'] = signature
            
            if not signature['success']:
                result['message'] = '서명 생성 실패'
                result['status'] = 'signature_failed'
                return result
            
            # ========== 최종 결과 ==========
            result['status'] = 'success'
            result['message'] = 'ECG 서명 생성 완료'
            result['feature_vector'] = signature['feature_vector']
            result['signature_hash'] = signature['signature_hex']
            
            return result
            
        except Exception as e:
            result['message'] = f'처리 중 오류 발생: {str(e)}'
            result['status'] = 'error'
            return result
    
    def process_streaming(self, ecg_buffer: List[int], 
                         min_beats: int = 5) -> Optional[Dict]:
        """
        스트리밍 데이터 처리 (Android 앱에서 실시간으로 받는 경우)
        
        Args:
            ecg_buffer: ECG 데이터 버퍼 (정수 리스트)
            min_beats: 최소 필요 비트 수
            
        Returns:
            처리 결과 또는 None (데이터 부족 시)
        """
        ecg = np.array(ecg_buffer, dtype=np.float64)
        
        # 최소 샘플 수 확인
        if len(ecg) < self.min_samples:
            return None
        
        # 빠른 R-peak 검출로 비트 수 확인
        try:
            preprocessed, _ = self.preprocessor.process(ecg)
            r_peaks, _ = self.r_peak_detector.detect(preprocessed)
            
            if len(r_peaks) < min_beats:
                return None
                
        except:
            return None
        
        # 충분한 데이터가 있으면 전체 처리
        return self.process(ecg)
    
    def get_summary(self, result: Dict) -> Dict:
        """
        처리 결과 요약
        
        Args:
            result: process() 반환값
            
        Returns:
            요약 정보
        """
        summary = {
            'status': result.get('status', 'unknown'),
            'message': result.get('message', ''),
            'quality_score': result.get('quality_score', 0),
            'signature_hash': result.get('signature_hash', '')[:16] + '...' if result.get('signature_hash') else '',
            'feature_count': len(result.get('feature_vector', [])),
        }
        
        # R-peak 정보
        if 'r_peak_detection' in result:
            summary['heart_rate'] = result['r_peak_detection'].get('mean_hr', 0)
            summary['num_beats'] = result['r_peak_detection'].get('num_peaks', 0)
        
        return summary
    
    def compare_ecg(self, ecg1: np.ndarray, ecg2: np.ndarray, 
                   threshold: float = 0.85) -> Dict:
        """
        두 ECG 신호 비교 (인증용)
        
        Args:
            ecg1: 첫 번째 ECG 신호
            ecg2: 두 번째 ECG 신호
            threshold: 일치 판단 임계값
            
        Returns:
            비교 결과
        """
        # 각각 서명 생성
        result1 = self.process(ecg1)
        result2 = self.process(ecg2)
        
        comparison = {
            'ecg1_status': result1['status'],
            'ecg2_status': result2['status'],
            'is_match': False,
            'similarity': 0.0,
            'message': ''
        }
        
        # 둘 다 성공해야 비교 가능
        if result1['status'] != 'success':
            comparison['message'] = f'첫 번째 ECG 처리 실패: {result1["message"]}'
            return comparison
            
        if result2['status'] != 'success':
            comparison['message'] = f'두 번째 ECG 처리 실패: {result2["message"]}'
            return comparison
        
        # 서명 비교
        compare_result = self.signature_generator.compare_signatures(
            result1['signature'],
            result2['signature'],
            threshold=threshold
        )
        
        comparison['is_match'] = compare_result['is_match']
        comparison['similarity'] = compare_result['similarity']
        comparison['hash_match'] = compare_result['hash_match']
        comparison['message'] = '비교 완료'
        
        return comparison


def create_pipeline(sampling_rate: int = 500) -> ECGSignaturePipeline:
    """
    파이프라인 생성 헬퍼 함수
    
    Args:
        sampling_rate: 샘플링 주파수
        
    Returns:
        ECGSignaturePipeline 인스턴스
    """
    return ECGSignaturePipeline(sampling_rate)

