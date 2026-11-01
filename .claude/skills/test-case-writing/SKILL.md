---
name: test-case-writing
description: 테스트 케이스 명세(docs/test-cases.md)와 자동 테스트 코드(tests/game.test.js)를 작성·수정하고 테스트를 실행할 때 사용한다. TC ID 규칙, SR 매핑 규칙, 명세 형식, 테스트 코드 작성 패턴, 실행 방법을 정의한다. "테스트 케이스", "TC 추가", "테스트 실행/수행" 요청에 적용.
---

# 테스트 케이스 작성 (Test Case Writing)

## 1. 원칙

- TC ID 는 `TC-001` 형식(3자리), 재사용 금지.
- 모든 TC 는 1개 이상의 SR 을 검증한다. 모든 SR 은 1개 이상의 TC 로 검증되어야 한다.
- TC↔SR 매핑은 **두 곳에 같은 값으로** 존재한다. 둘이 다르면 `traceability` 스크립트가 오류를 낸다.
  - 명세: `docs/test-cases.md` 의 요약 표
  - 코드: `tests/game.test.js` 의 `tc('TC-xxx', ['SR-yyy'], …)` 선언
- 기대 결과는 SR 의 수치를 그대로 쓴다 (예: "550ms", "(t+1)(t+2)/2"). 경계값(직전/직후)을 함께 확인한다.
- 테스트가 실패하면 **테스트를 통과하도록 기대값을 고치지 않는다.** 먼저 테스트 자체의 오류인지 확인하고, 아니라면 결함으로 보고한다.

## 2. 명세 형식 (`docs/test-cases.md`)

요약 표 — 첫 열이 `TC-nnn` 인 행만 인식, **열 순서 고정**:

```markdown
| TC ID | 제목 | 검증 SR | 유형 | 실행 변형 |
|---|---|---|---|---|
| TC-001 | 캐릭터 10단계와 반지름 정의 | SR-001 | 자동 | default |
```

- 유형: `자동`(game.test.js 로 실행) / `수동`(사람이 수행, 결과를 별도 기록). 가능한 한 자동으로 만든다.
- 실행 변형: 러너의 `VARIANTS` 이름 (`default`, `stored`, `nostorage`).

상세 — 요약 표 아래에 TC 마다 소제목으로 기술 (표 금지, 파서 혼동 방지):

```markdown
### TC-001 캐릭터 10단계와 반지름 정의
- **목적**: …
- **사전 조건**: …
- **절차**: 1) … 2) …
- **기대 결과**: …
```

## 3. 테스트 코드 패턴 (`tests/game.test.js`)

러너가 게임 HTML 에 스크립트를 주입하므로 게임의 전역(`engine`, `score`, `drop()`, `onCollide()`, `frame()` …)에 직접 접근한다.

```js
tc('TC-035', ['SR-0xx'], '제목', async () => {
  reset();                       // 매 테스트 시작 시 게임 초기화
  // 준비 → 실행 → 단언 (ok / eq / near)
}, ['default']);                 // 실행 변형 (생략 시 default)
```

보조 함수:
- `reset()` — 다시 하기와 같은 방식으로 초기화
- `frames(n, dtMs=33)` — 합성 시계로 `frame()` 을 n번 호출 (헤드리스 가상 시간에서는 rAF 가 반복되지 않으므로 루프를 직접 구동)
- `step(n)` — 물리 엔진만 n 스텝
- `recordFrame(fn)` — fn 실행 중 `fillText`, `drawFace`, `stroke`, `arc`, `drawImage` 호출 기록 (화면 표시 검증용)
- `key(k)`, `pointer(type, gameX)` — 입력 이벤트 발생
- `sleep(ms)` — 실제 타이머 대기 (가상 시간이므로 빠르게 진행)
- 무작위는 `Math.random` 을 고정값으로 교체해 결정적으로 만든다 (러너가 테스트 후 복원).

새 실행 변형(초기 환경)이 필요하면 `tests/run_tests.py` 의 `VARIANTS` 에 준비 스크립트를 추가한다.

## 4. 실행

```bash
python3 tests/run_tests.py
```

- 헤드리스 Chrome(네트워크 차단) 으로 변형마다 실행 → `tests/results/latest.json`, `docs/test-report.md`, `tests/results/screenshot.png` 생성.
- 종료 코드: 전부 통과 0, 그 외 1.
- Chrome 경로가 다르면 `--chrome <경로>`.

실행 후에는 반드시 `traceability` 스킬로 추적성 매트릭스를 갱신한다.
