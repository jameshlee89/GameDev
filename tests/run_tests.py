#!/usr/bin/env python3
"""치이카와 합치기 자동 테스트 러너.

game.test.js 를 게임 HTML 에 주입해 헤드리스 Chrome 으로 실행하고 결과를 수집한다.
네트워크는 차단된 상태(오프라인)로 실행한다.

산출물
  tests/results/latest.json   기계 판독용 결과 (traceability 스킬의 입력)
  docs/test-report.md         테스트 결과 보고서
  tests/results/screenshot.png 플레이 화면 증적

사용법: python3 tests/run_tests.py [--chrome PATH]
"""
import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, 'chiikawa-merge.html')
TEST_JS = os.path.join(ROOT, 'tests', 'game.test.js')
RESULTS = os.path.join(ROOT, 'tests', 'results', 'latest.json')
SCREENSHOT = os.path.join(ROOT, 'tests', 'results', 'screenshot.png')
REPORT = os.path.join(ROOT, 'docs', 'test-report.md')

CHROME_CANDIDATES = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    'google-chrome', 'chromium', 'chromium-browser', 'chrome',
]

# 게임 스크립트보다 먼저 실행되는 준비 스크립트.
# 오류 수집, rAF 가로채기(가상 시간에서는 rAF 가 반복되지 않으므로 테스트가 frame() 을 직접 구동), 저장소 상태 준비.
PRELUDE = """<script>
window.__VARIANT = %(variant)s;
window.__ERRORS = [];
addEventListener('error', e => window.__ERRORS.push(String(e.message)));
addEventListener('unhandledrejection', e => window.__ERRORS.push(String(e.reason)));
window.__RAF = [];
window.requestAnimationFrame = cb => (window.__RAF.push(cb), window.__RAF.length);
%(setup)s
</script>"""

VARIANTS = {
    # 기본: 저장소 비어 있음
    'default': "try { localStorage.clear(); } catch (e) {}",
    # 이전 최고 기록이 저장된 상태로 시작
    'stored': "localStorage.setItem('chiikawa-merge-best', '1234');",
    # 저장소 접근이 차단된 브라우저 (사파리 사생활 보호 모드 등)
    'nostorage': "Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new DOMException('blocked', 'SecurityError'); } });",
}

# 증적용 화면: 실제 rAF 로 몇 프레임 진행한 플레이 장면
SCREENSHOT_SCRIPT = """<script>
setTimeout(() => {
  score = 128;
  [[0,60],[1,110],[2,170],[3,240],[4,320],[5,90],[6,230],[7,350],[8,150]].forEach(([t,x], i) => {
    const b = makeFace(t, x, BOX_B - RADII[t] - (i > 4 ? 120 : 0)); b.born -= 5000;
  });
  for (let i = 0; i < 90; i++) Engine.update(engine, 1000 / 60);
  frame(performance.now());
}, 200);
</script>"""


def find_chrome(explicit):
    for c in ([explicit] if explicit else CHROME_CANDIDATES):
        path = c if os.path.isabs(c) else shutil.which(c)
        if path and os.path.exists(path):
            return path
    sys.exit('Chrome/Chromium 을 찾을 수 없습니다. --chrome 으로 경로를 지정하세요.')


def chrome_args(chrome, profile):
    return [chrome, '--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
            '--disable-extensions', f'--user-data-dir={profile}', '--window-size=1280,900',
            '--host-resolver-rules=MAP * ~NOTFOUND']


def inject(html, head_extra='', body_extra=''):
    html = html.replace('<head>', '<head>\n' + head_extra, 1)
    i = html.rindex('</body>')
    return html[:i] + body_extra + '\n' + html[i:]


def run_variant(chrome, html, test_js, variant, work):
    prelude = PRELUDE % {'variant': json.dumps(variant), 'setup': VARIANTS[variant]}
    page = os.path.join(work, f'harness-{variant}.html')
    with open(page, 'w', encoding='utf-8') as f:
        f.write(inject(html, prelude, '<script>\n' + test_js + '\n</script>'))
    cmd = chrome_args(chrome, os.path.join(work, 'profile-' + variant)) + [
        '--virtual-time-budget=60000', '--dump-dom', 'file://' + page]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout
    m = re.search(r'<script type="application/json" id="__results">(.*?)</script>', out, re.S)
    if not m:
        raise RuntimeError(f'[{variant}] 결과를 받지 못했습니다 (테스트가 가상 시간 내에 끝나지 않았거나 페이지 오류).')
    return json.loads(m.group(1))


def take_screenshot(chrome, html, work):
    page = os.path.join(work, 'screenshot.html')
    with open(page, 'w', encoding='utf-8') as f:
        f.write(inject(html, body_extra=SCREENSHOT_SCRIPT))
    cmd = chrome_args(chrome, os.path.join(work, 'profile-shot')) + [
        '--window-size=480,760', '--hide-scrollbars', '--virtual-time-budget=3000',
        f'--screenshot={SCREENSHOT}', 'file://' + page]
    subprocess.run(cmd, capture_output=True, timeout=120)
    return os.path.exists(SCREENSHOT)


def git_commit():
    try:
        rev = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', os.path.basename(GAME)], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
        return rev + (' (작업 트리 수정됨)' if dirty else '')
    except OSError:
        return 'unknown'


