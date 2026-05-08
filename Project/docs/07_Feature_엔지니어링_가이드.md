# 07_Feature_엔지니어링_가이드.md

# 국토안전관리 프로젝트 Feature 엔지니어링 가이드

## 1. 문서 목적

이 문서는 국토안전관리 프로젝트에서 사용할 입력 변수(Feature)를 정의하고,  
원천 데이터를 분석 가능한 형태로 변환하는 기준을 정리한 문서이다.

본 가이드는 다음을 목표로 한다.

1. 원천 데이터를 학습 가능한 정형 feature로 변환한다.
2. 국토안전관리원 중심 데이터의 핵심 변수 구조를 정의한다.
3. 기상, 지하수, 환경 등의 보조 데이터를 일관된 방식으로 feature화한다.
4. 모델 입력용 `feature_dataset` 생성 기준을 명확히 한다.
5. 결과 해석이 가능한 feature 구조를 설계한다.

---

## 2. Feature 엔지니어링 기본 원칙

### 2.1 원천 데이터보다 feature가 더 중요하다
모델은 원천 데이터 자체보다,  
원천 데이터를 어떻게 **가공하여 설명력 있는 변수로 바꾸는가**에 따라 성능이 달라진다.

### 2.2 국토안전관리원 데이터 중심
feature 설계의 중심은 반드시 아래 데이터여야 한다.
- 지반침하 이력
- 지반침하 안전점검
- GPR 탐사 결과
- 시설물 안전관리 정보

### 2.3 공간 feature를 정형화한다
공간 데이터는 지도 좌표 그대로 넣기보다,  
분석 단위(격자, 행정동, 도로구간) 기준으로 집계하여 정형 변수로 만든다.

### 2.4 설명 가능성이 있어야 한다
feature는 모델 성능뿐 아니라,  
“왜 이 지역이 위험한가”를 설명하는 데 사용되므로 해석 가능한 형태여야 한다.

### 2.5 공사 변수는 보조 feature
공사 관련 변수는 설계하되,  
핵심 설명 변수로 보이지 않도록 낮은 가중치의 보조 feature로 유지한다.

---

## 3. Feature 엔지니어링 전체 흐름

