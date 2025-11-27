"""
Pan-Tompkins R-peak 검출 알고리즘
- 미분 필터
- 제곱
- 이동 평균
- 적응형 임계값
"""

import numpy as np
from scipy import signal
from scipy.ndimage import maximum_filter1d
from typing import Tuple, List, Optional


class PanTompkinsDetector:
    """Pan-Tompkins 알고리즘 기반 R-peak 검출기"""
    
    def __init__(self, sampling_rate: int = 500):
        """
        Args:
            sampling_rate: 샘플링 주파수 (Hz)
        """
        self.fs = sampling_rate
        
        # 생리학적 제약 조건
        self.min_rr_interval = int(0.2 * sampling_rate)  # 최소 RR 간격 (200ms, 300bpm)
        self.max_rr_interval = int(2.0 * sampling_rate)  # 최대 RR 간격 (2000ms, 30bpm)
        
        # 이동 평균 윈도우 크기 (150ms)
        self.integration_window = int(0.15 * sampling_rate)
        
    def detect(self, ecg_signal: np.ndarray) -> Tuple[np.ndarray, dict]:
        """
        R-peak 검출 실행
        
        Args:
            ecg_signal: 전처리된 ECG 신호
            
        Returns:
            r_peaks: R-peak 위치 인덱스 배열
            info: 검출 정보 딕셔너리
        """
        ecg = np.array(ecg_signal, dtype=np.float64)
        
        # 1. 밴드패스 필터 (5-15Hz) - QRS 복합체 강조
        filtered = self._bandpass_filter(ecg, 5.0, 15.0)
        
        # 2. 미분 (기울기 강조)
        differentiated = self._differentiate(filtered)
        
        # 3. 제곱 (양수화 및 증폭)
        squared = differentiated ** 2
        
        # 4. 이동 평균 (적분)
        integrated = self._moving_average(squared, self.integration_window)
        
        # 5. 피크 검출 (적응형 임계값)
        r_peaks = self._find_peaks(integrated, ecg)
        
        # 6. R-peak 정제 (원본 신호에서 정확한 위치 찾기)
        r_peaks = self._refine_peaks(ecg, r_peaks)
        
        # 검출 정보
        info = {
            'num_peaks': len(r_peaks),
            'mean_hr': self._calculate_heart_rate(r_peaks),
            'detection_signal': integrated
        }
        
        return r_peaks, info
    
    def _bandpass_filter(self, ecg: np.ndarray, lowcut: float, highcut: float) -> np.ndarray:
        """밴드패스 필터 (5-15Hz)"""
        nyquist = self.fs / 2
        low = lowcut / nyquist
        high = highcut / nyquist
        
        # 경계값 조정
        low = max(0.001, min(0.99, low))
        high = max(0.001, min(0.99, high))
        
        if low >= high:
            high = min(0.99, low + 0.1)
        
        b, a = signal.butter(2, [low, high], btype='band')
        filtered = signal.filtfilt(b, a, ecg)
        
        return filtered
    
    def _differentiate(self, ecg: np.ndarray) -> np.ndarray:
        """5점 미분 필터"""
        # Pan-Tompkins 미분 필터 계수
        # H(z) = (1/8T)(-z^-2 - 2z^-1 + 2z + z^2)
        coefficients = np.array([1, 2, 0, -2, -1]) * (self.fs / 8.0)
        differentiated = np.convolve(ecg, coefficients, mode='same')
        
        return differentiated
    
    def _moving_average(self, ecg: np.ndarray, window_size: int) -> np.ndarray:
        """이동 평균 (적분)"""
        window = np.ones(window_size) / window_size
        integrated = np.convolve(ecg, window, mode='same')
        
        return integrated
    
    def _find_peaks(self, integrated: np.ndarray, original_ecg: np.ndarray) -> np.ndarray:
        """적응형 임계값을 사용한 피크 검출"""
        # 초기 임계값 설정
        threshold = np.mean(integrated) + 0.5 * np.std(integrated)
        
        # 피크 후보 찾기
        peaks = []
        
        # 로컬 최대값 찾기
        local_max = maximum_filter1d(integrated, size=self.min_rr_interval)
        peak_candidates = np.where((integrated == local_max) & (integrated > threshold))[0]
        
        if len(peak_candidates) == 0:
            # 임계값을 낮춰서 재시도
            threshold = np.mean(integrated)
            peak_candidates = np.where((integrated == local_max) & (integrated > threshold))[0]
        
        # RR 간격 제약 적용
        if len(peak_candidates) > 0:
            peaks = [peak_candidates[0]]
            
            for candidate in peak_candidates[1:]:
                # 이전 피크와의 간격 확인
                if candidate - peaks[-1] >= self.min_rr_interval:
                    peaks.append(candidate)
        
        return np.array(peaks)
    
    def _refine_peaks(self, ecg: np.ndarray, peaks: np.ndarray, search_window: int = None) -> np.ndarray:
        """
        원본 신호에서 정확한 R-peak 위치 찾기
        (적분 신호의 피크는 약간 지연됨)
        """
        if len(peaks) == 0:
            return peaks
            
        if search_window is None:
            search_window = int(0.05 * self.fs)  # 50ms 윈도우
        
        refined_peaks = []
        
        for peak in peaks:
            # 검색 범위 설정
            start = max(0, peak - search_window)
            end = min(len(ecg), peak + search_window)
            
            # 해당 범위에서 최대값 위치 찾기
            local_max_idx = start + np.argmax(ecg[start:end])
            refined_peaks.append(local_max_idx)
        
        return np.array(refined_peaks)
    
    def _calculate_heart_rate(self, r_peaks: np.ndarray) -> float:
        """평균 심박수 계산 (BPM)"""
        if len(r_peaks) < 2:
            return 0.0
            
        rr_intervals = np.diff(r_peaks) / self.fs  # 초 단위
        mean_rr = np.mean(rr_intervals)
        
        if mean_rr == 0:
            return 0.0
            
        heart_rate = 60.0 / mean_rr
        
        return heart_rate


class SimpleRPeakDetector:
    """간단한 R-peak 검출기 (백업용)"""
    
    def __init__(self, sampling_rate: int = 500):
        self.fs = sampling_rate
        
    def detect(self, ecg_signal: np.ndarray) -> np.ndarray:
        """
        간단한 임계값 기반 R-peak 검출
        """
        ecg = np.array(ecg_signal, dtype=np.float64)
        
        # 정규화
        ecg = (ecg - np.mean(ecg)) / (np.std(ecg) + 1e-8)
        
        # 임계값 (평균 + 1.5 * 표준편차)
        threshold = np.mean(ecg) + 1.5 * np.std(ecg)
        
        # 최소 피크 간격 (300ms)
        min_distance = int(0.3 * self.fs)
        
        # scipy의 find_peaks 사용
        peaks, _ = signal.find_peaks(ecg, height=threshold, distance=min_distance)
        
        return peaks

