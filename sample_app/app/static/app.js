/* Sample App — Client-side JavaScript */

/**
 * Add an existing participant from the dropdown to the meeting form.
 */
function addExistingParticipant() {
    const select = document.getElementById('existing-participant-select');
    if (!select || !select.value) return;

    const opt = select.options[select.selectedIndex];
    const id = opt.value;
    const firstName = opt.dataset.first;
    const lastName = opt.dataset.last;
    const phone = opt.dataset.phone;

    // Prevent duplicates
    const container = document.getElementById('participants-container');
    const existingIds = container.querySelectorAll('input[name="p_existing_id"]');
    for (const input of existingIds) {
        if (input.value === id) {
            select.value = '';
            return;
        }
    }

    const row = document.createElement('div');
    row.className = 'participant-row';
    row.innerHTML = `
        <button type="button" class="remove-participant" onclick="removeParticipantRow(this)">&times;</button>
        <input type="hidden" name="p_existing_id" value="${id}">
        <div class="grid">
            <label>
                First Name
                <input type="text" name="p_first_name" value="${firstName}" readonly>
            </label>
            <label>
                Last Name
                <input type="text" name="p_last_name" value="${lastName}" readonly>
            </label>
            <label>
                Phone
                <input type="tel" name="p_phone" value="${phone}" readonly>
            </label>
            <label>
                Priority
                <select name="p_priority">
                    <option value="1">1 - Critical</option>
                    <option value="2">2 - High</option>
                    <option value="3" selected>3 - Normal</option>
                    <option value="4">4 - Low</option>
                    <option value="5">5 - Optional</option>
                </select>
            </label>
        </div>
    `;
    container.appendChild(row);
    select.value = '';
}

/**
 * Remove a participant row from the create meeting form.
 */
function removeParticipantRow(button) {
    const row = button.closest('.participant-row');
    if (row) row.remove();
}

/* ============================================
   SSE Client
   ============================================ */

let sseSource = null;

/**
 * Connect to SSE endpoint for a meeting.
 */
function connectSSE(meetingId, basePath) {
    if (sseSource) sseSource.close();

    const statusEl = document.getElementById('sse-status');
    if (statusEl) {
        statusEl.textContent = 'connecting...';
        statusEl.className = 'badge';
    }

    basePath = basePath || '';
    sseSource = new EventSource(`${basePath}/sse/meetings/${meetingId}`);

    sseSource.onopen = function() {
        if (statusEl) {
            statusEl.textContent = 'connected';
            statusEl.className = 'badge badge-collecting';
        }
        appendToEventLog('connection', { message: 'SSE connected' });
    };

    sseSource.addEventListener('state_changed', function(e) {
        const data = JSON.parse(e.data);
        appendToEventLog('state_changed', data);
        htmx.trigger(document.body, 'refresh');
    });

    sseSource.addEventListener('outreach_updated', function(e) {
        const data = JSON.parse(e.data);
        appendToEventLog('outreach_updated', data);
        htmx.trigger(document.body, 'refresh');
    });

    sseSource.addEventListener('slot_selected', function(e) {
        const data = JSON.parse(e.data);
        appendToEventLog('slot_selected', data);
        htmx.trigger(document.body, 'refresh');
    });

    sseSource.addEventListener('participant_updated', function(e) {
        const data = JSON.parse(e.data);
        appendToEventLog('participant_updated', data);
        htmx.trigger(document.body, 'refresh');
    });

    sseSource.addEventListener('meeting_completed', function(e) {
        const data = JSON.parse(e.data);
        appendToEventLog('meeting_completed', data);
        htmx.trigger(document.body, 'refresh');
        if (sseSource) {
            sseSource.close();
            if (statusEl) statusEl.textContent = 'closed';
        }
    });

    sseSource.onerror = function() {
        if (statusEl) {
            statusEl.textContent = 'reconnecting...';
            statusEl.className = 'badge badge-failed';
        }
        appendToEventLog('connection', { message: 'SSE connection lost, reconnecting...' });
    };
}

