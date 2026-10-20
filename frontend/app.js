/**
 * Gerta AI — Autonomous Healthcare Voice Platform Application Logic
 * Powers the Admin Command Center, Patient Registry, and Voice Agent Console.
 */

const API_BASE = '';

// Application State
let state = {
  patients: [],
  selectedPatient: null,
  activeView: 'view-dashboard',
  filterStatus: 'active',
  searchQuery: '',
  callActive: false,
  callTimerInterval: null,
  callSeconds: 0,
  token: localStorage.getItem('gerta_auth_token') || null,
  user: JSON.parse(localStorage.getItem('gerta_auth_user') || 'null'),
  sessions: [],
  selectedSession: null,
};

// View Titles Mapping
const VIEW_TITLES = {
  'view-dashboard': 'Clinical Command Center',
  'view-patients': 'Patient Demographics Registry',
  'view-simulator': 'Voice Agent Console (Sarah)',
  'view-sessions': 'Call Transcripts & Telemetry Logs',
  'view-future-overview': 'Enterprise Roadmap Overview',
  'view-future-ehr': 'EHR & HL7 FHIR Bridge (Phase 2)',
  'view-future-scheduling': 'Clinic Slot Scheduling Simulator (Phase 2)',
  'view-future-insurance': 'Real-Time Insurance Eligibility X12 270/271 (Phase 3)',
  'view-future-multilingual': 'Multilingual Voice Routing Console (Phase 3)',
  'view-future-security': 'HIPAA KMS & Envelope Encryption Sandbox (Phase 4)',
};

// DOM References
const elements = {
  // Topbar
  topbarTitle: document.getElementById('topbar-dynamic-title'),
  btnTopbarSimulator: document.getElementById('btn-topbar-simulator'),
  btnTopbarAddPatient: document.getElementById('btn-topbar-add-patient'),
  toastBox: document.getElementById('gerta-toast-box'),

  // Stats
  statPatients: document.getElementById('stat-val-patients'),
  statSessions: document.getElementById('stat-val-sessions'),
  navPatientBadge: document.getElementById('nav-patient-badge'),
  btnDashboardRefresh: document.getElementById('btn-dashboard-refresh'),
  dashboardRecentTbody: document.getElementById('dashboard-recent-tbody'),

  // Patient Registry
  patientsTbody: document.getElementById('gerta-patients-tbody'),
  searchInput: document.getElementById('gerta-search-input'),
  btnSearchClear: document.getElementById('btn-gerta-search-clear'),
  statusFilter: document.getElementById('gerta-status-filter'),
  btnSyncPatients: document.getElementById('btn-sync-patients'),
  patientCountTxt: document.getElementById('gerta-patient-count-txt'),

  // Modals
  modalDetails: document.getElementById('gerta-modal-details'),
  detailsTitle: document.getElementById('details-gerta-title'),
  detailsId: document.getElementById('details-gerta-id'),
  detailsBody: document.getElementById('details-gerta-body'),
  btnCloseDetails: document.getElementById('btn-close-gerta-details'),
  btnEditPatient: document.getElementById('btn-gerta-edit-patient'),
  btnDeletePatient: document.getElementById('btn-gerta-delete-patient'),

  modalForm: document.getElementById('gerta-modal-form'),
  formTitle: document.getElementById('gerta-form-title'),
  form: document.getElementById('gerta-patient-form'),
  btnCloseForm: document.getElementById('btn-close-gerta-form'),
  btnCancelForm: document.getElementById('btn-cancel-gerta-form'),

  // Simulator
  callerNumInput: document.getElementById('gerta-caller-num-input'),
  btnDial: document.getElementById('btn-gerta-dial'),
  btnHangup: document.getElementById('btn-gerta-hangup'),
  simTimer: document.getElementById('gerta-sim-timer'),
  callPill: document.getElementById('gerta-call-pill'),
  avatarRing: document.getElementById('gerta-avatar-ring'),
  chatStreamBody: document.getElementById('gerta-chat-stream-body'),
  chatInputRow: document.getElementById('gerta-chat-input-row'),
  simUserText: document.getElementById('gerta-sim-user-text'),
  btnSimSend: document.getElementById('btn-gerta-sim-send'),
  btnClearChat: document.getElementById('btn-gerta-clear-chat'),

  // Presets
  preset1: document.getElementById('gerta-preset-1'),
  preset2: document.getElementById('gerta-preset-2'),
  preset3: document.getElementById('gerta-preset-3'),
  preset4: document.getElementById('gerta-preset-4'),

  // Sessions & Telemetry
  sessionsTbody: document.getElementById('gerta-sessions-tbody'),
  btnSyncSessions: document.getElementById('btn-sync-sessions'),

  // Authentication Elements
  authGate: document.getElementById('gerta-auth-gate'),
  loginForm: document.getElementById('gerta-login-form'),
  authUsername: document.getElementById('auth-input-username'),
  authPassword: document.getElementById('auth-input-password'),
  btnTogglePwd: document.getElementById('btn-toggle-pwd'),
  pwdIconShow: document.getElementById('pwd-icon-show'),
  btnAutofillDemo: document.getElementById('btn-autofill-demo'),
  btnAuthSubmit: document.getElementById('btn-auth-submit'),
  authSubmitTxt: document.getElementById('auth-submit-txt'),
  authErrorAlert: document.getElementById('auth-error-alert'),
  authErrorText: document.getElementById('auth-error-text'),
  topbarUserEmail: document.getElementById('topbar-user-email'),
  btnLogout: document.getElementById('btn-gerta-logout'),

  // Transcript Audit Modal
  modalTranscript: document.getElementById('gerta-modal-transcript'),
  btnCloseTranscript: document.getElementById('btn-close-gerta-transcript'),
  btnDismissTranscript: document.getElementById('btn-dismiss-transcript'),
  btnCopyTranscript: document.getElementById('btn-copy-transcript'),
  transMetaId: document.getElementById('trans-meta-id'),
  transMetaPhone: document.getElementById('trans-meta-phone'),
  transMetaStatus: document.getElementById('trans-meta-status'),
  transMetaTime: document.getElementById('trans-meta-time'),
  transDialogueBody: document.getElementById('transcript-dialogue-body'),
};

