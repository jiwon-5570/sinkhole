# 06_API_설계_가이드.md

# 국토안전관리 프로젝트 API 설계 가이드

## 1. 문서 목적

이 문서는 국토안전관리 프로젝트에서 사용할 API 구조를 정의한다.

본 가이드는 다음을 목표로 한다.

1. 프론트엔드와 백엔드가 공통으로 참조할 API 명세를 제공한다.
2. 화면별로 필요한 데이터 흐름을 명확히 한다.
3. 위험 분석, 지도 시각화, 그래프 출력, 리포트 생성까지 연결 가능한 API 구조를 설계한다.
4. 향후 확장 가능한 REST API 형태를 유지한다.

---

## 2. API 설계 기본 원칙

### 2.1 RESTful 구조 유지
- 리소스 중심 URL 설계
- GET / POST 역할 명확히 구분
- 응답은 JSON 중심

### 2.2 화면 중심 설계
API는 DB 구조만 반영하면 안 되고,  
**대시보드 / 지도 / 상세 분석 / 리포트 화면**이 실제로 필요로 하는 데이터 단위로 설계해야 한다.

### 2.3 결과 재사용성 확보
위험 분석 결과는 매번 실시간 계산만 하지 않고,  
가능하면 DB에 저장된 결과를 재사용할 수 있도록 한다.

### 2.4 생성형 AI와 예측 API 분리
- 예측 결과 API
- 설명 리포트 API
를 분리한다.

---

## 3. 전체 API 분류

전체 API는 다음 6개 그룹으로 분류한다.

1. 공통/기준 정보 API
2. 지역/지도 API
3. 위험 분석 API
4. 그래프/대시보드 API
5. 비교 분석 API
6. AI 리포트 API

---

## 4. 공통 응답 규칙

## 4.1 성공 응답 구조

