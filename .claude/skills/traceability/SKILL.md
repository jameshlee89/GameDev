---
name: traceability
description: 사용자 요구사항(UR) → 소프트웨어 요구사항(SR) → 구현 위치 → 테스트 케이스(TC) → 테스트 결과의 추적성을 연결·검증하고 추적성 매트릭스(docs/traceability-matrix.md)를 생성할 때 사용한다. 사양서·테스트 변경 후, 또는 "추적성", "RTM", "커버리지 확인" 요청에 적용.
---

# 추적성 연결 (Traceability)

## 1. 추적 사슬

```
UR (docs/SRS.md) ──상위 UR──▶ SR (docs/SRS.md) ──구현 위치──▶ 소스 식별자 (chiikawa-merge.html)
                                  ▲
                                  └──검증 SR── TC (docs/test-cases.md ＝ tests/game.test.js) ──▶ 결과 (tests/results/latest.json)
```

각 링크의 **원본은 한 곳**이며, 매트릭스는 항상 스크립트로 생성한다 (손으로 고치지 않는다).

| 링크 | 원본 |
|---|---|
| UR ↔ SR | `docs/SRS.md` SR 표의 `상위 UR` 열 |
| SR → 구현 | `docs/SRS.md` SR 표의 `구현 위치` 열 (줄 번호는 스크립트가 계산) |
| TC → SR | `docs/test-cases.md` 요약 표 (테스트 코드 선언과 일치해야 함) |
| TC → 결과 | `tests/results/latest.json` (`tests/run_tests.py` 가 생성) |

## 2. 실행 절차

```bash
python3 tests/run_tests.py                                  # 1) 테스트 수행
python3 .claude/skills/traceability/scripts/build_rtm.py    # 2) 검증 + 매트릭스 생성
```

`build_rtm.py` 는 `docs/traceability-matrix.md` 를 다시 쓰고, 검증 결과를 출력한다.
종료 코드: 0 = 구조 위반 없음·전 TC 통과, 1 = 구조 위반 있음, 2 = 구조는 정상이나 실패/미실행 TC 있음.

## 3. 검증 규칙

구조 위반 (반드시 수정):
1. UR 중 하위 SR 이 없는 것 (미구체화 UR)
2. SR 의 상위 UR 이 없거나 존재하지 않는 UR 을 참조 (고아 SR)
3. SR 중 검증 TC 가 없는 것 (미검증 SR)
4. TC 가 존재하지 않는 SR 을 참조
5. 명세(test-cases.md)와 코드(game.test.js)의 TC 목록 또는 TC→SR 매핑 불일치
6. `구현 위치` 의 식별자가 소스에 없음
7. ID 중복

경고 (확인 필요):
- 결과 파일의 대상 SHA-256 이 현재 소스와 다름 → 테스트 재실행 필요 (결과가 낡음)

## 4. 판정 규칙

- TC: 결과 파일의 `pass` / `fail` / `error`, 결과 없음은 `미실행`.
- SR: 연결된 TC 가 모두 pass → **충족**, 하나라도 fail/error → **미충족**, 결과 없는 TC 포함 → **미검증**.
- UR: 하위 SR 이 모두 충족 → **충족**, 하나라도 미충족 → **미충족**, 그 외 → **미검증**.

## 5. 결과 보고

매트릭스 생성 후 사용자에게 다음을 요약해 보고한다:
- UR/SR/TC 수, 커버리지(검증 TC 가 있는 SR 비율), 통과율
- 미충족 SR 과 원인 TC (실패 메시지), 연결된 UR — 즉 **어떤 사용자 요구가 영향을 받는지**
- 구조 위반·경고가 있으면 그 내용과 수정 방법
