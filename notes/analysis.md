# Wispy 코드베이스 분석 (작품소개자료 작성용)

- 분석 기준: `main` 브랜치 `1a56382` (커밋 141개, 2026-08-07 ~ 2026-08-27)
- 분석 일자: 2026-10-07
- 환경변수는 **이름과 사용처만** 기록했고 값은 열람·기록하지 않았다. (레포에는 `.env.example`만 있고 실제 `.env`는 없음)

## 1. 레포 구조

| 경로 | 내용 |
| --- | --- |
| `frontend/` | React 19 + Vite 8 + Tailwind CSS 4 PWA. 라우터 라이브러리 없이 `App.jsx`의 `screen` 상태로 화면 전환 |
| `backend/` | Express 4 + TypeScript. `api/index.ts`가 Express 앱을 export → Vercel Serverless Function 1개 (`vercel.json`이 모든 경로를 `/api/index`로 rewrite) |
| `backend/scripts/` | 프롬프트·음성·부하 테스트용 CLI 7종 |
| 루트 | `기획안.pdf`, `발표 자료.pdf`, 시연 영상 |

프론트와 백엔드는 **별도 Vercel 프로젝트로 배포**된다 (`VITE_API_BASE_URL`로 백엔드 주소 주입).

## 2. 화면(스크린) 목록 — `frontend/src/App.jsx`

| screen 값 | 컴포넌트 | 설명 |
| --- | --- | --- |
| `onboarding` | `pages/onboarding/*` | 8단계: 인트로 → 안내 2장 → 목표 선택 → 앱·제한시간 → 관심사·할 일 → 홈 화면 설치·알림 허용 → 준비 완료 |
| `home` | `Home.jsx` | 인사말, 체험해보기 버튼, 모니터링 앱, 관심사, 할 일, 벨(알림 미리보기) |
| `demo` | `DemoExperience.jsx` | 숏폼/SNS 피드 목업 → 5초 뒤 문구 알림 배너 → 10초 뒤 수신 전화 배너 |
| `callSplash` | `CallSplash.jsx` | 상태에 따라 연결 중(`CallConnecting`) / 통화 중(`CallActive`) / 통화 요약(`CallSummaryScreen`) / 오류(슬픈 위스피) |
| `log` | `Log.jsx` | 통화 기록(일자별 그룹, 앱·통화 시간·마지막 한 마디) |
| `report` | `Report.jsx` | 주간 개입 횟수, 평균 통화, 총 대화 시간, 요일별 막대, 앱별 개입 비중 |
| `settings` | `Settings.jsx` | 모니터링 앱 관리, 관심사·계획 수정, 설치/알림 카드 |
| `appManage` | `AppManage.jsx` | 앱 추가·삭제, 앱별 제한 시간 |
| `profileEdit` | `ProfileEdit.jsx` | 관심사·계획 수정 |
| `debugCallActive` | `CallActive` | 개발 빌드 전용 QA 진입점(`?debug=call-active`) |

딥링크: `/?call=1` (알림 탭 → 바로 통화 화면), 서비스워커 `postMessage('was:open-call')`.

## 3. 백엔드 API — `backend/src/routes/*`

| 메서드·경로 | 역할 |
| --- | --- |
| `POST /api/call` | 입력 검증 → (빈 필드는 KV 프로필로 보충) → OpenAI `POST /v1/realtime/client_secrets` 호출 → **임시 client_secret**과 모델명 반환 |
| `POST /api/call/summary` | 통화 요약을 프로필(`previousSummary`)에 저장 |
| `POST /api/profile`, `GET /api/profile` | 관심사·계획·페르소나 저장/조회. 저장 후 백그라운드로 다음 알림 문구를 미리 생성해 캐싱 |
| `GET /api/push/preview-text` | 현재 프로필 기준 알림 문구 1개 즉시 생성 |
| `POST /api/push/subscribe` | Web Push 구독 정보 저장 |
| `POST /api/push/send` | 캐싱된 문구로 Web Push 발송 (VAPID 미설정 시 501) |
| `GET /health`, `GET /docs` | 헬스체크, Swagger UI |

미들웨어: CORS 화이트리스트(`FRONTEND_ORIGIN`), `express.json` 10kb 제한, 공유 시크릿(`x-app-secret`), IP당 rate limit(통화 30회/분, 프로필·푸시 300회/분).

## 4. 통화(실시간 음성) 구조