```json
{
  "success": true,
  "message": "요청이 정상적으로 처리되었습니다.",
  "data": {}
}
4.2 실패 응답 구조
{
  "success": false,
  "message": "데이터를 찾을 수 없습니다.",
  "error_code": "NOT_FOUND"
}
4.3 권장 규칙
success: Boolean
message: 사용자 또는 개발자 확인용 메시지
data: 실제 응답 데이터
error_code: 실패 시 구분 코드
5. 공통/기준 정보 API
5.1 지역 목록 조회
목적
지역 선택 드롭다운
검색 자동완성
지도 초기 데이터 로드
Endpoint

GET /api/regions

Query Parameters
region_type (optional)
sido (optional)
sigungu (optional)
응답 예시
{
  "success": true,
  "data": [
    {
      "region_id": 101,
      "region_name": "부산광역시 해운대구",
      "region_type": "sigungu",
      "latitude": 35.1631,
      "longitude": 129.1635
    }
  ]
}
5.2 특정 지역 기본 정보 조회
목적
상세 분석 화면의 기본 지역 정보 제공
Endpoint

GET /api/region/{region_id}

응답 예시
{
  "success": true,
  "data": {
    "region_id": 101,
    "region_name": "부산광역시 해운대구",
    "region_type": "sigungu",
    "sido": "부산광역시",
    "sigungu": "해운대구",
    "latitude": 35.1631,
    "longitude": 129.1635
  }
}
6. 지도 관련 API
6.1 위험도 지도 레이어 조회
목적
위험 예측 지도 화면 표시
Endpoint

GET /api/map/risk-layer

Query Parameters
date
layer_type
base_risk
total_risk
rainfall_risk
groundwater_risk
gpr_layer
risk_level (optional)
sido (optional)
응답 예시
{
  "success": true,
  "data": [
    {
      "region_id": 101,
      "region_name": "부산광역시 해운대구",
      "latitude": 35.1631,
      "longitude": 129.1635,
      "risk_score": 82,
      "risk_level": "매우 높음"
    }
  ]
}
6.2 GPR 탐사 결과 레이어 조회
목적
지도에 GPR 탐사 또는 공동탐지 레이어 표시
Endpoint

GET /api/map/gpr-layer

Query Parameters
date_from
date_to
detected_only (optional)
응답 예시
{
  "success": true,
  "data": [
    {
      "region_id": 101,
      "inspection_date": "2026-04-01",
      "cavity_detected": true,
      "cavity_count": 2,
      "latitude": 35.1631,
      "longitude": 129.1635
    }
  ]
}
6.3 위험 핫스팟 조회
목적
우선 점검 또는 고위험 지점 마커 표시
Endpoint

GET /api/map/hotspots

Query Parameters
top_n (default=10)
risk_level (optional)
응답 예시
{
  "success": true,
  "data": [
    {
      "region_id": 101,
      "region_name": "부산광역시 해운대구",
      "risk_score": 89,
      "risk_level": "매우 높음",
      "priority_rank": 1
    }
  ]
}
7. 위험 분석 API
7.1 특정 지역 위험 분석 실행
목적
지역별 종합 위험도 계산
상세 분석 화면 및 리포트 생성의 핵심 API
Endpoint

POST /api/analyze-risk

요청 예시
{
  "region_id": 101,
  "analysis_date": "2026-04-19",
  "language": "Japanese" // 선택 사항. 기본값: "한국어". "English", "Japanese" 등 AI 모델이 지원하는 언어 사용 가능.
}
응답 예시
{
  "success": true,
  "data": {
    "region_id": 101,
    "analysis_date": "2026-04-19",
    "base_risk_score": 58,
    "weather_score": 10,
    "groundwater_score": 7,
    "environment_score": 5,
    "construction_score": 2,
    "total_risk_score": 82,
    "risk_level": "매우 높음",
    "risk_change_signal": "increasing",
    "priority_rank": 1
  }
}
7.2 저장된 분석 결과 조회
목적
이미 수행된 분석 결과를 재사용
지도/상세 분석/리포트에 공통 제공
Endpoint

GET /api/analysis/{region_id}

Query Parameters
analysis_date (optional)
응답 예시
{
  "success": true,
  "data": {
    "region_id": 101,
    "region_name": "부산광역시 해운대구",
    "analysis_date": "2026-04-19",
    "base_risk_score": 58,
    "weather_score": 10,
    "groundwater_score": 7,
    "environment_score": 5,
    "construction_score": 2,
    "total_risk_score": 82,
    "risk_level": "매우 높음",
    "risk_change_signal": "increasing",
    "priority_rank": 1
  }
}
7.3 우선 점검 대상지 조회
목적
대시보드 TOP 5
우선 점검 순위 표
Endpoint

GET /api/top-risk-regions

Query Parameters
top_n (default=5)
date
sido (optional)
응답 예시
{
  "success": true,
  "data": [
    {
      "region_id": 101,
      "region_name": "부산광역시 해운대구",
      "risk_score": 89,
      "risk_level": "매우 높음",
      "priority_rank": 1,
      "risk_reason": "과거 사고 이력 및 최근 강우량 증가"
    }
  ]
}
8. 그래프/대시보드 API
8.1 위험등급 분포 조회
목적
도넛 차트 출력
Endpoint

GET /api/charts/risk-distribution

Query Parameters
date
sido (optional)
응답 예시
{
  "success": true,
  "data": {
    "low": 120,
    "normal": 85,
    "high": 32,
    "very_high": 10
  }
}
8.2 위험도 추이 조회
목적
선그래프 출력
시간별 변화 확인
Endpoint

GET /api/charts/risk-trend

Query Parameters
region_id
date_from
date_to
응답 예시
{
  "success": true,
  "data": [
    {
      "date": "2026-04-01",
      "risk_score": 61
    },
    {
      "date": "2026-04-08",
      "risk_score": 67
    },
    {
      "date": "2026-04-15",
      "risk_score": 82
    }
  ]
}
8.3 변수 기여도 조회
목적
feature importance / SHAP 기반 그래프 출력
Endpoint

GET /api/charts/factor-importance

Query Parameters
region_id
analysis_date
응답 예시
{
  "success": true,
  "data": [
    {
      "factor": "과거 사고 이력",
      "score": 0.35
    },
    {
      "factor": "최근 7일 강우량",
      "score": 0.22
    },
    {
      "factor": "지하수위 변동",
      "score": 0.14
    },
    {
      "factor": "GPR 공동 탐지",
      "score": 0.18
    },
    {
      "factor": "공사 요인",
      "score": 0.03
    }
  ]
}

주의:
공사 요인은 항상 낮은 비중의 보조 factor로만 표현

8.4 우선 점검 순위 표 조회
목적
표 형태 실무용 데이터 제공
Endpoint

GET /api/charts/top-priority

Query Parameters
date
top_n
sido (optional)
응답 예시
{
  "success": true,
  "data": [
    {
      "priority_rank": 1,
      "region_name": "부산광역시 해운대구",
      "risk_score": 89,
      "risk_level": "매우 높음",
      "main_reason": "과거 사고 밀도와 최근 강우 증가"
    }
  ]
}
9. 비교 분석 API
9.1 두 지역 비교 분석
목적
지역 비교 화면
발표 시 비교 설명
Endpoint

POST /api/compare-regions

요청 예시
{
  "region_a_id": 101,
  "region_b_id": 205,
  "analysis_date": "2026-04-19"
}
응답 예시
{
  "success": true,
  "data": {
    "region_a": {
      "region_id": 101,
      "region_name": "부산광역시 해운대구",
      "risk_score": 82,
      "risk_level": "매우 높음"
    },
    "region_b": {
      "region_id": 205,
      "region_name": "부산광역시 사하구",
      "risk_score": 61,
      "risk_level": "높음"
    },
    "comparison": {
      "score_diff": 21,
      "main_difference": "과거 사고 이력 및 GPR 탐사 결과 차이"
    }
  }
}
10. AI 리포트 API
10.1 AI 요약 리포트 생성
목적
상세 분석 화면
리포트 화면
PDF 출력용 설명문 생성
Endpoint

POST /api/generate-report

요청 예시
{
  "region_id": 101,
  "analysis_date": "2026-04-19",
  "language": "English" // 선택 사항, 기본값: "한국어"
}
응답 예시
{
  "success": true,
  "data": {
    "summary_text": "이 지역은 과거 지반침하 이력과 GPR 탐사 결과를 기준으로 기본 취약성이 존재하며, 최근 강우량 증가와 지하수위 변동이 겹쳐 위험 상승 가능성이 높습니다.",
    "inspection_recommendation_text": "우선 점검 대상지로 분류되며, GPR 재탐사 및 시설물 점검이 권고됩니다."
  }
}
10.2 저장된 AI 리포트 조회
목적
리포트 재사용
상세 화면 렌더링 속도 향상
Endpoint

GET /api/report/{region_id}

Query Parameters
analysis_date
응답 예시
{
  "success": true,
  "data": {
    "region_id": 101,
    "analysis_date": "2026-04-19",
    "summary_text": "위험 원인 요약...",
    "inspection_recommendation_text": "점검 권고..."
  }
}
11. API 상태/헬스 체크
11.1 서버 상태 확인
Endpoint

GET /api/health

응답 예시
{
  "success": true,
  "message": "API server is running"
}
12. API 설계와 화면 연결표
화면	주요 API
대시보드	/api/top-risk-regions, /api/charts/risk-distribution, /api/charts/risk-trend
위험 지도	/api/map/risk-layer, /api/map/hotspots, /api/map/gpr-layer
상세 분석	/api/analysis/{region_id}, /api/charts/factor-importance, /api/generate-report
비교 분석	/api/compare-regions
리포트	/api/report/{region_id}, /api/generate-report
13. 에러 처리 기준
13.1 공통 에러 코드 예시
NOT_FOUND
INVALID_REQUEST
DB_ERROR
ANALYSIS_ERROR
AI_REPORT_ERROR
13.2 권장 처리 방식
프론트에서는 success=false일 때 에러 메시지 출력
백엔드에서는 반드시 try/except 처리
생성형 AI 실패 시에도 분석 결과는 제공되도록 설계
14. 캐싱 및 저장 전략

분석 결과와 리포트는 가능하면 저장해두고 재사용한다.

저장 권장 대상
risk_analysis_result
ai_reports
이유
매번 재분석 비용 절감
지도 렌더링 속도 개선
리포트 생성 속도 개선
15. 보안 및 운영 고려
15.1 API 키 보호
Gemini API 키는 서버 환경변수로 관리
프론트에 직접 노출 금지
15.2 CORS 설정
React 프론트와 Flask/FastAPI 간 통신 허용 필요
15.3 Rate limiting (선택)
AI 리포트 API 과호출 방지
16. 개발자 체크리스트
공통
 success/message/data 구조 통일
 에러 응답 구조 통일
지역/지도
 regions 조회 가능
 risk-layer 조회 가능
 hotspots 조회 가능
분석
 analyze-risk 동작
 analysis 조회 가능
 top-risk-regions 동작
그래프
 risk-distribution 동작
 risk-trend 동작
 factor-importance 동작
AI
 generate-report 동작
 report 조회 가능
17. 최종 요약

이 프로젝트의 API는 단순 DB 조회 API가 아니라,
지도 화면 / 그래프 화면 / 상세 분석 화면 / 리포트 화면이 직접 사용할 수 있는 서비스형 API로 설계해야 한다.

핵심 구조는 다음과 같다.

지역/지도 API
위험 분석 API
그래프 API
비교 분석 API
AI 리포트 API

즉, API 설계는
데이터 → 분석 → 시각화 → 설명
전체 흐름을 연결하는 핵심 계층이다.
