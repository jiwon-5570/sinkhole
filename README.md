# 🕳️ 국토안전 AI 지반침하 위험도 분석 서비스 (Sinkhole Risk Platform)

> **「제5회 AI·공공데이터 활용 및 창업 경진대회」 출품작**  
> 국토안전관리원 중심 공공데이터를 융합해 지반침하 위험을 정량화하고, 지도·그래프·AI 설명·PDF 보고서까지 연결한 실무형 의사결정 지원 서비스입니다.

<br/>

## 1. 프로젝트 개요 (Overview)

지반침하(싱크홀) 사고에 대한 사후 복구 중심의 한계를 극복하고자, **선제적 위험 파악 및 예방 점검을 지원**하기 위해 개발된 대시보드 애플리케이션입니다. 
다양한 공공데이터를 결합해 지역별 지반침하 위험도를 0~100점으로 산출하고, 의사결정권자와 현장 점검팀이 직관적으로 이해할 수 있도록 시각화 및 AI 자연어 리포트를 제공합니다.

### 🎯 핵심 가치
- **위험도 사전 파악**: 어디가 위험한지 지도와 데이터로 직관적 확인
- **위험 원인 설명**: 단순 점수가 아닌, 왜 위험한지 항목별 기여도 분해 제시
- **업무 효율화**: Gemini AI를 활용한 점검 권고안 자연어 요약 및 PDF 리포트 자동 생성

<br/>

## 2. 주요 기능 (Key Features)

* **지도 기반 위험도 시각화 (Interactive Map)**
  * 시나리오 모드(사전 데이터 기반) 및 실시간 모드(Live API 연동) 지원
  * 히트맵과 위험 단계별(안전/주의/위험/매우 위험) 마커 오버레이
* **위험도 점수 산정 및 기여도 분석 (Risk Scoring & Breakdown)**
  * 7개 주요 요인: 과거 침하 이력, GPR 탐지, 시설물 노후도, 강우량, 지하수 변동, 환경 요인, 공사 영향
  * 항목별 점수를 막대 그래프 및 차트로 분해하여 시각적으로 제공
* **What-If 시뮬레이션 (Predictive Analysis)**
  * 집중호우, 태풍, 대형 굴착 공사 등 특정 조건 발생 시 지반침하 위험도 변동 사전 시뮬레이션 지원
* **AI 설명형 리포트 자동 생성 (AI Report Generator)**
  * Google Gemini API를 활용하여 데이터 기반 종합 판단, 점검 권고안 자연어 작성
  * 분석 결과를 리포트 형태의 PDF로 즉시 변환 및 다운로드 기능 지원

<br/>

## 3. 데이터 및 AI 모델 (Data & AI)

### 📊 활용 공공데이터
* **국토안전관리원(핵심)**: 지반침하 사고 이력, GPR 공동 탐지 결과, 지하시설물 노후도
* **기상청**: 실시간 강우량 (위험도 단기 상승 요인)
* **공공데이터포털**: 지하수위 변동 관측 데이터
* **지자체 및 공간 데이터**: 건물/도로 밀집도 등 환경 요인

### 🤖 AI 및 알고리즘
* **분석 엔진 (Rule-based / ML Planned)**: 각 위험 지표(Feature)를 스코어링하여 0~100점의 위험도와 등급을 산출하는 하이브리드 규칙 기반 알고리즘 적용 (추후 XGBoost 및 SHAP 모델로 확장 예정).
* **설명형 AI (Generative AI)**: 위험 산출 엔진이 분석한 수치 데이터(점수, 기여도)를 `Gemini API`에 주입하여 환각(Hallucination) 없이 정확하고 근거 있는 보고서 생성.

<br/>

## 4. 기술 스택 (Tech Stack)

- **Backend**: Python 3.10+, FastAPI, SQLite (Proto)
- **Frontend**: HTML5, CSS3, Vanilla JS, Google Maps API / Leaflet
- **AI/ML**: Google Gemini (generative-ai), XGBoost, SHAP (고도화 예정)
- **PDF Generation**: Reportlab (Python)

<br/>

## 5. 설치 및 실행 방법 (Installation & Usage)

### 사전 요구사항 (Prerequisites)
- Python 3.10 이상
- Google Gemini API Key 발급
- (선택) Google Maps API Key

### 실행 스텝 (Local Setup)

1. **저장소 클론 및 디렉토리 이동**
   ```bash
   git clone <repository-url>
   cd disaster_system/Project/backend
   ```

2. **가상환경 설정 및 패키지 설치**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **환경 변수 설정 (`.env`)**
   프로젝트 루트(또는 backend 디렉토리)에 `.env` 파일을 생성하고 아래 값을 기입합니다.
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
   ```

4. **DB 초기화 및 시드 데이터 적재**
   *(제공된 스크립트 또는 seed.py 실행)*
   ```bash
   python -m app.db.seed
   ```

5. **서버 실행**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 5000
   ```

6. **서비스 접속**
   브라우저에서 `http://127.0.0.1:5000/static/index.html` 로 접속합니다.

<br/>

## 6. 향후 고도화 계획 (Future Roadmap)

1. **AI 예측 모델 도입**: 현재의 규칙 기반 점수화에서 XGBoost 학습 기반으로 예측 알고리즘 고도화 및 SHAP을 통한 세밀한 기여도 분석 적용.
2. **인프라 이관**: SQLite 형태의 단일 DB에서 PostgreSQL/PostGIS 등 공간분석 및 대용량 트래픽 처리가 가능한 상용 RDBMS로 마이그레이션.
3. **데이터 파이프라인 자동화**: 배치 스크립트를 통한 기상/지하수 공공데이터 주기적 수집 및 모델 재학습 파이프라인(MLOps) 구축.

<br/>

---
* 이 프로젝트는 「제5회 AI·공공데이터 활용 및 창업 경진대회」 참가를 위해 제작되었습니다.