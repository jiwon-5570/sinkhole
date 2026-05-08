# Sinkhole Risk Dashboard

공공데이터 기반 지반침하 위험도 분석 대시보드입니다. FastAPI 백엔드와 정적 HTML/CSS/JavaScript UI로 구성되어 있으며, 지역별 위험 점수, 기여 요인, 지도, AI 리포트, PDF 보고서를 제공합니다.

## 주요 기능

- 진주권 분석 지점 위험도 산정
- Google Maps 기반 위치 선택 및 지도 표시
- 공공데이터포털 API 자동 수집
- 위험 기여 요인 분해
- Gemini 기반 AI 채팅/리포트 생성
- PDF 보고서 생성 및 다운로드

## 실제 데이터 원칙

운영 기준에서는 임의 데모 데이터가 분석 점수에 섞이지 않도록 구성했습니다. DB 초기화는 스키마만 적용하며, 분석 데이터는 승인된 공공데이터 API와 사용자가 입력한 실제 데이터에서만 생성합니다.

현재 연결된 공공데이터 소스:

- KALIS 공공시설물 안전관리/점검진단
- MOLIT 지하안전정보
- MOLIT 지반침하 사고 이력
- KMA ASOS 시간 강우
- MOLIT 건축HUB 건축 인허가

## 빠른 실행

Windows에서 처음 설치:

```powershell
.\Install_Sinkhole.cmd
```

설치 후 실행:

```powershell
.\Run_Sinkhole.cmd
```

기본 접속 주소:

```text
http://127.0.0.1:5000
```

## 수동 실행

```powershell
cd .\Project\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe .\scripts\init_db.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 5000
```

## 환경 변수

실제 키는 `Project/backend/.env`에만 둡니다. 이 파일은 Git에 포함하지 않습니다.

```env
PUBLIC_DATA_API_KEY=your_public_data_key
GEMINI_API_KEY=your_gemini_key
GOOGLE_MAPS_API_KEY=your_google_maps_key
SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY=1
SINKHOLE_SEED_DEMO=0
```

## 정리 기준

이 저장소는 실행에 필요한 코드, 스키마, 설치/실행 스크립트, 운영 문서만 포함합니다. 다음 항목은 Git에서 제외합니다.

- `.env`, API 키
- SQLite DB 파일
- 가상환경
- 브라우저 테스트 프로필
- 로그, 임시 파일
- 생성된 PDF 보고서