1. 프론트 `useRealtimeCall.connect()` — 세션 발급(`/api/call`)과 마이크 캡처(`getUserMedia`)를 `Promise.all`로 병렬 수행
2. `RTCPeerConnection` + 데이터채널 `oai-events` 생성, SDP offer를 **브라우저가 직접** `https://api.openai.com/v1/realtime/calls`에 임시 토큰으로 전송
3. 오디오는 브라우저 ↔ OpenAI 사이에서만 흐른다. 백엔드는 토큰 발급만 담당(오디오 미경유, `OPENAI_API_KEY`는 서버에만 존재)
4. 세션 설정(`backend/src/openai.ts`): `server_vad`(무음 700ms), `interrupt_response: true`, `create_response: false`, 음성 `cedar`, 함수 도구 `end_call`
5. 모델: `gpt-realtime` / `gpt-realtime-mini`를 통화마다 **라운드로빈** 배정 (`REALTIME_MODEL` 환경변수로 고정 가능)

### 프롬프트 — `backend/src/realtimeInstructions.ts`
- 섹션: 상황 / 절대 하지 말 것 / 먼저 끝내야 하는 경우 / 대화 참고 정보(관심사·계획) / 통화 시작 / 통화 흐름 / end_call 도구 / 다양성 / 말투 텍스처 / 톤
- 통화 흐름 4단계: **진입**(고정 오프너 "지금 뭐 보고 있었어요?") → **전개** → **재정향**("이제 뭐 할 거예요?" — 통화당 1회, 거부·회피 신호 시 중단, 부정 감정엔 공감 우선) → **마무리** 후 `end_call`
- 훈계·명령조 금지, 편한 존댓말 유지
- 프론트가 매 턴(사용자 발화 종료 시) `TONE_REMINDER` + 계획 리마인더를 system 메시지로 주입해 긴 대화에서 지시 이탈을 보완

### Memory 처리
- 통화 종료 시 프론트 `deriveSummary()`가 **마지막 4개 발화를 480자 이내로 이어 붙여** 요약으로 사용 (별도 LLM 요약 호출 없음)
- 저장 위치: `localStorage`(`was:v1`의 `previousSummary`) + 서버 KV(`POST /api/call/summary`)
- 다음 통화의 `/api/call` 요청에 실려 프롬프트의 `[예전 통화 기억]` 섹션으로 삽입

## 5. 데이터 저장

| 위치 | 내용 |
| --- | --- |
| 브라우저 `localStorage` `was:v1` | 온보딩 여부, 목표, 모니터링 앱(제한 시간), 관심사, 계획, 이전 통화 요약, 통화 기록 |
| `localStorage` `was:userId` | 로그인 없는 익명 사용자 ID (`x-user-id` 헤더로 전송) |
| `localStorage` `was:leftAt`, `was:leftNotified` | 이탈 시각, 알림 발송 여부 |
| Upstash Redis `was:profile:{userId}` | 관심사, 계획, 페르소나, 이전 요약, 미리 생성한 알림 문구, 푸시 구독. 환경변수 미설정 시 in-memory Map 폴백 |

## 6. 사용 감지·알림

- `useAwayMonitor`: `visibilitychange`로 앱을 벗어난 시각을 `localStorage`에 기록 → 복귀 시 경과 시간이 제한 시간 이상이면 전화 화면 진입. 벗어나 있는 동안은 20초 주기로 확인해 로컬 알림(서비스워커 `showNotification`) 시도 — 백그라운드 JS 정지 시 보장 안 됨(코드 주석에 명시)
- 알림 문구: `notificationText.ts`가 `gpt-4o-mini`(Chat Completions, max 60 tokens, 타임아웃 6초)로 프로필 기반 생성. 실패 시 "지금 뭐 해요?" 폴백
- 서비스워커 `public/sw.js`: `push` 이벤트 수신 → 알림 표시, 클릭 시 통화 화면으로 이동

## 7. 환경변수 (이름만)

- 백엔드: `OPENAI_API_KEY`, `REALTIME_MODEL`, `REALTIME_VOICE`, `FRONTEND_ORIGIN`, `APP_SHARED_SECRET`, `KV_REST_API_URL`/`KV_REST_API_TOKEN` (또는 `UPSTASH_REDIS_REST_URL`/`_TOKEN`), `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`, `PORT`
- 프론트: `VITE_API_BASE_URL`, `VITE_APP_SHARED_SECRET`, `VITE_VAPID_PUBLIC_KEY`

## 8. 구현된 것 vs 기획만 된 것