/**
 * Append an event to the event log panel.
 */
function appendToEventLog(type, data) {
    const log = document.getElementById('event-log');
    if (!log) return;

    const entry = document.createElement('div');
    entry.className = `event-entry event-${type}`;

    const time = new Date().toLocaleTimeString();
    const dataStr = data.message || JSON.stringify(data.data || data);

    entry.innerHTML = `<span class="event-time">${time}</span>` +
                      `<span class="event-type badge">${type}</span>` +
                      `<span class="event-data">${dataStr}</span>`;
    log.prepend(entry);
}

window.addEventListener('beforeunload', function() {
    if (sseSource) sseSource.close();
});

/* ============================================
   Channel Priority Selector
   ============================================ */

const ALL_CHANNELS = [
    { id: 'whatsapp', label: 'WhatsApp', enabled: true },
    { id: 'sms', label: 'SMS', enabled: false },
    { id: 'voice', label: 'Voice', enabled: false },
];

function initChannelList() {
    const container = document.getElementById('channel-list');
    if (!container) return;

    const currentJson = container.dataset.current || '[]';
    let current = [];
    try { current = JSON.parse(currentJson); } catch (e) { current = []; }
    if (!current.length) current = ['whatsapp'];

    const ordered = [];
    for (const ch of current) {
        const def = ALL_CHANNELS.find(c => c.id === ch);
        if (def) ordered.push({ ...def, checked: true });
    }
    for (const def of ALL_CHANNELS) {
        if (!ordered.find(c => c.id === def.id)) {
            ordered.push({ ...def, checked: false });
        }
    }

    container.innerHTML = '';
    for (const ch of ordered) {
        const div = document.createElement('div');
        div.className = 'channel-item';
        div.dataset.channel = ch.id;
        const disabledAttr = ch.enabled ? '' : 'disabled';
        const checkedAttr = (ch.checked && ch.enabled) ? 'checked' : '';
        const soonTag = ch.enabled ? '' : ' <small>(coming soon)</small>';
        div.innerHTML = `
            <span class="drag-handle" draggable="true">&#x2630;</span>
            <label style="margin-bottom:0;display:flex;align-items:center;gap:0.4rem;cursor:pointer;">
                <input type="checkbox" value="${ch.id}" ${checkedAttr} ${disabledAttr}
                       onchange="updateChannelJson()">
                ${ch.label}${soonTag}
            </label>
        `;
        container.appendChild(div);
    }

    setupChannelDragDrop(container);
    updateChannelJson();
}

function updateChannelJson() {
    const container = document.getElementById('channel-list');
    const hidden = document.getElementById('communication-modes-json');
    if (!container || !hidden) return;

    const modes = [];
    container.querySelectorAll('.channel-item').forEach(item => {
        const cb = item.querySelector('input[type="checkbox"]');
        if (cb && cb.checked) modes.push(cb.value);
    });
    hidden.value = JSON.stringify(modes);
}

function setupChannelDragDrop(container) {
    let dragItem = null;

    container.addEventListener('dragstart', e => {
        if (!e.target.classList.contains('drag-handle')) {
            e.preventDefault();
            return;
        }
        dragItem = e.target.closest('.channel-item');
        if (dragItem) {
            dragItem.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
        }
    });

    container.addEventListener('dragend', e => {
        if (dragItem) {
            dragItem.classList.remove('dragging');
            dragItem = null;
            updateChannelJson();
        }
    });

    container.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        const target = e.target.closest('.channel-item');
        if (target && target !== dragItem) {
            const rect = target.getBoundingClientRect();
            const midY = rect.top + rect.height / 2;
            if (e.clientY < midY) {
                container.insertBefore(dragItem, target);
            } else {
                container.insertBefore(dragItem, target.nextSibling);
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', initChannelList);
