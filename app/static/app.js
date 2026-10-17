/**
 * Metro Health Clinic — Voice AI Patient Intake Dashboard Logic
 * Handles REST API CRUD, Live Search/Filtering, and Voice Agent Call Simulation.
 */

const API_BASE = '';

// State management
let state = {
  patients: [],
  selectedPatient: null,
  activeTab: 'tab-patients',
  filterStatus: 'active',
  searchQuery: '',
  callActive: false,
  callTimerInterval: null,
  callSeconds: 0,
};

// DOM Elements
const elements = {
  patientsTableBody: document.getElementById('patients-table-body'),
  patientSearchInput: document.getElementById('patient-search-input'),
  btnClearSearch: document.getElementById('btn-clear-search'),
  filterStatusSelect: document.getElementById('filter-status-select'),
  patientCountLabel: document.getElementById('patient-count-label'),
  statTotalPatients: document.getElementById('stat-total-patients'),
  statTotalSessions: document.getElementById('stat-total-sessions'),
  btnRefreshData: document.getElementById('btn-refresh-data'),
  toastContainer: document.getElementById('toast-container'),

  // Modals
  modalPatientDetails: document.getElementById('modal-patient-details'),
  btnCloseDetails: document.getElementById('btn-close-details'),
  detailsModalContent: document.getElementById('details-modal-content'),
  detailsPatientName: document.getElementById('details-patient-name'),
  detailsPatientId: document.getElementById('details-patient-id'),
  btnEditFromDetails: document.getElementById('btn-edit-from-details'),
  btnDeleteFromDetails: document.getElementById('btn-delete-from-details'),

  modalPatientForm: document.getElementById('modal-patient-form'),
  formModalTitle: document.getElementById('form-modal-title'),
  btnCloseForm: document.getElementById('btn-close-form'),
  btnCancelForm: document.getElementById('btn-cancel-form'),
  patientForm: document.getElementById('patient-registration-form'),
  btnOpenNewPatientModal: document.getElementById('btn-open-new-patient-modal'),

  // Simulator
  btnQuickSimulator: document.getElementById('btn-quick-simulator'),
  simCallerPhone: document.getElementById('sim-caller-phone'),
  btnStartCall: document.getElementById('btn-start-call'),
  btnEndCall: document.getElementById('btn-end-call'),
  callTimer: document.getElementById('call-timer'),
  callStatePill: document.getElementById('call-state-pill'),
  agentAvatarRing: document.getElementById('agent-avatar-ring'),
  chatMessagesContainer: document.getElementById('chat-messages-container'),
  chatInputBar: document.getElementById('chat-input-bar'),
  simUserInput: document.getElementById('sim-user-input'),
  btnSendMessage: document.getElementById('btn-send-message'),
  btnClearChat: document.getElementById('btn-clear-chat'),
  presetHappyPath: document.getElementById('preset-happy-path'),
  presetFutureDob: document.getElementById('preset-future-dob'),
  presetReturning: document.getElementById('preset-returning'),
};

