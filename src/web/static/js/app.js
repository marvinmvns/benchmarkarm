/**
 * Voice Processor - Interface Web
 * JavaScript leve e vanilla para configuração
 */

// Estado global
let config = {};
let isDirty = false;

// ==========================================================================
// Utilidades
// ==========================================================================

function $(selector) {
    return document.querySelector(selector);
}

function $$(selector) {
    return document.querySelectorAll(selector);
}

function showToast(message, type = 'info') {
    const existing = $('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.remove(), 3000);
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getNestedValue(obj, path) {
    return path.split('.').reduce((o, k) => (o || {})[k], obj);
}

function setNestedValue(obj, path, value) {
    const keys = path.split('.');
    const last = keys.pop();
    const target = keys.reduce((o, k) => {
        if (!(k in o)) o[k] = {};
        return o[k];
    }, obj);
    target[last] = value;
}

// ==========================================================================
// API
// ==========================================================================

async function apiGet(endpoint) {
    const response = await fetch(`/api/${endpoint}`);
    return response.json();
}

async function apiPost(endpoint, data) {
    const response = await fetch(`/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return response.json();
}

async function apiPut(endpoint, data) {
    const response = await fetch(`/api/${endpoint}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    return response.json();
}

// ==========================================================================
// Configuração
// ==========================================================================

async function loadConfig() {
    try {
        config = await apiGet('config');
        populateForm(config);
        updateStatus('online');
        showToast('Configuração carregada', 'success');
    } catch (error) {
        console.error('Erro ao carregar config:', error);
        updateStatus('offline');
        showToast('Erro ao carregar configuração', 'error');
    }
}

async function saveConfig() {
    try {
        // Coletar valores do formulário
        collectFormValues();

        const result = await apiPost('config', config);
        if (result.success) {
            isDirty = false;
            showToast('Configuração salva!', 'success');
            $('#save-status').textContent = '✓ Salvo';
            setTimeout(() => $('#save-status').textContent = '', 3000);
        } else {
            throw new Error(result.error || 'Erro desconhecido');
        }
    } catch (error) {
        console.error('Erro ao salvar:', error);
        showToast('Erro ao salvar: ' + error.message, 'error');
    }
}

function populateForm(cfg) {
    // Mode
    if (cfg.mode) $('#mode').value = cfg.mode;

    // System
    if (cfg.system) {
        $('#cache_enabled').checked = cfg.system.cache_enabled !== false;
        $('#low_memory_mode').checked = cfg.system.low_memory_mode !== false;
        if (cfg.system.log_level) $('#log_level').value = cfg.system.log_level;
        if (cfg.system.timeout) $('#timeout').value = cfg.system.timeout;
    }

    // Audio
    if (cfg.audio) {
        $('#sample_rate').value = cfg.audio.sample_rate || 16000;
        $('#max_duration').value = cfg.audio.max_duration || 30;
        $('#silence_duration').value = cfg.audio.silence_duration || 2.0;

        if (cfg.audio.vad) {
            $('#vad_enabled').checked = cfg.audio.vad.enabled !== false;
            $('#vad_aggressiveness').value = cfg.audio.vad.aggressiveness || 2;
            $('#vad_aggressiveness_value').textContent = cfg.audio.vad.aggressiveness || 2;
        }
    }

    // Whisper
    if (cfg.whisper) {
        $('#whisper_model').value = cfg.whisper.model || 'tiny';
        $('#whisper_language').value = cfg.whisper.language || 'pt';
        $('#whisper_use_cpp').checked = cfg.whisper.use_cpp !== false;
        $('#whisper_threads').value = cfg.whisper.threads || 4;
        $('#whisper_beam_size').value = cfg.whisper.beam_size || 1;
    }

    // LLM
    if (cfg.llm) {
        $('#llm_provider').value = cfg.llm.provider || 'local';
        updateLLMSection(cfg.llm.provider);

        if (cfg.llm.local) {
            $('#local_model').value = cfg.llm.local.model || 'tinyllama';
            $('#local_context_size').value = cfg.llm.local.context_size || 512;
            $('#local_max_tokens').value = cfg.llm.local.max_tokens || 150;
            $('#llm_temperature').value = cfg.llm.local.temperature || 0.3;
            $('#llm_temperature_value').textContent = cfg.llm.local.temperature || 0.3;
        }
    }

    // Offline Queue
    if (cfg.offline_queue) {
        $('#offline_enabled').checked = cfg.offline_queue.enabled !== false;
        $('#max_queue_size').value = cfg.offline_queue.max_queue_size || 1000;
        $('#retry_delay').value = cfg.offline_queue.retry_delay_base || 30;
        $('#max_retries').value = cfg.offline_queue.max_retries || 3;
        $('#use_local_fallback').checked = cfg.offline_queue.use_local_fallback !== false;
    }

    // Power Management
    if (cfg.power_management) {
        $('#power_enabled').checked = cfg.power_management.enabled === true;
        $('#power_mode').value = cfg.power_management.default_mode || 'balanced';
        $('#power_auto_adjust').checked = cfg.power_management.auto_adjust !== false;
        $('#idle_timeout').value = cfg.power_management.idle_timeout || 60;

        if (cfg.power_management.thermal) {
            $('#temp_high').value = cfg.power_management.thermal.threshold_high || 70;
            $('#temp_critical').value = cfg.power_management.thermal.threshold_critical || 80;
        }
    }
}

function collectFormValues() {
    // Mode
    config.mode = $('#mode').value;

    // System
    if (!config.system) config.system = {};
    config.system.cache_enabled = $('#cache_enabled').checked;
    config.system.low_memory_mode = $('#low_memory_mode').checked;
    config.system.log_level = $('#log_level').value;
    config.system.timeout = parseInt($('#timeout').value);

    // Audio
    if (!config.audio) config.audio = {};
    config.audio.sample_rate = parseInt($('#sample_rate').value);
    config.audio.max_duration = parseInt($('#max_duration').value);
    config.audio.silence_duration = parseFloat($('#silence_duration').value);

    if (!config.audio.vad) config.audio.vad = {};
    config.audio.vad.enabled = $('#vad_enabled').checked;
    config.audio.vad.aggressiveness = parseInt($('#vad_aggressiveness').value);

    // Whisper
    if (!config.whisper) config.whisper = {};
    config.whisper.model = $('#whisper_model').value;
    config.whisper.language = $('#whisper_language').value;
    config.whisper.use_cpp = $('#whisper_use_cpp').checked;
    config.whisper.threads = parseInt($('#whisper_threads').value);
    config.whisper.beam_size = parseInt($('#whisper_beam_size').value);

    // LLM
    if (!config.llm) config.llm = {};
    config.llm.provider = $('#llm_provider').value;

    if (!config.llm.local) config.llm.local = {};
    config.llm.local.model = $('#local_model').value;
    config.llm.local.context_size = parseInt($('#local_context_size').value);
    config.llm.local.max_tokens = parseInt($('#local_max_tokens').value);
    config.llm.local.temperature = parseFloat($('#llm_temperature').value);

    // Offline Queue
    if (!config.offline_queue) config.offline_queue = {};
    config.offline_queue.enabled = $('#offline_enabled').checked;
    config.offline_queue.max_queue_size = parseInt($('#max_queue_size').value);
    config.offline_queue.retry_delay_base = parseFloat($('#retry_delay').value);
    config.offline_queue.max_retries = parseInt($('#max_retries').value);
    config.offline_queue.use_local_fallback = $('#use_local_fallback').checked;

    // Power Management
    if (!config.power_management) config.power_management = {};
    config.power_management.enabled = $('#power_enabled').checked;
    config.power_management.default_mode = $('#power_mode').value;
    config.power_management.auto_adjust = $('#power_auto_adjust').checked;
    config.power_management.idle_timeout = parseFloat($('#idle_timeout').value);

    if (!config.power_management.thermal) config.power_management.thermal = {};
    config.power_management.thermal.threshold_high = parseFloat($('#temp_high').value);
    config.power_management.thermal.threshold_critical = parseFloat($('#temp_critical').value);
}

// ==========================================================================
// UI Updates
// ==========================================================================

function updateStatus(status) {
    const dot = $('#status-indicator');
    const text = $('#status-text');

    dot.className = 'status-dot ' + status;
    text.textContent = status === 'online' ? 'Conectado' : 'Desconectado';
}

function updateLLMSection(provider) {
    const localConfig = $('#llm-local-config');
    const apiConfig = $('#llm-api-config');

    if (provider === 'local') {
        localConfig.style.display = 'block';
        apiConfig.style.display = 'none';
    } else {
        localConfig.style.display = 'none';
        apiConfig.style.display = 'block';
    }
}

async function refreshSystemInfo() {
    try {
        const info = await apiGet('system');

        $('#sys-platform').textContent = info.platform || '-';
        $('#sys-hostname').textContent = info.hostname || '-';
        $('#sys-temp').textContent = info.cpu_temp ? `${info.cpu_temp.toFixed(1)}°C` : '-';
        $('#sys-memory').textContent = info.memory_total ?
            `${formatBytes(info.memory_available)} / ${formatBytes(info.memory_total)}` : '-';
        $('#sys-disk').textContent = info.disk_total ?
            `${formatBytes(info.disk_free)} livre` : '-';
    } catch (error) {
        console.error('Erro ao obter info do sistema:', error);
    }
}

async function refreshQueueStats() {
    try {
        const stats = await apiGet('queue/stats');

        $('#queue-pending').textContent = stats.pending || 0;
        $('#queue-processing').textContent = stats.processing || 0;
        $('#queue-completed').textContent = stats.completed || 0;
        $('#queue-online').textContent = stats.is_online ? '🟢 Online' : '🔴 Offline';
    } catch (error) {
        console.error('Erro ao obter stats da fila:', error);
        $('#queue-pending').textContent = '-';
        $('#queue-processing').textContent = '-';
        $('#queue-completed').textContent = '-';
        $('#queue-online').textContent = '-';
    }
}

async function refreshPowerStatus() {
    try {
        const status = await apiGet('power/status');

        $('#power-current-mode').textContent = status.current_mode || '-';
        $('#power-temp').textContent = status.temperature || '-';
        $('#power-idle').textContent = status.is_idle ? 'Sim' : 'Não';
    } catch (error) {
        console.error('Erro ao obter status de energia:', error);
    }
}

async function testAudio() {
    const resultBox = $('#audio-test-result');
    resultBox.textContent = 'Testando...';

    try {
        const result = await apiPost('test/audio', {});
        resultBox.textContent = result.devices || result.error || 'Sem resultado';
    } catch (error) {
        resultBox.textContent = 'Erro: ' + error.message;
    }
}

// ==========================================================================
// Tabs
// ==========================================================================

function initTabs() {
    $$('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active from all
            $$('.tab-btn').forEach(b => b.classList.remove('active'));
            $$('.tab-content').forEach(c => c.classList.remove('active'));

            // Add active to clicked
            btn.classList.add('active');
            const tabId = 'tab-' + btn.dataset.tab;
            $(`#${tabId}`).classList.add('active');

            // Refresh data for specific tabs
            if (btn.dataset.tab === 'system') refreshSystemInfo();
            if (btn.dataset.tab === 'offline') refreshQueueStats();
            if (btn.dataset.tab === 'power') refreshPowerStatus();
            if (btn.dataset.tab === 'transcription') refreshProcessorStatus();
        });
    });
}

