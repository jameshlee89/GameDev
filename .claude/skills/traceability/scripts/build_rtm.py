#!/usr/bin/env python3
"""추적성 검증 및 추적성 매트릭스(docs/traceability-matrix.md) 생성.

입력
  docs/SRS.md                 UR 표, SR 표 (상위 UR, 구현 위치)
  docs/test-cases.md          TC 요약 표 (검증 SR)
  tests/results/latest.json   테스트 결과 + 테스트 코드에 선언된 TC→SR (tests/run_tests.py 생성)
  chiikawa-merge.html         구현 위치 식별자 확인, 줄 번호 계산

종료 코드: 0 정상·전부 통과 / 1 구조 위반 / 2 실패·미실행 TC 있음
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

ID_RE = {p: re.compile(rf'^{p}-\d{{3}}$') for p in ('UR', 'SR', 'TC')}
LIST_RE = re.compile(r'\b(UR|SR|TC)-\d{3}\b')
ICON = {'pass': '✅', 'fail': '❌', 'error': '⚠️', None: '⬜'}
TC_LABEL = {'pass': '통과', 'fail': '실패', 'error': '오류', None: '미실행'}
VERDICT_ICON = {'충족': '✅ 충족', '미충족': '❌ 미충족', '미검증': '⬜ 미검증'}


def table_rows(path, prefix):
    """첫 열이 PREFIX-nnn 인 표 행을 셀 목록으로 반환."""
    rows = []
    with open(path, encoding='utf-8') as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line.startswith('|'):
                continue
            cells = [c.strip() for c in line.strip('|').split('|')]
            if cells and ID_RE[prefix].match(cells[0]):
                rows.append((n, cells))
    return rows


def ids_in(cell, prefix):
    return [m.group(0) for m in LIST_RE.finditer(cell) if m.group(1) == prefix]


def locate(source_lines, token):
    """식별자가 정의된(없으면 처음 나오는) 줄 번호. 없으면 None."""
    name = token[:-2] if token.endswith('()') else token
    pats = []
    if token.endswith('()'):
        pats.append(re.compile(rf'\bfunction\s+{re.escape(name)}\s*\('))
    else:
        pats.append(re.compile(rf'\b(const|let|var)\b[^;=]*\b{re.escape(name)}\b'))
    pats.append(re.compile(re.escape(name)))
    for pat in pats:
        for i, line in enumerate(source_lines, 1):
            if pat.search(line):
                return i
    return None


def main():
    root_default = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', default=root_default)
    ap.add_argument('--srs', default='docs/SRS.md')
    ap.add_argument('--tc', default='docs/test-cases.md')
    ap.add_argument('--results', default='tests/results/latest.json')
    ap.add_argument('--source', default='chiikawa-merge.html')
    ap.add_argument('--out', default='docs/traceability-matrix.md')
    a = ap.parse_args()
    P = lambda p: os.path.join(a.root, p)

    errors, warnings = [], []

    # ---------- 수집 ----------
    urs, srs, tcs = {}, {}, {}
    for n, c in table_rows(P(a.srs), 'UR'):
        if c[0] in urs:
            errors.append(f'{a.srs}:{n} UR ID 중복: {c[0]}')
        urs[c[0]] = {'text': c[1] if len(c) > 1 else '', 'priority': c[2] if len(c) > 2 else ''}
    for n, c in table_rows(P(a.srs), 'SR'):
        if len(c) < 4:
            errors.append(f'{a.srs}:{n} SR 표 열 부족 (ID|요구사항|상위 UR|구현 위치): {c[0]}')
            continue
        if c[0] in srs:
            errors.append(f'{a.srs}:{n} SR ID 중복: {c[0]}')
        srs[c[0]] = {'text': c[1], 'ur': ids_in(c[2], 'UR'), 'impl': re.findall(r'`([^`]+)`', c[3])}
    for n, c in table_rows(P(a.tc), 'TC'):
        if len(c) < 3:
            errors.append(f'{a.tc}:{n} TC 표 열 부족: {c[0]}')
            continue
        if c[0] in tcs:
            errors.append(f'{a.tc}:{n} TC ID 중복: {c[0]}')
        tcs[c[0]] = {'title': c[1], 'sr': ids_in(c[2], 'SR'), 'kind': c[3] if len(c) > 3 else ''}

    with open(P(a.source), encoding='utf-8') as f:
        source = f.read()
    source_lines = source.split('\n')
    source_sha = hashlib.sha256(source.encode()).hexdigest()

    results, run = {}, None
    if os.path.exists(P(a.results)):
        with open(P(a.results), encoding='utf-8') as f:
            run = json.load(f)
        results = {r['id']: r for r in run['results']}
        if run['target']['sha256'] != source_sha:
            warnings.append('테스트 결과가 현재 소스와 다른 버전에서 생성됨 → `python3 tests/run_tests.py` 재실행 필요')
    else:
        warnings.append(f'테스트 결과 파일 없음: {a.results}')

    # ---------- 구조 검증 ----------
    ur_children = {u: [s for s, v in srs.items() if u in v['ur']] for u in urs}
    sr_tcs = {s: [t for t, v in tcs.items() if s in v['sr']] for s in srs}
    for u, ch in ur_children.items():
        if not ch:
            errors.append(f'미구체화 UR: {u} 를 상위로 하는 SR 없음')
    for s, v in srs.items():
        if not v['ur']:
            errors.append(f'고아 SR: {s} 에 상위 UR 없음')
        for u in v['ur']:
            if u not in urs:
                errors.append(f'{s} 가 존재하지 않는 {u} 를 참조')
        if not v['impl']:
            errors.append(f'{s} 에 구현 위치 없음')
        if not sr_tcs[s]:
            errors.append(f'미검증 SR: {s} 를 검증하는 TC 없음')
    impl_lines = {}
    for s, v in srs.items():
        for tok in v['impl']:
            ln = locate(source_lines, tok)
            if ln is None:
                errors.append(f'{s} 구현 위치 `{tok}` 가 {a.source} 에 없음')
            impl_lines[(s, tok)] = ln
    for t, v in tcs.items():
        if not v['sr']:
            errors.append(f'{t} 에 검증 SR 없음')
        for s in v['sr']:
            if s not in srs:
                errors.append(f'{t} 가 존재하지 않는 {s} 를 참조')
    if run:
        declared = {d['id']: d['sr'] for d in run.get('declared', [])}
        for t in sorted(set(tcs) - set(declared)):
            if tcs[t]['kind'] != '수동':
                errors.append(f'{t}: 명세에는 있으나 테스트 코드에 선언 없음')
        for t in sorted(set(declared) - set(tcs)):
            errors.append(f'{t}: 테스트 코드에는 있으나 명세(test-cases.md)에 없음')
        for t in sorted(set(declared) & set(tcs)):
            if sorted(declared[t]) != sorted(tcs[t]['sr']):
                errors.append(f'{t}: SR 매핑 불일치 — 명세 {tcs[t]["sr"]} / 코드 {declared[t]}')

    # ---------- 판정 ----------
    tc_status = {t: (results[t]['status'] if t in results else None) for t in tcs}

    def sr_verdict(s):
        st = [tc_status[t] for t in sr_tcs[s]]
        if not st:
            return '미검증'
        if any(x in ('fail', 'error') for x in st):
            return '미충족'
        return '충족' if all(x == 'pass' for x in st) else '미검증'

    def ur_verdict(u):
        vs = [sr_verdict(s) for s in ur_children[u]]
        if not vs:
            return '미검증'
        if '미충족' in vs:
            return '미충족'
        return '충족' if all(v == '충족' for v in vs) else '미검증'

    srv = {s: sr_verdict(s) for s in srs}
    urv = {u: ur_verdict(u) for u in urs}

    # ---------- 출력 ----------
    src_link = os.path.relpath(P(a.source), os.path.dirname(P(a.out)))
    impl_md = lambda s: ', '.join(
        f'[`{tok}`]({src_link}#L{impl_lines[(s, tok)]})' if impl_lines.get((s, tok)) else f'`{tok}` ⚠️'
        for tok in srs[s]['impl'])
    tc_md = lambda s: ', '.join(f'{t} {ICON[tc_status[t]]}' for t in sr_tcs[s]) or '—'
    n_pass = sum(1 for v in tc_status.values() if v == 'pass')
    covered = sum(1 for s in srs if sr_tcs[s])
    pct = lambda x, y: f'{(x / y * 100 if y else 0):.1f}%'
    count = lambda d, k: sum(1 for v in d.values() if v == k)

    L = [
        '# 치이카와 합치기 — 요구사항 추적성 매트릭스 (RTM)',
        '',
        '> 이 문서는 `python3 .claude/skills/traceability/scripts/build_rtm.py` 가 자동 생성합니다. 직접 수정하지 마세요.',
        '',
        '| 항목 | 값 |', '|---|---|',
        f"| 생성 일시 | {datetime.datetime.now().astimezone().isoformat(timespec='seconds')} |",
        f'| 요구사항 원본 | [SRS.md]({os.path.relpath(P(a.srs), os.path.dirname(P(a.out)))}) |',
        f'| 테스트 케이스 원본 | [test-cases.md]({os.path.relpath(P(a.tc), os.path.dirname(P(a.out)))}) |',
        f"| 테스트 결과 | {('`' + a.results + '` (' + run['executed_at'] + ', 커밋 ' + run['target']['commit'] + ')') if run else '없음'} · [test-report.md](test-report.md) |",
        f'| 대상 소스 | [`{a.source}`]({src_link}) (SHA-256 `{source_sha[:16]}…`) |',
        '',
        '## 1. 요약',
        '',
        '| 구분 | 전체 | ✅ 충족/통과 | ❌ 미충족/실패 | ⬜ 미검증/미실행 |', '|---|---|---|---|---|',
        f"| 사용자 요구사항 (UR) | {len(urs)} | {count(urv, '충족')} | {count(urv, '미충족')} | {count(urv, '미검증')} |",
        f"| 소프트웨어 요구사항 (SR) | {len(srs)} | {count(srv, '충족')} | {count(srv, '미충족')} | {count(srv, '미검증')} |",
        f"| 테스트 케이스 (TC) | {len(tcs)} | {n_pass} | {sum(1 for v in tc_status.values() if v in ('fail', 'error'))} | {count(tc_status, None)} |",
        '',
        f'- SR 테스트 커버리지: **{pct(covered, len(srs))}** ({covered}/{len(srs)})',
        f'- TC 통과율: **{pct(n_pass, len(tcs))}** ({n_pass}/{len(tcs)})',
        f"- 구조 검증: {'✅ 위반 없음' if not errors else f'❌ 위반 {len(errors)}건 (6절 참고)'}"
        + (f' / 경고 {len(warnings)}건' if warnings else ''),
        '',
        '## 2. 사용자 요구사항 충족 현황',
        '',
        '| UR | 사용자 요구사항 | 우선순위 | 하위 SR | 판정 |', '|---|---|---|---|---|',
    ]
    for u, v in urs.items():
        L.append(f"| {u} | {v['text']} | {v['priority']} | {', '.join(ur_children[u]) or '—'} | {VERDICT_ICON[urv[u]]} |")

    L += ['', '## 3. 순방향 추적 (UR → SR → 구현 → TC → 결과)', '',
          '| UR | SR | 소프트웨어 요구사항 | 구현 위치 | 검증 TC | SR 판정 |', '|---|---|---|---|---|---|']
    for u in urs:
        for i, s in enumerate(ur_children[u]):
            L.append(f"| {u if i == 0 else '〃'} | {s} | {srs[s]['text']} | {impl_md(s)} | {tc_md(s)} | {VERDICT_ICON[srv[s]]} |")
        if not ur_children[u]:
            L.append(f'| {u} | — | — | — | — | ⬜ 미검증 |')

    L += ['', '## 4. 역방향 추적 (TC → SR → UR)', '',
          '| TC | 제목 | 결과 | 검증 SR | 관련 UR |', '|---|---|---|---|---|']
    for t, v in tcs.items():
        ur_of = sorted({u for s in v['sr'] if s in srs for u in srs[s]['ur']})
        L.append(f"| {t} | {v['title']} | {ICON[tc_status[t]]} {TC_LABEL[tc_status[t]]} | {', '.join(v['sr'])} | {', '.join(ur_of)} |")

    L += ['', '## 5. 미충족·미검증 상세', '']
    bad = [s for s in srs if srv[s] != '충족']
    if not bad:
        L.append('없음 — 모든 SR 이 충족되었습니다.')
    for s in bad:
        affected = ', '.join('%s (%s)' % (u, urs[u]['text']) for u in srs[s]['ur'] if u in urs)
        L += [f"### {s} — {VERDICT_ICON[srv[s]]}", '',
              f"- 요구사항: {srs[s]['text']}",
              f'- 영향받는 사용자 요구사항: {affected}',
              f'- 구현 위치: {impl_md(s)}']
        for t in sr_tcs[s]:
            if tc_status[t] != 'pass':
                detail = results[t]['detail'] if t in results else '결과 없음'
                L.append(f"- {t} {tcs[t]['title']}: {ICON[tc_status[t]]} {TC_LABEL[tc_status[t]]} — {detail}")
        L.append('')

    L += ['', '## 6. 구조 검증', '']
    L += [f'- ❌ {e}' for e in errors] or ['- ✅ 위반 없음 (UR 구체화, SR 상위 연결, SR 검증 TC, 명세↔코드 매핑, 구현 위치 존재, ID 중복)']
    L += [f'- ⚠️ {w}' for w in warnings]
    L.append('')

    with open(P(a.out), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))

    print(f'UR {len(urs)} (충족 {count(urv, "충족")}, 미충족 {count(urv, "미충족")}, 미검증 {count(urv, "미검증")})')
    print(f'SR {len(srs)} (충족 {count(srv, "충족")}, 미충족 {count(srv, "미충족")}, 미검증 {count(srv, "미검증")}), 커버리지 {pct(covered, len(srs))}')
    print(f'TC {len(tcs)} (통과 {n_pass}), 통과율 {pct(n_pass, len(tcs))}')
    for e in errors:
        print('ERROR', e)
    for w in warnings:
        print('WARN ', w)
    for s in bad:
        print(f'{srv[s]}: {s} ← UR {", ".join(srs[s]["ur"])}')
    print(f'→ {a.out}')
    sys.exit(1 if errors else (2 if bad else 0))


if __name__ == '__main__':
    main()