```text
원천 데이터 수집
→ 정제 및 표준화
→ 지역 단위 매핑
→ 시간 기준 집계
→ feature 생성
→ feature_dataset 저장
→ 모델 입력
4. Feature 분류 체계

이번 프로젝트의 feature는 다음 5그룹으로 나눈다.

기본 취약도 Feature
GPR/탐사 Feature
기상 Feature
지하수 Feature
환경/보조 Feature
5. 분석 단위 설정

Feature 생성 전 반드시 분석 단위를 먼저 정해야 한다.

5.1 후보 분석 단위
행정동
시군구
도로 구간
grid(격자)
5.2 권장 단위

grid 단위를 권장한다.

예시:

500m × 500m 격자
1km × 1km 격자

이유:

지도 시각화가 쉬움
공간 집계에 유리
지역별 위험도 히트맵 생성 가능
행정구역보다 세밀한 표현 가능
5.3 region_id 부여 기준

모든 feature는 최종적으로 아래 구조를 가져야 한다.

region_id + analysis_date + feature columns
6. 기본 취약도 Feature

이 그룹은 프로젝트의 핵심이다.

6.1 past_sinkhole_count
정의

특정 region 내 과거 지반침하 발생 건수

생성 방식
region_id 기준 단순 건수 집계
의미

과거 사고가 많을수록 기본 취약도 높음

6.2 past_sinkhole_density
정의

면적 대비 과거 지반침하 발생 밀도

생성 방식
과거 사고 건수 / 면적
또는 과거 사고 건수 / grid 수
의미

단순 건수보다 공간적으로 얼마나 집중되었는지 반영

6.3 past_sinkhole_recent_count
정의

최근 N년 내 지반침하 발생 건수

생성 방식
최근 1년 / 3년 / 5년 집계 가능
의미

오래된 사고보다 최근 사고 패턴을 더 민감하게 반영

6.4 cause_type_encoded
정의

주요 사고 원인 유형 인코딩 값

원천 데이터 예시
하수관 손상
굴착 영향
지반 약화
기타
생성 방식
Label Encoding 또는 One-hot Encoding
의미

원인 유형에 따른 위험 구조 차이 반영

6.5 ground_type_encoded
정의

지반 종류 또는 지질 특성 인코딩 값

의미

취약 지반 여부를 반영

6.6 facility_aging_score
정의

지역 내 시설물 노후도 점수

생성 방식 예시
노후 시설물 수
점검 누락 시설물 수
낮은 안전등급 시설물 비율
의미

구조적 취약성 반영

6.7 facility_density
정의

지역 내 시설물 밀집 정도

의미

노후 시설이 밀집된 지역일수록 위험 가중 가능

7. GPR/탐사 Feature

이 그룹은 지반침하 검증성과 현장성 측면에서 매우 중요하다.

7.1 gpr_detected_count
정의

특정 지역에서 탐지된 공동 또는 이상 신호 개수

생성 방식
region_id 기준 GPR 탐지 건수 집계
의미

지하 공동 가능성 반영

7.2 gpr_cavity_flag
정의

공동 탐지 여부

값 예시
0: 없음
1: 있음
의미

이진 판단용 강한 feature

7.3 gpr_inspection_count
정의

해당 지역 GPR 탐사 횟수

의미

탐사가 많이 이루어진 지역인지 반영
주의:
단순히 탐사가 많다고 위험하다고 해석하면 안 되므로 보정 필요

7.4 gpr_detected_density
정의

탐사 구간당 탐지 밀도

생성 방식
공동 탐지 개수 / 탐사 거리
의미

탐사 강도 차이를 보정하여 비교 가능하게 만듦

7.5 avg_cavity_depth
정의

탐지된 공동의 평균 추정 깊이

의미

심도에 따른 위험 특성 참고 가능
선택 feature로 사용 가능

8. 기상 Feature

단기 위험 상승 신호를 설명하는 데 중요하다.

8.1 rainfall_1d
정의

최근 1일 누적 강우량

의미

단기 급격한 강우 반영

8.2 rainfall_3d
정의

최근 3일 누적 강우량

의미

단기 집중강우 누적 반영

8.3 rainfall_7d
정의

최근 7일 누적 강우량

의미

위험 상승 신호의 핵심 변수 후보

8.4 rainfall_30d
정의

최근 30일 누적 강우량

의미

장기 수분 축적 영향 반영

8.5 rainfall_intensity_score
정의

강우 강도 점수

생성 방식 예시
시간당 최대 강우량
최근 강우의 집중도 계산
의미

같은 누적 강우량이라도 집중 강우 여부를 반영

8.6 temperature_avg
정의

평균 기온

8.7 temperature_change_range
정의

최근 일정 기간의 기온 변화 폭

생성 방식
max(temp) - min(temp)
의미

급격한 기온 변화로 인한 지반 상태 변화 가능성 반영

8.8 humidity_avg
정의

평균 습도

의미

보조적 설명 변수

9. 지하수 Feature
9.1 groundwater_level
정의

해당 지역 평균 지하수위

9.2 groundwater_variation_daily
정의

하루 단위 지하수위 변화량

9.3 groundwater_variation_weekly
정의

주 단위 지하수위 변화량

9.4 groundwater_variation_monthly
정의

월 단위 지하수위 변화량

의미

지반 내부 안정성 변화와 연관 가능

9.5 groundwater_volatility_score
정의

변동성 점수

생성 방식 예시
최근 N일 표준편차
변화율 절대값 평균
의미

안정/불안정 상태를 더 잘 반영

10. 환경 Feature

이 그룹은 지역별 구조적 차이를 설명하는 데 사용된다.

10.1 building_density
정의

건축물 밀집도

의미

도시화 밀집도, 지반 하중 가능성 보조 설명

10.2 road_density
정의

도로 밀집도

의미

지반침하 점검·사고가 도로 기반으로 발생할 가능성 반영

10.3 land_use_type
정의

토지 이용 유형

예시
주거지역
상업지역
공업지역
녹지지역
처리 방식
one-hot encoding 또는 label encoding
10.4 commercial_area_ratio
정의

상업지 비율

10.5 residential_area_ratio
정의

주거지 비율

10.6 old_building_ratio
정의

노후 건축물 비율

의미

오래된 지하시설과 함께 취약성 보조 설명 가능

10.7 impervious_surface_ratio
정의

불투수면 비율

의미

배수/침투 특성과 관련된 보조 feature

11. 공사/보조 Feature

주의:
이 그룹은 반드시 보조 feature로만 사용한다.

11.1 construction_flag
정의

인근 공사 존재 여부

값 예시
0: 없음
1: 있음
11.2 construction_scale_score
정의

공사 규모 점수

예시
소규모: 1
중규모: 2
대규모: 3
11.3 excavation_flag
정의

굴착 여부

의미

지반 교란 가능성 보조 반영

11.4 distance_to_construction
정의

공사 지점까지 거리

의미

가까울수록 보조 위험성 반영 가능

12. 파생 Feature 생성 전략

원천 데이터만 그대로 쓰지 않고, 파생 feature를 만드는 것이 중요하다.

12.1 집계형 Feature

예:

최근 7일 강우량 합
최근 30일 사고 발생 수
반경 내 GPR 탐지 수
12.2 비율형 Feature

예:

과거 사고 밀도
노후 건축물 비율
탐지 밀도
12.3 변화율 Feature

예:

지하수위 변화량
위험도 증감률
기온 변화 폭
12.4 조합 Feature

예:

rainfall_7d × groundwater_variation
past_sinkhole_density × gpr_cavity_flag

주의:
초기 MVP에서는 조합 feature를 너무 많이 만들지 않는다.

13. Feature Encoding 가이드
13.1 숫자형
그대로 사용
필요 시 로그 변환 가능
13.2 범주형
Label Encoding
One-hot Encoding
권장
feature 수가 적으면 one-hot
너무 많으면 label encoding
13.3 Boolean형
0/1로 변환
14. Feature Scaling 가이드

트리 기반 모델(XGBoost, LightGBM)은
일반적으로 엄격한 scaling이 필수는 아니다.

권장 원칙
숫자형은 기본값 유지
값 범위가 매우 큰 경우에만 로그 변환 또는 clipping 검토
StandardScaler는 필수 아님
15. Feature 선택 기준

좋은 feature는 다음 조건을 만족해야 한다.

설명력이 있다
해석 가능하다
데이터 품질이 안정적이다
지도와 그래프에서 설명 가능한 값이다
16. Feature 제거 기준

다음에 해당하면 제거 검토

결측치 비율이 너무 높음
실제 의미가 불명확함
중복된 변수와 거의 동일한 정보 제공
공사처럼 프로젝트 정체성을 흔들 수 있는 변수인데 비중이 커짐
17. feature_dataset 최종 구조 예시
region_id
analysis_date
past_sinkhole_count
past_sinkhole_density
past_sinkhole_recent_count
gpr_detected_count
gpr_cavity_flag
facility_aging_score
facility_density
rainfall_1d
rainfall_3d
rainfall_7d
rainfall_30d
temperature_change_range
humidity_avg
groundwater_level
groundwater_variation_weekly
groundwater_volatility_score
building_density
road_density
land_use_type
old_building_ratio
construction_flag
construction_scale_score
target_risk_score
target_risk_level
18. Feature 생성 순서
1단계

원천 데이터 정제

2단계

region_id 매핑

3단계

시간 단위 정렬

4단계

기본 집계 변수 생성

5단계

비율/변화율/파생 변수 생성

6단계

인코딩

7단계

feature_dataset 저장

19. Feature 품질 점검 체크리스트
 region_id 누락 없음
 analysis_date 정렬 가능
 숫자형 컬럼 타입 통일
 범주형 인코딩 완료
 결측치 처리 완료
 동일 의미 중복 컬럼 제거
 공사 변수 과대 반영 여부 점검
 목표 변수(target) 정의 완료
20. 서비스 연결 관점에서 중요한 Feature

UI와 리포트까지 고려하면 아래 feature는 특히 중요하다.

지도 설명용
total_risk_score
risk_level
past_sinkhole_density
gpr_detected_count
그래프 설명용
rainfall_7d
groundwater_variation_weekly
facility_aging_score
building_density
AI 리포트 설명용
top_contributing_features
risk_change_signal

즉, feature는 단순 학습용이 아니라
지도, 그래프, 리포트까지 이어질 수 있어야 한다.

21. 최종 요약

이 프로젝트의 feature 엔지니어링은 다음 구조로 정리된다.

국토안전관리원 중심의 기본 취약도 feature
기상/지하수 기반의 위험 상승 feature
공간/환경 기반의 설명력 강화 feature
공사 등 낮은 비중의 보조 feature

즉, feature 엔지니어링의 목적은 단순히 모델 정확도를 높이는 것이 아니라,
지반침하 위험을 설명 가능한 형태로 정량화하여 지도와 그래프로 보여줄 수 있게 만드는 것이다.