// ==========================================================================
// Event Listeners
// ==========================================================================

function initEventListeners() {
    // Save button
    $('#btn-save').addEventListener('click', saveConfig);

    // Reload button
    $('#btn-reload').addEventListener('click', loadConfig);

    // LLM provider change
    $('#llm_provider').addEventListener('change', (e) => {
        updateLLMSection(e.target.value);
    });

    // Range sliders
    $('#vad_aggressiveness').addEventListener('input', (e) => {
        $('#vad_aggressiveness_value').textContent = e.target.value;
    });

    $('#llm_temperature').addEventListener('input', (e) => {
        $('#llm_temperature_value').textContent = e.target.value;
    });

    // Test audio
    $('#btn-test-audio').addEventListener('click', testAudio);

    // Refresh buttons
    $('#btn-refresh-system').addEventListener('click', refreshSystemInfo);
    $('#btn-refresh-queue').addEventListener('click', refreshQueueStats);

    // Export config
    $('#btn-export').addEventListener('click', () => {
        const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'voice-processor-config.json';
        a.click();
        URL.revokeObjectURL(url);
        showToast('Configuração exportada', 'success');
    });

    // Import config
    $('#btn-import').addEventListener('click', () => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json,.yaml,.yml';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (file) {
                const text = await file.text();
                try {
                    const imported = JSON.parse(text);
                    config = imported;
                    populateForm(config);
                    showToast('Configuração importada', 'success');
                } catch (err) {
                    showToast('Erro ao importar: arquivo inválido', 'error');
                }
            }
        };
        input.click();
    });

    // Reset to defaults
    $('#btn-reset').addEventListener('click', () => {
        if (confirm('Tem certeza que deseja resetar para os padrões?')) {
            location.reload();
        }
    });

    // Track changes
    $$('input, select').forEach(el => {
        el.addEventListener('change', () => {
            isDirty = true;
            $('#save-status').textContent = '● Alterações não salvas';
        });
    });

    // Warn before leaving with unsaved changes
    window.addEventListener('beforeunload', (e) => {
        if (isDirty) {
            e.preventDefault();
            e.returnValue = '';
        }
    });
}

