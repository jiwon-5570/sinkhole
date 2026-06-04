# 07_Feature_엔지니어링_가이드

## 1. 목적

이 문서는 위험도 분석에 사용되는 feature의 생성 기준과 DB 원천을 설명한다. 현재 feature 생성은 `Project/backend/app/services/features.py`에 구현되어 있다.

## 2. Feature 생성 흐름

```text
분석 요청
-> analysis_date 결정
-> feature_dataset 조회
-> 없으면 원천 테이블 집계
-> 지층/시설물 사고 보정
-> score_rule_based() 입력
```

지역 feature:

```python
load_or_build_feature_row(conn, region_id, analysis_date)
```

도로 feature:

```python
load_or_build_road_feature_row(conn, road_id, analysis_date)
```

## 3. 공통 Feature 목록

| 컬럼 | 타입 | 설명 |
| --- | --- | --- |
| `past_sinkhole_count` | integer | 과거 지반침하 사고 건수 |
| `gpr_detected_count` | integer/real | GPR 공동 탐지 또는 탐사 이상 신호 |
| `facility_aging_score` | real | 시설물 노후/점검/사고 보정 점수 |
| `rainfall_score` | real | 최근 강우 영향 점수 |
| `groundwater_score` | real | 지하수 영향 점수 |
| `environment_score` | real | 환경/지층 영향 점수 |
| `construction_score` | real | 공사 영향 점수 |

보정 후 응답에는 다음 보조 필드가 포함될 수 있다.

- `facility_accident_score`
- `ground_layer_score`
- `ground_layer_nearby_count`
- `ground_layer_summary`

## 4. 분석일 결정

분석일은 다음 우선순위로 결정한다.

1. request의 `analysis_date`
2. request의 `client_local_datetime` 날짜 부분
3. 서버 기준 오늘 날짜

관련 함수:

```python
resolve_analysis_date()
normalize_local_datetime()
format_client_clock_label()
```

## 5. 지역 Feature 상세

### 5.1 과거 지반침하

```sql
SELECT COUNT(*) AS c
FROM sinkhole_history
WHERE region_id = ?
```

### 5.2 GPR/탐사

```sql
SELECT COALESCE(SUM(cavity_count), 0)
FROM gpr_inspection
WHERE region_id = ?
```

추가로 `molit_aggregate_geophysics`에서 탐사 신호를 최대 2.0까지 보조 반영한다.

### 5.3 시설물

기본:

```sql
SELECT COALESCE(AVG(aging_score), 0)
FROM facility_safety
WHERE region_id = ?
```

보정:

- `facility_status`의 노후 비율
- `facility_inspection.risk_score * 0.1`
- `facility_accidents` 최근 사고 위험

### 5.4 강우

```sql
SELECT COALESCE(SUM(rainfall), 0)
FROM weather_data
WHERE region_id = ?
  AND record_date >= date(?, '-7 day')
  AND record_date <= date(?)
```

계산:

```text
rainfall_score = min(10, rainfall_7d / 10)
```

### 5.5 지하수

우선 최근 7일 평균 변동을 사용한다.

```sql
SELECT COALESCE(AVG(variation), 0)
FROM groundwater_data
WHERE region_id = ?
  AND record_date >= date(?, '-7 day')
  AND record_date <= date(?)
```

관측값이 없으면 주변 시추공 기반 점수를 사용한다.

### 5.6 환경/지층

기본 환경:

```sql
SELECT building_density, road_density
FROM environment_features
WHERE region_id = ?
ORDER BY id DESC
LIMIT 1
```

지층 보정은 `ground_layers.py`에서 주변 지층 요약을 생성해 `environment_score`에 더한다. 최종 환경 점수는 factor 최대값 7점을 넘지 않게 제한한다.

### 5.7 공사 영향

```sql
SELECT COALESCE(MAX(scale_score), 0)
FROM construction_events
WHERE region_id = ?
```

공사 feature는 최대 20점으로 제한된다. 최종 기여점은 `risk_scoring.py`에서 최대 6점으로 제한된다.

## 6. 도로 Feature 상세

도로 feature는 지역 feature와 구조가 같지만 원천 테이블이 도로 단위 테이블을 우선 사용한다.

| Feature | 도로 원천 |
| --- | --- |
| 과거 침하 | `road_sinkhole_history` |
| GPR | `road_gpr_inspection` |
| 시설물 | `road_facility_safety`, 부모 region 시설물 |
| 강우 | 부모 region `weather_data` |
| 지하수 | 도로 중심 좌표 주변 시추공 |
| 환경 | `road_environment_features` |
| 공사 | `road_construction_events` |

도로가 속한 region은 `road_segments.region_id`로 확인한다.

## 7. 지층 보정

`ground_layers.py`는 대상 좌표 주변 지층 데이터를 분석한다.

반영 요소:

- 주변 지층 데이터 개수
- 지층명과 토질 분류
- N값
- 두께
- 깊이
- 연약층 또는 모래/매립/점토 계열 위험 신호

결과는 `ground_layer_summary`로 응답에 포함되어 AI 설명과 리포트 근거로 사용할 수 있다.

## 8. Feature 캐시

지역 feature 캐시:

```text
feature_dataset(region_id, analysis_date)
```

도로 feature 캐시:

```text
road_feature_dataset(road_id, analysis_date)
```

캐시 삭제 조건:

- 공공데이터 수집 후 정규화 데이터 변경
- 로컬 도로굴착 파일 추가/수정/삭제
- 지층/시추 데이터 재적재
- 알고리즘 변경 후 재분석 필요

## 9. 데이터 부족 처리

- 원천 데이터가 없으면 0점 또는 fallback을 사용한다.
- 지하수 관측값이 없으면 시추공 데이터를 사용한다.
- 지층 데이터가 없으면 지층 보정은 0점이다.
- 도로 데이터가 없으면 도로 API는 빈 목록을 반환한다.
- 차트는 지역 데이터가 부족하면 전체 지역 fallback을 명시할 수 있다.

## 10. Feature 변경 체크리스트

- [ ] DB 스키마 컬럼 추가 여부 확인
- [ ] `features.py` 지역/도로 양쪽 반영 여부 확인
- [ ] `risk_scoring.py` factor 배점 변경 여부 확인
- [ ] UI factor label과 리포트 문구 갱신
- [ ] 캐시 무효화 필요 여부 확인
- [ ] 기존 DB에서 null 값 처리 확인
- [ ] py_compile 실행

## 11. 향후 개선

- feature 생성 run 이력 저장
- feature별 데이터 품질 점수 별도 저장
- ML 학습용 feature snapshot 테이블 분리
- 도로망 데이터 확보 후 도로 feature 활성화
- 기상/지하수 실시간성 강화
