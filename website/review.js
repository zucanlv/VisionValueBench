(() => {
  'use strict';
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(location.hostname)) return;

  const blocks = new Map([...document.querySelectorAll('[data-review-id]')].map(el => [el.dataset.reviewId, el]));
  const normalize = text => text.replace(/\s+/g, ' ').trim();
  const originals = new Map([...blocks].map(([id, el]) => [id, { text: normalize(el.textContent), html: el.innerHTML }]));
  const cacheKey = 'visionvaluebench-homepage-feedback-v1';
  const composerKey = `${cacheKey}-composer`;
  let state, activeId = null, activeQuote = '', editingCommentId = null;
  let dirty = false, saving = false, blocked = false, loading = false, saveTimer, mode = false;
  let composerDrafts = {}, draftActiveId = null, skippedEdits = 0;
  try { const saved = JSON.parse(localStorage.getItem(composerKey)); composerDrafts = saved?.drafts || {}; draftActiveId = saved?.activeId; } catch (_) {}

  const entry = document.createElement('button');
  entry.type = 'button'; entry.className = 'review-entry'; entry.textContent = '编辑与批注';
  entry.setAttribute('aria-expanded', 'false'); entry.setAttribute('aria-controls', 'review-panel');
  const toolbar = document.createElement('div');
  toolbar.className = 'review-toolbar'; toolbar.hidden = true;
  toolbar.innerHTML = '<strong>本地编辑与批注</strong><span class="review-status" role="status" aria-live="polite">正在读取…</span><button type="button" class="review-exit">完成</button>';
  const panel = document.createElement('aside');
  panel.className = 'review-panel'; panel.id = 'review-panel'; panel.hidden = true;
  panel.setAttribute('aria-label', '网页批注');
  panel.innerHTML = '<header class="review-panel-header"><h2>修改与意见</h2><p>直接改文字，或点选段落、图片添加批注。</p></header>' +
    '<form class="review-composer"><p class="review-target">点选网页中的文字或图片</p><blockquote class="review-quote" hidden></blockquote>' +
    '<label for="review-comment">批注内容</label><textarea id="review-comment" rows="3" maxlength="4000" placeholder="例如：这里需要更明确地说明语言比较的条件。"></textarea>' +
    '<div class="review-compose-actions"><button type="submit">保存批注</button><button type="button" class="review-reset" hidden>恢复原文</button></div></form>' +
    '<div class="review-list-header"><strong>批注 <span class="review-count">0</span></strong><button type="button" class="review-export">导出修改与批注</button></div>' +
    '<div class="review-comment-list"></div>';
  document.body.append(entry, toolbar, panel);
  const status = toolbar.querySelector('.review-status');
  const form = panel.querySelector('form');
  const textarea = panel.querySelector('textarea');
  const submit = form.querySelector('[type="submit"]');
  const reset = panel.querySelector('.review-reset');
  const list = panel.querySelector('.review-comment-list');

  function setStatus(text, error = false) {
    status.textContent = text; status.classList.toggle('is-error', error);
    entry.classList.toggle('has-error', error);
  }
  function label(id) {
    const el = blocks.get(id);
    if (!el) return '原页面位置已更新';
    const sectionEl = el.closest('section');
    const section = sectionEl?.querySelector('h2')?.textContent || sectionEl?.getAttribute('aria-label') || '标题与作者';
    const detail = (el.closest('[hidden]') ? '（已移除）' : '') + (el.tagName === 'IMG' ? el.alt : normalize(el.textContent));
    return `${section} · ${detail}`;
  }
  function cache() {
    try { localStorage.setItem(cacheKey, JSON.stringify({ ...state, dirty })); } catch (_) { /* Server storage remains primary. */ }
  }
  function applyEdits() {
    skippedEdits = 0;
    for (const [id, edit] of Object.entries(state.edits)) {
      const el = blocks.get(id);
      if (!el || el.dataset.reviewEditable !== 'true') continue;
      const source = originals.get(id).text;
      if (source !== normalize(edit.originalText) && source !== normalize(edit.text)) { skippedEdits++; continue; }
      el.textContent = edit.text; el.classList.add('review-edited');
    }
  }
  function cacheComposer() {
    if (activeId) {
      if (textarea.value.trim()) composerDrafts[activeId] = { text: textarea.value, quote: activeQuote, editingCommentId };
      else delete composerDrafts[activeId];
    }
    try { localStorage.setItem(composerKey, JSON.stringify({ activeId, drafts: composerDrafts })); } catch (_) {}
  }
  function select(id, quote = '') {
    if (activeId !== id) {
      cacheComposer();
      const draft = composerDrafts[id];
      textarea.value = draft?.text || '';
      editingCommentId = state?.comments.some(c => c.id === draft?.editingCommentId) ? draft.editingCommentId : null;
      submit.textContent = editingCommentId ? '保存修改' : '保存批注';
      if (draft?.quote && !quote) quote = draft.quote;
    }
    blocks.get(activeId)?.classList.remove('review-selected');
    activeId = id; activeQuote = quote.slice(0, 2000);
    blocks.get(id)?.classList.add('review-selected');
    const target = panel.querySelector('.review-target');
    target.textContent = label(id); target.title = label(id);
    const quoted = panel.querySelector('.review-quote');
    quoted.textContent = activeQuote; quoted.hidden = !activeQuote;
    reset.hidden = !state?.edits[id];
    cacheComposer();
  }
  function change() {
    dirty = true; cache();
    if (blocked) { setStatus('保存冲突，草稿已保留；请先导出', true); return; }
    setStatus('尚未保存');
    clearTimeout(saveTimer); saveTimer = setTimeout(save, 450);
  }
  async function save() {
    if (!state || saving || !dirty || blocked) return;
    saving = true;
    try {
      while (dirty && !blocked) {
        dirty = false;
        const payload = JSON.stringify({ revision: state.revision, edits: state.edits, comments: state.comments });
        setStatus('正在保存…');
        const response = await fetch('/api/review', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload });
        if (response.status === 409) {
          dirty = true; blocked = true; cache();
          setStatus('保存冲突，草稿已保留；请先导出', true); break;
        }
        if (!response.ok) throw new Error('Save failed');
        const saved = await response.json();
        state.revision = saved.revision; state.updatedAt = saved.updatedAt;
        cache(); setStatus(dirty ? '尚未保存' : (skippedEdits ? `${skippedEdits} 处原文已更新，旧草稿保留在导出中` : '已自动保存'), Boolean(skippedEdits));
      }
    } catch (_) {
      dirty = true; cache(); setStatus('保存未成功，可导出草稿并重试', true);
    } finally { saving = false; }
  }
  function setMode(enabled) {
    mode = enabled; document.body.classList.toggle('review-mode', mode);
    toolbar.hidden = panel.hidden = !mode; entry.hidden = mode;
    entry.setAttribute('aria-expanded', String(mode));
    for (const el of blocks.values()) {
      if (el.dataset.reviewEditable === 'true') {
        if (mode && state) { el.setAttribute('contenteditable', 'plaintext-only'); el.setAttribute('spellcheck', 'true'); }
        else { el.removeAttribute('contenteditable'); el.removeAttribute('spellcheck'); }
      }
    }
    if (!mode) { blocks.get(activeId)?.classList.remove('review-selected'); save(); }
  }
  function button(text, action) {
    const el = document.createElement('button'); el.type = 'button'; el.textContent = text; el.addEventListener('click', action); return el;
  }
  function reveal(id) {
    const block = blocks.get(id);
    const el = block?.closest('[hidden]') ? block.closest('section') : block;
    if (!el) return;
    if (matchMedia('(max-width: 900px)').matches) {
      const rect = el.getBoundingClientRect(), bottom = panel.getBoundingClientRect().top - 12;
      if (rect.top < 66 || rect.bottom > bottom) window.scrollTo({ top: Math.max(0, scrollY + rect.top - 76), behavior: 'smooth' });
    } else el.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }
  function renderComments() {
    list.replaceChildren(); panel.querySelector('.review-count').textContent = state.comments.length;
    entry.textContent = state.comments.length ? `编辑与批注（${state.comments.filter(c => !c.resolved).length}）` : '编辑与批注';
    if (!state.comments.length) {
      const empty = document.createElement('p'); empty.className = 'review-empty'; empty.textContent = '还没有批注。文字改动会自动保存。'; list.append(empty); return;
    }
    for (const comment of [...state.comments].reverse()) {
      const card = document.createElement('article'); card.className = 'review-comment-card'; card.classList.toggle('is-resolved', comment.resolved);
      const target = document.createElement('p'); target.className = 'review-comment-target'; target.textContent = label(comment.blockId);
      const text = document.createElement('p'); text.className = 'review-comment-body'; text.textContent = comment.text;
      card.append(target);
      if (comment.quote) { const q = document.createElement('blockquote'); q.textContent = comment.quote; card.append(q); }
      card.append(text);
      const actions = document.createElement('div'); actions.className = 'review-comment-actions';
      const jump = () => { if (blocks.has(comment.blockId)) { select(comment.blockId, comment.quote); reveal(comment.blockId); } };
      actions.append(button('定位', jump), button('修改', () => { jump(); editingCommentId = comment.id; textarea.value = comment.text; submit.textContent = '保存修改'; cacheComposer(); textarea.focus(); }), button(comment.resolved ? '重新打开' : '标为已处理', () => { comment.resolved = !comment.resolved; comment.updatedAt = new Date().toISOString(); renderComments(); change(); }));
      card.append(actions); list.append(card);
    }
  }

  entry.addEventListener('click', () => {
    setMode(true);
    if (!state) setStatus('编辑服务未连接，正在重试…', true);
    if (!state) load();
  });
  toolbar.querySelector('.review-exit').addEventListener('click', () => setMode(false));
  status.addEventListener('click', () => { if (dirty && !blocked) save(); });
  document.querySelector('main').addEventListener('click', event => {
    if (!mode || !state) return;
    const el = event.target.closest('[data-review-id]');
    if (!el) return;
    if (event.target.closest('a') || el.tagName === 'IMG') event.preventDefault();
    select(el.dataset.reviewId, activeId === el.dataset.reviewId ? activeQuote : '');
    if (matchMedia('(max-width: 900px)').matches) reveal(el.dataset.reviewId);
  });
  document.querySelector('main').addEventListener('pointerup', () => {
    if (!mode || !state) return;
    const selection = getSelection();
    if (!selection || selection.isCollapsed) return;
    const start = selection.anchorNode?.parentElement?.closest('[data-review-id]');
    const end = selection.focusNode?.parentElement?.closest('[data-review-id]');
    if (start && start === end) select(start.dataset.reviewId, selection.toString());
  });
  document.querySelector('main').addEventListener('input', event => {
    if (!mode || !state) return;
    const el = event.target.closest('[data-review-id]');
    if (!el || el.dataset.reviewEditable !== 'true') return;
    const id = el.dataset.reviewId, text = el.innerText.trim();
    if (normalize(text) === originals.get(id).text) { delete state.edits[id]; el.classList.remove('review-edited'); }
    else { state.edits[id] = { text, originalText: originals.get(id).text, updatedAt: new Date().toISOString() }; el.classList.add('review-edited'); }
    select(id); change();
  });
  reset.addEventListener('click', () => {
    if (!activeId || !state.edits[activeId]) return;
    const el = blocks.get(activeId); el.innerHTML = originals.get(activeId).html;
    delete state.edits[activeId]; el.classList.remove('review-edited'); select(activeId); change();
  });
  textarea.addEventListener('input', cacheComposer);
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!state || !activeId) { setStatus('请先点选一段文字或图片', true); return; }
    const text = textarea.value.trim();
    if (!text) { textarea.focus(); return; }
    const now = new Date().toISOString();
    if (editingCommentId) {
      const comment = state.comments.find(c => c.id === editingCommentId);
      if (comment) { comment.text = text; comment.updatedAt = now; }
    } else {
      state.comments.push({ id: crypto.randomUUID(), blockId: activeId, quote: activeQuote, text, createdAt: now, updatedAt: now, resolved: false });
    }
    editingCommentId = null; textarea.value = ''; cacheComposer(); submit.textContent = '保存批注'; renderComments(); change(); save();
  });
  panel.querySelector('.review-export').addEventListener('click', () => {
    if (!state) return;
    const context = Object.fromEntries([...blocks].map(([id, el]) => [id, { label: label(id), originalText: originals.get(id).text, image: el.tagName === 'IMG' ? el.getAttribute('src') : null }]));
    cacheComposer();
    const url = URL.createObjectURL(new Blob([JSON.stringify({ ...state, blocks: context, unsubmittedComments: composerDrafts }, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = 'VisionValueBench-homepage-feedback.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.addEventListener('keydown', event => {
    if (mode && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') { event.preventDefault(); save(); }
    if (mode && event.key === 'Escape' && !textarea.value) setMode(false);
  });
  window.addEventListener('pagehide', () => {
    cacheComposer();
    if (state && dirty && !blocked && !saving) fetch('/api/review', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ revision: state.revision, edits: state.edits, comments: state.comments }), keepalive: true }).catch(() => {});
  });
  async function load() {
    if (loading) return;
    loading = true;
    try {
      const response = await fetch('/api/review', { cache: 'no-store' });
      if (!response.ok) throw new Error('Load failed');
      state = await response.json();
      let draft;
      try { draft = JSON.parse(localStorage.getItem(cacheKey)); } catch (_) {}
      if (draft?.dirty && draft.edits && Array.isArray(draft.comments)) {
        const alreadySaved = JSON.stringify(draft.edits) === JSON.stringify(state.edits) && JSON.stringify(draft.comments) === JSON.stringify(state.comments);
        if (!alreadySaved) {
          blocked = draft.revision !== state.revision;
          state = draft; dirty = true;
        }
      }
      applyEdits(); renderComments();
      if (draftActiveId && blocks.has(draftActiveId)) select(draftActiveId);
      setMode(mode);
      setStatus(blocked ? '保存冲突，草稿已保留；请先导出' : (dirty ? '正在恢复草稿…' : (skippedEdits ? `${skippedEdits} 处原文已更新，旧草稿保留在导出中` : '已自动保存')), blocked || Boolean(skippedEdits)); cache();
      if (dirty) save();
    } catch (_) { setStatus('编辑服务未连接，请稍后重试', true); }
    finally { loading = false; }
  }
  load();
})();
