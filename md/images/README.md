# md/images

이 폴더는 문서와 발표 자료에 사용할 이미지, 스크린샷, 다이어그램을 보관하는 위치다.

## 권장 파일

- 대시보드 전체 화면 스크린샷
- 위험도 지도 화면
- TOP 5 및 기여 요인 차트
- What-If 시뮬레이션 결과
- AI Chat 화면
- PDF 리포트 예시 화면
- 데이터 흐름 다이어그램
- 시스템 구조 다이어그램

## 파일명 규칙

영문 소문자와 하이픈을 사용한다.

```text
dashboard-overview.png
risk-map.png
top-risk-factor-chart.png
what-if-simulation.png
ai-chat.png
report-pdf-preview.png
data-flow.png
system-architecture.png
```

## 문서 삽입 예시

```markdown
![대시보드 전체 화면](images/dashboard-overview.png)
```

## 관리 기준

- 원본 캡처는 가능하면 PNG로 저장한다.
- 발표용 압축 이미지는 JPG를 사용할 수 있다.
- API 키, 개인정보, 민감한 주소가 보이는 화면은 저장 전에 가린다.
- 너무 큰 이미지는 문서 렌더링이 느려지므로 1920px 이하 폭을 권장한다.
- 자동 생성된 임시 이미지는 Git에 포함하지 않는다.
