(() => {
  const state = { sessionId: null, userId: null };
  const $ = (id) => document.getElementById(id);
  const show = (id, visible) => { $(id).hidden = !visible; };
  const addMessage = (text, kind) => {
    const node = document.createElement('div');
    node.className = `message ${kind}`;
    node.textContent = text;
    $('conversation').appendChild(node);
    $('conversation').scrollTop = $('conversation').scrollHeight;
    return node;
  };
  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault(); $('login-error').hidden = true;
    try {
      const response = await fetch('/api/login', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({user_id: $('user-id').value}) });
      if (!response.ok) throw new Error('登录失败');
      const data = await response.json();
      const sessionResponse = await fetch(`/api/sessions/${data.session_id}`);
      if (!sessionResponse.ok) throw new Error('会话创建失败');
      const session = await sessionResponse.json(); state.sessionId = session.session_id; state.userId = session.user_id;
      $('session-label').textContent = `${state.userId} · ${state.sessionId.slice(0, 8)}`;
      show('login-panel', false); show('chat-panel', true); $('message-input').focus();
    } catch (error) { $('login-error').textContent = error.message; $('login-error').hidden = false; }
  });
  $('new-session').addEventListener('click', () => { state.sessionId = null; $('conversation').replaceChildren(); show('chat-panel', false); show('login-panel', true); });
  $('chat-form').addEventListener('submit', async (event) => {
    event.preventDefault(); const input = $('message-input'); const message = input.value.trim(); if (!message) return;
    addMessage(message, 'user'); input.value = ''; $('send-button').disabled = true; $('stream-status').textContent = '正在处理…';
    const agentNode = addMessage('', 'agent');
    try {
      const response = await fetch('/api/chat/stream', { method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({message, user_id: state.userId, session_id: state.sessionId}) });
      if (!response.ok || !response.body) throw new Error('服务暂时不可用');
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
      while (true) {
        const part = await reader.read(); if (part.done) break; buffer += decoder.decode(part.value, {stream: true});
        const chunks = buffer.split('\n\n'); buffer = chunks.pop();
        for (const chunk of chunks) { const line = chunk.split('\n').find((item) => item.startsWith('data: ')); if (!line) continue; const eventData = JSON.parse(line.slice(6));
          if (eventData.type === 'chunk') agentNode.textContent += eventData.text;
          if (eventData.type === 'complete') { state.sessionId = eventData.response.conversation_id; $('stream-status').dataset.traceId = eventData.response.trace_id; $('stream-status').textContent = `完成 · trace ${eventData.response.trace_id}`; renderStatus(agentNode, eventData.response); }
        }
      }
    } catch (error) { agentNode.textContent = error.message; agentNode.classList.add('error'); $('stream-status').textContent = '请求失败'; }
    finally { $('send-button').disabled = false; }
  });
  function renderStatus(node, response) {
    const metadata = response.metadata || {}; const values = [];
    if (metadata.ticket_status) values.push(`工单：${metadata.ticket_status}`);
    if (metadata.approval_status) values.push(`审批：${metadata.approval_status}`);
    if (metadata.handoff_reason) values.push(`转人工：${metadata.handoff_reason}`);
    if (response.sources && response.sources.length) values.push(`引用：${response.sources.length} 条`);
    if (values.length) { const status = document.createElement('div'); status.className = 'status'; status.textContent = values.join(' · '); node.appendChild(status); }
  }
})();
