"""
ECG 전처리 모듈
- 베이스라인 원더링 제거
- 고주파 노이즈 제거  
- 파워라인 노이즈 제거 (60Hz)
- 신호 품질 검사
"""

import numpy as np
from scipy import signal
from scipy.ndimage import median_filter
from typing import Tuple, Optional


class ECGPreprocessor:
    """ECG 신호 전처리 클래스"""
    
    def __init__(self, sampling_rate: int = 500):
        """
        Args:
            sampling_rate: 샘플링 주파수 (Hz)
        """
        self.fs = sampling_rate
        self.nyquist = sampling_rate / 2
        
    def process(self, ecg_signal: np.ndarray) -> Tuple[np.ndarray, dict]:
        """
        전체 전처리 파이프라인 실행
        
        Args:
            ecg_signal: 원본 ECG 신호
            
        Returns:
            processed_signal: 전처리된 신호
            quality_info: 품질 정보 딕셔너리
        """
        # 1. 신호를 float으로 변환
        ecg = np.array(ecg_signal, dtype=np.float64)
        
        # 2. 베이스라인 원더링 제거 (High-pass filter, 0.5Hz)
        ecg = self.remove_baseline_wander(ecg)
        
        # 3. 고주파 노이즈 제거 (Low-pass filter, 45Hz)
        ecg = self.remove_high_frequency_noise(ecg)
        
        # 4. 파워라인 노이즈 제거 (Notch filter, 60Hz)
        ecg = self.remove_powerline_noise(ecg)
        
        # 5. 신호 품질 검사
        quality_info = self.assess_signal_quality(ecg)
        
        return ecg, quality_info
    
    def remove_baseline_wander(self, ecg: np.ndarray, cutoff: float = 0.5) -> np.ndarray:
        """
        베이스라인 원더링 제거 (호흡, 움직임으로 인한 저주파 노이즈)
        High-pass filter 적용 (0.5Hz)
        
        Args:
            ecg: ECG 신호
            cutoff: 차단 주파수 (Hz)
            
        Returns:
            필터링된 신호
        """
        # Butterworth high-pass filter 설계
        normalized_cutoff = cutoff / self.nyquist
        
        # 차단 주파수가 너무 낮으면 조정
        if normalized_cutoff >= 1:
            normalized_cutoff = 0.9
        if normalized_cutoff <= 0:
            normalized_cutoff = 0.01
            
        b, a = signal.butter(2, normalized_cutoff, btype='high')
        
        # 양방향 필터링 (위상 지연 없음)
        filtered = signal.filtfilt(b, a, ecg)
        
        return filtered
    
    def remove_high_frequency_noise(self, ecg: np.ndarray, cutoff: float = 45.0) -> np.ndarray:
        """
        고주파 노이즈 제거 (근전도, 전자기 간섭 등)
        Low-pass filter 적용 (45Hz)
        
        Args:
            ecg: ECG 신호
            cutoff: 차단 주파수 (Hz)
            
        Returns:
            필터링된 신호
        """
        normalized_cutoff = cutoff / self.nyquist
        
        if normalized_cutoff >= 1:
            normalized_cutoff = 0.99
            
        b, a = signal.butter(4, normalized_cutoff, btype='low')
        filtered = signal.filtfilt(b, a, ecg)
        
        return filtered
    
    def remove_powerline_noise(self, ecg: np.ndarray, freq: float = 60.0, Q: float = 30.0) -> np.ndarray:
        """
        파워라인 노이즈 제거 (60Hz 또는 50Hz)
        Notch filter 적용
        
        Args:
            ecg: ECG 신호
            freq: 제거할 주파수 (Hz)
            Q: Quality factor (높을수록 좁은 대역)
            
        Returns:
            필터링된 신호
        """
        # 샘플링 주파수가 너무 낮으면 notch filter 스킵
        if freq >= self.nyquist:
            return ecg
            
        b, a = signal.iirnotch(freq, Q, self.fs)
        filtered = signal.filtfilt(b, a, ecg)
        
        return filtered
    
    def assess_signal_quality(self, ecg: np.ndarray) -> dict:
        """
        신호 품질 평가
        
        Args:
            ecg: 전처리된 ECG 신호
            
        Returns:
            품질 정보 딕셔너리
        """
        quality = {
            'snr': 0.0,
            'is_saturated': False,
            'is_flat': False,
            'quality_score': 0.0,
            'is_acceptable': False
        }
        
        # 1. SNR (Signal-to-Noise Ratio) 추정
        quality['snr'] = self._estimate_snr(ecg)
        
        # 2. 신호 포화 검사 (클리핑)
        quality['is_saturated'] = self._check_saturation(ecg)
        
        # 3. 평탄 신호 검사 (센서 분리)
        quality['is_flat'] = self._check_flat_signal(ecg)
        
        # 4. 종합 품질 점수 (0-100)
        quality['quality_score'] = self._calculate_quality_score(quality)
        
        # 5. 허용 가능 여부 (점수 60 이상)
        quality['is_acceptable'] = quality['quality_score'] >= 60
        
        return quality
    
    def _estimate_snr(self, ecg: np.ndarray) -> float:
        """SNR 추정 (dB)"""
        # 신호 파워: 전체 분산
        signal_power = np.var(ecg)
        
        # 노이즈 추정: 고주파 성분 (미분의 분산)
        noise = np.diff(ecg)
        noise_power = np.var(noise) / 2  # 미분으로 인한 증폭 보정
        
        if noise_power == 0:
            return 0.0
            
        snr = 10 * np.log10(signal_power / noise_power)
        return float(snr)
    
    def _check_saturation(self, ecg: np.ndarray, threshold: float = 0.01) -> bool:
        """신호 포화 검사"""
        max_val = np.max(ecg)
        min_val = np.min(ecg)
        
        # 최대/최소값 근처에 있는 샘플 비율
        near_max = np.sum(ecg > max_val * 0.99) / len(ecg)
        near_min = np.sum(ecg < min_val * 0.99) / len(ecg)
        
        return (near_max > threshold) or (near_min > threshold)
    
    def _check_flat_signal(self, ecg: np.ndarray, threshold: float = 0.01) -> bool:
        """평탄 신호 검사"""
        # 표준편차가 매우 작으면 평탄 신호
        std = np.std(ecg)
        mean_abs = np.mean(np.abs(ecg))
        
        if mean_abs == 0:
            return True
            
        return (std / mean_abs) < threshold
    
    def _calculate_quality_score(self, quality: dict) -> float:
        """종합 품질 점수 계산 (0-100)"""
        score = 100.0
        
        # SNR 기반 점수 (SNR이 낮으면 감점)
        if quality['snr'] < 5:
            score -= 40
        elif quality['snr'] < 10:
            score -= 20
        elif quality['snr'] < 15:
            score -= 10
            
        # 포화 신호면 감점
        if quality['is_saturated']:
            score -= 30
            
        # 평탄 신호면 크게 감점
        if quality['is_flat']:
            score -= 50
            
        return max(0.0, min(100.0, score))


def bandpass_filter(ecg: np.ndarray, lowcut: float, highcut: float, 
                    fs: int, order: int = 4) -> np.ndarray:
    """
    밴드패스 필터 (유틸리티 함수)
    
    Args:
        ecg: ECG 신호
        lowcut: 하한 주파수 (Hz)
        highcut: 상한 주파수 (Hz)
        fs: 샘플링 주파수 (Hz)
        order: 필터 차수
        
    Returns:
        필터링된 신호
    """
    nyquist = fs / 2
    low = lowcut / nyquist
    high = highcut / nyquist
    
    # 경계값 조정
    low = max(0.001, min(0.99, low))
    high = max(0.001, min(0.99, high))
    
    if low >= high:
        low = high * 0.5
    
    b, a = signal.butter(order, [low, high], btype='band')
    filtered = signal.filtfilt(b, a, ecg)
    
    return filtered

