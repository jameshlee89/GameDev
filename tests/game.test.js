// 치이카와 합치기 자동 테스트 (브라우저 내부 실행)
// run_tests.py 가 게임 HTML 의 </body> 앞에 이 스크립트를 주입해 헤드리스 Chrome 으로 실행한다.
// 게임 스크립트의 최상위 const/let/function 은 전역 스코프를 공유하므로 직접 접근할 수 있다.
// 각 테스트는 tc(TC ID, [검증하는 SR ID], 제목, 본문, [실행 변형]) 으로 선언한다.
// 이 선언의 TC↔SR 매핑은 docs/test-cases.md 와 일치해야 한다 (traceability 스킬이 검증).
(() => {
  const TESTS = [];
  const tc = (id, sr, title, fn, variants = ['default']) => TESTS.push({ id, sr, title, fn, variants });

  // ---------- 단언 ----------
  class AssertionError extends Error {}
  const ok = (c, msg) => { if (!c) throw new AssertionError(msg); };
  const eq = (a, b, msg) => {
    const sa = JSON.stringify(a), sb = JSON.stringify(b);
    if (sa !== sb) throw new AssertionError(`${msg}: 기대값 ${sb}, 실제값 ${sa}`);
  };
  const near = (a, b, eps, msg) => {
    if (!(Math.abs(a - b) <= eps)) throw new AssertionError(`${msg}: 기대값 ${b}±${eps}, 실제값 ${a}`);
  };

  // ---------- 보조 함수 ----------
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const faces = () => Composite.allBodies(world).filter(b => b.tier !== undefined);
  const walls = () => Composite.allBodies(world).filter(b => b.tier === undefined && b.isStatic);
  const step = (n = 1) => { for (let i = 0; i < n; i++) Engine.update(engine, 1000 / 60); };
  const realRandom = Math.random;
  const reset = () => {
    Math.random = realRandom;
    Composite.clear(world, false); Engine.clear(engine); init();
    canDrop = true;
  };
  // 합성 시계로 frame() 을 직접 호출 (가상 시간에서는 rAF 가 반복 실행되지 않음)
  let clock = performance.now() + 100000;
  const frames = (n, dtMs = 33) => {
    for (let i = 0; i < n; i++) { last = clock; clock += dtMs; frame(clock); }
  };
  // 캔버스/함수 호출 기록
  function spy(obj, name, rec) {
    const orig = obj[name];
    obj[name] = function (...args) { rec(args, this); return orig.apply(this, args); };
    return () => { obj[name] = orig; };
  }
  function recordFrame(fn) {
    const log = { text: [], face: [], stroke: [], arc: 0, image: 0 };
    const undo = [
      spy(ctx, 'fillText', a => log.text.push({ s: String(a[0]), x: a[1], y: a[2] })),
      spy(ctx, 'stroke', () => log.stroke.push({ style: ctx.strokeStyle, dash: ctx.getLineDash() })),
      spy(ctx, 'arc', () => log.arc++),
      spy(ctx, 'drawImage', () => log.image++),
      spy(window, 'drawFace', a => log.face.push({ tier: a[0], x: a[1], y: a[2], alpha: a[5] ?? 1 })),
    ];
    try { fn(); } finally { undo.reverse().forEach(u => u()); }
    return log;
  }
  const key = k => { const e = new KeyboardEvent('keydown', { key: k, cancelable: true, bubbles: true }); dispatchEvent(e); return e; };
  const pointer = (type, gameX) => {
    const rect = cvs.getBoundingClientRect();
    cvs.dispatchEvent(new PointerEvent(type, { clientX: rect.left + gameX * scale, clientY: rect.top + 50, pointerId: 1, bubbles: true }));
  };
  // 정지 상태로 위험선 위에 걸친 캐릭터를 만든다
  const stuckFace = (tier = 5) => {
    const b = makeFace(tier, W / 2, DANGER_Y);
    Body.setStatic(b, true);
    b.born = clock - 5000;
    return b;
  };

  // ================= 캐릭터 정의 =================
  tc('TC-001', ['SR-001'], '캐릭터 10단계와 반지름 정의', () => {
    eq(RADII, [16, 22, 29, 36, 44, 53, 63, 74, 87, 104], '반지름 표');
    eq(IMGS.length, 10, '이미지 수'); eq(META.length, 10, '이미지 보정값 수');
    for (let i = 1; i < RADII.length; i++) ok(RADII[i] > RADII[i - 1], `단계 ${i} 반지름이 이전 단계보다 커야 함`);
  });

  tc('TC-002', ['SR-002'], '드롭 캐릭터는 0~4단계 중 무작위', () => {
    Math.random = () => 0; eq(randTier(), 0, 'random=0');
    Math.random = () => 0.999999; eq(randTier(), 4, 'random≈1');
    Math.random = realRandom;
    const seen = new Set();
    for (let i = 0; i < 2000; i++) {
      const t = randTier();
      ok(Number.isInteger(t) && t >= 0 && t <= 4, `범위를 벗어난 단계 ${t}`);
      seen.add(t);
    }
    eq([...seen].sort(), [0, 1, 2, 3, 4], '2000회 중 등장한 단계');
    reset();
    ok(current >= 0 && current <= 4 && next >= 0 && next <= 4, '시작 시 현재/다음 캐릭터 범위');
  });

  // ================= 조작 =================
  tc('TC-003', ['SR-003'], '포인터 이동/누름으로 조준 위치 갱신', () => {
    reset();
    pointer('pointermove', 100); near(aimX, 100, 0.5, 'pointermove 후 aimX');
    pointer('pointerdown', 300); near(aimX, 300, 0.5, 'pointerdown 후 aimX');
    eq(faces().length, 0, '누르기만 해서는 드롭되지 않음');
  });

  tc('TC-004', ['SR-003'], '포인터를 떼면 그 위치에 드롭', () => {
    reset();
    const tier = current;
    pointer('pointerup', 150);
    const f = faces();
    eq(f.length, 1, '드롭된 캐릭터 수');
    eq(f[0].tier, tier, '드롭된 캐릭터 단계');
    near(f[0].position.x, 150, 0.5, '드롭 x 좌표');
  });

  tc('TC-005', ['SR-004'], '←/→ 키로 조준 12px 이동', () => {
    reset();
    aimX = 200;
    key('ArrowLeft'); eq(aimX, 188, '← 1회');
    key('ArrowRight'); key('ArrowRight'); eq(aimX, 212, '→ 2회');
  });

  tc('TC-006', ['SR-004'], 'Space/↓ 키로 드롭, 기본 동작 차단', async () => {
    reset();
    const e1 = key(' ');
    eq(faces().length, 1, 'Space 후 캐릭터 수');
    ok(e1.defaultPrevented, 'Space 기본 동작(스크롤) 차단');
    await sleep(600);
    const e2 = key('ArrowDown');
    eq(faces().length, 2, '↓ 후 캐릭터 수');
    ok(e2.defaultPrevented, '↓ 기본 동작 차단');
  });

  tc('TC-007', ['SR-005'], '드롭 위치를 벽 안쪽으로 제한', async () => {
    reset();
    const r = RADII[4];
    current = 4; aimX = -500; drop();
    near(faces()[0].position.x, BOX_L + r, 0.01, '왼쪽 끝 드롭 x');
    near(faces()[0].position.y, DROP_Y, 0.01, '드롭 y');
    await sleep(600);
    current = 4; aimX = 5000; drop();
    near(faces()[1].position.x, BOX_R - r, 0.01, '오른쪽 끝 드롭 x');
  });

  tc('TC-008', ['SR-005'], '키 조준은 이동 범위 밖으로 누적되지 않음', () => {
    reset();
    current = 0; const r = RADII[0];
    aimX = W / 2;
    for (let i = 0; i < 40; i++) key('ArrowLeft');  // 480px: 왼쪽 벽을 훨씬 넘는 입력
    key('ArrowRight');
    const shown = recordFrame(() => frames(1)).face.find(f => f.y === DROP_Y);
    ok(shown, '조준 중인 캐릭터가 그려져야 함');
    near(shown.x, BOX_L + r + 12, 0.01, '왼쪽 끝에서 → 1회 후 조준 x');
  });

  tc('TC-009', ['SR-006', 'SR-012'], '드롭 후 550ms 쿨다운과 다음 캐릭터 승계', async () => {
    reset();
    const nextBefore = next;
    drop();
    eq(current, nextBefore, '드롭 후 현재 캐릭터는 직전의 "다음" 캐릭터');
    ok(!canDrop, '드롭 직후 canDrop=false');
    drop(); eq(faces().length, 1, '쿨다운 중 재드롭 무시');
    const dim = recordFrame(() => frames(1)).face.find(f => f.y === DROP_Y);
    eq(dim.alpha, 0.35, '대기 중 캐릭터 반투명 표시');
    await sleep(400);
    drop(); eq(faces().length, 1, '400ms 시점에도 무시');
    await sleep(250);
    ok(canDrop, '650ms 이후 canDrop=true');
    eq(recordFrame(() => frames(1)).face.find(f => f.y === DROP_Y).alpha, 1, '드롭 가능 시 불투명 표시');
    drop(); eq(faces().length, 2, '쿨다운 이후 드롭 허용');
  });

  // ================= 합체 =================
  tc('TC-010', ['SR-007', 'SR-010'], '같은 단계가 닿으면 다음 단계 1개로 합체', () => {
    reset();
    const r = RADII[2];
    const a = makeFace(2, 200, 500), b = makeFace(2, 200 + 2 * r - 6, 500);
    const mid = (a.position.x + b.position.x) / 2;
    for (let i = 0; i < 5 && faces().length === 2; i++) step();
    const f = faces();
    eq(f.length, 1, '합체 후 캐릭터 수');
    eq(f[0].tier, 3, '합체 결과 단계');
    near(f[0].position.x, mid, 3, '합체 결과는 두 캐릭터의 중점에 생성');
    eq(score, 6, '2단계 합체 점수 (3·4/2)');
  });

  tc('TC-011', ['SR-008'], '서로 다른 단계는 합체하지 않음', () => {
    reset();
    makeFace(1, 200, 560); makeFace(2, 200 + RADII[1] + RADII[2] - 6, 560);
    step(60);
    eq(faces().map(b => b.tier).sort(), [1, 2], '60스텝 후 남은 단계');
    eq(score, 0, '점수 변화 없음');
  });

  tc('TC-012', ['SR-009'], '한 캐릭터는 한 번만 합체 (3개 동시 접촉)', () => {
    reset();
    const a = makeFace(0, 100, 300), b = makeFace(0, 110, 300), c = makeFace(0, 105, 308);
    onCollide({ pairs: [{ bodyA: a, bodyB: b }, { bodyA: a, bodyB: c }, { bodyA: b, bodyB: c }] });
    eq(faces().map(x => x.tier).sort(), [0, 1], '남은 캐릭터 단계');
    eq(score, 1, '합체 1회분 점수');
  });

  tc('TC-013', ['SR-010'], '단계별 합체 점수 (t+1)(t+2)/2', () => {
    for (let t = 0; t <= 8; t++) {
      reset();
      const a = makeFace(t, 200, 400), b = makeFace(t, 210, 400);
      onCollide({ pairs: [{ bodyA: a, bodyB: b }] });
      eq(score, (t + 1) * (t + 2) / 2, `단계 ${t} 합체 점수`);
      eq(faces().map(x => x.tier), [t + 1], `단계 ${t} 합체 결과`);
    }
  });

  tc('TC-014', ['SR-011'], '최고 단계 두 개 합체 시 소멸 + 200점 보너스', () => {
    reset();
    const a = makeFace(9, 150, 400), b = makeFace(9, 250, 400);
    onCollide({ pairs: [{ bodyA: a, bodyB: b }] });
    eq(faces().length, 0, '최고 단계는 둘 다 사라짐');
    eq(score, 55 + 200, '점수 (합체 55 + 보너스 200)');
    ok(effects.some(e => e.kind === 'text' && e.text === '세이렌 보너스 +200'), '보너스 문구 이펙트');
  });

  tc('TC-015', ['SR-019'], '합체 이펙트 (파티클 14개 + 링)', () => {
    reset();
    const a = makeFace(2, 200, 400), b = makeFace(2, 210, 400);
    onCollide({ pairs: [{ bodyA: a, bodyB: b }] });
    eq(effects.filter(e => e.kind === 'dot').length, 14, '파티클 수');
    eq(effects.filter(e => e.kind === 'ring').length, 1, '링 수');
    eq(faces()[0].pop, 1, '새 캐릭터 팝 애니메이션 시작값');
    frames(30);
    eq(effects.length, 0, '약 1초 후 이펙트 소멸');
  });

  // ================= 점수/HUD/기록 =================
  tc('TC-016', ['SR-012'], 'HUD에 점수·최고 기록·다음 캐릭터 표시', () => {
    reset();
    const savedBest = best;
    try {
      score = 37; best = 100;
      let log = recordFrame(() => frames(1));
      const texts = log.text.map(t => t.s);
      ok(texts.includes('점수') && texts.includes('37'), `점수 표시 (${texts.join(',')})`);
      ok(texts.includes('최고 100'), '최고 기록 표시');
      ok(texts.includes('다음'), '"다음" 라벨');
      ok(log.face.some(f => f.tier === next && f.x === W - 40 && f.y === 56), '다음 캐릭터 미리보기');
      score = 150;
      log = recordFrame(() => frames(1));
      ok(log.text.some(t => t.s === '최고 150'), '현재 점수가 더 높으면 최고 기록에 현재 점수 표시');
    } finally { best = savedBest; }
  });

  tc('TC-017', ['SR-013'], '저장된 최고 기록을 시작 시 불러옴', () => {
    eq(best, 1234, '시작 시 best');
  }, ['stored']);

  tc('TC-018', ['SR-013'], '게임 오버 시 최고 기록 갱신·저장', () => {
    reset();
    const savedBest = best;
    try {
      best = 50; score = 80; endGame();
      eq(localStorage.getItem('chiikawa-merge-best'), '80', '높은 점수 저장');
      reset(); score = 30; endGame();
      eq(localStorage.getItem('chiikawa-merge-best'), '80', '낮은 점수는 덮어쓰지 않음');
      eq(best, 80, 'best 값 유지');
    } finally { best = savedBest; localStorage.removeItem('chiikawa-merge-best'); reset(); }
  });

  tc('TC-019', ['SR-013'], '저장소 사용 불가 환경에서도 정상 동작', () => {
    let blocked = false;
    try { localStorage.getItem('x'); } catch (e) { blocked = true; }
    ok(blocked, '전제: localStorage 접근이 차단된 환경');
    eq(best, 0, '시작 시 best=0');
    eq(window.__STARTUP_ERRORS, [], '시작 중 오류 없음');
    reset(); score = 10; endGame();
    ok(gameOver, '저장 실패와 무관하게 게임 오버 처리');
    eq(best, 10, '메모리상 최고 기록 갱신');
  }, ['nostorage']);

  // ================= 게임 오버/재시작 =================
  tc('TC-020', ['SR-014'], '위험선 초과 상태 2.2초 지속 시 게임 오버', () => {
    reset(); stuckFace();
    frames(60);   // 1.98초
    ok(!gameOver, '1.98초 시점에는 게임 오버 아님');
    frames(10);   // 2.31초
    ok(gameOver, '2.31초 시점에 게임 오버');
  });

  tc('TC-021', ['SR-014'], '생성 1.2초 이내 캐릭터는 판정 제외', () => {
    reset();
    const b = stuckFace(); b.born = clock;
    frames(30);   // 약 1초
    eq(dangerTimer, 0, '위험 타이머');
  });

  tc('TC-022', ['SR-014'], '움직이는 캐릭터(속도≥1.5)는 판정 제외', () => {
    reset();
    engine.gravity.y = 0;
    const b = makeFace(5, W / 2, DANGER_Y); b.born = clock - 5000;
    for (let i = 0; i < 90; i++) {
      Body.setPosition(b, { x: W / 2, y: DANGER_Y }); Body.setVelocity(b, { x: 3, y: 0 });
      frames(1);
    }
    ok(!gameOver, '게임 오버 아님'); eq(dangerTimer, 0, '위험 타이머');
  });

  tc('TC-023', ['SR-014'], '위험 해소 시 타이머가 2배 속도로 감소', () => {
    reset();
    const b = stuckFace();
    frames(30);
    near(dangerTimer, 0.99, 1e-9, '30프레임 후 위험 타이머');
    Composite.remove(world, b);
    frames(10);
    near(dangerTimer, 0.99 - 0.66, 1e-9, '해소 10프레임 후 위험 타이머');
  });

  tc('TC-024', ['SR-015'], '게임 오버 화면과 진행 정지', () => {
    reset();
    const savedBest = best;
    try {
      const b = makeFace(3, 200, 300);
      score = 42; endGame();
      const over = document.getElementById('over');
      eq(getComputedStyle(over).display, 'flex', '오버레이 표시');
      const txt = document.getElementById('final').textContent;
      ok(txt.includes('점수 42') && txt.includes('최고 기록'), `결과 문구 (${txt})`);
      const y = b.position.y;
      const log = recordFrame(() => frames(20));
      eq(b.position.y, y, '게임 오버 후 물리 정지');
      ok(!log.face.some(f => f.y === DROP_Y && f.x !== W - 40), '조준 캐릭터 미표시');
      drop(); eq(faces().length, 1, '게임 오버 후 드롭 불가');
    } finally { best = savedBest; try { localStorage.removeItem('chiikawa-merge-best'); } catch (e) {} }
  });

  tc('TC-025', ['SR-016'], '다시 하기로 초기 상태 복귀', async () => {
    reset(); makeFace(4, 200, 400); score = 99; endGame();
    document.getElementById('retry').click();
    eq(getComputedStyle(document.getElementById('over')).display, 'none', '오버레이 숨김');
    ok(!gameOver, 'gameOver=false'); eq(score, 0, '점수 0'); eq(dangerTimer, 0, '위험 타이머 0');
    eq(faces().length, 0, '캐릭터 제거'); eq(walls().length, 3, '바닥/좌우 벽 재생성');
    drop(); eq(faces().length, 1, '재시작 후 드롭 가능');
    try { localStorage.removeItem('chiikawa-merge-best'); } catch (e) {}
  });

  // ================= 화면/표시 =================
  tc('TC-026', ['SR-017'], '화면 크기에 맞춘 비율 유지 스케일과 DPR 대응', () => {
    const saved = { iw: innerWidth, ih: innerHeight, dpr: devicePixelRatio };
    const check = (vw, vh, d) => {
      window.innerWidth = vw; window.innerHeight = vh; window.devicePixelRatio = d;
      dispatchEvent(new Event('resize'));
      const s = Math.min((vw - 16) / W, (vh - 16) / H);
      near(scale, s, 1e-9, `${vw}x${vh} 스케일`);
      near(parseFloat(cvs.style.width), W * s, 0.01, `${vw}x${vh} CSS 너비`);
      near(parseFloat(cvs.style.height), H * s, 0.01, `${vw}x${vh} CSS 높이`);
      ok(parseFloat(cvs.style.width) <= vw - 16 + 0.01 && parseFloat(cvs.style.height) <= vh - 16 + 0.01, '화면 안에 들어감');
      eq(cvs.width, Math.round(W * s * d), `${vw}x${vh}@${d}x 캔버스 픽셀 너비`);
      eq(cvs.height, Math.round(H * s * d), `${vw}x${vh}@${d}x 캔버스 픽셀 높이`);
    };
    try {
      check(375, 667, 3);    // 모바일 세로
      check(1920, 1080, 1);  // PC
      check(1024, 600, 2);   // 가로로 긴 화면
    } finally {
      window.innerWidth = saved.iw; window.innerHeight = saved.ih; window.devicePixelRatio = saved.dpr;
      dispatchEvent(new Event('resize'));
    }
  });

  tc('TC-027', ['SR-018'], '단일 파일 구성 (엔진·이미지 내장)', () => {
    eq(document.querySelectorAll('script[src]').length, 0, '외부 스크립트 수');
    eq(Matter.version, '0.19.0', '내장 matter-js 버전');
    ok(IMGS.every(s => s.startsWith('data:image/')), '이미지가 모두 data URI 로 내장');
    const ext = [...document.querySelectorAll('link[href]')].map(l => new URL(l.href).host);
    eq(ext, ['fonts.googleapis.com'], '외부 참조는 Google Fonts 뿐');
    ok(images.every(i => i.complete && i.naturalWidth > 0), '내장 이미지 10종 디코딩 성공');
  });

  tc('TC-028', ['SR-018'], '오프라인(폰트 미수신)에서도 시작·렌더링', () => {
    eq(window.__STARTUP_ERRORS, [], '시작 중 오류 없음');
    ok(/Apple SD Gothic Neo|Malgun Gothic|system-ui|sans-serif/.test(getComputedStyle(document.body).fontFamily), '대체 폰트 지정');
    reset();
    const before = window.__ERRORS.length;
    const log = recordFrame(() => frames(1));
    ok(log.text.length > 0 && log.face.length > 0, '오프라인 상태에서 HUD/캐릭터 렌더링');
    eq(window.__ERRORS.slice(before), [], '렌더링 중 오류 없음');
  });

  tc('TC-029', ['SR-019'], '이미지 미로딩 시 색상 원으로 대체', () => {
    const saved = images[3];
    try {
      let log = recordFrame(() => drawFace(3, 100, 100, 0));
      eq([log.image, log.arc], [1, 0], '정상 이미지: drawImage 1회');
      images[3] = new Image();
      log = recordFrame(() => drawFace(3, 100, 100, 0));
      eq([log.image, log.arc], [0, 1], '미로딩 이미지: 원 1개');
    } finally { images[3] = saved; }
  });

  tc('TC-030', ['SR-020'], '하단 진화 단계 10종 표시', () => {
    reset();
    const log = recordFrame(() => frames(1));
    const chain = log.face.filter(f => f.y === BOX_B + 36);
    eq(chain.map(f => f.tier), [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], '진화 단계 순서');
    eq(log.text.filter(t => t.s === '›').length, 9, '단계 사이 화살표 수');
  });

  tc('TC-031', ['SR-021'], '위험선 표시 및 위험 시 강조', () => {
    reset();
    const line = log => log.stroke.filter(s => s.dash.join() === '10,8');
    let l = line(recordFrame(() => frames(1)));
    eq(l.length, 1, '점선 위험선 1개');
    eq(l[0].style, 'rgba(230, 90, 100, 0.35)', '평상시 색');
    dangerTimer = 1;
    l = line(recordFrame(() => frames(1)));
    ok(/^rgba\(230, 60, 70, /.test(l[0].style), `위험 중 강조 색 (${l[0].style})`);
  });

  // ================= 루프/플랫폼 =================
  tc('TC-032', ['SR-022'], '프레임 간격 33ms 상한', () => {
    reset();
    const dts = [];
    const undo = spy(Matter.Engine, 'update', a => dts.push(a[1]));
    try {
      last = clock; clock += 5000; frame(clock);   // 탭 복귀 등 5초 공백
      last = clock; clock += 16; frame(clock);
    } finally { undo(); }
    near(dts[0], 33, 1e-9, '긴 공백 후 물리 스텝');
    near(dts[1], 16, 1e-9, '일반 프레임 물리 스텝');
  });

  tc('TC-033', ['SR-022'], 'requestAnimationFrame 기반 연속 루프', () => {
    ok(window.__RAF.length >= 1 && window.__RAF[0] === frame, '시작 시 frame 이 rAF 에 등록됨');
    const n = window.__RAF.length;
    frames(1);
    eq(window.__RAF.length, n + 1, '매 프레임 다음 프레임을 다시 요청');
  });

  tc('TC-034', ['SR-023'], '모바일 확대/스크롤/선택 방지', () => {
    const vp = document.querySelector('meta[name=viewport]').content;
    ok(/user-scalable=no/.test(vp) && /maximum-scale=1/.test(vp), `viewport (${vp})`);
    const cs = getComputedStyle(document.body);
    eq(cs.touchAction, 'none', 'touch-action');
    eq(cs.overflow, 'hidden', 'overflow');
    eq(cs.userSelect, 'none', 'user-select');
  });

  // ---------- 실행 ----------
  async function run() {
    const variant = window.__VARIANT || 'default';
    const results = [];
    window.__STARTUP_ERRORS = [...window.__ERRORS];
    for (const t of TESTS) {
      if (!t.variants.includes(variant)) continue;
      const t0 = performance.now();
      let status = 'pass', detail = '';
      try { await t.fn(); } catch (e) {
        status = e instanceof AssertionError ? 'fail' : 'error';
        detail = e instanceof AssertionError ? e.message : `${e.name}: ${e.message}`;
      }
      Math.random = realRandom; engine.gravity.y = 1.6;
      results.push({ id: t.id, sr: t.sr, title: t.title, variant, status, detail, ms: Math.round(performance.now() - t0) });
    }
    const out = document.createElement('script');
    out.type = 'application/json'; out.id = '__results';
    out.textContent = JSON.stringify({ variant, declared: TESTS.map(({ id, sr, title, variants }) => ({ id, sr, title, variants })), results });
    document.body.appendChild(out);
  }
  setTimeout(run, 300);   // 내장 이미지 디코딩 대기
})();