// ==========================================================================
// Transcription Functions
// ==========================================================================

let isRecording = false;
let statusPollInterval = null;

async function startRecording() {
    const recordBtn = $('#btn-record');
    const recordText = $('#record-btn-text');
    const recordingStatus = $('#recording-status');
    const recordingStatusText = $('#recording-status-text');

    if (isRecording) {
        showToast('Gravação já em andamento', 'warning');
        return;
    }

    try {
        const result = await apiPost('record/start', {});

        if (result.success) {
            isRecording = true;
            recordBtn.classList.add('recording');
            recordBtn.disabled = true;
            recordText.textContent = 'Gravando...';
            recordingStatus.classList.remove('hidden');
            recordingStatusText.textContent = 'Gravando áudio...';

            // Iniciar polling de status
            startStatusPolling();

            showToast('Gravação iniciada!', 'success');
        } else {
            throw new Error(result.error || 'Erro ao iniciar gravação');
        }
    } catch (error) {
        console.error('Erro ao iniciar gravação:', error);
        showToast('Erro: ' + error.message, 'error');
        resetRecordingUI();
    }
}

function startStatusPolling() {
    // Poll a cada 500ms
    statusPollInterval = setInterval(async () => {
        try {
            const result = await apiGet('processor/status');

            if (result.success) {
                const status = result.status;
                const recordingStatusText = $('#recording-status-text');

                if (status.is_recording) {
                    recordingStatusText.textContent = 'Gravando áudio...';
                } else if (status.is_processing) {
                    recordingStatusText.textContent = 'Processando transcrição...';
                } else if (status.current_transcription) {
                    // Processamento concluído
                    stopStatusPolling();
                    resetRecordingUI();

                    if (status.current_transcription.error) {
                        showToast('Erro: ' + status.current_transcription.error, 'error');
                    } else {
                        displayTranscription(status.current_transcription);
                        showToast('Transcrição concluída!', 'success');
                        loadTranscriptionHistory();
                    }
                }

                // Atualizar status do processador
                updateProcessorStatus(result);
            }
        } catch (error) {
            console.error('Erro no polling:', error);
        }
    }, 500);
}

