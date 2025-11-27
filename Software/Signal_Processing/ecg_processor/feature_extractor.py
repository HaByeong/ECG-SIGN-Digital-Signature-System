"""
ECG 특징 추출 모듈
- P, QRS, T 파형 경계 탐지
- 형태학적 특징 추출
- 시간 영역 특징 (HRV)
- 주파수 영역 특징
"""

import numpy as np
from scipy import signal
from scipy.fft import fft, fftfreq
from scipy.stats import skew, kurtosis
from typing import Dict, List, Tuple, Optional


class FeatureExtractor:
    """ECG 특징 추출 클래스"""
    
    def __init__(self, sampling_rate: int = 500):
        """
        Args:
            sampling_rate: 샘플링 주파수 (Hz)
        """
        self.fs = sampling_rate
        
        # 템플릿 내 R-peak 예상 위치 (정규화된 템플릿 기준)
        # pre_r_ms=250, post_r_ms=400 -> R-peak는 약 38% 위치
        self.r_peak_ratio = 0.38
        
    def extract_all_features(self, template: np.ndarray, r_peaks: np.ndarray, 
                            ecg_signal: np.ndarray = None) -> Dict:
        """
        모든 특징 추출
        
        Args:
            template: 대표 템플릿
            r_peaks: R-peak 위치 배열
            ecg_signal: 원본 ECG 신호 (HRV 계산용, 선택적)
            
        Returns:
            모든 특징을 포함한 딕셔너리
        """
        features = {}
        
        # 1. 형태학적 특징 (템플릿 기반)
        morphological = self.extract_morphological_features(template)
        features['morphological'] = morphological
        
        # 2. 시간 영역 특징 (HRV)
        if len(r_peaks) >= 2:
            hrv = self.extract_hrv_features(r_peaks)
            features['hrv'] = hrv
        else:
            features['hrv'] = self._get_empty_hrv_features()
        
        # 3. 주파수 영역 특징
        frequency = self.extract_frequency_features(template)
        features['frequency'] = frequency
        
        # 4. 통계적 특징
        statistical = self.extract_statistical_features(template)
        features['statistical'] = statistical
        
        return features
    
    def extract_morphological_features(self, template: np.ndarray) -> Dict:
        """
        형태학적 특징 추출 (P, QRS, T 파형)
        
        Args:
            template: 대표 템플릿
            
        Returns:
            형태학적 특징 딕셔너리
        """
        features = {}
        
        if len(template) == 0:
            return self._get_empty_morphological_features()
        
        # R-peak 위치 찾기 (템플릿 내)
        r_idx = int(len(template) * self.r_peak_ratio)
        
        # 실제 R-peak 위치 미세 조정
        search_start = max(0, r_idx - 20)
        search_end = min(len(template), r_idx + 20)
        r_idx = search_start + np.argmax(template[search_start:search_end])
        
        # === P, QRS, T 경계 탐지 ===
        boundaries = self._detect_wave_boundaries(template, r_idx)
        
        # === R-peak 특징 ===
        features['r_amplitude'] = float(template[r_idx])
        features['r_position'] = r_idx / len(template)  # 정규화된 위치
        
        # === Q파 특징 ===
        q_idx = boundaries.get('q_onset', r_idx - 10)
        if 0 <= q_idx < len(template):
            features['q_amplitude'] = float(template[q_idx])
            features['qr_interval'] = (r_idx - q_idx) / self.fs * 1000  # ms
        else:
            features['q_amplitude'] = 0.0
            features['qr_interval'] = 0.0
        
        # === S파 특징 ===
        s_idx = boundaries.get('s_end', r_idx + 10)
        if 0 <= s_idx < len(template):
            features['s_amplitude'] = float(template[s_idx])
            features['rs_interval'] = (s_idx - r_idx) / self.fs * 1000  # ms
        else:
            features['s_amplitude'] = 0.0
            features['rs_interval'] = 0.0
        
        # === QRS 복합체 특징 ===
        features['qrs_duration'] = features['qr_interval'] + features['rs_interval']
        features['qrs_area'] = self._calculate_area(template, q_idx, s_idx)
        
        # === P파 특징 ===
        p_start = boundaries.get('p_onset', 0)
        p_end = boundaries.get('p_offset', q_idx)
        p_peak = boundaries.get('p_peak', (p_start + p_end) // 2)
        
        if 0 <= p_peak < len(template):
            features['p_amplitude'] = float(template[p_peak])
            features['p_duration'] = (p_end - p_start) / self.fs * 1000  # ms
            features['pr_interval'] = (r_idx - p_start) / self.fs * 1000  # ms
            features['p_area'] = self._calculate_area(template, p_start, p_end)
        else:
            features['p_amplitude'] = 0.0
            features['p_duration'] = 0.0
            features['pr_interval'] = 0.0
            features['p_area'] = 0.0
        
        # === T파 특징 ===
        t_start = boundaries.get('t_onset', s_idx)
        t_end = boundaries.get('t_offset', len(template) - 1)
        t_peak = boundaries.get('t_peak', (t_start + t_end) // 2)
        
        if 0 <= t_peak < len(template):
            features['t_amplitude'] = float(template[t_peak])
            features['t_duration'] = (t_end - t_start) / self.fs * 1000  # ms
            features['qt_interval'] = (t_end - q_idx) / self.fs * 1000  # ms
            features['st_segment'] = (t_start - s_idx) / self.fs * 1000  # ms
            features['t_area'] = self._calculate_area(template, t_start, t_end)
        else:
            features['t_amplitude'] = 0.0
            features['t_duration'] = 0.0
            features['qt_interval'] = 0.0
            features['st_segment'] = 0.0
            features['t_area'] = 0.0
        
        # === 파형 간 비율 ===
        if features['r_amplitude'] != 0:
            features['p_r_ratio'] = features['p_amplitude'] / features['r_amplitude']
            features['t_r_ratio'] = features['t_amplitude'] / features['r_amplitude']
        else:
            features['p_r_ratio'] = 0.0
            features['t_r_ratio'] = 0.0
        
        # === 기울기 특징 ===
        features['r_upslope'] = self._calculate_slope(template, q_idx, r_idx)
        features['r_downslope'] = self._calculate_slope(template, r_idx, s_idx)
        
        return features
    
    def _detect_wave_boundaries(self, template: np.ndarray, r_idx: int) -> Dict:
        """
        P, QRS, T 파형 경계 탐지
        """
        boundaries = {}
        n = len(template)
        
        # === QRS 경계 ===
        # Q onset: R-peak 이전 최소값
        q_search_start = max(0, r_idx - int(0.1 * self.fs))
        q_search_end = r_idx
        if q_search_start < q_search_end:
            q_onset = q_search_start + np.argmin(template[q_search_start:q_search_end])
        else:
            q_onset = max(0, r_idx - 10)
        boundaries['q_onset'] = q_onset
        
        # S end: R-peak 이후 최소값
        s_search_start = r_idx
        s_search_end = min(n, r_idx + int(0.1 * self.fs))
        if s_search_start < s_search_end:
            s_end = s_search_start + np.argmin(template[s_search_start:s_search_end])
        else:
            s_end = min(n - 1, r_idx + 10)
        boundaries['s_end'] = s_end
        
        # === P파 경계 ===
        p_search_end = q_onset
        p_search_start = max(0, p_search_end - int(0.15 * self.fs))
        
        if p_search_start < p_search_end:
            p_region = template[p_search_start:p_search_end]
            p_peak_rel = np.argmax(p_region)
            p_peak = p_search_start + p_peak_rel
            
            # P onset: P peak 이전 최소값
            p_onset = p_search_start + np.argmin(p_region[:p_peak_rel]) if p_peak_rel > 0 else p_search_start
            # P offset: P peak 이후 최소값
            p_offset = p_search_start + p_peak_rel + np.argmin(p_region[p_peak_rel:]) if p_peak_rel < len(p_region) else p_search_end
        else:
            p_peak = p_search_start
            p_onset = p_search_start
            p_offset = p_search_end
            
        boundaries['p_onset'] = p_onset
        boundaries['p_peak'] = p_peak
        boundaries['p_offset'] = p_offset
        
        # === T파 경계 ===
        t_search_start = s_end + int(0.02 * self.fs)  # ST segment 이후
        t_search_end = min(n, s_end + int(0.4 * self.fs))
        
        if t_search_start < t_search_end:
            t_region = template[t_search_start:t_search_end]
            t_peak_rel = np.argmax(t_region)
            t_peak = t_search_start + t_peak_rel
            
            # T onset
            t_onset = t_search_start
            # T offset: T peak 이후 기준선 복귀 지점
            if t_peak_rel < len(t_region) - 1:
                t_offset = t_search_start + t_peak_rel + np.argmin(np.abs(t_region[t_peak_rel:]))
            else:
                t_offset = t_search_end - 1
        else:
            t_peak = t_search_start
            t_onset = t_search_start
            t_offset = min(n - 1, t_search_end)
            
        boundaries['t_onset'] = t_onset
        boundaries['t_peak'] = t_peak
        boundaries['t_offset'] = t_offset
        
        return boundaries
    
    def _calculate_area(self, template: np.ndarray, start: int, end: int) -> float:
        """파형 면적 계산 (절대값 적분)"""
        if start >= end or start < 0 or end > len(template):
            return 0.0
        return float(np.trapz(np.abs(template[start:end])))
    
    def _calculate_slope(self, template: np.ndarray, start: int, end: int) -> float:
        """기울기 계산"""
        if start >= end or start < 0 or end >= len(template):
            return 0.0
        return float((template[end] - template[start]) / (end - start + 1))
    
    def extract_hrv_features(self, r_peaks: np.ndarray) -> Dict:
        """
        심박변이도 (HRV) 특징 추출
        
        Args:
            r_peaks: R-peak 위치 배열
            
        Returns:
            HRV 특징 딕셔너리
        """
        features = {}
        
        if len(r_peaks) < 2:
            return self._get_empty_hrv_features()
        
        # RR 간격 계산 (ms)
        rr_intervals = np.diff(r_peaks) / self.fs * 1000
        
        # 이상치 RR 간격 제거 (300ms ~ 2000ms)
        valid_rr = rr_intervals[(rr_intervals > 300) & (rr_intervals < 2000)]
        
        if len(valid_rr) < 2:
            return self._get_empty_hrv_features()
        
        # === 시간 영역 HRV ===
        features['mean_rr'] = float(np.mean(valid_rr))
        features['std_rr'] = float(np.std(valid_rr))
        features['mean_hr'] = 60000.0 / features['mean_rr'] if features['mean_rr'] > 0 else 0
        
        # SDNN: RR 간격의 표준편차
        features['sdnn'] = float(np.std(valid_rr))
        
        # RMSSD: 연속 RR 간격 차이의 제곱평균제곱근
        rr_diff = np.diff(valid_rr)
        features['rmssd'] = float(np.sqrt(np.mean(rr_diff ** 2))) if len(rr_diff) > 0 else 0
        
        # pNN50: 50ms 이상 차이나는 연속 RR 간격 비율
        if len(rr_diff) > 0:
            features['pnn50'] = float(np.sum(np.abs(rr_diff) > 50) / len(rr_diff) * 100)
        else:
            features['pnn50'] = 0.0
        
        # pNN20: 20ms 이상 차이나는 연속 RR 간격 비율
        if len(rr_diff) > 0:
            features['pnn20'] = float(np.sum(np.abs(rr_diff) > 20) / len(rr_diff) * 100)
        else:
            features['pnn20'] = 0.0
        
        # CV: 변동계수 (SDNN / Mean RR)
        features['cv_rr'] = features['sdnn'] / features['mean_rr'] if features['mean_rr'] > 0 else 0
        
        return features
    
    def extract_frequency_features(self, template: np.ndarray) -> Dict:
        """
        주파수 영역 특징 추출
        
        Args:
            template: 대표 템플릿
            
        Returns:
            주파수 특징 딕셔너리
        """
        features = {}
        
        if len(template) == 0:
            return self._get_empty_frequency_features()
        
        # FFT 계산
        n = len(template)
        yf = fft(template)
        xf = fftfreq(n, 1/self.fs)
        
        # 양의 주파수만 사용
        positive_freq_mask = xf >= 0
        xf = xf[positive_freq_mask]
        yf = np.abs(yf[positive_freq_mask])
        
        # 파워 스펙트럼
        power = yf ** 2
        total_power = np.sum(power)
        
        if total_power == 0:
            return self._get_empty_frequency_features()
        
        # === 주파수 대역별 에너지 ===
        # 저주파 (0-5Hz): P, T 파
        lf_mask = (xf >= 0) & (xf < 5)
        features['lf_power'] = float(np.sum(power[lf_mask]) / total_power)
        
        # 중주파 (5-15Hz): QRS 복합체
        mf_mask = (xf >= 5) & (xf < 15)
        features['mf_power'] = float(np.sum(power[mf_mask]) / total_power)
        
        # 고주파 (15-40Hz): 고주파 성분
        hf_mask = (xf >= 15) & (xf < 40)
        features['hf_power'] = float(np.sum(power[hf_mask]) / total_power)
        
        # LF/HF 비율
        hf_power_abs = np.sum(power[hf_mask])
        features['lf_hf_ratio'] = float(np.sum(power[lf_mask]) / hf_power_abs) if hf_power_abs > 0 else 0
        
        # 주파수 중심 (Spectral centroid)
        features['spectral_centroid'] = float(np.sum(xf * power) / total_power)
        
        # 주파수 분산
        features['spectral_spread'] = float(np.sqrt(np.sum(((xf - features['spectral_centroid']) ** 2) * power) / total_power))
        
        # 지배 주파수 (최대 파워 주파수)
        features['dominant_freq'] = float(xf[np.argmax(power)])
        
        # 상위 5개 FFT 계수 (정규화)
        top_indices = np.argsort(yf)[-5:]
        features['top_fft_coeffs'] = [float(yf[i] / np.max(yf)) for i in top_indices]
        
        return features
    
    def extract_statistical_features(self, template: np.ndarray) -> Dict:
        """
        통계적 특징 추출
        
        Args:
            template: 대표 템플릿
            
        Returns:
            통계적 특징 딕셔너리
        """
        features = {}
        
        if len(template) == 0:
            return self._get_empty_statistical_features()
        
        # 기본 통계
        features['mean'] = float(np.mean(template))
        features['std'] = float(np.std(template))
        features['var'] = float(np.var(template))
        features['max'] = float(np.max(template))
        features['min'] = float(np.min(template))
        features['range'] = features['max'] - features['min']
        
        # 고차 통계
        features['skewness'] = float(skew(template))
        features['kurtosis'] = float(kurtosis(template))
        
        # 에너지
        features['energy'] = float(np.sum(template ** 2))
        features['rms'] = float(np.sqrt(np.mean(template ** 2)))
        
        # Zero-crossing rate
        zero_crossings = np.sum(np.abs(np.diff(np.sign(template))) > 0)
        features['zero_crossing_rate'] = float(zero_crossings / len(template))
        
        # 엔트로피 (히스토그램 기반)
        hist, _ = np.histogram(template, bins=50, density=True)
        hist = hist[hist > 0]  # 0 제거
        features['entropy'] = float(-np.sum(hist * np.log2(hist + 1e-10)))
        
        return features
    
    def _get_empty_morphological_features(self) -> Dict:
        """빈 형태학적 특징 반환"""
        return {
            'r_amplitude': 0.0, 'r_position': 0.0,
            'q_amplitude': 0.0, 'qr_interval': 0.0,
            's_amplitude': 0.0, 'rs_interval': 0.0,
            'qrs_duration': 0.0, 'qrs_area': 0.0,
            'p_amplitude': 0.0, 'p_duration': 0.0, 'pr_interval': 0.0, 'p_area': 0.0,
            't_amplitude': 0.0, 't_duration': 0.0, 'qt_interval': 0.0, 'st_segment': 0.0, 't_area': 0.0,
            'p_r_ratio': 0.0, 't_r_ratio': 0.0,
            'r_upslope': 0.0, 'r_downslope': 0.0
        }
    
    def _get_empty_hrv_features(self) -> Dict:
        """빈 HRV 특징 반환"""
        return {
            'mean_rr': 0.0, 'std_rr': 0.0, 'mean_hr': 0.0,
            'sdnn': 0.0, 'rmssd': 0.0, 'pnn50': 0.0, 'pnn20': 0.0, 'cv_rr': 0.0
        }
    
    def _get_empty_frequency_features(self) -> Dict:
        """빈 주파수 특징 반환"""
        return {
            'lf_power': 0.0, 'mf_power': 0.0, 'hf_power': 0.0, 'lf_hf_ratio': 0.0,
            'spectral_centroid': 0.0, 'spectral_spread': 0.0, 'dominant_freq': 0.0,
            'top_fft_coeffs': [0.0] * 5
        }
    
    def _get_empty_statistical_features(self) -> Dict:
        """빈 통계적 특징 반환"""
        return {
            'mean': 0.0, 'std': 0.0, 'var': 0.0, 'max': 0.0, 'min': 0.0, 'range': 0.0,
            'skewness': 0.0, 'kurtosis': 0.0, 'energy': 0.0, 'rms': 0.0,
            'zero_crossing_rate': 0.0, 'entropy': 0.0
        }

