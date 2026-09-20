(() => {
  const $ = selector => document.querySelector(selector);
  const escape = value => String(value ?? '').replace(/[&<>"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[char]));
  const state = {sandboxes: [], activeId: null, graph: {nodes: [], edges: []}, tags: [], selected: new Set(), filters: new Set(), focusMode: false, focusNodes: new Set(), transform: {x: 0, y: 0, scale: 1}};
  const active = () => state.sandboxes.find(sandbox => sandbox.id === state.activeId);
  const nodes = () => state.graph.nodes || [];
  const nodeById = id => nodes().find(node => String(node.id) === String(id));
  const selectedNodes = () => nodes().filter(node => state.selected.has(String(node.id)));
  const tagById = id => state.tags.find(tag => String(tag.id) === String(id));
  const hasTagId = (node, id) => (node.tag_ids || []).some(tagId => String(tagId) === String(id));

  function showError(message) { openModal(`<h2>Something went wrong</h2><p class="sub">${escape(message)}</p><div class="modal-actions"><button class="primary-button" data-close-modal>Okay</button></div>`); }
  function focusedNodeIds() {
    if (!state.focusMode) return null;
    const visible = new Set([...state.focusNodes].filter(nodeById).map(String));
    const pending = [...visible];
    while (pending.length) {
      const topicId = pending.pop();
      state.graph.edges.filter(edge => String(edge.topic) === topicId).forEach(edge => {
        const prerequisiteId = String(edge.prerequisite);
        if (!visible.has(prerequisiteId)) { visible.add(prerequisiteId); pending.push(prerequisiteId); }
      });
    }
    return visible;
  }
  function graphNodes() {
    const focused = focusedNodeIds();
    const visible = nodes().filter(node => (!state.filters.size || (node.tag_ids || []).some(id => state.filters.has(String(id)))) && (!focused || focused.has(String(node.id))));
    const columns = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(visible.length || 1))));
    return visible.map((node, index) => ({...node, x: node.x ?? 230 + (index % columns) * (540 / Math.max(columns - 1, 1)), y: node.y ?? 105 + Math.floor(index / columns) * 145}));
  }
  async function loadSandboxes(preferredId = null) {
    const data = await workspaceApi.getSandboxes();
    state.sandboxes = data.sandboxes;
    const next = preferredId && state.sandboxes.some(s => s.id === preferredId) ? preferredId : state.sandboxes[0]?.id || null;
    state.activeId = next;
    state.selected.clear(); state.filters.clear();
    if (next) await loadGraph(next); else { state.graph = {nodes: [], edges: []}; render(); }
  }
  async function loadGraph(sandboxId = state.activeId) {
    if (!sandboxId) return;
    const data = await workspaceApi.getGraph(sandboxId);
    state.graph = {nodes: data.nodes, edges: data.edges};
    const sandbox = state.sandboxes.find(item => item.id === sandboxId);
    if (sandbox) sandbox.name = data.sandbox.name;
    state.selected = new Set([...state.selected].filter(id => nodeById(id)));
    render();
  }
  async function refreshGraph() { await loadGraph(state.activeId); }
  async function loadTags() { state.tags = (await workspaceApi.getTags()).tags; renderFilter(); }

  function render() {
    renderSidebar(); $('#sandboxTitle').textContent = active()?.name || 'Knowledge map';
    renderFilter(); renderFocusMode(); renderGraph(); renderSelection(); renderDetail();
    $('#emptyState').classList.toggle('hidden', !active() || nodes().length !== 0);
    $('#graphHint').classList.toggle('hidden', !active() || nodes().length === 0);
    if (window.lucide) window.lucide.createIcons({attrs: {'stroke-width': 1.9}});
  }
  function renderSidebar() {
    $('#sandboxList').innerHTML = state.sandboxes.map(s => `<div class="sandbox-row"><button class="sandbox-item ${s.id === state.activeId ? 'active' : ''}" data-sandbox="${s.id}"><i data-lucide="folder"></i>${escape(s.name)}</button><button class="sandbox-delete" data-delete-sandbox="${s.id}" aria-label="Delete ${escape(s.name)}"><i data-lucide="trash-2"></i></button></div>`).join('');
  }
  function renderFilter() {
    const allTags = state.tags;
    $('#filterMenu').innerHTML = `<button class="filter-all filter-check" data-all-filter><span class="custom-checkbox ${state.filters.size ? '' : 'checked'}"><i data-lucide="check"></i></span>All topics</button><h4>Tags</h4>${allTags.map(tag => `<label class="filter-check"><input type="checkbox" data-filter-tag="${tag.id}" ${state.filters.has(String(tag.id)) ? 'checked' : ''}><span class="custom-checkbox"><i data-lucide="check"></i></span>${escape(tag.name)}</label>`).join('')}<button class="reset-filter ${state.filters.size ? '' : 'hidden'}" data-reset-filter>Reset filters</button>`;
  }
  function renderFocusMode() {
    const button = $('#focusMode');
    const focused = focusedNodeIds();
    button.classList.toggle('active', state.focusMode);
    button.setAttribute('aria-pressed', String(state.focusMode));
    button.title = state.focusMode && focused ? `Focus: ${focused.size} topic${focused.size === 1 ? '' : 's'}` : 'Focus Mode';
  }
  function renderGraph() {
    const positioned = graphNodes(), visibleIds = new Set(positioned.map(node => String(node.id))), viewport = $('#graphViewport');
    viewport.setAttribute('transform', `translate(${state.transform.x} ${state.transform.y}) scale(${state.transform.scale})`);
    const positions = new Map(positioned.map(node => [String(node.id), node]));
    const edges = state.graph.edges.filter(edge => visibleIds.has(String(edge.prerequisite)) && visibleIds.has(String(edge.topic))).map(edge => { const source = positions.get(String(edge.prerequisite)), target = positions.get(String(edge.topic)); return `<line class="edge" x1="${source.x}" y1="${source.y + 34}" x2="${target.x}" y2="${target.y - 34}" marker-end="url(#arrow)"/>`; }).join('');
    const nodeMarkup = positioned.map(node => `<g class="node-group ${state.selected.has(String(node.id)) ? 'selected' : ''}" data-node="${node.id}" transform="translate(${node.x - 87} ${node.y - 31})"><rect class="node-bg" width="174" height="62" rx="14"/><text class="node-title" x="87" y="27" text-anchor="middle">${escape(node.name)}</text><text class="node-tag" x="87" y="46" text-anchor="middle">${escape(node.tags.slice(0, 2).join(' · ') || 'Untagged')}</text></g>`).join('');
    viewport.innerHTML = edges + nodeMarkup;
  }
  function renderSelection() { const count = state.selected.size; $('#selectionBar').classList.toggle('hidden', count < 2); $('#selectionCount').textContent = `${count} topics selected`; }
  function renderDetail() {
    const one = selectedNodes().length === 1 ? selectedNodes()[0] : null; $('#detailPanel').classList.toggle('hidden', !one); if (!one) return;
    $('#detailName').textContent = one.name; $('#detailDescription').textContent = one.description || 'No description yet.';
    const prerequisites = state.graph.edges.filter(edge => String(edge.topic) === String(one.id)).map(edge => nodeById(edge.prerequisite)?.name).filter(Boolean);
    $('#detailPrerequisites').innerHTML = (prerequisites.length ? prerequisites : ['None yet']).map(value => `<li>${escape(value)}</li>`).join('');
    $('#detailDocuments').innerHTML = (one.documents.length ? one.documents.map(document => document.name) : ['No documents attached']).map(value => `<li>${escape(value)}</li>`).join('');
    $('#detailTags').innerHTML = (one.tag_ids || []).map(id => {
      const tag = tagById(id);
      return tag ? `<button class="tag tag-remove" data-remove-tag-id="${tag.id}">${escape(tag.name)}<i data-lucide="x"></i></button>` : '';
    }).join('');
  }
  function selectNode(id, event) { id = String(id); if (event.shiftKey) state.selected.has(id) ? state.selected.delete(id) : state.selected.add(id); else state.selected = new Set([id]); render(); }
  function openModal(content) { $('#modalContent').innerHTML = content; $('#modalBackdrop').classList.remove('hidden'); if (window.lucide) window.lucide.createIcons({attrs: {'stroke-width': 1.9}}); }
  function closeModal() { $('#modalBackdrop').classList.add('hidden'); }

  const topicFields = (node = {name: '', description: '', tag_ids: []}, includeTags = true) => `<div class="field"><label for="topicName">Topic name</label><input id="topicName" value="${escape(node.name)}" placeholder="e.g. Related rates" autofocus></div><div class="field"><label for="topicDescription">Description</label><textarea id="topicDescription" placeholder="What should a student understand?">${escape(node.description)}</textarea></div>${includeTags ? `<div class="field"><label>Tags</label><div class="modal-tags">${state.tags.map(tag => `<button type="button" class="tag-toggle ${hasTagId(node, tag.id) ? 'active' : ''}" data-tag="${tag.id}">${escape(tag.name)}</button>`).join('')}<button type="button" class="new-tag-button" data-create-tag="topic-create"><i data-lucide="plus"></i>New tag</button></div></div>` : ''}`;
  function draftTopic() { return {name: $('#topicName')?.value || '', description: $('#topicDescription')?.value || '', tag_ids: [...document.querySelectorAll('.tag-toggle.active')].map(button => Number(button.dataset.tag))}; }
  function createNodeModal(edit = false, draft = null) {
    const node = draft || (edit ? selectedNodes()[0] : undefined); openModal(`<h2>${edit ? 'Edit topic' : 'Create node'}</h2><p class="sub">${edit ? 'Update this topic in your knowledge map.' : 'Add a concept to your knowledge map.'}</p><form id="topicForm">${topicFields(node, !edit)}<div class="modal-actions"><button type="button" class="soft-button" data-close-modal>Cancel</button><button class="primary-button">${edit ? 'Save changes' : 'Create topic'}</button></div></form>`);
    $('#topicForm').addEventListener('submit', async event => { event.preventDefault(); const name = $('#topicName').value.trim(); if (!name) return; const data = {name, description: $('#topicDescription').value.trim()}; if (!edit) data.tag_ids = [...document.querySelectorAll('.tag-toggle.active')].map(button => Number(button.dataset.tag)); try { if (edit) await workspaceApi.updateNode(node.id, data); else await workspaceApi.createNode(state.activeId, data); closeModal(); await refreshGraph(); if (!edit) state.selected = new Set([String(state.graph.nodes.at(-1)?.id)]); render(); } catch (error) { showError(error.message); } });
  }
  function tagModal(ids) { openModal(`<h2>Add tag</h2><p class="sub">Apply a label to ${ids.size} selected ${ids.size === 1 ? 'topic' : 'topics'}.</p><div class="modal-tags tag-choice">${state.tags.map(tag => `<button data-apply-tag="${tag.id}">${escape(tag.name)}</button>`).join('')}<button class="new-tag-button" data-create-tag="bulk"><i data-lucide="plus"></i>New tag</button></div><div class="modal-actions"><button class="soft-button" data-close-modal>Cancel</button></div>`); }
  function createTagModal(context, draft = null) {
    openModal(`<h2>Create Tag</h2><form id="createTagForm"><div class="field"><label for="customTagName">Tag name</label><input id="customTagName" placeholder="e.g. Final review" required autofocus></div><p class="tag-error hidden" id="tagError"></p><div class="modal-actions"><button type="button" class="soft-button" data-close-modal>Cancel</button><button class="primary-button">Create</button></div></form>`);
    $('#createTagForm').addEventListener('submit', async event => { event.preventDefault(); const name = $('#customTagName').value.trim(); if (!name) return; try { const {tag} = await workspaceApi.createTag(name); state.tags.push(tag); renderFilter(); if (context === 'bulk') return tagModal(state.selected); createNodeModal(context === 'topic-edit', {...draft, tag_ids: [...(draft.tag_ids || []), tag.id]}); } catch (error) { const element = $('#tagError'); element.textContent = error.message; element.classList.remove('hidden'); } });
  }
  function deleteNodesModal() { const selected = selectedNodes(); if (!selected.length) return; const single = selected.length === 1; openModal(`<h2>Delete ${single ? 'node' : 'nodes'}?</h2><p class="sub">${single ? `Are you sure you want to delete &quot;${escape(selected[0].name)}&quot;?` : `Are you sure you want to delete these ${selected.length} nodes?`}</p><div class="modal-actions"><button class="soft-button" data-close-modal>Cancel</button><button class="danger-button" id="confirmDeleteNodes">Delete</button></div>`); }
  function deleteSandboxModal(sandboxId) { const sandbox = state.sandboxes.find(item => item.id === sandboxId); if (!sandbox) return; openModal(`<h2>Delete sandbox?</h2><p class="sub">Are you sure you want to delete &quot;${escape(sandbox.name)}&quot;?<br><br>This will also delete its topics, documents, relationships, and other associated data.</p><div class="modal-actions"><button class="soft-button" data-close-modal>Cancel</button><button class="danger-button" id="confirmDeleteSandbox" data-sandbox-id="${sandbox.id}">Delete</button></div>`); }
  function documentModal() {
    const selected = state.selected.size ? [...state.selected] : nodes().slice(0, 1).map(node => String(node.id)); if (!selected.length) return showError('Create a topic before uploading a document.');
    openModal(`<h2>Upload document</h2><p class="sub upload-intro">Choose a PDF or DOCX. This file will be added to ${selected.length ? 'the selected topic' : 'your first topic'}.</p><label class="upload-drop" id="documentDrop"><i data-lucide="file-up"></i><span class="upload-choose"><i data-lucide="plus"></i>Choose a file</span><input id="documentFile" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"></label><p class="upload-help">PDF or DOCX, up to 20 MB</p>`);
    const drop = $('#documentDrop'), useFile = async file => { if (!file) return; $('#modalContent').innerHTML = `<h2>Uploading document</h2><p class="sub">${escape(file.name)}</p><div class="progress"><i></i></div><p class="sub">Saving and associating your document…</p>`; try { await workspaceApi.uploadDocument(state.activeId, file, selected); closeModal(); await refreshGraph(); } catch (error) { showError(error.message); } }; $('#documentFile').addEventListener('change', event => useFile(event.target.files[0])); drop.addEventListener('dragover', event => { event.preventDefault(); drop.classList.add('is-dragover'); }); drop.addEventListener('dragleave', event => { if (!drop.contains(event.relatedTarget)) drop.classList.remove('is-dragover'); }); drop.addEventListener('drop', event => { event.preventDefault(); drop.classList.remove('is-dragover'); useFile(event.dataTransfer.files[0]); });
  }
  function syllabusModal() {
    openModal(`<h2>Upload syllabus</h2><p class="sub">Upload a syllabus to extract topics and prerequisite relationships.</p><label class="upload-drop"><i data-lucide="file-up"></i><span class="upload-choose"><i data-lucide="plus"></i>Choose a syllabus</span><input id="syllabusFile" type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"></label><p class="upload-help">PDF or DOCX, up to 20 MB</p>`);
    $('#syllabusFile').addEventListener('change', async event => { const file = event.target.files[0]; if (!file) return; $('#modalContent').innerHTML = `<h2>Building your knowledge map</h2><p class="sub">${escape(file.name)}</p><div class="step-list"><div class="step active"><b>●</b> Extracting topics</div><div class="step active"><b>●</b> Finding prerequisites</div><div class="step active"><b>●</b> Building knowledge map</div></div><div class="progress"><i></i></div>`; try { const graph = await workspaceApi.uploadSyllabus(state.activeId, file); state.graph = {nodes: graph.nodes, edges: graph.edges}; state.selected.clear(); state.filters.clear(); closeModal(); render(); } catch (error) { showError(error.message); } });
  }
  function changeZoom(amount, anchor = null) {
    const previousScale = state.transform.scale;
    const nextScale = Math.max(.55, Math.min(1.8, previousScale + amount));
    if (nextScale === previousScale) return;
    const viewBox = graphSvg.viewBox.baseVal;
    const zoomAnchor = anchor || {x: viewBox.width / 2, y: viewBox.height / 2};
    const worldX = (zoomAnchor.x - state.transform.x) / previousScale;
    const worldY = (zoomAnchor.y - state.transform.y) / previousScale;
    state.transform.scale = nextScale;
    state.transform.x = zoomAnchor.x - worldX * nextScale;
    state.transform.y = zoomAnchor.y - worldY * nextScale;
    renderGraph();
  }
  function closeRenamePopover() { $('#renamePopover').classList.add('hidden'); }
  function openRenamePopover() { if (!active()) return; $('#renameInput').value = active().name; $('#renamePopover').classList.remove('hidden'); setTimeout(() => { $('#renameInput').focus(); $('#renameInput').select(); }, 0); }

  document.addEventListener('click', event => {
    if (!event.target.closest('#renameWrap')) closeRenamePopover();
    if (!event.target.closest('#profileArea') && !event.target.closest('#profileMenu')) { $('#profileMenu').classList.add('hidden'); $('#profileArea').setAttribute('aria-expanded', 'false'); }
    const deleteSandbox = event.target.closest('[data-delete-sandbox]'); if (deleteSandbox) { deleteSandboxModal(Number(deleteSandbox.dataset.deleteSandbox)); return; }
    const node = event.target.closest('[data-node]'); if (node) { if (suppressNodeClick) return; selectNode(node.dataset.node, event); return; }
    const sandbox = event.target.closest('[data-sandbox]'); if (sandbox) { state.activeId = Number(sandbox.dataset.sandbox); state.selected.clear(); state.filters.clear(); loadGraph(state.activeId).catch(error => showError(error.message)); return; }
    const action = event.target.closest('[data-action]')?.dataset.action; if (action === 'node' && active()) createNodeModal(); if (action === 'document' && active()) documentModal(); if (action === 'syllabus' && active()) syllabusModal();
    if (event.target.closest('#addButton')) $('#addMenu').classList.toggle('hidden'); if (event.target.closest('#filterButton')) $('#filterMenu').classList.toggle('hidden'); if (event.target.closest('#focusMode')) { if (state.focusMode) { state.focusMode = false; state.focusNodes.clear(); render(); } else { const focusNodes = new Set(selectedNodes().map(node => String(node.id))); if (!focusNodes.size) return showError('Select one or more topics before enabling Focus Mode.'); state.focusNodes = focusNodes; state.focusMode = true; render(); } }
    if (event.target.closest('#profileArea') && !event.target.closest('#profileMenu')) { const menu = $('#profileMenu'), hidden = menu.classList.toggle('hidden'); $('#profileArea').setAttribute('aria-expanded', String(!hidden)); }
    if (event.target.closest('#bulkTag') || event.target.closest('#addTagToNode')) tagModal(state.selected); if (event.target.closest('#deleteNode') || event.target.closest('#deleteNodes')) deleteNodesModal(); if (event.target.closest('#clearSelection') || event.target.closest('#closePanel')) { state.selected.clear(); render(); }
    if (event.target.closest('#editNode')) createNodeModal(true);
    if (event.target.closest('#newSandbox')) workspaceApi.createSandbox(`New Sandbox ${state.sandboxes.length + 1}`).then(({sandbox}) => loadSandboxes(sandbox.id)).catch(error => showError(error.message));
    if (event.target.closest('#renameSandbox')) openRenamePopover(); if (event.target.closest('#cancelRename')) closeRenamePopover();
    if (event.target.closest('#zoomIn')) changeZoom(.12); if (event.target.closest('#zoomOut')) changeZoom(-.12); if (event.target.closest('[data-close-modal]') || event.target === $('#modalBackdrop')) closeModal();
    const createTag = event.target.closest('[data-create-tag]'); if (createTag) { const context = createTag.dataset.createTag; createTagModal(context, context.startsWith('topic') ? draftTopic() : null); }
    const apply = event.target.closest('[data-apply-tag]'); if (apply) { const tag = tagById(apply.dataset.applyTag), topicIds = selectedNodes().map(node => node.id); if (!tag || !state.activeId || !topicIds.length) return showError('Select one or more topics before applying a tag.'); workspaceApi.applyTag(state.activeId, tag.id, topicIds).then(() => { selectedNodes().forEach(node => { if (!hasTagId(node, tag.id)) node.tag_ids = [...(node.tag_ids || []), tag.id]; if (!(node.tags || []).includes(tag.name)) node.tags = [...(node.tags || []), tag.name]; }); closeModal(); render(); }).catch(error => showError(error.message)); }
    const remove = event.target.closest('[data-remove-tag-id]'); if (remove) { const node = selectedNodes()[0], tag = tagById(remove.dataset.removeTagId); if (!node || !tag) return showError('This tag is no longer available.'); workspaceApi.removeTag(node.id, tag.id).then(() => { node.tag_ids = (node.tag_ids || []).filter(id => String(id) !== String(tag.id)); node.tags = (node.tags || []).filter(name => name !== tag.name); render(); }).catch(error => showError(error.message)); }
    if (event.target.closest('#confirmDeleteNodes')) Promise.all([...state.selected].map(workspaceApi.deleteNode)).then(async () => { state.selected.clear(); closeModal(); await refreshGraph(); }).catch(error => showError(error.message));
    const confirmDeleteSandbox = event.target.closest('#confirmDeleteSandbox'); if (confirmDeleteSandbox) { const sandboxId = Number(confirmDeleteSandbox.dataset.sandboxId); workspaceApi.deleteSandbox(sandboxId).then(async () => { const wasActive = state.activeId === sandboxId; state.sandboxes = state.sandboxes.filter(sandbox => sandbox.id !== sandboxId); closeModal(); if (wasActive) { state.activeId = state.sandboxes[0]?.id || null; state.selected.clear(); state.filters.clear(); if (state.activeId) await loadGraph(state.activeId); else { state.graph = {nodes: [], edges: []}; render(); } } else render(); }).catch(error => showError(error.message)); }
    if (event.target.closest('[data-all-filter]') || event.target.closest('[data-reset-filter]')) { state.filters.clear(); render(); }
  });
  $('#renameForm').addEventListener('submit', event => { event.preventDefault(); const name = $('#renameInput').value.trim(); if (!name || !active()) return; workspaceApi.renameSandbox(active().id, name).then(({sandbox}) => { active().name = sandbox.name; closeRenamePopover(); render(); }).catch(error => showError(error.message)); });
  $('#profileArea').addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); $('#profileArea').click(); } });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('#renamePopover').classList.contains('hidden')) { event.preventDefault(); closeRenamePopover(); } });
  document.addEventListener('change', event => { if (event.target.matches('[data-filter-tag]')) { const tag = tagById(event.target.dataset.filterTag); if (!tag) return; event.target.checked ? state.filters.add(String(tag.id)) : state.filters.delete(String(tag.id)); render(); } });

  const graphSvg = $('#graphSvg'), selectionBox = $('#selectionBox'); let graphDrag = null, suppressNodeClick = false;
  const pointInSvg = event => { const point = graphSvg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY; return point.matrixTransform(graphSvg.getScreenCTM().inverse()); };
  const drawSelectionBox = (start, end) => { selectionBox.setAttribute('x', Math.min(start.x, end.x)); selectionBox.setAttribute('y', Math.min(start.y, end.y)); selectionBox.setAttribute('width', Math.abs(end.x - start.x)); selectionBox.setAttribute('height', Math.abs(end.y - start.y)); selectionBox.classList.remove('hidden'); };
  const clearSelectionBox = () => selectionBox.classList.add('hidden');
  const selectBoxContents = drag => { const left = Math.min(drag.start.x, drag.current.x), right = Math.max(drag.start.x, drag.current.x), top = Math.min(drag.start.y, drag.current.y), bottom = Math.max(drag.start.y, drag.current.y); const inside = graphNodes().filter(node => { const x = node.x * state.transform.scale + state.transform.x, y = node.y * state.transform.scale + state.transform.y; return x + 87 * state.transform.scale >= left && x - 87 * state.transform.scale <= right && y + 31 * state.transform.scale >= top && y - 31 * state.transform.scale <= bottom; }); if (!drag.additive) state.selected.clear(); inside.forEach(node => state.selected.add(String(node.id))); render(); };
  graphSvg.addEventListener('contextmenu', event => event.preventDefault());
  graphSvg.addEventListener('pointerdown', event => { if (event.button !== 0 && event.button !== 2) return; const point = pointInSvg(event); if (event.button === 2) { event.preventDefault(); graphDrag = {kind: 'pan', x: event.clientX, y: event.clientY, tx: state.transform.x, ty: state.transform.y}; graphSvg.setPointerCapture(event.pointerId); graphSvg.classList.add('dragging'); return; } const nodeElement = event.target.closest('[data-node]'); if (nodeElement) { const node = graphNodes().find(item => String(item.id) === nodeElement.dataset.node); if (!node) return; const graphPoint = {x: (point.x - state.transform.x) / state.transform.scale, y: (point.y - state.transform.y) / state.transform.scale}; graphDrag = {kind: 'node', id: String(node.id), shiftKey: event.shiftKey, offsetX: graphPoint.x - node.x, offsetY: graphPoint.y - node.y, startX: graphPoint.x, startY: graphPoint.y, previous: {x: node.x, y: node.y}, moved: false}; graphSvg.setPointerCapture(event.pointerId); return; } graphDrag = {kind: 'select', start: point, current: point, additive: event.shiftKey}; graphSvg.setPointerCapture(event.pointerId); drawSelectionBox(point, point); });
  graphSvg.addEventListener('pointermove', event => { if (!graphDrag) return; if (graphDrag.kind === 'pan') { state.transform.x = graphDrag.tx + event.clientX - graphDrag.x; state.transform.y = graphDrag.ty + event.clientY - graphDrag.y; renderGraph(); } else if (graphDrag.kind === 'node') { const point = pointInSvg(event), graphPoint = {x: (point.x - state.transform.x) / state.transform.scale, y: (point.y - state.transform.y) / state.transform.scale}; graphDrag.moved ||= Math.abs(graphPoint.x - graphDrag.startX) > 5 || Math.abs(graphPoint.y - graphDrag.startY) > 5; if (!graphDrag.moved) return; const node = nodeById(graphDrag.id); if (!node) return; node.x = graphPoint.x - graphDrag.offsetX; node.y = graphPoint.y - graphDrag.offsetY; renderGraph(); } else { graphDrag.current = pointInSvg(event); drawSelectionBox(graphDrag.start, graphDrag.current); } });
  graphSvg.addEventListener('pointerup', event => { if (!graphDrag) return; const drag = graphDrag; graphDrag = null; graphSvg.classList.remove('dragging'); if (graphSvg.hasPointerCapture(event.pointerId)) graphSvg.releasePointerCapture(event.pointerId); if (drag.kind === 'node') { suppressNodeClick = true; setTimeout(() => { suppressNodeClick = false; }, 0); if (!drag.moved) { selectNode(drag.id, {shiftKey: drag.shiftKey}); return; } const node = nodeById(drag.id); workspaceApi.updateNode(drag.id, {x: node.x, y: node.y}).then(({topic}) => { Object.assign(node, topic); renderGraph(); }).catch(error => { node.x = drag.previous.x; node.y = drag.previous.y; renderGraph(); showError(`Position was not saved: ${error.message}`); }); } if (drag.kind === 'select') { drag.current = pointInSvg(event); const moved = Math.abs(drag.current.x - drag.start.x) > 4 || Math.abs(drag.current.y - drag.start.y) > 4; clearSelectionBox(); if (moved) selectBoxContents(drag); else { state.selected.clear(); render(); } } });
  graphSvg.addEventListener('pointercancel', () => { graphDrag = null; clearSelectionBox(); graphSvg.classList.remove('dragging'); }); graphSvg.addEventListener('wheel', event => { event.preventDefault(); changeZoom(event.deltaY > 0 ? -.08 : .08, pointInSvg(event)); }, {passive: false});
  Promise.all([loadTags(), loadSandboxes()]).catch(error => showError(error.message));
})();