function stopStatusPolling() {
    if (statusPollInterval) {
        clearInterval(statusPollInterval);
        statusPollInterval = null;
    }
}

function resetRecordingUI() {
    isRecording = false;
    const recordBtn = $('#btn-record');
    const recordText = $('#record-btn-text');
    const recordingStatus = $('#recording-status');

    recordBtn.classList.remove('recording');
    recordBtn.disabled = false;
    recordText.textContent = 'Iniciar Gravação';
    recordingStatus.classList.add('hidden');
}

function displayTranscription(data) {
    const container = $('#current-transcription');
    const textEl = $('#transcription-text');
    const timestampEl = $('#trans-timestamp');
    const durationEl = $('#trans-duration');
    const timeEl = $('#trans-time');
    const summaryContainer = $('#transcription-summary');
    const summaryText = $('#summary-text');

    container.classList.remove('hidden');

    textEl.textContent = data.text || 'Nenhum texto transcrito';
    timestampEl.textContent = data.timestamp || '';
    durationEl.textContent = data.audio_duration ? `${data.audio_duration}s de áudio` : '';
    timeEl.textContent = data.processing_time ? `${data.processing_time}s processamento` : '';

    if (data.summary) {
        summaryContainer.classList.remove('hidden');
        summaryText.textContent = data.summary;
    } else {
        summaryContainer.classList.add('hidden');
    }
}