// ---------------------------------------------------------------------------
// Toast Alerts
// ---------------------------------------------------------------------------
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${message}</span>`;
  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 250);
  }, 3500);
}

// ---------------------------------------------------------------------------
// API Helpers (Unwraps { data, error } envelope)
// ---------------------------------------------------------------------------
async function apiRequest(endpoint, options = {}) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });

    const json = await res.json();
    if (!res.ok || json.error) {
      const errMsg = json.error ? json.error.message : `HTTP ${res.status}`;
      throw new Error(errMsg);
    }
    return json.data;
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Load & Render Patients
// ---------------------------------------------------------------------------
async function loadPatients() {
  try {
    elements.patientsTableBody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <div class="loading-spinner"></div>
          <p>Loading patient directory...</p>
        </td>
      </tr>
    `;

    // Query parameters
    const params = new URLSearchParams();
    if (state.searchQuery) {
      // Check if phone or last name
      if (/^\d+$/.test(state.searchQuery.replace(/\D/g, '')) && state.searchQuery.replace(/\D/g, '').length >= 4) {
        params.append('phone_number', state.searchQuery);
      } else {
        params.append('last_name', state.searchQuery);
      }
    }

    const data = await apiRequest(`/patients?${params.toString()}`);
    state.patients = data || [];
    renderPatientsTable();
    updateStats();
  } catch (err) {
    elements.patientsTableBody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <p style="color: var(--color-rose);">Failed to load patients: ${err.message}</p>
        </td>
      </tr>
    `;
    showToast(`Error: ${err.message}`, 'error');
  }
}

function renderPatientsTable() {
  let list = [...state.patients];

  // Client-side filter for active vs soft-deleted
  if (state.filterStatus === 'active') {
    list = list.filter((p) => !p.deleted_at);
  } else if (state.filterStatus === 'deleted') {
    list = list.filter((p) => !!p.deleted_at);
  }

  // Client-side text filter refinement
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

  elements.patientCountLabel.textContent = `Showing ${list.length} ${
    list.length === 1 ? 'patient' : 'patients'
  }`;

  if (list.length === 0) {
    elements.patientsTableBody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <p>No matching patient records found.</p>
        </td>
      </tr>
    `;
    return;
  }

  elements.patientsTableBody.innerHTML = list
    .map((patient) => {
      const isDeleted = !!patient.deleted_at;
      const statusBadge = isDeleted
        ? '<span class="badge-status deleted"><span class="dot-deleted"></span> Soft-Deleted</span>'
        : '<span class="badge-status active"><span class="dot-active"></span> Active</span>';

      const insuranceDisplay = patient.insurance_provider
        ? `${patient.insurance_provider} (${patient.insurance_member_id || 'ID on file'})`
        : '<span style="color: var(--text-muted);">Self-Pay</span>';

      const formattedPhone = formatPhoneNumber(patient.phone_number);

      return `
      <tr data-id="${patient.id}">
        <td>
          <div class="patient-name-cell">${escapeHtml(patient.first_name)} ${escapeHtml(patient.last_name)}</div>
          <div class="patient-meta">${patient.email ? escapeHtml(patient.email) : 'No email'}</div>
        </td>
        <td>${patient.date_of_birth}</td>
        <td><span class="badge-sex">${escapeHtml(patient.sex)}</span></td>
        <td>${formattedPhone}</td>
        <td>${escapeHtml(patient.city || '')}, ${escapeHtml(patient.state || '')} ${escapeHtml(patient.zip_code || '')}</td>
        <td>${insuranceDisplay}</td>
        <td>${statusBadge}</td>
        <td class="text-right">
          <div class="table-row-actions">
            <button class="btn-action-icon btn-view" title="View Profile" onclick="openPatientDetails('${patient.id}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                <circle cx="12" cy="12" r="3"/>
              </svg>
            </button>
            <button class="btn-action-icon btn-edit" title="Edit" onclick="openEditPatient('${patient.id}')">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
              </svg>
            </button>
            ${
              !isDeleted
                ? `<button class="btn-action-icon danger btn-delete" title="Soft-Delete" onclick="deletePatient('${patient.id}')">
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

function updateStats() {
  const activeCount = state.patients.filter((p) => !p.deleted_at).length;
  elements.statTotalPatients.textContent = activeCount;
}

// ---------------------------------------------------------------------------
// Patient Details Modal
// ---------------------------------------------------------------------------
window.openPatientDetails = function (patientId) {
  const patient = state.patients.find((p) => p.id === patientId);
  if (!patient) return;

  state.selectedPatient = patient;
  elements.detailsPatientName.textContent = `${patient.first_name} ${patient.last_name}`;
  elements.detailsPatientId.textContent = `ID: ${patient.id}`;

  const isDeleted = !!patient.deleted_at;

  elements.detailsModalContent.innerHTML = `
    <div class="profile-grid">
      <div>
        <div class="profile-field-label">Date of Birth</div>
        <div class="profile-field-value">${patient.date_of_birth}</div>
      </div>
      <div>
        <div class="profile-field-label">Sex</div>
        <div class="profile-field-value">${escapeHtml(patient.sex)}</div>
      </div>
      <div>
        <div class="profile-field-label">Phone Number</div>
        <div class="profile-field-value">${formatPhoneNumber(patient.phone_number)}</div>
      </div>
      <div>
        <div class="profile-field-label">Email Address</div>
        <div class="profile-field-value">${patient.email ? escapeHtml(patient.email) : 'None'}</div>
      </div>
      <div>
        <div class="profile-field-label">Street Address</div>
        <div class="profile-field-value">${escapeHtml(patient.address_line_1)} ${patient.address_line_2 ? escapeHtml(patient.address_line_2) : ''}</div>
      </div>
      <div>
        <div class="profile-field-label">City, State ZIP</div>
        <div class="profile-field-value">${escapeHtml(patient.city)}, ${escapeHtml(patient.state)} ${escapeHtml(patient.zip_code)}</div>
      </div>
      <div>
        <div class="profile-field-label">Insurance Provider</div>
        <div class="profile-field-value">${patient.insurance_provider ? escapeHtml(patient.insurance_provider) : 'None (Self-Pay)'}</div>
      </div>
      <div>
        <div class="profile-field-label">Insurance Member ID</div>
        <div class="profile-field-value">${patient.insurance_member_id ? escapeHtml(patient.insurance_member_id) : 'N/A'}</div>
      </div>
      <div>
        <div class="profile-field-label">Emergency Contact</div>
        <div class="profile-field-value">${patient.emergency_contact_name ? escapeHtml(patient.emergency_contact_name) : 'None provided'}</div>
      </div>
      <div>
        <div class="profile-field-label">Emergency Phone</div>
        <div class="profile-field-value">${patient.emergency_contact_phone ? formatPhoneNumber(patient.emergency_contact_phone) : 'N/A'}</div>
      </div>
      <div>
        <div class="profile-field-label">Preferred Language</div>
        <div class="profile-field-value">${escapeHtml(patient.preferred_language || 'English')}</div>
      </div>
      <div>
        <div class="profile-field-label">Status</div>
        <div class="profile-field-value">${isDeleted ? '<span style="color:var(--color-rose);">Soft-Deleted</span>' : '<span style="color:var(--color-emerald);">Active</span>'}</div>
      </div>
    </div>
  `;

  elements.btnDeleteFromDetails.style.display = isDeleted ? 'none' : 'inline-flex';
  elements.modalPatientDetails.classList.remove('hidden');
};

function closePatientDetails() {
  elements.modalPatientDetails.classList.add('hidden');
  state.selectedPatient = null;
}

// ---------------------------------------------------------------------------
// Add / Edit Patient Modal
// ---------------------------------------------------------------------------
function openNewPatientModal() {
  document.getElementById('form-patient-id').value = '';
  elements.patientForm.reset();
  elements.formModalTitle.textContent = 'Register New Patient';
  clearFormErrors();
  elements.modalPatientForm.classList.remove('hidden');
}

window.openEditPatient = function (patientId) {
  const patient = state.patients.find((p) => p.id === patientId);
  if (!patient) return;

  closePatientDetails();
  clearFormErrors();
  elements.formModalTitle.textContent = 'Edit Patient Demographics';

  document.getElementById('form-patient-id').value = patient.id;
  document.getElementById('input-first-name').value = patient.first_name;
  document.getElementById('input-last-name').value = patient.last_name;
  document.getElementById('input-dob').value = patient.date_of_birth;
  document.getElementById('input-sex').value = patient.sex;
  document.getElementById('input-phone').value = patient.phone_number;
  document.getElementById('input-email').value = patient.email || '';
  document.getElementById('input-address1').value = patient.address_line_1;
  document.getElementById('input-address2').value = patient.address_line_2 || '';
  document.getElementById('input-city').value = patient.city;
  document.getElementById('input-state').value = patient.state;
  document.getElementById('input-zip').value = patient.zip_code;
  document.getElementById('input-insurance-provider').value = patient.insurance_provider || '';
  document.getElementById('input-insurance-id').value = patient.insurance_member_id || '';
  document.getElementById('input-emergency-name').value = patient.emergency_contact_name || '';
  document.getElementById('input-emergency-phone').value = patient.emergency_contact_phone || '';

  elements.modalPatientForm.classList.remove('hidden');
};

function closePatientForm() {
  elements.modalPatientForm.classList.add('hidden');
  clearFormErrors();
}

function clearFormErrors() {
  document.querySelectorAll('.field-error').forEach((el) => (el.textContent = ''));
}

async function handlePatientFormSubmit(e) {
  e.preventDefault();
  clearFormErrors();

  const patientId = document.getElementById('form-patient-id').value;
  const isEdit = !!patientId;

  const payload = {
    first_name: document.getElementById('input-first-name').value.trim(),
    last_name: document.getElementById('input-last-name').value.trim(),
    date_of_birth: document.getElementById('input-dob').value,
    sex: document.getElementById('input-sex').value,
    phone_number: document.getElementById('input-phone').value.trim(),
    email: document.getElementById('input-email').value.trim() || null,
    address_line_1: document.getElementById('input-address1').value.trim(),
    address_line_2: document.getElementById('input-address2').value.trim() || null,
    city: document.getElementById('input-city').value.trim(),
    state: document.getElementById('input-state').value.trim().toUpperCase(),
    zip_code: document.getElementById('input-zip').value.trim(),
    insurance_provider: document.getElementById('input-insurance-provider').value.trim() || null,
    insurance_member_id: document.getElementById('input-insurance-id').value.trim() || null,
    emergency_contact_name: document.getElementById('input-emergency-name').value.trim() || null,
    emergency_contact_phone: document.getElementById('input-emergency-phone').value.trim() || null,
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
    showToast(`Validation Error: ${err.message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Soft-Delete Action
// ---------------------------------------------------------------------------
window.deletePatient = async function (patientId) {
  const patient = state.patients.find((p) => p.id === patientId);
  const name = patient ? `${patient.first_name} ${patient.last_name}` : 'this patient';

  if (!confirm(`Are you sure you want to soft-delete ${name}?`)) {
    return;
  }

  try {
    await apiRequest(`/patients/${patientId}`, { method: 'DELETE' });
    showToast(`Patient ${name} soft-deleted.`, 'success');
    closePatientDetails();
    await loadPatients();
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  }
};

// ---------------------------------------------------------------------------
// Interactive Voice Agent Call Simulator
// ---------------------------------------------------------------------------
function addChatMessage(speaker, message, type = 'agent', toolMeta = null) {
  // Clear empty state if present
  const emptyState = elements.chatMessagesContainer.querySelector('.chat-empty-state');
  if (emptyState) emptyState.remove();

  const msgDiv = document.createElement('div');
  msgDiv.className = `chat-msg ${type}`;

  let toolHtml = '';
  if (toolMeta) {
    toolHtml = `
      <div class="tool-call-pill">
        <span>⚡ Tool: ${toolMeta.name}</span>
        <span>(${toolMeta.summary})</span>
      </div>
    `;
  }

  msgDiv.innerHTML = `
    <span class="msg-sender">${speaker}</span>
    <div class="msg-bubble">${escapeHtml(message).replace(/\n/g, '<br>')}</div>
    ${toolHtml}
  `;

  elements.chatMessagesContainer.appendChild(msgDiv);
  elements.chatMessagesContainer.scrollTop = elements.chatMessagesContainer.scrollHeight;
}

function setAvatarSpeaking(speaking) {
  if (speaking) {
    elements.agentAvatarRing.classList.add('speaking');
  } else {
    elements.agentAvatarRing.classList.remove('speaking');
  }
}

async function startSimulatorCall() {
  const phone = elements.simCallerPhone.value.trim() || '5125550188';

  state.callActive = true;
  state.callSeconds = 0;
  elements.btnStartCall.classList.add('hidden');
  elements.btnEndCall.classList.remove('hidden');
  elements.callTimer.classList.remove('hidden');
  elements.callStatePill.classList.add('in-call');
  elements.callStatePill.textContent = 'Call Connected';
  elements.chatInputBar.classList.remove('hidden');

  // Start timer
  state.callTimerInterval = setInterval(() => {
    state.callSeconds++;
    const mins = String(Math.floor(state.callSeconds / 60)).padStart(2, '0');
    const secs = String(state.callSeconds % 60).padStart(2, '0');
    elements.callTimer.textContent = `${mins}:${secs}`;
  }, 1000);

  // 1. Assistant Request
  setAvatarSpeaking(true);
  try {
    const resp = await fetch('/api/voice/webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: {
          type: 'assistant-request',
          call: { id: `sim-${Date.now()}`, customer: { number: phone } },
        },
      }),
    });
    const data = await resp.json();
    const firstMsg =
      data?.assistant?.firstMessage ||
      'Hello! Thank you for calling Metro Health Clinic. My name is Sarah.';

    addChatMessage('Sarah (Agent)', firstMsg, 'agent');

    // 2. Immediate returning caller lookup
    const lookupResp = await fetch('/api/voice/webhook', {
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
    const lookupData = await lookupResp.json();
    const lookupResult = JSON.parse(lookupData.results[0].result);

    if (lookupResult.found) {
      addChatMessage(
        'System',
        `Lookup match found for returning caller (${lookupResult.patient.first_name} ${lookupResult.patient.last_name}).`,
        'system',
        { name: 'lookup_patient', summary: 'MATCH FOUND' }
      );
      addChatMessage(
        'Sarah (Agent)',
        `Welcome back, ${lookupResult.patient.first_name}! I see we already have your information on file. Would you like to update anything today?`,
        'agent'
      );
    } else {
      addChatMessage(
        'System',
        'No existing record found for caller ID. Proceeding with new patient intake.',
        'system',
        { name: 'lookup_patient', summary: 'NEW CALLER' }
      );
    }
  } catch (err) {
    addChatMessage('System', `Webhook connection error: ${err.message}`, 'system');
  } finally {
    setAvatarSpeaking(false);
  }
}

async function endSimulatorCall() {
  state.callActive = false;
  clearInterval(state.callTimerInterval);
  elements.btnStartCall.classList.remove('hidden');
  elements.btnEndCall.classList.add('hidden');
  elements.callTimer.classList.add('hidden');
  elements.callStatePill.classList.remove('in-call');
  elements.callStatePill.textContent = 'Call Ended';
  elements.chatInputBar.classList.add('hidden');
  setAvatarSpeaking(false);

  addChatMessage(
    'Sarah (Agent)',
    'Thank you for calling Metro Health Clinic. Have a wonderful day!',
    'agent'
  );

  // Send end-of-call report
  try {
    await fetch('/api/voice/webhook', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: {
          type: 'end-of-call-report',
          call: { id: `sim-${Date.now()}`, customer: { number: elements.simCallerPhone.value } },
          transcript: 'Simulated call completed from dashboard.',
        },
      }),
    });
  } catch (e) {
    console.error('End of call report error:', e);
  }
}

// ---------------------------------------------------------------------------
// Preset Automation Scenarios
// ---------------------------------------------------------------------------
async function runPresetScenario1() {
  // Scenario 1: Fresh caller happy path
  elements.simCallerPhone.value = '5125550188';
  elements.chatMessagesContainer.innerHTML = '';
  await startSimulatorCall();

  await sleep(800);
  addChatMessage('Caller', 'My name is Marcus Vance.', 'user');

  await sleep(1000);
  addChatMessage('Sarah (Agent)', 'Thank you, Marcus. And what is your date of birth?', 'agent');

  await sleep(800);
  addChatMessage('Caller', 'August 24th, 1988.', 'user');

  await sleep(1000);
  addChatMessage(
    'Sarah (Agent)',
    'Got it, August 24, 1988. For our medical records, how should we record your sex?',
    'agent'
  );

  await sleep(800);
  addChatMessage('Caller', 'Male. And my address is 742 Evergreen Terrace, Austin TX 78704.', 'user');

  await sleep(1200);
  addChatMessage(
    'Sarah (Agent)',
    'Let me read that back to make sure everything is exact:\n' +
      '  - Name: Marcus Vance\n' +
      '  - DOB: August 24, 1988\n' +
      '  - Sex: Male\n' +
      '  - Phone: (512) 555-0188\n' +
      '  - Address: 742 Evergreen Terrace, Austin TX 78704\n' +
      'Does everything sound correct?',
    'agent'
  );

  await sleep(1000);
  addChatMessage('Caller', "Yes, that's completely correct!", 'user');

  await sleep(1200);
  // Execute tool call
  const saveResp = await fetch('/api/voice/webhook', {
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
  const saveJson = await saveResp.json();
  const saveResult = JSON.parse(saveJson.results[0].result);

  addChatMessage(
    'System',
    `Database save successful! Created Patient UUID: ${saveResult.patient_id}`,
    'system',
    { name: 'register_patient', summary: 'SAVED TO DB' }
  );

  addChatMessage(
    'Sarah (Agent)',
    `Wonderful! You are now registered with Metro Health Clinic, Marcus. Your patient ID is ${saveResult.patient_id}. Have a wonderful day!`,
    'agent'
  );

  showToast('Patient Marcus Vance registered via Voice AI!', 'success');
  await loadPatients();
  await endSimulatorCall();
}

async function runPresetScenario2() {
  // Scenario 2: Future DOB rejection & re-prompt
  elements.simCallerPhone.value = '5125557766';
  elements.chatMessagesContainer.innerHTML = '';
  await startSimulatorCall();

  await sleep(800);
  addChatMessage('Caller', 'My name is Jordan Miller, born January 1st, 2099.', 'user');

  await sleep(1000);
  // Attempt invalid tool call
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
  const badJson = await badResp.json();
  const badResult = JSON.parse(badJson.results[0].result);

  addChatMessage(
    'System',
    `Validation Rejected: ${badResult.validation_errors.join(', ')}`,
    'system',
    { name: 'register_patient', summary: 'VALIDATION REJECTED' }
  );

  await sleep(1000);
  addChatMessage(
    'Sarah (Agent)',
    "I'm sorry Jordan, but that birth date appears to be in the future. Could you please confirm the four-digit year you were born?",
    'agent'
  );

  await sleep(900);
  addChatMessage('Caller', 'Oops! I meant 1999, not 2099.', 'user');

  await sleep(1200);
  // Corrected save
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
  const goodJson = await goodResp.json();
  const goodResult = JSON.parse(goodJson.results[0].result);

  addChatMessage(
    'System',
    `Correction accepted! Patient ID: ${goodResult.patient_id}`,
    'system',
    { name: 'register_patient', summary: 'CORRECTED & SAVED' }
  );
  addChatMessage('Sarah (Agent)', 'That worked! You are now registered.', 'agent');

  showToast('Scenario 2: Validation recovery tested successfully!', 'success');
  await loadPatients();
  await endSimulatorCall();
}

async function runPresetScenario3() {
  // Scenario 3: Returning caller recognition
  elements.simCallerPhone.value = '5125550188';
  elements.chatMessagesContainer.innerHTML = '';
  await startSimulatorCall();
}

// ---------------------------------------------------------------------------
// Helper Utilities
// ---------------------------------------------------------------------------
function formatPhoneNumber(phone) {
  if (!phone) return 'N/A';
  const digits = phone.replace(/\D/g, '');
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  if (digits.length === 11 && digits.startsWith('1')) {
    return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
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
// Event Listeners
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  loadPatients();

  // Tabs switching
  document.querySelectorAll('.tab-button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-button').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach((tc) => tc.classList.remove('active'));

      btn.classList.add('active');
      const targetTab = btn.getAttribute('data-tab');
      document.getElementById(targetTab).classList.add('active');
      state.activeTab = targetTab;
    });
  });

  // Search input debouncing
  let searchTimeout = null;
  elements.patientSearchInput.addEventListener('input', (e) => {
    const val = e.target.value.trim();
    state.searchQuery = val;
    elements.btnClearSearch.classList.toggle('hidden', !val);

    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      renderPatientsTable();
    }, 250);
  });

  elements.btnClearSearch.addEventListener('click', () => {
    elements.patientSearchInput.value = '';
    state.searchQuery = '';
    elements.btnClearSearch.classList.add('hidden');
    renderPatientsTable();
  });

  // Filter dropdown
  elements.filterStatusSelect.addEventListener('change', (e) => {
    state.filterStatus = e.target.value;
    renderPatientsTable();
  });

  // Refresh
  elements.btnRefreshData.addEventListener('click', () => {
    loadPatients();
    showToast('Data refreshed.', 'info');
  });

  // Modal handlers
  elements.btnOpenNewPatientModal.addEventListener('click', openNewPatientModal);
  elements.btnCloseForm.addEventListener('click', closePatientForm);
  elements.btnCancelForm.addEventListener('click', closePatientForm);
  elements.patientForm.addEventListener('submit', handlePatientFormSubmit);

  elements.btnCloseDetails.addEventListener('click', closePatientDetails);
  elements.btnEditFromDetails.addEventListener('click', () => {
    if (state.selectedPatient) {
      openEditPatient(state.selectedPatient.id);
    }
  });
  elements.btnDeleteFromDetails.addEventListener('click', () => {
    if (state.selectedPatient) {
      deletePatient(state.selectedPatient.id);
    }
  });

  // Quick simulator jump
  elements.btnQuickSimulator.addEventListener('click', () => {
    document.getElementById('tab-btn-simulator').click();
  });

  // Simulator controls
  elements.btnStartCall.addEventListener('click', startSimulatorCall);
  elements.btnEndCall.addEventListener('click', endSimulatorCall);
  elements.btnClearChat.addEventListener('click', () => {
    elements.chatMessagesContainer.innerHTML = `
      <div class="chat-empty-state">
        <h4>No Active Call</h4>
        <p>Click "Start Inbound Call" or choose a quick preset on the left to begin a voice session.</p>
      </div>
    `;
  });

  // Simulator user text input
  elements.btnSendMessage.addEventListener('click', () => {
    const msg = elements.simUserInput.value.trim();
    if (!msg) return;
    addChatMessage('Caller', msg, 'user');
    elements.simUserInput.value = '';
  });
  elements.simUserInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      elements.btnSendMessage.click();
    }
  });

  // Presets
  elements.presetHappyPath.addEventListener('click', runPresetScenario1);
  elements.presetFutureDob.addEventListener('click', runPresetScenario2);
  elements.presetReturning.addEventListener('click', runPresetScenario3);
});