def write_report(data):
    s = data['summary']
    icon = {'pass': '✅ 통과', 'fail': '❌ 실패', 'error': '⚠️ 오류'}
    lines = [
        '# 치이카와 합치기 — 소프트웨어 테스트 결과 보고서',
        '',
        '> 이 문서는 `python3 tests/run_tests.py` 가 자동 생성합니다. 직접 수정하지 마세요.',
        '',
        '## 1. 실행 정보',
        '',
        '| 항목 | 값 |', '|---|---|',
        f"| 실행 일시 | {data['executed_at']} |",
        f"| 대상 파일 | `{data['target']['file']}` |",
        f"| 대상 SHA-256 | `{data['target']['sha256'][:16]}…` |",
        f"| 대상 커밋 | {data['target']['commit']} |",
        f"| 실행 환경 | {data['environment']['browser']} (헤드리스, 네트워크 차단) / {data['environment']['os']} |",
        f"| 실행 변형 | {', '.join(data['variants'])} |",
        '',
        '## 2. 요약',
        '',
        '| 전체 | 통과 | 실패 | 오류 | 통과율 |', '|---|---|---|---|---|',
        f"| {s['total']} | {s['pass']} | {s['fail']} | {s['error']} | {s['pass'] / s['total'] * 100:.1f}% |",
        '',
        '## 3. 테스트 케이스별 결과',
        '',
        '| TC ID | 제목 | 검증 SR | 변형 | 결과 | 소요(ms) |', '|---|---|---|---|---|---|',
    ]
    for r in data['results']:
        lines.append(f"| {r['id']} | {r['title']} | {', '.join(r['sr'])} | {r['variant']} | {icon[r['status']]} | {r['ms']} |")
    bad = [r for r in data['results'] if r['status'] != 'pass']
    lines += ['', '## 4. 실패/오류 상세', '']
    if bad:
        for r in bad:
            lines += [f"### {r['id']} {r['title']}", '', f"- 검증 SR: {', '.join(r['sr'])}",
                      f"- 판정: {icon[r['status']]}", f"- 내용: {r['detail']}", '']
    else:
        lines.append('없음.')
    lines += ['', '## 5. 증적', '']
    if data.get('screenshot'):
        lines += ['플레이 화면 (헤드리스 Chrome, 오프라인):', '', '![플레이 화면](../tests/results/screenshot.png)']
    else:
        lines.append('스크린샷 생성 실패.')
    lines += ['', '추적성(요구사항 ↔ 테스트 결과)은 [traceability-matrix.md](traceability-matrix.md) 를 참고하세요.', '']
    with open(REPORT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chrome')
    args = ap.parse_args()
    chrome = find_chrome(args.chrome)
    with open(GAME, encoding='utf-8') as f:
        html = f.read()
    with open(TEST_JS, encoding='utf-8') as f:
        test_js = f.read()
    if '</script>' in test_js:
        sys.exit('game.test.js 에 "</script>" 문자열을 넣을 수 없습니다.')
    version = subprocess.run([chrome, '--version'], capture_output=True, text=True).stdout.strip() or 'Chrome'

    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    work = tempfile.mkdtemp(prefix='chiikawa-test-')
    try:
        runs = [run_variant(chrome, html, test_js, v, work) for v in VARIANTS]
        shot = take_screenshot(chrome, html, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    declared = {d['id']: d for d in runs[0]['declared']}
    results = sorted((r for run in runs for r in run['results']), key=lambda r: r['id'])
    ran = {r['id'] for r in results}
    for tid in sorted(set(declared) - ran):   # 어떤 변형에서도 실행되지 않은 선언
        d = declared[tid]
        results.append({'id': tid, 'sr': d['sr'], 'title': d['title'], 'variant': '-', 'status': 'error',
                        'detail': f"선언된 변형 {d['variants']} 이 러너에 없음", 'ms': 0})
    count = lambda st: sum(r['status'] == st for r in results)
    data = {
        'executed_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
        'target': {'file': os.path.relpath(GAME, ROOT), 'sha256': hashlib.sha256(html.encode()).hexdigest(),
                   'commit': git_commit()},
        'environment': {'browser': version, 'os': f'{platform.system()} {platform.release()}'},
        'variants': list(VARIANTS),
        'summary': {'total': len(results), 'pass': count('pass'), 'fail': count('fail'), 'error': count('error')},
        'declared': list(declared.values()),
        'results': results,
        'screenshot': os.path.relpath(SCREENSHOT, ROOT) if shot else None,
    }
    with open(RESULTS, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    write_report(data)

    s = data['summary']
    for r in results:
        mark = {'pass': 'PASS', 'fail': 'FAIL', 'error': 'ERR '}[r['status']]
        print(f"{mark} {r['id']} [{','.join(r['sr'])}] {r['title']}" + (f"\n     → {r['detail']}" if r['detail'] else ''))
    print(f"\n합계 {s['total']} / 통과 {s['pass']} / 실패 {s['fail']} / 오류 {s['error']}")
    print(f'결과: {os.path.relpath(RESULTS, ROOT)}, 보고서: {os.path.relpath(REPORT, ROOT)}')
    sys.exit(0 if s['pass'] == s['total'] else 1)


if __name__ == '__main__':
    main()
