(() => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;

  async function request(path, options = {}) {
    const headers = {...(options.headers || {})};
    if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    if (!['GET', 'HEAD'].includes(options.method || 'GET')) headers['X-CSRFToken'] = csrfToken;
    const response = await fetch(`/api/${path}`, {...options, headers});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
    return data;
  }

  window.workspaceApi = {
    getSandboxes: () => request('sandboxes/'),
    createSandbox: name => request('sandboxes/', {method: 'POST', body: JSON.stringify({name})}),
    renameSandbox: (id, name) => request(`sandboxes/${id}/`, {method: 'PATCH', body: JSON.stringify({name})}),
    deleteSandbox: id => request(`sandboxes/${id}/`, {method: 'DELETE'}),
    getGraph: id => request(`sandboxes/${id}/graph/`),
    createNode: (sandboxId, data) => request(`sandboxes/${sandboxId}/topics/`, {method: 'POST', body: JSON.stringify(data)}),
    updateNode: (id, data) => request(`topics/${id}/`, {method: 'PATCH', body: JSON.stringify(data)}),
    deleteNode: id => request(`topics/${id}/`, {method: 'DELETE'}),
    generateQuiz: id => request(`topics/${id}/quiz/`, {method: 'POST'}),
    getTags: () => request('tags/'),
    createTag: name => request('tags/', {method: 'POST', body: JSON.stringify({name})}),
    applyTag: (sandboxId, tagId, topicIds) => request(`sandboxes/${sandboxId}/tags/`, {method: 'POST', body: JSON.stringify({tag_id: tagId, topic_ids: topicIds})}),
    removeTag: (topicId, tagId) => request(`topics/${topicId}/tags/${tagId}/`, {method: 'DELETE'}),
    createPrerequisite: (sandboxId, prerequisite, topic) => request(`sandboxes/${sandboxId}/prerequisites/`, {method: 'POST', body: JSON.stringify({prerequisite, topic})}),
    uploadDocument: (sandboxId, file, topicIds) => { const form = new FormData(); form.append('file', file); form.append('topic_ids', JSON.stringify(topicIds)); return request(`sandboxes/${sandboxId}/documents/`, {method: 'POST', body: form}); },
    deleteDocument: id => request(`documents/${id}/`, {method: 'DELETE'}),
    updateDocument: (id, data) => request(`documents/${id}/`, {method: 'PATCH', body: JSON.stringify(data)}),
    uploadSyllabus: (sandboxId, file) => { const form = new FormData(); form.append('file', file); return request(`sandboxes/${sandboxId}/syllabus/`, {method: 'POST', body: form}); },
    generateVideo: (sandboxId, topicIds) => request('videos/generate/', {method: 'POST', body: JSON.stringify({sandbox_id: sandboxId, topic_ids: topicIds})}),
    getVideoJob: jobId => request(`videos/jobs/${jobId}/`),
  };
})();
