"""
ECG 비트 처리 모듈
- R-peak 기준 비트 분할
- 비트 정렬 및 정규화
- 이상치 비트 제거
- 대표 템플릿 생성
"""

import numpy as np
from scipy import signal
from scipy.interpolate import interp1d
from typing import Tuple, List, Optional


class BeatProcessor:
    """ECG 비트 처리 클래스"""
    
    def __init__(self, sampling_rate: int = 500):
        """
        Args:
            sampling_rate: 샘플링 주파수 (Hz)
        """
        self.fs = sampling_rate
        
        # 비트 윈도우 설정 (R-peak 기준)
        self.pre_r_ms = 250   # R-peak 이전 250ms
        self.post_r_ms = 400  # R-peak 이후 400ms
        
        self.pre_r_samples = int(self.pre_r_ms * sampling_rate / 1000)
        self.post_r_samples = int(self.post_r_ms * sampling_rate / 1000)
        
        # 리샘플링 후 고정 길이
        self.fixed_beat_length = 300  # 고정 300 샘플
        
    def extract_beats(self, ecg_signal: np.ndarray, r_peaks: np.ndarray) -> Tuple[np.ndarray, List[int]]:
        """
        R-peak 기준으로 개별 비트 추출
        
        Args:
            ecg_signal: ECG 신호
            r_peaks: R-peak 위치 배열
            
        Returns:
            beats: 추출된 비트 배열 (N x beat_length)
            valid_indices: 유효한 비트의 원본 인덱스
        """
        ecg = np.array(ecg_signal, dtype=np.float64)
        beats = []
        valid_indices = []
        
        for i, r_peak in enumerate(r_peaks):
            # 비트 시작/끝 인덱스
            start = r_peak - self.pre_r_samples
            end = r_peak + self.post_r_samples
            
            # 경계 검사
            if start < 0 or end > len(ecg):
                continue
                
            # 비트 추출
            beat = ecg[start:end]
            beats.append(beat)
            valid_indices.append(i)
        
        if len(beats) == 0:
            return np.array([]), []
            
        return np.array(beats), valid_indices
    
    def normalize_beats(self, beats: np.ndarray) -> np.ndarray:
        """
        비트 정규화 (진폭 정규화)
        
        Args:
            beats: 비트 배열 (N x beat_length)
            
        Returns:
            정규화된 비트 배열
        """
        if len(beats) == 0:
            return beats
            
        normalized = np.zeros_like(beats)
        
        for i, beat in enumerate(beats):
            # Z-score 정규화
            mean = np.mean(beat)
            std = np.std(beat)
            
            if std > 0:
                normalized[i] = (beat - mean) / std
            else:
                normalized[i] = beat - mean
                
        return normalized
    
    def resample_beats(self, beats: np.ndarray, target_length: int = None) -> np.ndarray:
        """
        비트를 고정 길이로 리샘플링
        
        Args:
            beats: 비트 배열
            target_length: 목표 길이 (기본값: self.fixed_beat_length)
            
        Returns:
            리샘플링된 비트 배열
        """
        if len(beats) == 0:
            return beats
            
        if target_length is None:
            target_length = self.fixed_beat_length
            
        original_length = beats.shape[1]
        resampled = np.zeros((len(beats), target_length))
        
        # 보간을 위한 인덱스
        original_indices = np.linspace(0, 1, original_length)
        target_indices = np.linspace(0, 1, target_length)
        
        for i, beat in enumerate(beats):
            # 선형 보간
            interpolator = interp1d(original_indices, beat, kind='linear')
            resampled[i] = interpolator(target_indices)
            
        return resampled
    
    def remove_outlier_beats(self, beats: np.ndarray, threshold: float = 2.0) -> Tuple[np.ndarray, np.ndarray]:
        """
        이상치 비트 제거
        
        Args:
            beats: 비트 배열
            threshold: 이상치 판단 임계값 (표준편차 배수)
            
        Returns:
            clean_beats: 이상치가 제거된 비트 배열
            outlier_mask: 이상치 마스크 (True = 이상치)
        """
        if len(beats) < 3:
            return beats, np.zeros(len(beats), dtype=bool)
        
        # 중앙값 비트 계산
        median_beat = np.median(beats, axis=0)
        
        # 각 비트와 중앙값 비트의 거리 계산
        distances = np.array([np.sqrt(np.mean((beat - median_beat) ** 2)) for beat in beats])
        
        # 거리의 중앙값과 MAD (Median Absolute Deviation)
        median_distance = np.median(distances)
        mad = np.median(np.abs(distances - median_distance))
        
        # 이상치 판단 (Modified Z-score)
        if mad > 0:
            modified_z_scores = 0.6745 * (distances - median_distance) / mad
            outlier_mask = np.abs(modified_z_scores) > threshold
        else:
            outlier_mask = np.zeros(len(beats), dtype=bool)
        
        clean_beats = beats[~outlier_mask]
        
        return clean_beats, outlier_mask
    
    def create_template(self, beats: np.ndarray, method: str = 'median') -> np.ndarray:
        """
        대표 템플릿 생성
        
        Args:
            beats: 비트 배열 (이상치 제거 후)
            method: 'mean', 'median', 'weighted_mean'
            
        Returns:
            대표 템플릿
        """
        if len(beats) == 0:
            return np.array([])
            
        if len(beats) == 1:
            return beats[0]
        
        if method == 'mean':
            template = np.mean(beats, axis=0)
            
        elif method == 'median':
            template = np.median(beats, axis=0)
            
        elif method == 'weighted_mean':
            # 중앙값에 가까운 비트에 더 높은 가중치
            median_beat = np.median(beats, axis=0)
            distances = np.array([np.sqrt(np.mean((beat - median_beat) ** 2)) for beat in beats])
            
            # 거리의 역수를 가중치로 사용
            weights = 1.0 / (distances + 1e-8)
            weights = weights / np.sum(weights)
            
            template = np.average(beats, axis=0, weights=weights)
            
        else:
            template = np.mean(beats, axis=0)
            
        return template
    
    def process_beats(self, ecg_signal: np.ndarray, r_peaks: np.ndarray) -> dict:
        """
        전체 비트 처리 파이프라인
        
        Args:
            ecg_signal: ECG 신호
            r_peaks: R-peak 위치 배열
            
        Returns:
            처리 결과 딕셔너리
        """
        result = {
            'beats': None,
            'normalized_beats': None,
            'resampled_beats': None,
            'clean_beats': None,
            'template': None,
            'num_total_beats': 0,
            'num_valid_beats': 0,
            'num_outliers': 0,
            'success': False
        }
        
        # 1. 비트 추출
        beats, valid_indices = self.extract_beats(ecg_signal, r_peaks)
        result['num_total_beats'] = len(r_peaks)
        
        if len(beats) == 0:
            return result
            
        result['beats'] = beats
        
        # 2. 정규화
        normalized_beats = self.normalize_beats(beats)
        result['normalized_beats'] = normalized_beats
        
        # 3. 리샘플링
        resampled_beats = self.resample_beats(normalized_beats)
        result['resampled_beats'] = resampled_beats
        
        # 4. 이상치 제거
        clean_beats, outlier_mask = self.remove_outlier_beats(resampled_beats)
        result['clean_beats'] = clean_beats
        result['num_outliers'] = np.sum(outlier_mask)
        result['num_valid_beats'] = len(clean_beats)
        
        if len(clean_beats) == 0:
            return result
        
        # 5. 대표 템플릿 생성
        template = self.create_template(clean_beats, method='weighted_mean')
        result['template'] = template
        result['success'] = True
        
        return result


def align_beats_to_r_peak(beats: np.ndarray, r_position: int) -> np.ndarray:
    """
    비트들을 R-peak 기준으로 정렬 (유틸리티 함수)
    
    Args:
        beats: 비트 배열
        r_position: R-peak 위치 (비트 내 인덱스)
        
    Returns:
        정렬된 비트 배열
    """
    aligned = np.zeros_like(beats)
    
    for i, beat in enumerate(beats):
        # 각 비트에서 최대값 위치 찾기
        max_pos = np.argmax(beat)
        
        # 시프트 계산
        shift = r_position - max_pos
        
        # 시프트 적용
        if shift > 0:
            aligned[i, shift:] = beat[:-shift]
        elif shift < 0:
            aligned[i, :shift] = beat[-shift:]
        else:
            aligned[i] = beat
            
    return aligned