async function loadTranscriptionHistory() {
    try {
        const result = await apiGet('transcriptions?limit=20');

        if (result.success) {
            renderHistory(result.transcriptions);
            $('#proc-total').textContent = result.total || 0;
        }
    } catch (error) {
        console.error('Erro ao carregar histórico:', error);
    }
}

function renderHistory(transcriptions) {
    const container = $('#transcription-history');

    if (!transcriptions || transcriptions.length === 0) {
        container.innerHTML = '<p class="empty-history">Nenhuma transcrição ainda.</p>';
        return;
    }

    container.innerHTML = transcriptions.map(t => `
        <div class="history-item" data-id="${t.id}" onclick="displayTranscription(${JSON.stringify(t).replace(/"/g, '&quot;')})">
            <div class="history-item-header">
                <span>${t.timestamp}</span>
                <span>${t.audio_duration || 0}s | ${t.processing_time || 0}s</span>
            </div>
            <div class="history-item-text">${t.text || 'Sem texto'}</div>
        </div>
    `).join('');
}

async function clearTranscriptionHistory() {
    if (!confirm('Tem certeza que deseja limpar o histórico?')) return;

    try {
        const response = await fetch('/api/transcriptions', { method: 'DELETE' });
        const result = await response.json();

        if (result.success) {
            loadTranscriptionHistory();
            $('#current-transcription').classList.add('hidden');
            showToast('Histórico limpo!', 'success');
        }
    } catch (error) {
        console.error('Erro ao limpar histórico:', error);
        showToast('Erro ao limpar histórico', 'error');
    }
}

async function uploadAudioFile() {
    const input = $('#audio-upload');
    const file = input.files[0];

    if (!file) return;

    $('#upload-filename').textContent = file.name;

    const formData = new FormData();
    formData.append('audio', file);

    try {
        showToast('Enviando arquivo...', 'info');

        const response = await fetch('/api/transcribe', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            displayTranscription(result.transcription);
            loadTranscriptionHistory();
            showToast('Transcrição concluída!', 'success');
        } else {
            throw new Error(result.error || 'Erro na transcrição');
        }
    } catch (error) {
        console.error('Erro no upload:', error);
        showToast('Erro: ' + error.message, 'error');
    }

    input.value = '';
    $('#upload-filename').textContent = '';
}

async function updateProcessorStatus(result) {
    if (result && result.config) {
        $('#proc-mode').textContent = result.config.mode || '-';
        $('#proc-whisper').textContent = result.config.whisper_model || '-';
        $('#proc-llm').textContent = result.config.llm_provider || '-';
    }
}

async function refreshProcessorStatus() {
    try {
        const result = await apiGet('processor/status');
        if (result.success) {
            updateProcessorStatus(result);
        }

        // Também carregar histórico
        loadTranscriptionHistory();
    } catch (error) {
        console.error('Erro ao obter status:', error);
    }
}

// ==========================================================================
// Transcription Event Listeners
// ==========================================================================

function initTranscriptionListeners() {
    // Botão de gravação
    $('#btn-record').addEventListener('click', startRecording);

    // Botão de upload
    $('#btn-upload').addEventListener('click', () => {
        $('#audio-upload').click();
    });

    // Quando arquivo é selecionado
    $('#audio-upload').addEventListener('change', uploadAudioFile);

    // Limpar histórico
    $('#btn-clear-history').addEventListener('click', clearTranscriptionHistory);
}

// ==========================================================================
// Init
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initEventListeners();
    initTranscriptionListeners();
    loadConfig();

    // Auto-refresh system info every 30s
    setInterval(refreshSystemInfo, 30000);
});

