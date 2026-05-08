싱크홀 데모 - 설치 및 실행 가이드
1) 로컬 설치 (최초 실행 권장)
Install_Sinkhole.cmd 파일 더블클릭

설치 프로그램 수행 내용:

.venv 가상환경 생성
Python 패키지 설치
SQLite 데이터베이스 초기화
루트 폴더 및 바탕화면에 실행용 바로가기 생성
2) 실행 방법

다음 중 하나를 더블클릭:

Sinkhole Launcher.lnk
Run_Sinkhole.cmd

기본 접속 주소:

http://127.0.0.1:5000

상태 확인(Health Check):

http://127.0.0.1:5000/api/health
3) UI / 데모 참고사항
데모 기본 지도 영역: 경상국립대학교 주변(진주)
F1 키 → 상세 도움말(Help) 창 열기
메인 타이틀(Hero) 및 지표/결과 폰트 크기는 과도하게 커지지 않도록 조정됨
4) AI 리포트 및 PDF 다운로드 목록
분석 후 AI 리포트 생성 버튼 클릭

서버 기능:

리포트 텍스트 생성
동시에 PDF 파일 생성 및 저장

AI 리포트 패널 하단에 PDF 목록 패널 표시

가능 기능:

브라우저에서 PDF 열기
PDF 직접 다운로드

API 엔드포인트:

POST /api/generate-report
GET /api/reports
GET /api/reports/files/{file_name}
5) Google Maps / API Key 설정

API 키 위치:
Project\backend\.env

사용 키:

GEMINI_API_KEY
GOOGLE_MAPS_API_KEY
6) 클라우드 배포 (Google Cloud Run)

참고 문서:
Project\backend\README_CLOUD_RUN.md

빠른 배포 절차
cd Project\backend
Copy-Item cloudrun.env.example cloudrun.env
cloudrun.env 파일 열어서 API 키 입력

배포 실행:

.\Deploy_Cloud_Run.ps1 -ProjectId <YOUR_PROJECT_ID> -AllowUnauthenticated
7) 요구 사항
Windows 10 / 11
Python 3.11 이상
패키지 설치 및 외부 API 사용을 위한 인터넷 연결 필요