### 실제 구현됨 (문서에 '구현 결과'로 기재)
- 온보딩 8단계와 개인화 입력(목표, 앱, 제한 시간, 관심사, 할 일)
- 앱 이탈 시간 기반 감지와 복귀 시 전화 화면 자동 진입
- LLM 기반 개인화 알림 문구 생성, 로컬 알림 표시
- 체험 모드(피드 목업 → 알림 배너 → 수신 전화 배너)
- OpenAI Realtime API(WebRTC) 실시간 음성 통화, 끼어들기(barge-in), 음소거·스피커 전환
- 서버리스 임시 토큰 발급(API 키 비노출)
- AI 주도 통화 종료(`end_call`)
- 이전 통화 요약 기억(로컬 + Redis)
- 통화 기록, 주간 리포트(실제 통화 기록 기반 집계)
- PWA(manifest, 서비스워커, 홈 화면 설치 안내)
- 보안 가드레일(CORS, 공유 시크릿, rate limit, 입력 길이 제한)
- 모델 라운드로빈, 429 전용 오류 화면, 세션 프리페치
- 프롬프트·음성·부하 테스트 스크립트

### 부분 구현 / 주의
- **서버 Web Push**: 백엔드 발송 API, 구독 등록, 서비스워커 수신 코드는 있으나, 프론트 감지 로직(`useAwayMonitor`)은 현재 `/api/push/send`를 **호출하지 않고** 로컬 알림만 사용한다(코드 주석: 발표 안정성을 위한 팀 결정). → 문서에는 "발송 경로 구현, 현재 데모는 로컬 알림 사용"으로만 표현
- **사용 감지**: 타 앱의 실제 사용 시간이 아니라 "Wispy 앱을 벗어나 있던 시간"의 근사치
- **홈 '지금 집중하고 있던 것' 카드**: "보고 계신 지 45분" 문구가 고정값(`Home.jsx:104`)
- **기록 화면 초기 2건**: 빈 화면 방지용 시드 데이터(`storage.js`)
- **통화 요약**: LLM 요약이 아니라 마지막 발화 발췌
- **모니터링 앱 목록**: 고정 6종(YouTube, Instagram, 카카오톡, 틱톡, X, 넷플릭스), 실제 스크린타임 연동 없음
- **온보딩 목표 선택(goals)**: 저장만 되고 통화·알림 프롬프트에는 쓰이지 않음
- **페르소나**: 위스피 1종 (과거 10종에서 단일화)
- **통화 화면의 키패드·통화 추가·메시지·연락처 버튼**: UI만 존재
- **설정의 사운드·다크 모드·개인정보 처리방침·이용약관**: UI만 존재

### 미구현 (문서에는 '향후 계획'으로만 기재)
- 앱별 실제 사용 시간 감지(네이티브 스크린타임 API 연동)
- 리포트의 가족·친구 공유(온보딩 안내 문구에만 존재)
- 로그인·계정, 결제, Freemium/Premium 구분
- 개입 타이밍 개인화 학습, 고도화 행동 리포트
- 통화 후 행동 재선택 여부 측정

## 9. README·기획안과 코드가 다른 부분

| 문서 기재 | 실제 코드 |
| --- | --- |
| README: IP당 분당 10회 rate limit | 30회/분 (`app.ts`) |
| `.env.example`: 통화 모델 `gpt-realtime-mini` 고정, 알림 모델 `gpt-4.1-nano` 고정 | 통화는 `gpt-realtime`/`gpt-realtime-mini` 라운드로빈, 알림은 `gpt-4o-mini` |
| README: "실제 PWA 웹 푸시로 문자를 보냄" | 프론트는 로컬 알림 경로만 사용 |
| README: 앱별 사용 시간 제한 | 앱 이탈 시간 근사치, 제한 시간이 가장 짧은 앱 1개 기준 |
| 포인트 컬러 요청값 `#A78BFA` | 앱 코드의 accent는 `#b190ea` |

## 10. 통계 근거 확인 결과 (웹 확인, 2026-10-07)

- 「2025년 스마트폰 과의존 실태조사」(과기정통부·NIA, 2026-03 발표): 전체 과의존 위험군 **22.7%**, 청소년 **43.0%**, 청년층(20~30대) **29.5%**, 유아동 26.0% — 머니투데이·농민신문 보도로 확인
- 「2024년 조사」(2025-03 발표): 전체 22.9%, 성인(만 20~59세) **22.4%**, 청소년 42.6% — 부산일보 보도로 확인. 기획안의 "22.4%"는 이 수치와 일치
- 요청서에 적힌 "성인 22.3%, 20대 34.3%, 30대 25.3%"는 보도 자료에서 **확인하지 못함** → 문서에는 확인된 수치만 사용