// ---------------------------------------------------------------------------
// Toast Notification Engine
// ---------------------------------------------------------------------------
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast-item ${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  elements.toastBox.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

// ---------------------------------------------------------------------------
// API Gateway (Enforces { data, error } Envelope + Auth Bearer Token)
// ---------------------------------------------------------------------------
async function apiRequest(endpoint, options = {}) {
  try {
    const headers = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...(options.headers || {}),
    };
    if (state.token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${state.token}`;
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    const json = await res.json();
    if (!res.ok || json.error) {
      const errMsg = json.error ? json.error.message : `HTTP ${res.status}`;
      throw new Error(errMsg);
    }
    return json.data;
  } catch (err) {
    console.error(`Gerta AI API Error [${endpoint}]:`, err);
    throw err;
  }
}

// ---------------------------------------------------------------------------
// View Navigation Routing
// ---------------------------------------------------------------------------
window.switchGertaView = function (viewId) {
  // Update sidebar active class
  document.querySelectorAll('.app-sidebar .nav-item').forEach((item) => {
    item.classList.toggle('active', item.getAttribute('data-view') === viewId);
  });

  // Activate view section
  document.querySelectorAll('.view-section').forEach((sec) => {
    sec.classList.toggle('active', sec.id === viewId);
  });

  state.activeView = viewId;
  elements.topbarTitle.textContent = VIEW_TITLES[viewId] || 'Command Center';
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

// ---------------------------------------------------------------------------
// Patients Data Fetching & Table Rendering
// ---------------------------------------------------------------------------
async function loadPatients() {
  try {
    elements.patientsTbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <p>Loading patient directory from database...</p>
        </td>
      </tr>
    `;

    const params = new URLSearchParams();
    if (state.searchQuery) {
      const cleanDigits = state.searchQuery.replace(/\D/g, '');
      if (cleanDigits.length >= 4) {
        params.append('phone_number', state.searchQuery);
      } else {
        params.append('last_name', state.searchQuery);
      }
    }

    const data = await apiRequest(`/patients?${params.toString()}`);
    state.patients = data || [];

    renderRegistryTable();
    renderRecentTable();
    updateDashboardMetrics();
  } catch (err) {
    elements.patientsTbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <p style="color: var(--rose-accent);">Failed to load patient records: ${err.message}</p>
        </td>
      </tr>
    `;
    showToast(`Failed to load patients: ${err.message}`, 'error');
  }
}

function renderRegistryTable() {
  let list = [...state.patients];

  // Status Filter
  if (state.filterStatus === 'active') {
    list = list.filter((p) => !p.deleted_at);
  } else if (state.filterStatus === 'deleted') {
    list = list.filter((p) => !!p.deleted_at);
  }

  // Refine Search Query
  if (state.searchQuery) {
    const q = state.searchQuery.toLowerCase();
    list = list.filter(
      (p) =>
        p.first_name.toLowerCase().includes(q) ||
        p.last_name.toLowerCase().includes(q) ||
        p.phone_number.includes(q) ||
        (p.city && p.city.toLowerCase().includes(q)) ||
        (p.state && p.state.toLowerCase().includes(q))
    );
  }

  elements.patientCountTxt.textContent = `Showing ${list.length} ${
    list.length === 1 ? 'patient' : 'patients'
  }`;

  if (list.length === 0) {
    elements.patientsTbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <p>No matching patient records found.</p>
        </td>
      </tr>
    `;
    return;
  }

  elements.patientsTbody.innerHTML = list
    .map((p) => {
      const isDeleted = !!p.deleted_at;
      const statusBadge = isDeleted
        ? '<span class="badge-tag deleted">Soft-Deleted</span>'
        : '<span class="badge-tag active">Active</span>';

      const insurance = p.insurance_provider
        ? `${escapeHtml(p.insurance_provider)}`
        : '<span style="color:var(--text-muted);">Self-Pay</span>';

      return `
      <tr data-id="${p.id}">
        <td>
          <div class="patient-primary-cell">
            <span class="patient-name-bold">${escapeHtml(p.first_name)} ${escapeHtml(p.last_name)}</span>
            <span class="patient-email-sub">${p.email ? escapeHtml(p.email) : 'No email'}</span>
          </div>
        </td>
        <td>${p.date_of_birth}</td>
        <td><span class="badge-tag sex">${escapeHtml(p.sex)}</span></td>
        <td>${formatPhone(p.phone_number)}</td>
        <td>${escapeHtml(p.city || '')}, ${escapeHtml(p.state || '')} ${escapeHtml(p.zip_code || '')}</td>
        <td>${insurance}</td>
        <td>${statusBadge}</td>
        <td class="text-right">
          <div class="table-row-actions">
            <button class="btn-icon-action" title="View Profile" onclick="openPatientDetails('${p.id}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
            <button class="btn-icon-action" title="Edit" onclick="openEditPatient('${p.id}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </button>
            ${
              !isDeleted
                ? `<button class="btn-icon-action danger" title="Soft-Delete" onclick="deletePatient('${p.id}')">
                     <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                       <polyline points="3 6 5 6 21 6"/>
                       <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                     </svg>
                   </button>`
                : ''
            }
          </div>
        </td>
      </tr>
    `;
    })
    .join('');
}

function renderRecentTable() {
  const activeList = state.patients.filter((p) => !p.deleted_at).slice(0, 5);
  if (activeList.length === 0) {
    elements.dashboardRecentTbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state"><p>No patient records registered yet.</p></td>
      </tr>
    `;
    return;
  }

  elements.dashboardRecentTbody.innerHTML = activeList
    .map(
      (p) => `
    <tr>
      <td><span class="patient-name-bold">${escapeHtml(p.first_name)} ${escapeHtml(p.last_name)}</span></td>
      <td>${p.date_of_birth}</td>
      <td><span class="badge-tag sex">${escapeHtml(p.sex)}</span></td>
      <td>${formatPhone(p.phone_number)}</td>
      <td>${escapeHtml(p.city || '')}, ${escapeHtml(p.state || '')}</td>
      <td><span class="badge-tag active">Active</span></td>
    </tr>
  `
    )
    .join('');
}

function updateDashboardMetrics() {
  const activeCount = state.patients.filter((p) => !p.deleted_at).length;
  elements.statPatients.textContent = activeCount;
  elements.navPatientBadge.textContent = activeCount;
}

// ---------------------------------------------------------------------------
// Patient Profile Drawer Modal
// ---------------------------------------------------------------------------
window.openPatientDetails = function (patientId) {
  const p = state.patients.find((item) => item.id === patientId);
  if (!p) return;

  state.selectedPatient = p;
  elements.detailsTitle.textContent = `${p.first_name} ${p.last_name}`;
  elements.detailsId.textContent = `UUID: ${p.id}`;

  const isDeleted = !!p.deleted_at;

  elements.detailsBody.innerHTML = `
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 1.25rem;">
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Date of Birth</div>
        <div style="font-size:0.95rem; font-weight:600; color:#fff; margin-top:0.2rem;">${p.date_of_birth}</div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Sex / Gender</div>
        <div style="font-size:0.95rem; font-weight:600; color:#fff; margin-top:0.2rem;">${escapeHtml(p.sex)}</div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Phone Number</div>
        <div style="font-size:0.95rem; font-weight:600; color:var(--cyan-primary); margin-top:0.2rem;">${formatPhone(p.phone_number)}</div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Email Address</div>
        <div style="font-size:0.95rem; font-weight:500; color:#fff; margin-top:0.2rem;">${p.email ? escapeHtml(p.email) : 'None provided'}</div>
      </div>
      <div style="grid-column: 1 / -1;">
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Mailing Address</div>
        <div style="font-size:0.95rem; font-weight:500; color:#fff; margin-top:0.2rem;">
          ${escapeHtml(p.address_line_1)} ${p.address_line_2 ? escapeHtml(p.address_line_2) : ''}<br>
          ${escapeHtml(p.city)}, ${escapeHtml(p.state)} ${escapeHtml(p.zip_code)}
        </div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Insurance Carrier</div>
        <div style="font-size:0.92rem; font-weight:500; color:#fff; margin-top:0.2rem;">${p.insurance_provider ? escapeHtml(p.insurance_provider) : 'None (Self-Pay)'}</div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Subscriber Member ID</div>
        <div style="font-size:0.92rem; font-weight:500; color:#fff; margin-top:0.2rem;">${p.insurance_member_id ? escapeHtml(p.insurance_member_id) : 'N/A'}</div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Emergency Contact</div>
        <div style="font-size:0.92rem; font-weight:500; color:#fff; margin-top:0.2rem;">${p.emergency_contact_name ? escapeHtml(p.emergency_contact_name) : 'None'}</div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Emergency Phone</div>
        <div style="font-size:0.92rem; font-weight:500; color:#fff; margin-top:0.2rem;">${p.emergency_contact_phone ? formatPhone(p.emergency_contact_phone) : 'N/A'}</div>
      </div>
      <div>
        <div style="font-size:0.72rem; text-transform:uppercase; color:var(--text-muted); font-weight:700;">Clinical Record Status</div>
        <div style="font-size:0.92rem; margin-top:0.2rem;">
          ${isDeleted ? '<span class="badge-tag deleted">Soft-Deleted</span>' : '<span class="badge-tag active">Active Patient</span>'}
        </div>
      </div>
    </div>
  `;

  elements.btnDeletePatient.style.display = isDeleted ? 'none' : 'inline-flex';
  elements.modalDetails.classList.remove('hidden');
};

function closePatientDetails() {
  elements.modalDetails.classList.add('hidden');
  state.selectedPatient = null;
}

// ---------------------------------------------------------------------------
// Add / Edit Patient Modal
// ---------------------------------------------------------------------------
window.openNewPatientModal = function () {
  document.getElementById('form-patient-id-input').value = '';
  elements.form.reset();
  elements.formTitle.textContent = 'Register New Patient';
  clearFormErrors();
  elements.modalForm.classList.remove('hidden');
};

window.openEditPatient = function (patientId) {
  const p = state.patients.find((item) => item.id === patientId);
  if (!p) return;

  closePatientDetails();
  clearFormErrors();
  elements.formTitle.textContent = 'Edit Patient Demographics';

  document.getElementById('form-patient-id-input').value = p.id;
  document.getElementById('form-in-first-name').value = p.first_name;
  document.getElementById('form-in-last-name').value = p.last_name;
  document.getElementById('form-in-dob').value = p.date_of_birth;
  document.getElementById('form-in-sex').value = p.sex;
  document.getElementById('form-in-phone').value = p.phone_number;
  document.getElementById('form-in-email').value = p.email || '';
  document.getElementById('form-in-address1').value = p.address_line_1;
  document.getElementById('form-in-address2').value = p.address_line_2 || '';
  document.getElementById('form-in-city').value = p.city;
  document.getElementById('form-in-state').value = p.state;
  document.getElementById('form-in-zip').value = p.zip_code;
  document.getElementById('form-in-insurance-provider').value = p.insurance_provider || '';
  document.getElementById('form-in-insurance-id').value = p.insurance_member_id || '';
  document.getElementById('form-in-emergency-name').value = p.emergency_contact_name || '';
  document.getElementById('form-in-emergency-phone').value = p.emergency_contact_phone || '';

  elements.modalForm.classList.remove('hidden');
};

function closePatientForm() {
  elements.modalForm.classList.add('hidden');
  clearFormErrors();
}

function clearFormErrors() {
  document.querySelectorAll('.input-field-error').forEach((el) => (el.textContent = ''));
}

async function handlePatientFormSubmit(e) {
  e.preventDefault();
  clearFormErrors();

  const patientId = document.getElementById('form-patient-id-input').value;
  const isEdit = !!patientId;

  const payload = {
    first_name: document.getElementById('form-in-first-name').value.trim(),
    last_name: document.getElementById('form-in-last-name').value.trim(),
    date_of_birth: document.getElementById('form-in-dob').value,
    sex: document.getElementById('form-in-sex').value,
    phone_number: document.getElementById('form-in-phone').value.trim(),
    email: document.getElementById('form-in-email').value.trim() || null,
    address_line_1: document.getElementById('form-in-address1').value.trim(),
    address_line_2: document.getElementById('form-in-address2').value.trim() || null,
    city: document.getElementById('form-in-city').value.trim(),
    state: document.getElementById('form-in-state').value.trim().toUpperCase(),
    zip_code: document.getElementById('form-in-zip').value.trim(),
    insurance_provider: document.getElementById('form-in-insurance-provider').value.trim() || null,
    insurance_member_id: document.getElementById('form-in-insurance-id').value.trim() || null,
    emergency_contact_name: document.getElementById('form-in-emergency-name').value.trim() || null,
    emergency_contact_phone: document.getElementById('form-in-emergency-phone').value.trim() || null,
  };

  try {
    if (isEdit) {
      await apiRequest(`/patients/${patientId}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast('Patient record updated successfully!', 'success');
    } else {
      await apiRequest('/patients', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast('Patient registered successfully!', 'success');
    }

    closePatientForm();
    await loadPatients();
  } catch (err) {
    showToast(`Validation Rejected: ${err.message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Soft-Delete Record Action
// ---------------------------------------------------------------------------
window.deletePatient = async function (patientId) {
  const p = state.patients.find((item) => item.id === patientId);
  const name = p ? `${p.first_name} ${p.last_name}` : 'this patient';

  if (!confirm(`Are you sure you want to soft-delete the record for ${name}?`)) {
    return;
  }

  try {
    await apiRequest(`/patients/${patientId}`, { method: 'DELETE' });
    showToast(`Patient ${name} soft-deleted.`, 'success');
    closePatientDetails();
    await loadPatients();
  } catch (err) {
    showToast(`Delete Error: ${err.message}`, 'error');
  }
};

// ---------------------------------------------------------------------------
// Voice Agent Console & Call Simulator
// ---------------------------------------------------------------------------
function appendTranscriptMsg(speaker, text, type = 'agent', toolMeta = null) {
  const empty = elements.chatStreamBody.querySelector('.empty-state, [style*="text-align: center"]');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = `transcript-msg ${type}`;

  let toolHtml = '';
  if (toolMeta) {
    toolHtml = `
      <div class="tool-badge-pill">
        <span>⚡ Tool: ${toolMeta.name}</span>
        <span>(${toolMeta.summary})</span>
      </div>
    `;
  }

  div.innerHTML = `
    <span class="speaker-label">${speaker}</span>
    <div class="bubble">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
    ${toolHtml}
  `;

  elements.chatStreamBody.appendChild(div);
  elements.chatStreamBody.scrollTop = elements.chatStreamBody.scrollHeight;
}

function setAvatarPulse(active) {
  elements.avatarRing.classList.toggle('speaking', active);
}

async function startGertaCall() {
  const phone = elements.callerNumInput.value.trim() || '5125550188';

  state.callActive = true;
  state.callSeconds = 0;
  elements.btnDial.classList.add('hidden');
  elements.btnHangup.classList.remove('hidden');
  elements.simTimer.classList.remove('hidden');
  elements.callPill.textContent = 'Call Connected';
  elements.callPill.style.background = 'rgba(16, 185, 129, 0.2)';
  elements.callPill.style.color = '#34d399';
  elements.chatInputRow.classList.remove('hidden');

  // Timer
  state.callTimerInterval = setInterval(() => {
    state.callSeconds++;
    const m = String(Math.floor(state.callSeconds / 60)).padStart(2, '0');
    const s = String(state.callSeconds % 60).padStart(2, '0');
    elements.simTimer.textContent = `${m}:${s}`;
  }, 1000);

  // 1. Assistant Request
  setAvatarPulse(true);
  try {
    const res = await fetch('/api/voice/webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: {
          type: 'assistant-request',
          call: { id: `sim-${Date.now()}`, customer: { number: phone } },
        },
      }),
    });
    const data = await res.json();
    const firstMsg =
      data?.assistant?.firstMessage ||
      'Hello! Thank you for calling Metro Health Clinic. My name is Sarah.';

    appendTranscriptMsg('Sarah (Agent)', firstMsg, 'agent');

    // 2. Caller ID Lookup
    const lookupRes = await fetch('/api/voice/webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: {
          type: 'function-call',
          functionCall: {
            name: 'lookup_patient',
            parameters: { phone_number: phone },
          },
        },
      }),
    });
    const lookupJson = await lookupRes.json();
    const lookupObj = JSON.parse(lookupJson.results[0].result);

    if (lookupObj.found) {
      appendTranscriptMsg(
        'System Telemetry',
        `Caller ID matched existing patient: ${lookupObj.patient.first_name} ${lookupObj.patient.last_name}`,
        'system',
        { name: 'lookup_patient', summary: 'MATCH FOUND' }
      );
      appendTranscriptMsg(
        'Sarah (Agent)',
        `Welcome back, ${lookupObj.patient.first_name}! I see we already have your information on file. Would you like to update anything today?`,
        'agent'
      );
    } else {
      appendTranscriptMsg(
        'System Telemetry',
        'No prior patient record found for this caller ID. Beginning new intake protocol.',
        'system',
        { name: 'lookup_patient', summary: 'NEW INTAKE' }
      );
    }
  } catch (err) {
    appendTranscriptMsg('System Error', `Webhook connection error: ${err.message}`, 'system');
  } finally {
    setAvatarPulse(false);
  }
}

async function endGertaCall() {
  state.callActive = false;
  clearInterval(state.callTimerInterval);
  elements.btnDial.classList.remove('hidden');
  elements.btnHangup.classList.add('hidden');
  elements.simTimer.classList.add('hidden');
  elements.callPill.textContent = 'Call Disconnected';
  elements.callPill.style.background = 'rgba(255,255,255,0.08)';
  elements.callPill.style.color = 'var(--text-secondary)';
  elements.chatInputRow.classList.add('hidden');
  setAvatarPulse(false);

  appendTranscriptMsg('Sarah (Agent)', 'Thank you for calling. Have a wonderful day!', 'agent');

  // Extract all turns from chatStreamBody into serialized conversation log
  const turns = [];
  elements.chatStreamBody.querySelectorAll('.transcript-msg').forEach((msg) => {
    const speaker = msg.querySelector('.speaker-label')?.textContent?.trim() || '';
    const bubble = msg.querySelector('.bubble')?.textContent?.trim() || '';
    if (speaker && bubble) {
      turns.push(`${speaker}: ${bubble}`);
    }
  });
  const serializedTranscript = turns.join('\n\n') || 'Simulated voice intake completed from Gerta AI console.';
  const phone = elements.callerNumInput.value.trim() || '5125550188';

  // Send end-of-call report with complete conversation transcript
  try {
    await fetch('/api/voice/webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: {
          type: 'end-of-call-report',
          call: { id: `sim-${Date.now()}`, customer: { number: phone } },
          transcript: serializedTranscript,
        },
      }),
    });
    showToast('Call session transcript logged to database.', 'info');
    await loadSessions();
  } catch (e) {
    console.error('Failed to log end-of-call session:', e);
  }
}

// ---------------------------------------------------------------------------
// 4 Automated Scenario Presets
// ---------------------------------------------------------------------------
async function runScenario1HappyPath() {
  elements.callerNumInput.value = '5125550188';
  elements.chatStreamBody.innerHTML = '';
  await startGertaCall();

  await sleep(750);
  appendTranscriptMsg('Caller', 'My name is Marcus Vance.', 'caller');

  await sleep(900);
  appendTranscriptMsg('Sarah (Agent)', 'Thank you, Marcus. And what is your date of birth?', 'agent');

  await sleep(750);
  appendTranscriptMsg('Caller', 'August 24th, 1988.', 'caller');

  await sleep(900);
  appendTranscriptMsg('Sarah (Agent)', 'Got it, August 24, 1988. For medical records, how should we record your sex?', 'agent');

  await sleep(750);
  appendTranscriptMsg('Caller', 'Male. And my address is 742 Evergreen Terrace, Austin TX 78704.', 'caller');

  await sleep(1100);
  appendTranscriptMsg(
    'Sarah (Agent)',
    'Let me read that back to make sure everything is exact:\n' +
      '  - Name: Marcus Vance\n' +
      '  - Date of Birth: August 24, 1988\n' +
      '  - Sex: Male\n' +
      '  - Phone: (512) 555-0188\n' +
      '  - Address: 742 Evergreen Terrace, Austin TX 78704\n' +
      'Does everything sound correct?',
    'agent'
  );

  await sleep(900);
  appendTranscriptMsg('Caller', "Yes, that's completely correct!", 'caller');

  await sleep(1000);
  const resp = await fetch('/api/voice/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        type: 'function-call',
        functionCall: {
          name: 'register_patient',
          parameters: {
            first_name: 'Marcus',
            last_name: 'Vance',
            date_of_birth: '1988-08-24',
            sex: 'Male',
            phone_number: '5125550188',
            address_line_1: '742 Evergreen Terrace',
            city: 'Austin',
            state: 'TX',
            zip_code: '78704',
          },
        },
      },
    }),
  });
  const resData = await resp.json();
  const resObj = JSON.parse(resData.results[0].result);

  appendTranscriptMsg(
    'System Telemetry',
    `Database transaction committed! Patient ID: ${resObj.patient_id}`,
    'system',
    { name: 'register_patient', summary: 'SUCCESS 201' }
  );

  appendTranscriptMsg(
    'Sarah (Agent)',
    `Wonderful! You are now registered with Metro Health Clinic, Marcus. Your patient ID is ${resObj.patient_id}. Have a wonderful day!`,
    'agent'
  );

  showToast('Scenario 1: Happy path intake completed successfully!', 'success');
  await loadPatients();
  await endGertaCall();
}

async function runScenario2FutureDob() {
  elements.callerNumInput.value = '5125557766';
  elements.chatStreamBody.innerHTML = '';
  await startGertaCall();

  await sleep(750);
  appendTranscriptMsg('Caller', 'My name is Jordan Miller, born January 1st, 2099.', 'caller');

  await sleep(900);
  // Rejection
  const badResp = await fetch('/api/voice/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        type: 'function-call',
        functionCall: {
          name: 'register_patient',
          parameters: {
            first_name: 'Jordan',
            last_name: 'Miller',
            date_of_birth: '2099-01-01',
            sex: 'Female',
            phone_number: '5125557766',
            address_line_1: '100 Congress Ave',
            city: 'Austin',
            state: 'TX',
            zip_code: '78701',
          },
        },
      },
    }),
  });
  const badData = await badResp.json();
  const badObj = JSON.parse(badData.results[0].result);

  appendTranscriptMsg(
    'System Gatekeeper',
    `Validation Rejected: ${badObj.validation_errors.join(', ')}`,
    'system',
    { name: 'register_patient', summary: 'REJECTED: FUTURE DOB' }
  );

  await sleep(900);
  appendTranscriptMsg(
    'Sarah (Agent)',
    "I'm sorry Jordan, but that birth date appears to be in the future. Could you please confirm the four-digit year you were born?",
    'agent'
  );

  await sleep(750);
  appendTranscriptMsg('Caller', 'Oh sorry about that! I meant 1999, not 2099.', 'caller');

  await sleep(1000);
  const goodResp = await fetch('/api/voice/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        type: 'function-call',
        functionCall: {
          name: 'register_patient',
          parameters: {
            first_name: 'Jordan',
            last_name: 'Miller',
            date_of_birth: '1999-01-01',
            sex: 'Female',
            phone_number: '5125557766',
            address_line_1: '100 Congress Ave',
            city: 'Austin',
            state: 'TX',
            zip_code: '78701',
          },
        },
      },
    }),
  });
  const goodData = await goodResp.json();
  const goodObj = JSON.parse(goodData.results[0].result);

  appendTranscriptMsg(
    'System Telemetry',
    `Validation passed! Patient record created: ${goodObj.patient_id}`,
    'system',
    { name: 'register_patient', summary: 'CORRECTED & COMMITTED' }
  );

  appendTranscriptMsg('Sarah (Agent)', "That worked perfectly! You're all registered.", 'agent');
  showToast('Scenario 2: Future DOB rejection resilience verified!', 'success');
  await loadPatients();
  await endGertaCall();
}

async function runScenario3Returning() {
  elements.callerNumInput.value = '5125550188';
  elements.chatStreamBody.innerHTML = '';
  await startGertaCall();

  await sleep(900);
  appendTranscriptMsg('Caller', 'Yes, I moved recently. My new address is 500 South Congress Ave, Apt 12B, Austin TX 78704.', 'caller');

  await sleep(1000);
  // Match patient id
  const targetPatient = state.patients.find((p) => p.phone_number.includes('5125550188'));
  const pId = targetPatient ? targetPatient.id : 'temp-id';

  const updateResp = await fetch('/api/voice/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        type: 'function-call',
        functionCall: {
          name: 'update_patient',
          parameters: {
            patient_id: pId,
            address_line_1: '500 South Congress Ave',
            address_line_2: 'Apt 12B',
            zip_code: '78704',
          },
        },
      },
    }),
  });
  const updData = await updateResp.json();
  const updObj = JSON.parse(updData.results[0].result);

  appendTranscriptMsg(
    'System Telemetry',
    `Database record updated: ${updObj.message}`,
    'system',
    { name: 'update_patient', summary: 'RECORD UPDATED' }
  );

  appendTranscriptMsg(
    'Sarah (Agent)',
    'I have updated your address to 500 South Congress Ave, Apartment 12B. Everything is up to date!',
    'agent'
  );

  showToast('Scenario 3: Returning caller update flow passed!', 'success');
  await loadPatients();
  await endGertaCall();
}

async function runScenario4Spelling() {
  elements.callerNumInput.value = '5125558833';
  elements.chatStreamBody.innerHTML = '';
  await startGertaCall();

  await sleep(750);
  appendTranscriptMsg('Caller', 'My name is John Davis.', 'caller');

  await sleep(900);
  appendTranscriptMsg('Sarah (Agent)', 'Could you spell your last name for me to ensure accurate records?', 'agent');

  await sleep(750);
  appendTranscriptMsg('Caller', "It's spelled D-A-V-I-S.", 'caller');

  await sleep(900);
  appendTranscriptMsg('Sarah (Agent)', 'Thank you, D-A-V-I-S. Got it!', 'agent');

  await sleep(750);
  appendTranscriptMsg('Caller', "Actually, I gave you my brother's spelling by mistake, mine is D-A-V-I-E-S.", 'caller');

  await sleep(900);
  appendTranscriptMsg('Sarah (Agent)', 'Understood, D-A-V-I-E-S, John Davies. Let me update that.', 'agent');

  await sleep(1000);
  const resp = await fetch('/api/voice/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: {
        type: 'function-call',
        functionCall: {
          name: 'register_patient',
          parameters: {
            first_name: 'John',
            last_name: 'Davies',
            date_of_birth: '1994-03-11',
            sex: 'Male',
            phone_number: '5125558833',
            address_line_1: '888 West 6th St',
            city: 'Austin',
            state: 'TX',
            zip_code: '78703',
          },
        },
      },
    }),
  });
  const data = await resp.json();
  const obj = JSON.parse(data.results[0].result);

  appendTranscriptMsg(
    'System Telemetry',
    `Patient registered as John Davies (ID: ${obj.patient_id})`,
    'system',
    { name: 'register_patient', summary: 'SPELLING CONFIRMED' }
  );

  showToast('Scenario 4: Spell-out correction verified!', 'success');
  await loadPatients();
  await endGertaCall();
}

// ---------------------------------------------------------------------------
// Telephony Call Sessions & Audit Logs
// ---------------------------------------------------------------------------
async function loadSessions() {
  if (!elements.sessionsTbody) return;
  try {
    elements.sessionsTbody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-state">
          <p>Loading telephony call records from database...</p>
        </td>
      </tr>
    `;

    const sessions = await apiRequest('/api/voice/sessions');
    state.sessions = sessions || [];

    if (elements.statSessions) {
      elements.statSessions.textContent = state.sessions.length;
    }

    if (!state.sessions.length) {
      elements.sessionsTbody.innerHTML = `
        <tr>
          <td colspan="5" class="empty-state">
            <p>No call sessions recorded yet. Start a call in the simulator or dial in via Vapi.</p>
          </td>
        </tr>
      `;
      return;
    }

    elements.sessionsTbody.innerHTML = state.sessions
      .map((s) => {
        const phone = formatPhone(s.caller_phone);
        const statusColor = s.status === 'completed' ? '#34d399' : s.status === 'in-progress' ? 'var(--amber-accent)' : '#f87171';
        const dateStr = s.created_at ? new Date(s.created_at).toLocaleString() : 'N/A';
        const preview = s.transcript ? escapeHtml(s.transcript.slice(0, 85)) + (s.transcript.length > 85 ? '...' : '') : 'No transcript text available';

        return `
          <tr>
            <td>
              <code style="color:var(--cyan-primary); font-size:0.75rem;">${escapeHtml(s.id.slice(0, 8))}...</code>
            </td>
            <td>
              <span style="font-weight:600; color:#ffffff;">${escapeHtml(phone)}</span>
            </td>
            <td>
              <span class="badge-status-pill" style="border-color:${statusColor}; color:${statusColor}; font-size:0.7rem; text-transform:uppercase;">
                ${escapeHtml(s.status)}
              </span>
            </td>
            <td style="color:var(--text-muted); font-size:0.8rem;">
              ${escapeHtml(dateStr)}
            </td>
            <td>
              <div style="display:flex; align-items:center; justify-content:space-between; gap:0.75rem;">
                <span style="color:var(--text-secondary); font-size:0.78rem; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                  ${preview}
                </span>
                <button class="btn-gerta ghost sm" onclick="openTranscriptModal('${s.id}')" style="padding:0.25rem 0.65rem; font-size:0.75rem; white-space:nowrap;">
                  View Transcript
                </button>
              </div>
            </td>
          </tr>
        `;
      })
      .join('');
  } catch (err) {
    console.error('Failed to load call sessions:', err);
    elements.sessionsTbody.innerHTML = `
      <tr>
        <td colspan="5" class="empty-state">
          <p style="color:var(--rose-accent);">Failed to load call records: ${escapeHtml(err.message)}</p>
        </td>
      </tr>
    `;
  }
}

window.openTranscriptModal = function (sessionId) {
  const session = state.sessions.find((s) => s.id === sessionId);
  if (!session) return;
  state.selectedSession = session;

  elements.transMetaId.textContent = session.id;
  elements.transMetaPhone.textContent = formatPhone(session.caller_phone);
  elements.transMetaStatus.textContent = (session.status || 'COMPLETED').toUpperCase();
  elements.transMetaTime.textContent = session.created_at ? new Date(session.created_at).toLocaleString() : 'N/A';

  // Render dialogue turns
  elements.transDialogueBody.innerHTML = '';
  if (!session.transcript) {
    elements.transDialogueBody.innerHTML = '<p class="empty-state" style="padding:2rem 0;">No transcript text available for this session.</p>';
  } else {
    let turns = [];
    try {
      const parsed = JSON.parse(session.transcript);
      if (Array.isArray(parsed)) turns = parsed;
    } catch (_) {
      const rawTurns = session.transcript.split(/\n\n+/);
      rawTurns.forEach((block) => {
        const trimmed = block.trim();
        if (!trimmed) return;
        if (trimmed.startsWith('Sarah (Agent):') || trimmed.startsWith('Sarah:')) {
          turns.push({ speaker: 'Sarah (Agent)', text: trimmed.replace(/^Sarah.*?:/i, '').trim(), type: 'agent' });
        } else if (trimmed.startsWith('Caller:')) {
          turns.push({ speaker: 'Caller', text: trimmed.replace(/^Caller:/i, '').trim(), type: 'caller' });
        } else if (trimmed.startsWith('System') || trimmed.startsWith('⚡ Tool:')) {
          turns.push({ speaker: 'System Telemetry', text: trimmed, type: 'system' });
        } else {
          turns.push({ speaker: 'Dialogue', text: trimmed, type: 'agent' });
        }
      });
    }

    if (!turns.length) {
      elements.transDialogueBody.innerHTML = `<div class="transcript-turn agent"><span class="turn-speaker">Recorded Audio Transcript</span><div class="turn-bubble">${escapeHtml(session.transcript)}</div></div>`;
    } else {
      elements.transDialogueBody.innerHTML = turns
        .map((t) => `
          <div class="transcript-turn ${t.type || (t.speaker?.includes('Sarah') ? 'agent' : t.speaker?.includes('Caller') ? 'caller' : 'system')}">
            <span class="turn-speaker">${escapeHtml(t.speaker || 'Voice Turn')}</span>
            <div class="turn-bubble">${escapeHtml(t.text || '').replace(/\n/g, '<br>')}</div>
          </div>
        `)
        .join('');
    }
  }

  elements.modalTranscript.classList.remove('hidden');
};

window.closeTranscriptModal = function () {
  elements.modalTranscript.classList.add('hidden');
};

// ---------------------------------------------------------------------------
// Authentication & HIPAA Access Control
// ---------------------------------------------------------------------------
function checkAuth() {
  if (state.token) {
    elements.authGate?.classList.add('hidden');
    if (elements.topbarUserEmail) {
      elements.topbarUserEmail.textContent = state.user?.email || 'admin@gerta.ai';
    }
  } else {
    elements.authGate?.classList.remove('hidden');
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function formatPhone(phone) {
  if (!phone) return 'N/A';
  const d = phone.replace(/\D/g, '');
  if (d.length === 10) return `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}`;
  if (d.length === 11 && d.startsWith('1')) return `+1 (${d.slice(1, 4)}) ${d.slice(4, 7)}-${d.slice(7)}`;
  return phone;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Event Listeners Initialization
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  checkAuth();
  loadPatients();
  loadSessions();

  // Authentication Events
  elements.loginForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = elements.authUsername.value.trim();
    const password = elements.authPassword.value.trim();
    elements.authSubmitTxt.textContent = 'Verifying credentials...';
    elements.btnAuthSubmit.disabled = true;
    elements.authErrorAlert.classList.add('hidden');

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error ? data.error.message : 'Authentication failed.');
      }

      state.token = data.data.token;
      state.user = data.data.user;
      localStorage.setItem('gerta_auth_token', state.token);
      localStorage.setItem('gerta_auth_user', JSON.stringify(state.user));

      checkAuth();
      showToast('Welcome, Administrator. HIPAA session active.', 'success');
      loadPatients();
      loadSessions();
    } catch (err) {
      elements.authErrorText.textContent = err.message || 'Invalid username or password.';
      elements.authErrorAlert.classList.remove('hidden');
    } finally {
      elements.authSubmitTxt.textContent = 'Authenticate & Enter Portal';
      elements.btnAuthSubmit.disabled = false;
    }
  });

  elements.btnLogout?.addEventListener('click', async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
    } catch (_) {}
    state.token = null;
    state.user = null;
    localStorage.removeItem('gerta_auth_token');
    localStorage.removeItem('gerta_auth_user');
    checkAuth();
    showToast('Signed out of clinical session.', 'info');
  });

  elements.btnAutofillDemo?.addEventListener('click', () => {
    elements.authUsername.value = 'admin@gerta.ai';
    elements.authPassword.value = 'admin123gertai';
    showToast('Standard administrator credentials populated.', 'info');
  });

  elements.btnTogglePwd?.addEventListener('click', () => {
    const isPwd = elements.authPassword.type === 'password';
    elements.authPassword.type = isPwd ? 'text' : 'password';
    elements.pwdIconShow.innerHTML = isPwd
      ? '<path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>'
      : '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>';
  });

  // Transcript Modal Events
  elements.btnCloseTranscript?.addEventListener('click', closeTranscriptModal);
  elements.btnDismissTranscript?.addEventListener('click', closeTranscriptModal);
  elements.btnSyncSessions?.addEventListener('click', () => {
    loadSessions();
    showToast('Telephony audit records refreshed.', 'info');
  });
  elements.btnCopyTranscript?.addEventListener('click', () => {
    if (state.selectedSession?.transcript) {
      navigator.clipboard.writeText(state.selectedSession.transcript);
      showToast('Transcript copied to clipboard.', 'success');
    }
  });

  // Sidebar navigation
  document.querySelectorAll('.app-sidebar .nav-item').forEach((item) => {
    item.addEventListener('click', () => {
      const targetView = item.getAttribute('data-view');
      switchGertaView(targetView);
    });
  });

  // Topbar quick triggers
  elements.btnTopbarSimulator.addEventListener('click', () => {
    switchGertaView('view-simulator');
  });

  elements.btnTopbarAddPatient.addEventListener('click', () => {
    openNewPatientModal();
  });

  // Search input debouncing
  let searchTimeout = null;
  elements.searchInput.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    state.searchQuery = val;
    elements.btnSearchClear.classList.toggle('hidden', !val);

    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      renderRegistryTable();
    }, 250);
  });

  elements.btnSearchClear.addEventListener('click', () => {
    elements.searchInput.value = '';
    state.searchQuery = '';
    elements.btnSearchClear.classList.add('hidden');
    renderRegistryTable();
  });

  // Status Filter Select
  elements.statusFilter.addEventListener('change', (e) => {
    state.filterStatus = e.target.value;
    renderRegistryTable();
  });

  // Refresh Buttons
  elements.btnSyncPatients.addEventListener('click', () => {
    loadPatients();
    showToast('Patient registry synchronized with database.', 'info');
  });

  elements.btnDashboardRefresh.addEventListener('click', () => {
    loadPatients();
    showToast('Command center telemetry updated.', 'info');
  });

  // Modals
  elements.btnCloseDetails.addEventListener('click', closePatientDetails);
  elements.btnCloseForm.addEventListener('click', closePatientForm);
  elements.btnCancelForm.addEventListener('click', closePatientForm);
  elements.form.addEventListener('submit', handlePatientFormSubmit);

  elements.btnEditPatient.addEventListener('click', () => {
    if (state.selectedPatient) openEditPatient(state.selectedPatient.id);
  });

  elements.btnDeletePatient.addEventListener('click', () => {
    if (state.selectedPatient) deletePatient(state.selectedPatient.id);
  });

  // Simulator Events
  elements.btnDial.addEventListener('click', startGertaCall);
  elements.btnHangup.addEventListener('click', endGertaCall);
  elements.btnClearChat.addEventListener('click', () => {
    elements.chatStreamBody.innerHTML = `
      <div style="margin: auto; text-align: center; color: var(--text-muted);">
        <h4 style="color:#ffffff; font-size:1.1rem; margin-bottom:0.25rem;">No Active Call</h4>
        <p style="font-size:0.84rem;">Click "Connect Inbound Call" or select a preset on the left to start.</p>
      </div>
    `;
  });

  elements.btnSimSend.addEventListener('click', () => {
    const text = elements.simUserText.value.trim();
    if (!text) return;
    appendTranscriptMsg('Caller', text, 'caller');
    elements.simUserText.value = '';
  });

  elements.simUserText.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') elements.btnSimSend.click();
  });

  // Automated Presets
  elements.preset1.addEventListener('click', runScenario1HappyPath);
  elements.preset2.addEventListener('click', runScenario2FutureDob);
  elements.preset3.addEventListener('click', runScenario3Returning);
  elements.preset4.addEventListener('click', runScenario4Spelling);

  // =========================================================================
  // ENTERPRISE ROADMAP & FUTURE WORK INTERACTIVE SANDBOXES
  // =========================================================================

  // 1. HL7 FHIR R4 Patient Resource Generator
  const btnDispatchFhir = document.getElementById('btn-dispatch-fhir');
  const btnCopyFhir = document.getElementById('btn-copy-fhir');
  const fhirSelectPatient = document.getElementById('fhir-select-patient');
  const fhirSelectEndpoint = document.getElementById('fhir-select-endpoint');
  const fhirJsonOutput = document.getElementById('fhir-json-output');
  const fhirStatusTxt = document.getElementById('fhir-status-txt');
  const fhirMrnTxt = document.getElementById('fhir-mrn-txt');
  const fhirLatencyTxt = document.getElementById('fhir-latency-txt');

  if (btnDispatchFhir) {
    btnDispatchFhir.addEventListener('click', () => {
      const pChoice = fhirSelectPatient ? fhirSelectPatient.value : 'current';
      const endpoint = fhirSelectEndpoint ? fhirSelectEndpoint.value : 'epic';

      let patientObj = {
        name: { family: 'Baig', given: ['Sheharyar'] },
        dob: '1998-05-14',
        gender: 'male',
        phone: '(512) 555-0188',
        address: { line: ['100 Congress Ave'], city: 'Austin', state: 'TX', zip: '78701' },
        id: '32f0e79a-67b0-45b7-b20f-059375f468ca'
      };

      if (pChoice === 'sample1') {
        patientObj = {
          name: { family: 'Vance', given: ['Marcus'] },
          dob: '1988-11-24',
          gender: 'male',
          phone: '(214) 555-0199',
          address: { line: ['742 Evergreen Terrace'], city: 'Dallas', state: 'TX', zip: '75201' },
          id: '1163c7da-7ae0-4f3e-ba53-3f882eb3323e'
        };
      } else if (pChoice === 'sample2') {
        patientObj = {
          name: { family: 'Rostova', given: ['Elena'] },
          dob: '1992-03-08',
          gender: 'female',
          phone: '(713) 555-0144',
          address: { line: ['500 Main St, Ste 400'], city: 'Houston', state: 'TX', zip: '77002' },
          id: '29c49458-80ad-4525-b67d-6cda2d97a287'
        };
      } else if (state.patients && state.patients.length > 0) {
        const topP = state.patients[0];
        patientObj = {
          name: { family: topP.last_name, given: [topP.first_name] },
          dob: topP.date_of_birth,
          gender: topP.sex.toLowerCase(),
          phone: topP.phone_number,
          address: { line: [topP.address_line_1], city: topP.city, state: topP.state, zip: topP.zip_code },
          id: topP.id
        };
      }

      const fhirPayload = {
        resourceType: 'Patient',
        id: `gerta-${patientObj.id.substring(0, 8)}`,
        meta: {
          versionId: '1',
          lastUpdated: new Date().toISOString(),
          profile: ['http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient']
        },
        text: {
          status: 'generated',
          div: `<div xmlns="http://www.w3.org/1999/xhtml">${patientObj.name.given.join(' ')} ${patientObj.name.family}, ${patientObj.gender}, DOB ${patientObj.dob}</div>`
        },
        identifier: [
          {
            use: 'official',
            system: 'urn:oid:2.16.840.1.113883.4.1',
            value: patientObj.id
          }
        ],
        active: true,
        name: [
          {
            use: 'official',
            family: patientObj.name.family,
            given: patientObj.name.given
          }
        ],
        telecom: [
          {
            system: 'phone',
            value: patientObj.phone,
            use: 'mobile'
          }
        ],
        gender: patientObj.gender === 'male' || patientObj.gender === 'female' ? patientObj.gender : 'other',
        birthDate: patientObj.dob,
        address: [
          {
            use: 'home',
            line: patientObj.address.line,
            city: patientObj.address.city,
            state: patientObj.address.state,
            postalCode: patientObj.address.zip,
            country: 'US'
          }
        ]
      };

      if (fhirJsonOutput) {
        fhirJsonOutput.textContent = JSON.stringify(fhirPayload, null, 2);
      }

      const latency = Math.floor(120 + Math.random() * 45);
      const mrn = `MRN-${endpoint.toUpperCase()}-${Math.floor(1000000 + Math.random() * 9000000)}`;

      if (fhirStatusTxt) fhirStatusTxt.textContent = `HTTP 201 CREATED (SYNCHRONIZED)`;
      if (fhirMrnTxt) fhirMrnTxt.textContent = mrn;
      if (fhirLatencyTxt) fhirLatencyTxt.textContent = `${latency} ms (mTLS handshake verified)`;

      showToast(`HL7 FHIR R4 Patient synchronized with ${endpoint.toUpperCase()} (MRN: ${mrn})`, 'success');
    });
  }

  if (btnCopyFhir && fhirJsonOutput) {
    btnCopyFhir.addEventListener('click', () => {
      navigator.clipboard.writeText(fhirJsonOutput.textContent).then(() => {
        showToast('FHIR R4 JSON copied to clipboard.', 'info');
      }).catch(() => {
        showToast('FHIR payload ready in viewer.', 'info');
      });
    });
  }

  // 2. Clinic Slot Scheduling Simulator
  const btnScheduleSlot = document.getElementById('btn-schedule-slot');
  const schedSelectDept = document.getElementById('sched-select-dept');
  const schedSelectDoctor = document.getElementById('sched-select-doctor');
  const schedSelectSlot = document.getElementById('sched-select-slot');
  const schedInPhone = document.getElementById('sched-in-phone');
  const schedDocName = document.getElementById('sched-doc-name');
  const schedVisitDetails = document.getElementById('sched-visit-details');
  const schedRefCode = document.getElementById('sched-ref-code');
  const schedSmsPreview = document.getElementById('sched-sms-preview');
  const schedSmsSid = document.getElementById('sched-sms-sid');

  if (btnScheduleSlot) {
    btnScheduleSlot.addEventListener('click', () => {
      const docText = schedSelectDoctor ? schedSelectDoctor.options[schedSelectDoctor.selectedIndex].text.split('(')[0].trim() : 'Dr. Sarah Chen, MD';
      const slotText = schedSelectSlot ? schedSelectSlot.options[schedSelectSlot.selectedIndex].text.split('(')[0].trim() : 'Tomorrow at 09:30 AM';
      const phone = schedInPhone ? schedInPhone.value : '(512) 555-0188';
      const ref = `METRO-CAD-${Math.floor(1000 + Math.random() * 9000)}`;
      const smsSid = `SM${Math.random().toString(36).substring(2, 10)}${Math.random().toString(36).substring(2, 10)}`;

      if (schedDocName) schedDocName.textContent = docText;
      if (schedVisitDetails) schedVisitDetails.textContent = `Confirmed for ${slotText} • Primary Clinic`;
      if (schedRefCode) schedRefCode.textContent = ref;

      if (schedSmsPreview) {
        schedSmsPreview.textContent = `"Metro Health: Your visit with ${docText} is confirmed for ${slotText}. Reply 1 to confirm, 2 to reschedule. Location: 100 Congress Ave, Suite 300, Austin TX."`;
      }
      if (schedSmsSid) {
        schedSmsSid.textContent = `SID: ${smsSid} • Target: ${phone} • Status: Delivered • Concurrency Lock: ACTIVE`;
      }

      showToast(`Appointment reserved with ${docText} (Code: ${ref})`, 'success');
    });
  }

  // 3. Real-Time Insurance Eligibility Verification (EDI X12 270/271)
  const btnVerifyInsurance = document.getElementById('btn-verify-insurance');
  const insSelectCarrier = document.getElementById('ins-select-carrier');
  const insInMemberId = document.getElementById('ins-in-member-id');
  const insInDob = document.getElementById('ins-in-dob');
  const insStatusBadge = document.getElementById('ins-status-badge');
  const insPlanName = document.getElementById('ins-plan-name');
  const insCopayPrimary = document.getElementById('ins-copay-primary');
  const insCopaySpecialist = document.getElementById('ins-copay-specialist');
  const insDeductibleMet = document.getElementById('ins-deductible-met');
  const insDeductibleRem = document.getElementById('ins-deductible-rem');
  const insEdiTrace = document.getElementById('ins-edi-trace');

  if (btnVerifyInsurance) {
    btnVerifyInsurance.addEventListener('click', () => {
      const carrier = insSelectCarrier ? insSelectCarrier.value : 'bcbs';
      const memId = insInMemberId ? insInMemberId.value || 'BCB-99482103' : 'BCB-99482103';
      const dob = insInDob ? insInDob.value || '1998-05-14' : '1998-05-14';

      const plans = {
        bcbs: { name: 'Blue Cross Blue Shield Preferred PPO Gold', primary: '$25.00', spec: '$45.00', met: '$1,150 / $1,500', rem: '$350.00', payerId: '00020' },
        uhc: { name: 'UnitedHealthcare Choice Plus Comprehensive', primary: '$20.00', spec: '$40.00', met: '$1,300 / $1,500', rem: '$200.00', payerId: '87726' },
        aetna: { name: 'Aetna Open Access Managed Care HMO', primary: '$30.00', spec: '$50.00', met: '$900 / $1,400', rem: '$500.00', payerId: '60054' },
        cigna: { name: 'Cigna Open Access Plus In-Network', primary: '$25.00', spec: '$45.00', met: '$1,200 / $1,600', rem: '$400.00', payerId: '62308' },
        medicare: { name: 'Medicare Part B Fee-for-Service (CMS)', primary: '$0.00 (80/20)', spec: '$0.00 (80/20)', met: '$240 / $240', rem: '$0.00', payerId: '00400' },
      };

      const sel = plans[carrier] || plans.bcbs;

      if (insStatusBadge) insStatusBadge.textContent = 'COVERAGE ACTIVE';
      if (insPlanName) insPlanName.textContent = sel.name;
      if (insCopayPrimary) insCopayPrimary.textContent = sel.primary;
      if (insCopaySpecialist) insCopaySpecialist.textContent = sel.spec;
      if (insDeductibleMet) insDeductibleMet.textContent = sel.met;
      if (insDeductibleRem) insDeductibleRem.textContent = sel.rem;

      if (insEdiTrace) {
        const cleanDob = dob.replace(/-/g, '');
        insEdiTrace.textContent = 
`ISA*00*          *00*          *ZZ*GERTA_AI       *ZZ*CLEARINGHOUSE  *261019*0200*^*00501*000000001*0*P*:~
GS*HS*GERTA_AI*CLEARINGHOUSE*20261019*0200*1*X*005010X279A1~
ST*270*0001*005010X279A1~
BHT*0022*13*10001*20261019*0200~
HL*1**20*1~
NM1*PR*2*${sel.name.substring(0, 24)}*****PI*${sel.payerId}~
HL*2*1*21*1~
NM1*1P*2*METRO HEALTH CLINIC*****XX*1920192810~
HL*3*2*22*0~
NM1*IL*1*BAIG*SHEHARYAR****MI*${memId}~
DMG*D8*${cleanDob}*M~
EQ*30~
SE*13*0001~
GE*1*1~
IEA*1*000000001~
--- [X12 271 RESPONSE SEGMENT] ---
EB*1**30*PR*${sel.name.substring(0, 20)}~
EB*B**98*PR**27*${sel.primary.replace('$', '').split(' ')[0]}~
EB*B**98*PR**27*${sel.spec.replace('$', '').split(' ')[0]}*SP~
EB*C**30*PR**29*${sel.rem.replace('$', '')}~`;
      }

      showToast(`Payer eligibility verified: Coverage ACTIVE (Copay: ${sel.primary})`, 'success');
    });
  }

  // 4. Multilingual Speech Synthesizer & Dialogue Simulator
  const btnPlayMultiAudio = document.getElementById('btn-play-multilingual-audio');
  const btnSimulateAgentReply = document.getElementById('btn-simulate-agent-reply');
  const multiSelectLang = document.getElementById('multi-select-lang');
  const multiSelectPhrase = document.getElementById('multi-select-phrase');
  const multiStreamText = document.getElementById('multi-stream-text');
  const multiLidConfidence = document.getElementById('multi-lid-confidence');
  const multiSchemaLang = document.getElementById('multi-schema-lang');
  const multiAgentVoice = document.getElementById('multi-agent-voice');

  const langPhrases = {
    es: [
      '"Hola, buenos días. Necesito registrarme como nuevo paciente en la clínica."',
      '"Mi fecha de nacimiento es el catorce de mayo de mil novecientos noventa y ocho."',
      '"Mi número de teléfono es el cinco uno dos, cinco cinco cinco, cero uno ocho ocho."'
    ],
    fr: [
      '"Bonjour, je voudrais m\'inscrire comme nouveau patient au centre médical."',
      '"Ma date de naissance est le quatorze mai mil neuf cent quatre-vingt-dix-huit."',
      '"Mon numéro de téléphone est le cinq un deux, cinq cinq cinq, zéro un huit huit."'
    ],
    en: [
      '"Hello, I would like to register as a new patient at the clinic."',
      '"My date of birth is May fourteenth, nineteen ninety-eight."',
      '"My phone number is five one two, five five five, zero one eight eight."'
    ]
  };

  if (multiSelectLang && multiSelectPhrase) {
    multiSelectLang.addEventListener('change', () => {
      const l = multiSelectLang.value;
      const phrases = langPhrases[l] || langPhrases.es;
      multiSelectPhrase.innerHTML = phrases.map((p, idx) => `<option value="p${idx}">${p}</option>`).join('');
      if (multiStreamText) multiStreamText.textContent = phrases[0];

      if (l === 'es') {
        if (multiSchemaLang) multiSchemaLang.textContent = '"Spanish"';
        if (multiAgentVoice) multiAgentVoice.textContent = '"Cartesia Sonic (es-US-Sofia)"';
        if (multiLidConfidence) multiLidConfidence.textContent = '99.4% (Spanish es-US)';
      } else if (l === 'fr') {
        if (multiSchemaLang) multiSchemaLang.textContent = '"French"';
        if (multiAgentVoice) multiAgentVoice.textContent = '"Cartesia Sonic (fr-FR-Claire)"';
        if (multiLidConfidence) multiLidConfidence.textContent = '98.9% (French fr-FR)';
      } else {
        if (multiSchemaLang) multiSchemaLang.textContent = '"English"';
        if (multiAgentVoice) multiAgentVoice.textContent = '"Cartesia Sonic (en-US-Sarah)"';
        if (multiLidConfidence) multiLidConfidence.textContent = '99.8% (English en-US)';
      }
    });
  }

  function speakTextBrowser(text, langCode) {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text.replace(/"/g, ''));
      u.lang = langCode;
      u.rate = 0.95;
      window.speechSynthesis.speak(u);
    }
  }

  if (btnPlayMultiAudio) {
    btnPlayMultiAudio.addEventListener('click', () => {
      const lang = multiSelectLang ? multiSelectLang.value : 'es';
      const text = multiSelectPhrase ? multiSelectPhrase.options[multiSelectPhrase.selectedIndex].text : '';
      if (multiStreamText) multiStreamText.textContent = text;

      const codeMap = { es: 'es-US', fr: 'fr-FR', en: 'en-US' };
      speakTextBrowser(text, codeMap[lang] || 'es-US');
      showToast(`Playing synthesized audio (${codeMap[lang] || lang}).`, 'info');
    });
  }

  if (btnSimulateAgentReply) {
    btnSimulateAgentReply.addEventListener('click', () => {
      const lang = multiSelectLang ? multiSelectLang.value : 'es';
      const replies = {
        es: { text: '¡Hola! Con mucho gusto le ayudo con su registro en Metro Health Clinic. ¿Podría confirmarme su nombre completo y fecha de nacimiento?', code: 'es-US' },
        fr: { text: 'Bonjour! Je serais ravie de vous aider avec votre inscription à Metro Health Clinic. Pourriez-vous me confirmer votre nom complet et date de naissance?', code: 'fr-FR' },
        en: { text: 'Hello! I would be glad to help you register with Metro Health Clinic today. Could you please share your full legal name and date of birth?', code: 'en-US' },
      };
      const rep = replies[lang] || replies.es;
      if (multiStreamText) multiStreamText.textContent = `[Sarah / Agent]: "${rep.text}"`;
      speakTextBrowser(rep.text, rep.code);
      showToast(`Sarah responding in ${lang === 'es' ? 'Spanish' : lang === 'fr' ? 'French' : 'English'}.`, 'success');
    });
  }

  // 5. HIPAA KMS Envelope Encryption Sandbox
  const btnKmsEncrypt = document.getElementById('btn-kms-encrypt');
  const btnKmsDecrypt = document.getElementById('btn-kms-decrypt');
  const kmsInPhi = document.getElementById('kms-in-phi');
  const kmsOutCiphertext = document.getElementById('kms-out-ciphertext');
  const kmsOutTag = document.getElementById('kms-out-tag');
  const kmsOutDecrypted = document.getElementById('kms-out-decrypted');

  let activeCipherState = {
    plaintext: 'DOB: 1998-05-14 | Phone: 512-555-0188 | MemberID: BCB-99482103',
    iv: '01a9b4c2d3e4f506',
    tag: '7e1f4a9b2c3d0e1f',
  };

  if (btnKmsEncrypt) {
    btnKmsEncrypt.addEventListener('click', () => {
      const pt = kmsInPhi ? kmsInPhi.value || 'DOB: 1998-05-14 | Phone: 512-555-0188' : 'DOB: 1998-05-14';
      const iv = Math.random().toString(36).substring(2, 10) + Math.random().toString(36).substring(2, 10);
      const tag = Math.random().toString(36).substring(2, 10) + Math.random().toString(36).substring(2, 10);
      const b64 = btoa(pt);
      const ciphertext = `AQIDAHj5p7q6v5F9...GCM:${tag.substring(0, 16)}...IV:${iv.substring(0, 16)}...DATA:${b64}`;

      activeCipherState = { plaintext: pt, iv, tag };

      if (kmsOutCiphertext) kmsOutCiphertext.textContent = ciphertext;
      if (kmsOutTag) kmsOutTag.textContent = `128-bit MAC: 0x${tag.toUpperCase()} (Integrity Verified)`;
      if (kmsOutDecrypted) kmsOutDecrypted.textContent = '[Encrypted payload sealed in memory]';

      showToast('Plaintext PHI encrypted with AWS KMS AES-256-GCM envelope.', 'success');
    });
  }

  if (btnKmsDecrypt) {
    btnKmsDecrypt.addEventListener('click', () => {
      if (kmsOutDecrypted) {
        kmsOutDecrypted.textContent = activeCipherState.plaintext;
      }
      showToast('GCM authentication tag verified. Plaintext PHI restored.', 'info');
    });
  }
});
