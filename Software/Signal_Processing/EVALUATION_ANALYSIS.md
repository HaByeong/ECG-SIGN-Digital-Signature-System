# ECG 인증 시스템 보안 분석 및 개선 방안

## 📊 현재 시스템 분석

### 현재 설정
- **임계값**: 0.75 (75%)
- **비교 방법**: 코사인 유사도
- **특징 벡터 크기**: 약 37-47개
- **검증 상태**: 더미 데이터만 테스트됨 ⚠️

---

## 🔍 False Positive Rate (FAR) 분석

### 1. 예상 시나리오

#### 시나리오 A: 낙관적 경우 (임계값 0.75 적절)
- 같은 사람 내 유사도: 0.85-0.95
- 다른 사람 간 유사도: 0.50-0.70
- **예상 FAR**: 5-15% (100명 중 5-15명이 우연히 통과)

#### 시나리오 B: 비관적 경우 (임계값 0.75 낮음)
- 같은 사람 내 유사도: 0.80-0.90
- 다른 사람 간 유사도: 0.65-0.78
- **예상 FAR**: 20-40% (100명 중 20-40명이 우연히 통과) ⚠️

### 2. 문제점

1. **임계값이 너무 낮을 가능성**
   - 0.75는 생체 인증에서 낮은 편
   - 일반적으로 0.85-0.90 이상 권장

2. **실제 데이터 검증 부족**
   - 더미 데이터는 같은 파라미터로 생성되어 비현실적
   - 실제 사람들의 ECG 패턴 차이가 충분한지 미확인

3. **특징 벡터의 구분력 미확인**
   - 37-47개 특징이 충분한지 불명확
   - 일부 특징이 사람별로 유사할 수 있음

---

## 🔒 보안 개선 방안

### 방안 1: 임계값 상향 조정 (즉시 적용 가능)

**권장 임계값**: 0.85-0.90

```python
# ecg_server.py
SIMILARITY_THRESHOLD = 0.85  # 0.75에서 0.85로 상향
```

**효과**:
- FAR 감소: 약 20-40% → 5-15%
- FRR 증가 가능 (본인이 로그인 실패 확률 증가)
- **권장**: 0.85부터 시작하여 실제 데이터로 튜닝

---

### 방안 2: 다중 템플릿 등록 (Medium Priority)

현재 시스템은 여러 템플릿 저장이 가능하지만, 최고 유사도만 비교함.

**개선**:
- 평균 유사도 사용
- 또는 N개 템플릿 중 M개 이상 일치해야 성공

```python
# 예시: 3개 템플릿 중 2개 이상 0.85 이상이면 성공
def login(self, ecg_signature, user_id=None):
    # ... 기존 코드 ...
    
    # 여러 템플릿과 비교 후 평균 유사도 계산
    similarities = []
    for template in user_data.get('ecg_templates', []):
        similarity = self._cosine_similarity(input_vector, template_vector)
        similarities.append(similarity)
    
    avg_similarity = np.mean(similarities)
    max_similarity = np.max(similarities)
    
    # 평균과 최대 모두 고려
    final_score = 0.7 * avg_similarity + 0.3 * max_similarity
    
    if final_score >= self.similarity_threshold:
        # 로그인 성공
```

---

### 방안 3: 역치 기반 점진적 인증 (High Priority)

단일 임계값 대신 여러 레벨의 보안 적용:

```python
# ecg_server.py
# 다단계 임계값 설정
STRICT_THRESHOLD = 0.90   # 높은 보안 필요 시
NORMAL_THRESHOLD = 0.85   # 일반 사용
RELAXED_THRESHOLD = 0.80  # 테스트/개발용
```

---

### 방안 4: 실제 데이터 수집 및 평가 (Critical)

**즉시 필요한 작업**:

1. **테스트 데이터 수집**
   - 최소 10-20명의 실제 사용자 데이터
   - 각 사용자당 3-5회 등록 및 로그인 시도

2. **성능 평가 지표 계산**
   ```python
   # 평가 스크립트 예시
   def evaluate_system(thresholds=[0.70, 0.75, 0.80, 0.85, 0.90]):
       results = {}
       
       for threshold in thresholds:
           # True Positive Rate (TPR)
           tpr = calculate_tpr(threshold)
           
           # False Positive Rate (FAR)
           far = calculate_far(threshold)
           
           # Equal Error Rate (EER)
           eer = find_eer(threshold)
           
           results[threshold] = {
               'TPR': tpr,
               'FAR': far,
               'EER': eer
           }
       
       return results
   ```

3. **ROC 곡선 그리기**
   - 다양한 임계값에서 TPR vs FAR 그래프
   - 최적 임계값 선택 (보통 EER 지점)

---

### 방안 5: 특징 벡터 개선 (Long-term)

1. **특징 선택 (Feature Selection)**
   - 개인 식별에 효과적인 특징만 선택
   - 상관관계 분석으로 중복 특징 제거

2. **특징 가중치 조정**
   - 현재는 형태학적 특징에 높은 가중치
   - 실제 데이터로 가중치 최적화

3. **추가 특징 고려**
   - 심박수 변동성 패턴
   - 시간대별 변동성
   - 호흡 패턴 연관성

---

## 📈 권장 조치 사항

### 즉시 조치 (즉시)

1. ✅ **임계값 상향**: 0.75 → 0.85
2. ✅ **로그 추가**: 모든 로그인 시도 기록 (유사도 점수 포함)

### 단기 조치 (1-2주 내)

3. ⚠️ **실제 데이터 수집**: 최소 10명 이상 테스트
4. ⚠️ **평가 스크립트 작성**: FAR, FRR, EER 계산

### 중기 조치 (1-2개월 내)

5. 📊 **성능 평가 완료**: ROC 곡선 및 최적 임계값 결정
6. 🔒 **다중 템플릿 로직 개선**: 평균 유사도 또는 투표 방식

### 장기 조치 (3개월 이상)

7. 🎯 **특징 선택 및 최적화**
8. 🤖 **머신러닝 모델 고려** (선택사항)

---

## 🎯 목표 성능 지표

### 권장 목표 (일반 생체 인증 기준)
- **FAR (False Acceptance Rate)**: < 1%
- **FRR (False Rejection Rate)**: < 5%
- **EER (Equal Error Rate)**: < 3%

### 현재 예상 성능 (임계값 0.75)
- **FAR**: 약 15-40% ⚠️ (너무 높음)
- **FRR**: 약 5-10%
- **EER**: 약 10-20%

### 개선 후 예상 성능 (임계값 0.85)
- **FAR**: 약 5-15% (개선됨)
- **FRR**: 약 10-20% (약간 증가)
- **EER**: 약 5-10%

---

## 💡 결론

**현재 상태**: 다른 사람의 로그인 성공 확률이 **높을 가능성이 큼** (15-40%)

**주요 원인**:
1. 임계값 0.75가 낮음
2. 실제 데이터 검증 부족

**즉시 개선 필요**:
1. 임계값을 0.85로 상향
2. 실제 사용자 데이터로 검증 시작

**장기 개선**:
- 평가 지표 계산 및 최적화
- 특징 벡터 개선
- 다중 템플릿 로직 강화

