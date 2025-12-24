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
    const response = await fetch(`/api/${endpoint}`, { cache: 'no-store' });
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
        updateConfigStatus(config);
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
    // Mode removed - system uses provider settings directly

    // System
    if (cfg.system) {
        $('#cache_enabled').checked = cfg.system.cache_enabled !== false;
        $('#memory_logs_enabled').checked = cfg.system.memory_logs_enabled !== false;
        $('#low_memory_mode').checked = cfg.system.low_memory_mode !== false;
        if (cfg.system.log_level) $('#log_level').value = cfg.system.log_level;
        if (cfg.system.timeout) $('#timeout').value = cfg.system.timeout;
        // CPU Limiter
        $('#cpu_limit_enabled').checked = cfg.system.cpu_limit_enabled !== false;
        if (cfg.system.cpu_limit_percent) {
            $('#cpu_limit_percent').value = cfg.system.cpu_limit_percent;
            $('#cpu_limit_value').textContent = cfg.system.cpu_limit_percent;
        }
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

    // Hardware
    if (cfg.hardware) {
        $('#led_enabled').checked = cfg.hardware.led_enabled !== false;
    }

    // Whisper
    if (cfg.whisper) {
        $('#whisper_provider').value = cfg.whisper.provider || 'local';
        updateWhisperSection(cfg.whisper.provider || 'local');
        $('#whisper_model').value = cfg.whisper.model || 'tiny';
        $('#whisper_language').value = cfg.whisper.language || 'pt';
        $('#whisper_use_cpp').checked = cfg.whisper.use_cpp !== false;
        $('#whisper_threads').value = cfg.whisper.threads || 2;  // Default 2 para Pi Zero
        $('#whisper_beam_size').value = cfg.whisper.beam_size || 1;
        $('#whisper_stream_mode').checked = cfg.whisper.stream_mode === true;
        if (cfg.whisper.openai_api_key) {
            $('#whisper_openai_api_key').value = cfg.whisper.openai_api_key;
        }
        // WhisperAPI config
        if (cfg.whisper.whisperapi_url) {
            $('#whisperapi_url').value = cfg.whisper.whisperapi_url;
        }
        if (cfg.whisper.whisperapi_urls && Array.isArray(cfg.whisper.whisperapi_urls)) {
            $('#whisperapi_urls').value = cfg.whisper.whisperapi_urls.join('\n');
        }
        if (cfg.whisper.whisperapi_timeout) {
            $('#whisperapi_timeout').value = cfg.whisper.whisperapi_timeout;
        }
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

        // ChatMock config
        if (cfg.llm.chatmock) {
            $('#chatmock_base_url').value = cfg.llm.chatmock.base_url || 'http://127.0.0.1:8000/v1';
            $('#chatmock_model').value = cfg.llm.chatmock.model || 'gpt-5';
            $('#chatmock_reasoning').value = cfg.llm.chatmock.reasoning_effort || 'medium';
            $('#chatmock_max_tokens').value = cfg.llm.chatmock.max_tokens || 500;
            $('#chatmock_web_search').checked = cfg.llm.chatmock.enable_web_search === true;
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

    // USB Receiver / Escuta Contínua
    if (cfg.usb_receiver) {
        $('#usb_receiver_enabled').checked = cfg.usb_receiver.enabled !== false;
        $('#usb_continuous_listen').checked = cfg.usb_receiver.continuous_listen !== false;
        $('#usb_auto_start').checked = cfg.usb_receiver.auto_start === true;
        $('#usb_auto_process').checked = cfg.usb_receiver.auto_process === true;
        $('#usb_gadget_enabled').checked = cfg.usb_receiver.usb_gadget_enabled === true;
        $('#usb_save_directory').value = cfg.usb_receiver.save_directory || '~/audio-recordings';
        $('#usb_sample_rate').value = cfg.usb_receiver.sample_rate || 44100;
        $('#usb_channels').value = cfg.usb_receiver.channels || 2;
        $('#usb_max_duration').value = cfg.usb_receiver.max_audio_duration || 300;
        $('#usb_auto_transcribe').checked = cfg.usb_receiver.auto_transcribe !== false;
        $('#usb_auto_summarize').checked = cfg.usb_receiver.auto_summarize !== false;
        $('#usb_min_duration').value = cfg.usb_receiver.min_audio_duration || 3;
        $('#usb_silence_split').checked = cfg.usb_receiver.silence_split !== false;
        $('#usb_silence_threshold').value = cfg.usb_receiver.silence_threshold || 2;
        $('#usb_process_on_disconnect').checked = cfg.usb_receiver.process_on_disconnect !== false;
        $('#usb_keep_original').checked = cfg.usb_receiver.keep_original_audio !== false;
    }
}

// Update config status display in Transcription tab
function updateConfigStatus(cfg) {
    // Whisper provider/model
    const whisperProvider = cfg.whisper?.provider || 'local';
    const cfgWhisperProvider = $('#cfg-whisper-provider');
    const cfgWhisperModel = $('#cfg-whisper-model');
    if (cfgWhisperProvider) cfgWhisperProvider.textContent = whisperProvider;
    if (cfgWhisperModel) {
        if (whisperProvider === 'local') {
            cfgWhisperModel.textContent = cfg.whisper?.model || 'tiny';
        } else if (whisperProvider === 'whisperapi') {
            cfgWhisperModel.textContent = 'servidor externo';
        } else if (whisperProvider === 'openai') {
            cfgWhisperModel.textContent = cfg.whisper?.openai_model || 'whisper-1';
        } else {
            cfgWhisperModel.textContent = '-';
        }
    }

    // LLM provider/model
    const llmProvider = cfg.llm?.provider || 'local';
    const cfgLLMProvider = $('#cfg-llm-provider');
    const cfgLLMModel = $('#cfg-llm-model');
    if (cfgLLMProvider) cfgLLMProvider.textContent = llmProvider;
    if (cfgLLMModel) {
        if (llmProvider === 'local') {
            cfgLLMModel.textContent = cfg.llm?.local?.model || 'tinyllama';
        } else if (llmProvider === 'chatmock') {
            cfgLLMModel.textContent = cfg.llm?.chatmock?.model || 'gpt-5';
        } else if (llmProvider === 'openai') {
            cfgLLMModel.textContent = cfg.llm?.openai?.model || 'gpt-4o-mini';
        } else if (llmProvider === 'ollama') {
            cfgLLMModel.textContent = cfg.llm?.ollama?.model || 'ollama';
        } else {
            cfgLLMModel.textContent = '-';
        }
    }

    // Language
    const cfgLanguage = $('#cfg-language');
    if (cfgLanguage) cfgLanguage.textContent = cfg.whisper?.language || 'pt';

    // Remove mode display since we removed operation mode
    const cfgMode = $('#cfg-mode');
    if (cfgMode) cfgMode.textContent = whisperProvider === 'local' ? 'local' : 'api';
}

function collectFormValues() {
    // System uses configured providers directly (no mode selection)

    // System
    if (!config.system) config.system = {};
    config.system.cache_enabled = $('#cache_enabled').checked;
    config.system.memory_logs_enabled = $('#memory_logs_enabled').checked;
    config.system.low_memory_mode = $('#low_memory_mode').checked;
    config.system.log_level = $('#log_level').value;
    config.system.timeout = parseInt($('#timeout').value);
    // CPU Limiter
    config.system.cpu_limit_enabled = $('#cpu_limit_enabled').checked;
    config.system.cpu_limit_percent = parseInt($('#cpu_limit_percent').value);

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
    config.whisper.provider = $('#whisper_provider').value;
    config.whisper.model = $('#whisper_model').value;
    config.whisper.language = $('#whisper_language').value;
    config.whisper.use_cpp = $('#whisper_use_cpp').checked;
    config.whisper.threads = parseInt($('#whisper_threads').value);
    config.whisper.beam_size = parseInt($('#whisper_beam_size').value);
    config.whisper.stream_mode = $('#whisper_stream_mode').checked;
    config.whisper.openai_api_key = $('#whisper_openai_api_key').value;
    config.whisper.whisperapi_url = $('#whisperapi_url').value;

    const urlsText = $('#whisperapi_urls').value;
    if (urlsText) {
        config.whisper.whisperapi_urls = urlsText.split('\n')
            .map(u => u.trim())
            .filter(u => u.length > 0);
    } else {
        config.whisper.whisperapi_urls = [];
    }
    config.whisper.whisperapi_timeout = parseInt($('#whisperapi_timeout').value);

    // LLM
    if (!config.llm) config.llm = {};
    config.llm.provider = $('#llm_provider').value;

    if (!config.llm.local) config.llm.local = {};
    config.llm.local.model = $('#local_model').value;
    config.llm.local.context_size = parseInt($('#local_context_size').value);
    config.llm.local.max_tokens = parseInt($('#local_max_tokens').value);
    config.llm.local.temperature = parseFloat($('#llm_temperature').value);

    // ChatMock config
    if (!config.llm.chatmock) config.llm.chatmock = {};
    config.llm.chatmock.base_url = $('#chatmock_base_url').value;
    config.llm.chatmock.model = $('#chatmock_model').value;
    config.llm.chatmock.reasoning_effort = $('#chatmock_reasoning').value;
    config.llm.chatmock.max_tokens = parseInt($('#chatmock_max_tokens').value);
    config.llm.chatmock.enable_web_search = $('#chatmock_web_search').checked;

    // Hardware
    if (!config.hardware) config.hardware = {};
    config.hardware.led_enabled = $('#led_enabled').checked;

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

    // USB Receiver / Escuta Contínua
    if (!config.usb_receiver) config.usb_receiver = {};
    config.usb_receiver.enabled = $('#usb_receiver_enabled').checked;
    config.usb_receiver.continuous_listen = $('#usb_continuous_listen').checked;
    config.usb_receiver.auto_start = $('#usb_auto_start').checked;
    config.usb_receiver.auto_process = $('#usb_auto_process').checked;
    config.usb_receiver.usb_gadget_enabled = $('#usb_gadget_enabled').checked;
    config.usb_receiver.save_directory = $('#usb_save_directory').value;
    config.usb_receiver.sample_rate = parseInt($('#usb_sample_rate').value);
    config.usb_receiver.channels = parseInt($('#usb_channels').value);
    config.usb_receiver.max_audio_duration = parseInt($('#usb_max_duration').value);
    config.usb_receiver.auto_transcribe = $('#usb_auto_transcribe').checked;
    config.usb_receiver.auto_summarize = $('#usb_auto_summarize').checked;
    config.usb_receiver.min_audio_duration = parseFloat($('#usb_min_duration').value);
    config.usb_receiver.silence_split = $('#usb_silence_split').checked;
    config.usb_receiver.silence_threshold = parseFloat($('#usb_silence_threshold').value);
    config.usb_receiver.process_on_disconnect = $('#usb_process_on_disconnect').checked;
    config.usb_receiver.keep_original_audio = $('#usb_keep_original').checked;
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
    const chatmockConfig = $('#llm-chatmock-config');

    // Esconder todas as seções primeiro
    if (localConfig) localConfig.style.display = 'none';
    if (apiConfig) apiConfig.style.display = 'none';
    if (chatmockConfig) chatmockConfig.style.display = 'none';

    // Mostrar seção apropriada
    if (provider === 'local') {
        if (localConfig) localConfig.style.display = 'block';
    } else if (provider === 'chatmock') {
        if (chatmockConfig) chatmockConfig.style.display = 'block';
    } else {
        if (apiConfig) apiConfig.style.display = 'block';
    }
}

function updateWhisperSection(provider) {
    const localConfig = $('#whisper-local-config');
    const openaiConfig = $('#whisper-openai-config');
    const whisperapiConfig = $('#whisper-whisperapi-config');

    // Esconder todas as seções primeiro
    if (localConfig) localConfig.style.display = 'none';
    if (openaiConfig) openaiConfig.style.display = 'none';
    if (whisperapiConfig) whisperapiConfig.style.display = 'none';

    // Mostrar seção apropriada
    if (provider === 'local') {
        if (localConfig) localConfig.style.display = 'block';
    } else if (provider === 'whisperapi') {
        if (whisperapiConfig) whisperapiConfig.style.display = 'block';
    } else if (provider === 'openai') {
        if (openaiConfig) openaiConfig.style.display = 'block';
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
            if (btn.dataset.tab === 'models') refreshModelStatus();
            if (btn.dataset.tab === 'usb-receiver') {
                refreshListenerStatus();
                refreshLiveTranscriptions();
            }
        });
    });
}

// ==========================================================================
// Event Listeners
// ==========================================================================

function initEventListeners() {
    // Save button
    $('#btn-save').addEventListener('click', saveConfig);

    // Save and Restart button
    $('#btn-save-restart').addEventListener('click', async () => {
        await saveConfig();
        showToast('Reiniciando aplicação...', 'info');
        try {
            await apiPost('restart');
            // Recarregar página após 5 segundos
            setTimeout(() => {
                window.location.reload();
            }, 5000);
        } catch (error) {
            console.error('Erro ao reiniciar:', error);
        }
    });

    // Reload button
    $('#btn-reload').addEventListener('click', loadConfig);

    // LLM provider change
    $('#llm_provider').addEventListener('change', (e) => {
        updateLLMSection(e.target.value);
    });

    // Whisper provider change
    $('#whisper_provider').addEventListener('change', (e) => {
        updateWhisperSection(e.target.value);
    });

    // Range sliders
    $('#vad_aggressiveness').addEventListener('input', (e) => {
        $('#vad_aggressiveness_value').textContent = e.target.value;
    });

    $('#llm_temperature').addEventListener('input', (e) => {
        $('#llm_temperature_value').textContent = e.target.value;
    });

    // Test audio - Obsoleto (substituído por Hardware Tests)
    // $('#btn-test-audio')?.addEventListener('click', testAudio);

    // Refresh buttons
    $('#btn-refresh-system').addEventListener('click', refreshSystemInfo);
    $('#btn-refresh-queue').addEventListener('click', refreshQueueStats);

    // Whisper Tests
    const btnTestWhisperAPI = $('#btn-test-whisperapi');
    if (btnTestWhisperAPI) btnTestWhisperAPI.addEventListener('click', testWhisperAPIConnection);

    const btnTestWhisper = $('#btn-test-whisper');
    if (btnTestWhisper) btnTestWhisper.addEventListener('click', testWhisperTranscription);

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

                // Visualização detalhada de status
                let statusMsg = '';
                if (status.current_stage === 'recording') {
                    statusMsg = '🎙️ Gravando áudio...';
                } else if (status.current_stage === 'transcribing') {
                    const details = status.details || {};
                    statusMsg = `📝 Transcrevendo (${details.model || 'auto'})...`;
                } else if (status.current_stage === 'llm_processing') {
                    const details = status.details || {};
                    statusMsg = `🧠 Processando LLM (${details.provider || 'local'})...`;
                } else if (status.is_processing) {
                    statusMsg = '⚙️ Processando...';
                }

                if (statusMsg) {
                    recordingStatusText.textContent = statusMsg;
                }

                if (status.current_transcription) {
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
                // updateProcessorStatus(result); // Função não definida ou externa
            }
        } catch (error) {
            console.error('Erro no polling:', error);
        }
    }, 500);
}

async function testMicrophone() {
    const btn = $('#btn-test-mic');
    const resultDiv = $('#mic-test-result');
    const audio = new Audio();

    btn.disabled = true;
    btn.textContent = '⏳ Gravando (3s)...';
    resultDiv.innerHTML = '';

    try {
        const response = await fetch('/api/audio/test/mic', { method: 'POST' });

        if (!response.ok) throw new Error('Falha na gravação');

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        audio.src = url;
        audio.controls = true;
        resultDiv.appendChild(audio);

        btn.textContent = '▶️ Reproduzindo...';
        await audio.play();

        audio.onended = () => {
            btn.disabled = false;
            btn.textContent = '🎤 Testar Gravação';
        };

    } catch (error) {
        console.error(error);
        resultDiv.textContent = 'Erro: ' + error.message;
        btn.disabled = false;
        btn.textContent = '🎤 Testar Gravação';
    }
}

async function testSpeaker() {
    const btn = $('#btn-test-speaker');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '🔊 Tocando...';

    try {
        const result = await apiPost('audio/test/speaker', {});
        if (result.success) {
            showToast('Som reproduzido com sucesso', 'success');
        } else {
            showToast('Erro: ' + result.error, 'error');
        }
    } catch (error) {
        showToast('Erro na requisição', 'error');
    } finally {
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = originalText;
        }, 1000);
    }
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
    // Use updateConfigStatus instead - processor status elements were removed
    if (result && result.config) {
        // Config display is now handled by updateConfigStatus
        updateConfigStatus(result.config);
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
// Escuta Contínua
// ==========================================================================

let listenerStatusInterval = null;

async function startListener() {
    try {
        const result = await apiPost('listener/start');
        if (result.success) {
            updateListenerUI(result.status);
            startListenerStatusPolling();
        } else {
            alert(result.error || 'Erro ao iniciar escuta');
        }
    } catch (error) {
        console.error('Erro ao iniciar listener:', error);
        alert('Erro ao iniciar escuta contínua');
    }
}

async function stopListener() {
    try {
        const result = await apiPost('listener/stop');
        if (result.success) {
            updateListenerUI(result.status);
            stopListenerStatusPolling();
        }
    } catch (error) {
        console.error('Erro ao parar listener:', error);
    }
}

async function pauseListener() {
    try {
        const result = await apiPost('listener/pause');
        if (result.success) {
            updateListenerUI(result.status);
        }
    } catch (error) {
        console.error('Erro ao pausar listener:', error);
    }
}

async function resumeListener() {
    try {
        const result = await apiPost('listener/resume');
        if (result.success) {
            updateListenerUI(result.status);
        }
    } catch (error) {
        console.error('Erro ao retomar listener:', error);
    }
}

async function refreshListenerStatus() {
    try {
        const result = await apiGet('listener/status');
        if (result.success) {
            updateListenerUI(result.status);
        }
    } catch (error) {
        console.error('Erro ao obter status do listener:', error);
    }
}

// Note: refreshLiveTranscriptions is defined below in the Transcription UI section

function updateListenerUI(status) {
    const startBtn = $('#btn-listener-start');
    const pauseBtn = $('#btn-listener-pause');
    const stopBtn = $('#btn-listener-stop');
    const stateEl = $('#listener-state');
    const countEl = $('#listener-segments-count');

    if (status.running) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        pauseBtn.disabled = false;

        if (status.paused) {
            stateEl.textContent = 'Pausado';
            stateEl.className = 'status-badge paused';
            pauseBtn.textContent = '▶️ Retomar';
        } else {
            stateEl.textContent = 'Escutando';
            stateEl.className = 'status-badge running';
            pauseBtn.textContent = '⏸️ Pausar';
        }
    } else {
        startBtn.disabled = false;
        pauseBtn.disabled = true;
        stopBtn.disabled = true;
        stateEl.textContent = 'Parado';
        stateEl.className = 'status-badge stopped';
    }

    countEl.textContent = status.segments_count || 0;
}

function startListenerStatusPolling() {
    if (listenerStatusInterval) return;
    listenerStatusInterval = setInterval(() => {
        refreshListenerStatus();
        refreshLiveTranscriptions();
    }, 3000);
}

function stopListenerStatusPolling() {
    if (listenerStatusInterval) {
        clearInterval(listenerStatusInterval);
        listenerStatusInterval = null;
    }
}

// Armazenar segmentos para filtros
let allSegments = [];

function renderLiveTranscriptionsFiltered() {
    const searchQuery = $('#transcription-search')?.value?.toLowerCase() || '';
    const filterDuration = $('#filter-duration')?.value || '';
    const filterWithSummary = $('#filter-with-summary')?.checked;

    let filtered = allSegments;

    // Filtro de busca
    if (searchQuery) {
        filtered = filtered.filter(seg =>
            (seg.text && seg.text.toLowerCase().includes(searchQuery)) ||
            (seg.summary && seg.summary.toLowerCase().includes(searchQuery))
        );
    }

    // Filtro de duração
    if (filterDuration) {
        filtered = filtered.filter(seg => {
            const dur = seg.audio_duration || 0;
            if (filterDuration === 'short') return dur < 10;
            if (filterDuration === 'medium') return dur >= 10 && dur <= 60;
            if (filterDuration === 'long') return dur > 60;
            return true;
        });
    }

    // Filtro com resumo (mostrar todos, não apenas com resumo)
    // Se desmarcado, não filtra

    renderTranscriptionItems(filtered);
    updateTranscriptionCount(filtered.length);
}

function renderTranscriptionItems(segments) {
    const container = $('#live-transcriptions');

    if (!segments || segments.length === 0) {
        container.innerHTML = '<p class="empty-message">Nenhuma transcrição encontrada.</p>';
        return;
    }

    container.innerHTML = segments.slice().reverse().map(seg => `
        <div class="transcription-item" data-id="${seg.timestamp}">
            <div class="timestamp">${new Date(seg.timestamp).toLocaleString('pt-BR')}</div>
            <div class="text">${seg.text || '[Sem texto]'}</div>
            ${seg.summary ? `<div class="summary">📋 ${seg.summary}</div>` : ''}
            <div class="meta">
                ⏱️ ${seg.audio_duration?.toFixed(1)}s | 
                ⚡ ${seg.processing_time?.toFixed(1)}s
                ${seg.audio_file ? `| 🎵 <a href="#" onclick="playAudio('${seg.audio_file}')">${seg.audio_file.split('/').pop()}</a>` : ''}
            </div>
        </div>
    `).join('');
}

function updateTranscriptionCount(count) {
    const countEl = $('#transcription-count');
    if (countEl) {
        countEl.textContent = `${count} transcrição${count !== 1 ? 'ões' : ''}`;
    }
}

async function refreshLiveTranscriptions() {
    try {
        const result = await apiGet('listener/segments?limit=50');
        if (result.success) {
            allSegments = result.segments || [];
            renderLiveTranscriptionsFiltered();
        }
    } catch (error) {
        console.error('Erro ao obter transcrições:', error);
    }
}

function exportTranscriptionsJSON() {
    if (allSegments.length === 0) {
        alert('Nenhuma transcrição para exportar');
        return;
    }

    const data = JSON.stringify(allSegments, null, 2);
    const blob = new Blob([data], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcricoes_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function exportTranscriptionsTXT() {
    if (allSegments.length === 0) {
        alert('Nenhuma transcrição para exportar');
        return;
    }

    const lines = allSegments.map(seg => {
        const date = new Date(seg.timestamp).toLocaleString('pt-BR');
        let txt = `[${date}] (${seg.audio_duration?.toFixed(1)}s)\n`;
        txt += `${seg.text || '[Sem texto]'}\n`;
        if (seg.summary) {
            txt += `\n📋 Resumo: ${seg.summary}\n`;
        }
        txt += '\n---\n';
        return txt;
    }).join('\n');

    const blob = new Blob([lines], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcricoes_${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
}

async function clearAllSegments() {
    if (!confirm('Limpar todas as transcrições?')) return;

    try {
        // Chamar API para limpar (se existir)
        await apiPost('listener/stop');
        allSegments = [];
        renderLiveTranscriptionsFiltered();
    } catch (error) {
        console.error('Erro ao limpar:', error);
    }
}

function initListenerControls() {
    // Botões de controle
    $('#btn-listener-start').addEventListener('click', startListener);
    $('#btn-listener-stop').addEventListener('click', stopListener);

    $('#btn-listener-pause').addEventListener('click', () => {
        const pauseBtn = $('#btn-listener-pause');
        if (pauseBtn.textContent.includes('Pausar')) {
            pauseListener();
        } else {
            resumeListener();
        }
    });

    $('#btn-refresh-transcriptions').addEventListener('click', refreshLiveTranscriptions);

    // Filtros e busca
    const searchInput = $('#transcription-search');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(renderLiveTranscriptionsFiltered, 300));
    }

    const filterDuration = $('#filter-duration');
    if (filterDuration) {
        filterDuration.addEventListener('change', renderLiveTranscriptionsFiltered);
    }

    const filterSummary = $('#filter-with-summary');
    if (filterSummary) {
        filterSummary.addEventListener('change', renderLiveTranscriptionsFiltered);
    }

    // Exportação
    const btnExportJSON = $('#btn-export-json');
    if (btnExportJSON) {
        btnExportJSON.addEventListener('click', exportTranscriptionsJSON);
    }

    const btnExportTXT = $('#btn-export-txt');
    if (btnExportTXT) {
        btnExportTXT.addEventListener('click', exportTranscriptionsTXT);
    }

    const btnClear = $('#btn-clear-segments');
    if (btnClear) {
        btnClear.addEventListener('click', clearAllSegments);
    }

    // Carregar status inicial
    refreshListenerStatus();
    refreshLiveTranscriptions();
}

// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==========================================================================
// Gerenciamento de Modelos
// ==========================================================================

let downloadPollingInterval = null;

async function refreshModelStatus() {
    try {
        const result = await apiGet('models/status');
        if (result.success) {
            // Atualizar status modelos Whisper
            for (const [model, installed] of Object.entries(result.whisper || {})) {
                const statusEl = $(`#whisper-${model}-status`);
                const cardEl = document.querySelector(`#whisper-models [data-model="${model}"]`);
                if (statusEl) {
                    statusEl.textContent = installed ? '✅' : '❌';
                }
                if (cardEl) {
                    cardEl.classList.toggle('installed', installed);
                }
            }

            // Atualizar status modelos LLM
            for (const [model, installed] of Object.entries(result.llm || {})) {
                const statusEl = $(`#llm-${model}-status`);
                const cardEl = document.querySelector(`#llm-models [data-model="${model}"]`);
                if (statusEl) {
                    statusEl.textContent = installed ? '✅' : '❌';
                }
                if (cardEl) {
                    cardEl.classList.toggle('installed', installed);
                }
            }

            // Atualizar status dos executáveis
            if (result.executables) {
                const whisperReady = result.executables.whisper_cpp_ready;
                const llamaReady = result.executables.llama_cpp_ready;

                // Atualizar indicadores se existirem
                const whisperExeStatus = $('#whisper-exe-status');
                const llamaExeStatus = $('#llama-exe-status');

                if (whisperExeStatus) {
                    whisperExeStatus.textContent = whisperReady ? '✅ Compilado' : '❌ Não compilado';
                    whisperExeStatus.className = whisperReady ? 'exe-status ready' : 'exe-status not-ready';
                }
                if (llamaExeStatus) {
                    llamaExeStatus.textContent = llamaReady ? '✅ Compilado' : '❌ Não compilado';
                    llamaExeStatus.className = llamaReady ? 'exe-status ready' : 'exe-status not-ready';
                }

                // Console log para debug
                console.log('Executables status:', result.executables);
            }

            // Atualizar progresso de download
            updateDownloadProgress(result.download);
        }
    } catch (error) {
        console.error('Erro ao obter status dos modelos:', error);
    }
}

function updateDownloadProgress(download) {
    const progressDiv = $('#download-progress');
    const progressFill = $('#download-progress-fill');
    const progressText = $('#download-progress-text');

    if (!progressDiv) return;

    if (download && download.downloading) {
        progressDiv.style.display = 'block';
        progressFill.style.width = `${download.progress}%`;
        progressText.textContent = `Baixando ${download.model}... ${download.progress}%`;

        // Iniciar polling se não estiver ativo
        if (!downloadPollingInterval) {
            downloadPollingInterval = setInterval(pollDownloadProgress, 2000);
        }
    } else {
        if (download && download.error) {
            progressText.textContent = `Erro: ${download.error}`;
            progressFill.style.width = '0%';
        } else if (download && download.progress === 100) {
            progressText.textContent = 'Download concluído!';
            setTimeout(() => {
                progressDiv.style.display = 'none';
                refreshModelStatus();
            }, 2000);
        } else {
            progressDiv.style.display = 'none';
        }

        // Parar polling
        if (downloadPollingInterval) {
            clearInterval(downloadPollingInterval);
            downloadPollingInterval = null;
        }
    }
}

async function pollDownloadProgress() {
    try {
        const result = await apiGet('models/download/status');
        if (result.success) {
            updateDownloadProgress(result);
        }
    } catch (error) {
        console.error('Erro ao obter progresso:', error);
    }
}

async function downloadWhisperModel(model) {
    try {
        const result = await apiPost(`models/download/whisper/${model}`);
        if (result.success) {
            refreshModelStatus();
        } else {
            alert(result.error || 'Erro ao iniciar download');
        }
    } catch (error) {
        console.error('Erro ao baixar modelo:', error);
        alert('Erro ao iniciar download');
    }
}

async function downloadLLMModel(model) {
    try {
        const result = await apiPost(`models/download/llm/${model}`);
        if (result.success) {
            refreshModelStatus();
        } else {
            alert(result.error || 'Erro ao iniciar download');
        }
    } catch (error) {
        console.error('Erro ao baixar modelo:', error);
        alert('Erro ao iniciar download');
    }
}

// ==========================================================================
// Batch Processor & Files Tab
// ==========================================================================

let currentViewingFile = null;

async function refreshBatchStatus() {
    try {
        const result = await apiGet('batch/status');
        if (result.success) {
            updateBatchUI(result.status);
        }
    } catch (error) {
        console.error('Erro ao obter status do batch:', error);
    }
}

function updateBatchUI(status) {
    const stateEl = $('#batch-state');
    const pendingEl = $('#batch-pending');
    const processedEl = $('#batch-processed');
    const failedEl = $('#batch-failed');
    const lastRunEl = $('#batch-last-run');
    const nextRunEl = $('#batch-next-run');
    const startBtn = $('#btn-batch-start');
    const stopBtn = $('#btn-batch-stop');

    if (stateEl) {
        if (status.is_processing) {
            stateEl.textContent = 'Processando...';
            stateEl.className = 'status-badge running';
        } else if (status.running) {
            stateEl.textContent = 'Automático Ativo';
            stateEl.className = 'status-badge running';
        } else {
            stateEl.textContent = 'Parado';
            stateEl.className = 'status-badge stopped';
        }
    }

    if (pendingEl) pendingEl.textContent = status.pending_files || 0;
    if (processedEl) processedEl.textContent = status.processed_files || 0;
    if (failedEl) failedEl.textContent = status.failed_files || 0;

    if (lastRunEl) {
        lastRunEl.textContent = status.last_run
            ? new Date(status.last_run).toLocaleString('pt-BR')
            : '-';
    }

    if (nextRunEl) {
        nextRunEl.textContent = status.next_run
            ? new Date(status.next_run).toLocaleString('pt-BR')
            : '-';
    }

    if (startBtn && stopBtn) {
        startBtn.disabled = status.running;
        stopBtn.disabled = !status.running;
    }
}

async function runBatchProcess() {
    try {
        const result = await apiPost('batch/run');
        if (result.success) {
            showToast('Processamento iniciado!', 'success');
            // Poll for updates
            setTimeout(refreshBatchStatus, 2000);
            setTimeout(refreshBatchStatus, 5000);
            setTimeout(refreshTranscriptionFiles, 5000);
        } else {
            showToast(result.error || 'Erro', 'error');
        }
    } catch (error) {
        console.error('Erro ao executar batch:', error);
        showToast('Erro ao executar processamento', 'error');
    }
}

async function startBatchAutomatic() {
    try {
        const result = await apiPost('batch/start');
        if (result.success) {
            showToast('Processamento automático iniciado!', 'success');
            refreshBatchStatus();
        } else {
            showToast(result.error || 'Erro', 'error');
        }
    } catch (error) {
        console.error('Erro ao iniciar batch automático:', error);
        showToast('Erro ao iniciar', 'error');
    }
}

async function stopBatchAutomatic() {
    try {
        const result = await apiPost('batch/stop');
        if (result.success) {
            showToast('Processamento automático parado', 'info');
            refreshBatchStatus();
        }
    } catch (error) {
        console.error('Erro ao parar batch:', error);
    }
}

async function refreshTranscriptionFiles() {
    try {
        const result = await apiGet('files/transcriptions');
        if (result.success) {
            renderFilesList(result.files);
            $('#files-count').textContent = `${result.total} arquivos`;

            // Também atualizar pendentes no batch status
            if ($('#batch-pending')) {
                $('#batch-pending').textContent = result.pending_wav || 0;
            }
        }
    } catch (error) {
        console.error('Erro ao carregar arquivos:', error);
        $('#files-list').innerHTML = '<p class="empty-message">Erro ao carregar arquivos</p>';
    }
}

function renderFilesList(files) {
    const container = $('#files-list');

    if (!files || files.length === 0) {
        container.innerHTML = '<p class="empty-message">Nenhuma transcrição salva ainda.</p>';
        return;
    }

    container.innerHTML = files.map(f => `
        <div class="file-item" data-name="${f.name}">
            <div class="file-info">
                <span class="file-name">📄 ${f.name}</span>
                <span class="file-meta">
                    ${new Date(f.created).toLocaleString('pt-BR')} | 
                    ${formatBytes(f.size)}
                    ${f.audio_duration ? ` | ${f.audio_duration.toFixed(1)}s áudio` : ''}
                </span>
            </div>
            <div class="file-actions">
                <button class="btn btn-small" onclick="viewFile('${f.name}')">👁️ Ver</button>
                <button class="btn btn-small btn-danger" onclick="deleteFile('${f.name}')">🗑️</button>
            </div>
        </div>
    `).join('');
}

async function viewFile(filename) {
    try {
        const result = await apiGet(`files/transcriptions/${encodeURIComponent(filename)}`);
        if (result.success) {
            currentViewingFile = filename;
            $('#modal-filename').textContent = filename;
            $('#modal-file-content').textContent = result.content;
            $('#file-view-modal').style.display = 'flex';
        } else {
            showToast('Arquivo não encontrado', 'error');
        }
    } catch (error) {
        console.error('Erro ao ler arquivo:', error);
        showToast('Erro ao ler arquivo', 'error');
    }
}

function closeFileModal() {
    $('#file-view-modal').style.display = 'none';
    currentViewingFile = null;
}

async function deleteFile(filename) {
    if (!confirm(`Deletar ${filename}?`)) return;

    try {
        const response = await fetch(`/api/files/transcriptions/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });
        const result = await response.json();

        if (result.success) {
            showToast('Arquivo deletado!', 'success');
            refreshTranscriptionFiles();

            // Fechar modal se era o arquivo sendo visualizado
            if (currentViewingFile === filename) {
                closeFileModal();
            }
        } else {
            showToast(result.error || 'Erro ao deletar', 'error');
        }
    } catch (error) {
        console.error('Erro ao deletar:', error);
        showToast('Erro ao deletar arquivo', 'error');
    }
}

async function deleteAllTranscriptions() {
    const confirmMsg = 'Tem certeza que deseja apagar TODOS os arquivos de transcrição (.txt)?\n\nEsta ação não pode ser desfeita!';
    if (!confirm(confirmMsg)) return;

    try {
        showToast('Apagando arquivos...', 'info');

        const response = await fetch('/api/files/transcriptions/all', {
            method: 'DELETE'
        });
        const result = await response.json();

        if (result.success) {
            showToast(`${result.deleted_count} arquivos deletados!`, 'success');
            refreshTranscriptionFiles();
            closeFileModal();
        } else {
            showToast(result.error || 'Erro ao deletar', 'error');
        }
    } catch (error) {
        console.error('Erro ao deletar todos:', error);
        showToast('Erro ao deletar arquivos', 'error');
    }
}

async function searchTranscriptionFiles() {
    const query = $('#files-search-input').value.trim();

    if (!query) {
        // Limpar busca, mostrar todos
        $('#search-results').style.display = 'none';
        refreshTranscriptionFiles();
        return;
    }

    try {
        const result = await apiGet(`files/search?q=${encodeURIComponent(query)}`);
        if (result.success) {
            renderSearchResults(result.results, query);
        }
    } catch (error) {
        console.error('Erro na busca:', error);
        showToast('Erro na busca', 'error');
    }
}

function renderSearchResults(results, query) {
    const container = $('#search-results');
    const listEl = $('#search-results-list');

    container.style.display = 'block';

    if (!results || results.length === 0) {
        listEl.innerHTML = `<p class="empty-message">Nenhum resultado para "${query}"</p>`;
        return;
    }

    listEl.innerHTML = results.map(r => `
        <div class="search-result-item" onclick="viewFile('${r.filename}')">
            <div class="result-filename">📄 ${r.filename}</div>
            <div class="result-meta">${new Date(r.created).toLocaleString('pt-BR')} | ${r.matches} ocorrências</div>
            <div class="result-preview">${highlightQuery(r.preview, query)}</div>
        </div>
    `).join('');
}

function highlightQuery(text, query) {
    if (!text || !query) return text || '';
    const regex = new RegExp(`(${query})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

function clearFileSearch() {
    $('#files-search-input').value = '';
    $('#search-results').style.display = 'none';
    refreshTranscriptionFiles();
}

function initFilesTab() {
    // Botões de batch
    const btnBatchRun = $('#btn-batch-run');
    if (btnBatchRun) {
        btnBatchRun.addEventListener('click', runBatchProcess);
    }

    const btnBatchStart = $('#btn-batch-start');
    if (btnBatchStart) {
        btnBatchStart.addEventListener('click', startBatchAutomatic);
    }

    const btnBatchStop = $('#btn-batch-stop');
    if (btnBatchStop) {
        btnBatchStop.addEventListener('click', stopBatchAutomatic);
    }

    // Busca
    const btnSearch = $('#btn-files-search');
    if (btnSearch) {
        btnSearch.addEventListener('click', searchTranscriptionFiles);
    }

    const searchInput = $('#files-search-input');
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                searchTranscriptionFiles();
            }
        });
    }

    const btnClearSearch = $('#btn-clear-search');
    if (btnClearSearch) {
        btnClearSearch.addEventListener('click', clearFileSearch);
    }

    // Refresh
    const btnRefresh = $('#btn-files-refresh');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => {
            refreshBatchStatus();
            refreshTranscriptionFiles();
        });
    }

    // Modal delete button
    const btnModalDelete = $('#btn-modal-delete');
    if (btnModalDelete) {
        btnModalDelete.addEventListener('click', () => {
            if (currentViewingFile) {
                deleteFile(currentViewingFile);
            }
        });
    }

    // Fechar modal ao clicar fora
    const modal = $('#file-view-modal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                closeFileModal();
            }
        });
    }

    // Carregar dados iniciais
    refreshBatchStatus();
    refreshTranscriptionFiles();
}

// ==========================================================================
// Systemd Auto-Start Control
// ==========================================================================

async function checkSystemdAutoStart() {
    try {
        const result = await apiGet('system/autostart');
        const checkbox = $('#autostart_enabled');
        const statusDiv = $('#autostart-status');

        if (checkbox && result.success) {
            checkbox.checked = result.enabled;
            if (statusDiv) {
                if (result.status === 'not_available') {
                    statusDiv.textContent = '⚠️ Systemd não disponível';
                    statusDiv.style.color = 'var(--warning)';
                } else {
                    statusDiv.textContent = result.enabled ? '✅ Serviço habilitado no boot' : '❌ Serviço desabilitado no boot';
                    statusDiv.style.color = result.enabled ? 'var(--success)' : 'var(--text-muted)';
                }
            }
        }
    } catch (error) {
        console.error('Erro ao verificar autostart:', error);
    }
}

async function toggleAutoStart(enable) {
    const statusDiv = $('#autostart-status');

    try {
        if (statusDiv) {
            statusDiv.textContent = '⏳ Alterando...';
            statusDiv.style.color = 'var(--primary)';
        }

        const result = await apiPost('system/autostart', { enable });

        if (result.success) {
            showToast(result.message, 'success');
            if (statusDiv) {
                statusDiv.textContent = enable ? '✅ Serviço habilitado no boot' : '❌ Serviço desabilitado no boot';
                statusDiv.style.color = enable ? 'var(--success)' : 'var(--text-muted)';
            }
        } else {
            showToast('Erro: ' + result.error, 'error');
            // Reverter checkbox
            const checkbox = $('#autostart_enabled');
            if (checkbox) checkbox.checked = !enable;
            checkSystemdAutoStart();
        }
    } catch (error) {
        showToast('Erro de rede', 'error');
        const checkbox = $('#autostart_enabled');
        if (checkbox) checkbox.checked = !enable;
    }
}

// ==========================================================================
// USB Receiver Auto-Start (Auto-Start Feature)
// ==========================================================================

async function checkAutoStart() {
    try {
        const result = await apiGet('config');
        if (result && result.usb_receiver) {
            const usbConfig = result.usb_receiver;

            // Se auto_start está habilitado, iniciar escuta automaticamente
            if (usbConfig.auto_start && usbConfig.enabled) {
                console.log('🚀 Auto-start habilitado, iniciando escuta...');

                // Iniciar escuta contínua
                await startListener();

                // Também iniciar batch processor se configurado
                if (usbConfig.auto_process) {
                    await startBatchAutomatic();
                }

                showToast('Escuta automática iniciada!', 'success');
            }
        }
    } catch (error) {
        console.error('Erro ao verificar auto-start:', error);
    }
}

// ==========================================================================
// Logs Tab
// ==========================================================================

let logsAutoRefreshInterval = null;

async function loadLogs(errorsOnly = false) {
    try {
        const level = errorsOnly ? 'ERROR' : ($('#logs-level-filter')?.value || '');
        const limit = parseInt($('#logs-limit')?.value || 100);

        const url = errorsOnly
            ? `logs/errors?limit=${limit}`
            : `logs?level=${level}&limit=${limit}`;

        const result = await apiGet(url);

        if (result.success) {
            if (errorsOnly) {
                renderLogs(result.errors || []);
            } else {
                renderLogs(result.logs || []);
                updateLogStats(result.stats);
            }

            // Atualizar timestamp
            const now = new Date().toLocaleTimeString('pt-BR');
            const updateEl = $('#logs-last-update');
            if (updateEl) updateEl.textContent = `Atualizado: ${now}`;
        }
    } catch (error) {
        console.error('Erro ao carregar logs:', error);
        $('#logs-list').innerHTML = '<p class="empty-message">Erro ao carregar logs</p>';
    }
}

function updateLogStats(stats) {
    if (!stats) return;

    const totalEl = $('#logs-total');
    const errorsEl = $('#logs-errors');
    const warningsEl = $('#logs-warnings');

    if (totalEl) totalEl.textContent = stats.total || 0;
    if (errorsEl) errorsEl.textContent = stats.errors || 0;
    if (warningsEl) warningsEl.textContent = stats.warnings || 0;
}

function renderLogs(logs) {
    const container = $('#logs-list');
    if (!container) return;

    if (!logs || logs.length === 0) {
        container.innerHTML = '<p class="empty-message">Nenhum log encontrado</p>';
        return;
    }

    container.innerHTML = logs.map(log => {
        const levelClass = log.level?.toLowerCase() || 'info';
        const timestamp = log.timestamp ? new Date(log.timestamp).toLocaleString('pt-BR') : '';

        return `
            <div class="log-entry ${levelClass}">
                <div class="log-header">
                    <span class="log-level ${levelClass}">${log.level}</span>
                    <span class="log-time">${timestamp}</span>
                    <span class="log-logger">${log.logger || ''}</span>
                </div>
                <div class="log-message">${escapeHtml(log.raw_message || log.message || '')}</div>
                ${log.exception ? `<pre class="log-exception">${escapeHtml(log.exception)}</pre>` : ''}
            </div>
        `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function clearLogs() {
    if (!confirm('Limpar todos os logs em memória?')) return;

    try {
        const result = await apiPost('logs/clear');
        if (result.success) {
            showToast('Logs limpos!', 'success');
            loadLogs();
        }
    } catch (error) {
        console.error('Erro ao limpar logs:', error);
        showToast('Erro ao limpar logs', 'error');
    }
}

function toggleLogsAutoRefresh() {
    const checkbox = $('#logs-auto-refresh');

    if (checkbox?.checked) {
        logsAutoRefreshInterval = setInterval(loadLogs, 5000);
        showToast('Auto-refresh ativado', 'info');
    } else {
        if (logsAutoRefreshInterval) {
            clearInterval(logsAutoRefreshInterval);
            logsAutoRefreshInterval = null;
        }
    }
}

function initLogsTab() {
    const refreshBtn = $('#btn-refresh-logs');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => loadLogs());
    }

    const errorsBtn = $('#btn-errors-only');
    if (errorsBtn) {
        errorsBtn.addEventListener('click', () => loadLogs(true));
    }

    const clearBtn = $('#btn-clear-logs');
    if (clearBtn) {
        clearBtn.addEventListener('click', clearLogs);
    }

    const levelFilter = $('#logs-level-filter');
    if (levelFilter) {
        levelFilter.addEventListener('change', () => loadLogs());
    }

    const autoRefresh = $('#logs-auto-refresh');
    if (autoRefresh) {
        autoRefresh.addEventListener('change', toggleLogsAutoRefresh);
    }

    // Carregar logs quando a aba for aberta
    const logsTabBtn = document.querySelector('[data-tab="logs"]');
    if (logsTabBtn) {
        logsTabBtn.addEventListener('click', () => loadLogs());
    }
}

async function testWhisperAPIConnection() {
    const btn = $('#btn-test-whisperapi');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳ Conectando...';

    try {
        const result = await apiPost('test/whisperapi_connection', {});
        if (result.success) {
            showToast(result.message, 'success');
        } else {
            showToast('Erro: ' + result.error, 'error');
        }
    } catch (error) {
        showToast('Erro de rede', 'error');
    } finally {
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = originalText;
        }, 1000);
    }
}

async function testWhisperTranscription() {
    const btn = $('#btn-test-whisper');
    const stateBox = $('#whisper-test-state');
    const stateIcon = $('#test-state-icon');
    const stateMessage = $('#test-state-message');
    const stateCountdown = $('#test-state-countdown');
    const resultDiv = $('#whisper-test-result');
    const textDiv = $('#whisper-test-text');
    const timingDiv = $('#whisper-test-timing');
    const durationSelect = $('#test_duration');

    const originalText = btn.textContent;
    const duration = parseInt(durationSelect?.value || '5', 10);

    // Reset states
    btn.disabled = true;
    resultDiv.style.display = 'none';
    resultDiv.classList.remove('error');
    stateBox.className = 'test-state-box';
    stateBox.style.display = 'block';

    // Phase 1: Prepare (show prompt to speak)
    stateIcon.textContent = '🎙️';
    stateMessage.textContent = '🔊 FALE AGORA!';
    stateCountdown.textContent = duration + 's';
    stateBox.classList.add('recording');

    try {
        // Start countdown animation
        let countdown = duration;
        const countdownInterval = setInterval(() => {
            countdown--;
            if (countdown > 0) {
                stateCountdown.textContent = countdown + 's';
            } else {
                // Phase 2: Transcribing
                stateBox.classList.remove('recording');
                stateBox.classList.add('transcribing');
                stateIcon.textContent = '⏳';
                stateMessage.textContent = 'Transcrevendo...';
                stateCountdown.textContent = '';
                clearInterval(countdownInterval);
            }
        }, 1000);

        // Make API call (this runs in parallel with countdown)
        const result = await apiPost('test/whisper_transcription', { duration });
        clearInterval(countdownInterval);

        if (result.success) {
            // Phase 3: Success
            stateBox.classList.remove('recording', 'transcribing');
            stateBox.classList.add('success');
            stateIcon.textContent = '✅';
            stateMessage.textContent = 'Transcrição concluída!';
            stateCountdown.textContent = '';

            // Wait a moment then show result
            await sleep(800);
            stateBox.style.display = 'none';

            // Display result
            textDiv.textContent = result.text || '(Nenhum texto detectado)';

            const timing = result.timing || {};
            timingDiv.innerHTML = `
                <span>🎤 Gravação: ${timing.record_seconds || 0}s</span>
                <span>🤖 Transcrição: ${timing.transcribe_seconds || 0}s</span>
                <span>⏱️ Total: ${timing.total_seconds || 0}s</span>
                <span>🌍 Idioma: ${result.language || 'auto'}</span>
                <span>📡 Provider: ${result.provider || 'local'}</span>
            `;

            resultDiv.querySelector('h4').textContent = '✅ Resultado:';
            resultDiv.style.display = 'block';
            showToast('Transcrição concluída!', 'success');
        } else {
            // Error state
            stateBox.style.display = 'none';
            textDiv.textContent = result.error || 'Erro desconhecido';
            timingDiv.innerHTML = '';
            resultDiv.classList.add('error');
            resultDiv.querySelector('h4').textContent = '❌ Erro:';
            resultDiv.style.display = 'block';
            showToast('Erro: ' + result.error, 'error');
        }
    } catch (error) {
        stateBox.style.display = 'none';
        textDiv.textContent = 'Erro de rede: ' + error.message;
        timingDiv.innerHTML = '';
        resultDiv.classList.add('error');
        resultDiv.querySelector('h4').textContent = '❌ Erro:';
        resultDiv.style.display = 'block';
        showToast('Erro de rede', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

// Helper function for delays
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ==========================================================================
// LLM Testing & Models
// ==========================================================================

async function testLLMConnection() {
    const btn = $('#btn-test-llm');
    const resultDiv = $('#llm-test-result');
    const originalText = btn.textContent;

    try {
        btn.textContent = '⏳ Testando...';
        btn.disabled = true;
        resultDiv.style.display = 'none';

        // Save first to ensure server has latest config
        collectFormValues();
        const response = await apiPost('test/llm', config);

        if (response.success) {
            showToast(`Sucesso! Latência: ${response.latency.toFixed(2)}s`, 'success');
            resultDiv.style.display = 'block';
            resultDiv.style.color = '#4ade80';
            resultDiv.textContent = `Resposta: "${response.response}"\nLatência: ${response.latency.toFixed(3)}s`;
        } else {
            throw new Error(response.error);
        }
    } catch (error) {
        showToast('Erro no teste: ' + error.message, 'error');
        resultDiv.style.display = 'block';
        resultDiv.style.color = '#ef4444';
        resultDiv.textContent = `Erro: ${error.message}`;
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

async function fetchLLMModels(provider) {
    try {
        showToast('Buscando modelos... (Salve a config antes se alterou URL/Key)', 'info');

        // Auto-save if dirty to ensure backend has correct URL
        if (isDirty) {
            await saveConfig();
        }

        const response = await apiGet('llm/models');

        if (response.error) throw new Error(response.error);

        const models = response.models;
        if (!models || models.length === 0) {
            showToast('Nenhum modelo encontrado.', 'warning');
            return;
        }

        showToast(`${models.length} modelos encontrados!`, 'success');

        if (provider === 'chatmock') {
            const select = $('#chatmock_model');
            const current = select.value;
            select.innerHTML = '';

            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (m === current) opt.selected = true;
                select.appendChild(opt);
            });
            if (!models.includes(current) && current) {
                const opt = document.createElement('option');
                opt.value = current;
                opt.textContent = `${current} (Atual)`;
                opt.selected = true;
                select.appendChild(opt);
            }
        } else if (provider === 'openai') {
            const input = $('#api_model');
            let datalist = $('#openai_models_list');
            if (!datalist) {
                datalist = document.createElement('datalist');
                datalist.id = 'openai_models_list';
                document.body.appendChild(datalist);
                input.setAttribute('list', 'openai_models_list');
            }

            datalist.innerHTML = '';
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                datalist.appendChild(opt);
            });
            input.focus();
        }

    } catch (error) {
        showToast('Erro ao buscar modelos: ' + error.message, 'error');
    }
}

async function testLivePipeline() {
    const btn = $('#btn-test-live');
    const resultDiv = $('#live-test-result');
    const originalText = btn.textContent;
    const includeLLM = $('#test-include-llm').checked;

    try {
        btn.textContent = '🎙️ Gravando (5s)...';
        btn.disabled = true;
        resultDiv.style.display = 'none';

        if (isDirty) await saveConfig();

        // Wait for config save
        await new Promise(r => setTimeout(r, 200));

        const response = await apiPost('test/live', {
            duration: 5.0,
            generate_summary: includeLLM
        });

        btn.textContent = '⚙️ Processando...';

        if (response.success) {
            showToast('Teste concluído!', 'success');
            resultDiv.style.display = 'block';
            resultDiv.style.color = '#e2e8f0';

            let html = `<strong>Transcrição:</strong><br>${response.text}<br><br>`;
            if (response.summary && response.summary !== "(Ignorado)") {
                html += `<strong>Resumo:</strong><br>${response.summary}<br><br>`;
            }

            html += `<small style="color:#888">
                    Processamento: ${response.stats.transcription.processing_time.toFixed(2)}s | 
                    LLM: ${response.stats.summary_time ? response.stats.summary_time.toFixed(2) : '0.00'}s
                </small>`;

            resultDiv.innerHTML = html;
        } else {
            throw new Error(response.error);
        }
    } catch (error) {
        showToast('Erro no teste live: ' + error.message, 'error');
        resultDiv.style.display = 'block';
        resultDiv.style.color = '#ef4444';
        resultDiv.textContent = `Erro: ${error.message}`;
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// ==========================================================================
// History Tab
// ==========================================================================

let historyTranscriptions = [];
let currentLLMTranscriptionId = null;

async function loadHistoryByDate(dateStr) {
    const timeline = $('#history-timeline');
    if (!timeline) return;

    timeline.innerHTML = '<p class="loading">Carregando...</p>';

    try {
        const result = await apiGet(`transcriptions/daily/${dateStr}`);

        if (result.success) {
            historyTranscriptions = result.transcriptions || [];
            updateHistoryStats(result);
            renderHistoryTimeline(historyTranscriptions);
        } else {
            timeline.innerHTML = `<p class="error-message">${result.error}</p>`;
        }
    } catch (error) {
        console.error('Erro ao carregar histórico:', error);
        timeline.innerHTML = '<p class="error-message">Erro ao carregar histórico.</p>';
    }
}

async function searchHistory(query) {
    const timeline = $('#history-timeline');
    if (!timeline) return;

    timeline.innerHTML = '<p class="loading">Buscando...</p>';

    try {
        const result = await apiPost('transcriptions/search', { query, limit: 100 });

        if (result.success) {
            historyTranscriptions = result.results || [];
            renderHistoryTimeline(historyTranscriptions);
            $('#history-total').textContent = result.total;
            $('#history-count').textContent = `${result.total} resultados para "${query}"`;
        } else {
            timeline.innerHTML = `<p class="error-message">${result.error}</p>`;
        }
    } catch (error) {
        console.error('Erro na busca:', error);
        timeline.innerHTML = '<p class="error-message">Erro na busca.</p>';
    }
}

function updateHistoryStats(data) {
    const total = data.total_transcriptions || data.transcriptions?.length || 0;
    const durationSec = data.total_duration_seconds ||
        (data.transcriptions || []).reduce((sum, t) => sum + (t.duration_seconds || 0), 0);
    const words = (data.transcriptions || [])
        .reduce((sum, t) => sum + (t.text || '').split(/\s+/).length, 0);

    $('#history-total').textContent = total;
    $('#history-duration').textContent = formatDuration(durationSec);
    $('#history-words').textContent = words;
}

function formatDuration(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${minutes % 60}m`;
}

function renderHistoryTimeline(transcriptions) {
    const timeline = $('#history-timeline');
    if (!timeline) return;

    if (!transcriptions || transcriptions.length === 0) {
        timeline.innerHTML = '<p class="empty-message">Nenhuma transcrição encontrada.</p>';
        $('#history-count').textContent = '0 transcrições';
        return;
    }

    timeline.innerHTML = transcriptions.map(t => {
        const time = t.timestamp ? new Date(t.timestamp).toLocaleTimeString('pt-BR') : '--:--:--';
        const duration = t.duration_seconds ? `${t.duration_seconds.toFixed(1)}s` : '';
        const preview = (t.text || '').substring(0, 200);
        const hasLLM = t.llm_result ? '✅' : '';

        return `
            <div class="timeline-item" data-id="${t.id}">
                <div class="timeline-time">${time}</div>
                <div class="timeline-content">
                    <div class="timeline-header">
                        <span class="timeline-duration">⏱️ ${duration}</span>
                        <span class="timeline-provider">${t.processed_by || 'local'}</span>
                        ${hasLLM}
                    </div>
                    <div class="timeline-text">${preview}${t.text?.length > 200 ? '...' : ''}</div>
                    <div class="timeline-actions">
                        <button class="btn btn-small" onclick="showFullTranscription('${t.id}')">👁️ Ver</button>
                        <button class="btn btn-small" onclick="openLLMModal('${t.id}')">🤖 LLM</button>
                        <button class="btn btn-small btn-danger" onclick="deleteTranscription('${t.id}')">🗑️</button>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    $('#history-count').textContent = `${transcriptions.length} transcrições`;
}

function showFullTranscription(id) {
    const t = historyTranscriptions.find(x => x.id === id);
    if (!t) return;

    alert(`[${new Date(t.timestamp).toLocaleString('pt-BR')}]\n\n${t.text}\n\n${t.llm_result ? '--- LLM ---\n' + t.llm_result : ''}`);
}

function openLLMModal(id) {
    const t = historyTranscriptions.find(x => x.id === id);
    if (!t) return;

    currentLLMTranscriptionId = id;
    $('#llm-input-text').textContent = t.text;
    $('#llm-result').textContent = '';
    $('#llm-result-container').style.display = 'none';
    $('#llm-modal').style.display = 'flex';
}

function closeLLMModal() {
    $('#llm-modal').style.display = 'none';
    currentLLMTranscriptionId = null;
}

async function processWithLLM() {
    if (!currentLLMTranscriptionId) return;

    const prompt = $('#llm-prompt').value;
    const btn = $('#btn-process-llm');
    btn.disabled = true;
    btn.textContent = '⏳ Processando...';

    try {
        const result = await apiPost(`transcriptions/${currentLLMTranscriptionId}/llm`, { prompt });

        if (result.success) {
            $('#llm-result').textContent = result.result;
            $('#llm-result-container').style.display = 'block';
            showToast('Processamento LLM concluído!', 'success');

            // Atualizar na lista local
            const t = historyTranscriptions.find(x => x.id === currentLLMTranscriptionId);
            if (t) t.llm_result = result.result;
        } else {
            showToast('Erro: ' + result.error, 'error');
        }
    } catch (error) {
        showToast('Erro de conexão', 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🚀 Processar';
    }
}

async function deleteTranscription(id) {
    if (!confirm('Deletar esta transcrição?')) return;

    try {
        const result = await fetch(`/api/transcriptions/${id}`, { method: 'DELETE' }).then(r => r.json());

        if (result.success) {
            showToast('Transcrição removida', 'success');
            historyTranscriptions = historyTranscriptions.filter(t => t.id !== id);
            renderHistoryTimeline(historyTranscriptions);
        } else {
            showToast('Erro: ' + result.error, 'error');
        }
    } catch (error) {
        showToast('Erro de conexão', 'error');
    }
}

async function exportDayJSON() {
    const dateInput = $('#history-date');
    const dateStr = dateInput?.value || new Date().toISOString().split('T')[0];

    try {
        const result = await apiGet(`transcriptions/daily/${dateStr}`);
        if (result.success) {
            const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `transcriptions_${dateStr}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }
    } catch (error) {
        showToast('Erro ao exportar', 'error');
    }
}

async function exportDayTXT() {
    const dateInput = $('#history-date');
    const dateStr = dateInput?.value || new Date().toISOString().split('T')[0];

    try {
        const result = await apiGet(`transcriptions/daily/${dateStr}`);
        if (result.success && result.transcriptions) {
            const text = result.transcriptions
                .map(t => `[${new Date(t.timestamp).toLocaleTimeString('pt-BR')}] ${t.text}`)
                .join('\n\n');

            const blob = new Blob([text], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `transcriptions_${dateStr}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        }
    } catch (error) {
        showToast('Erro ao exportar', 'error');
    }
}

async function consolidateDay() {
    const dateInput = $('#history-date');
    const dateStr = dateInput?.value;

    try {
        const result = await apiPost('transcriptions/consolidate', dateStr ? { date: dateStr } : {});
        showToast(result.message || 'Consolidação concluída', result.success ? 'success' : 'warning');
    } catch (error) {
        showToast('Erro na consolidação', 'error');
    }
}

function initHistoryTab() {
    // Set default date to today
    const dateInput = $('#history-date');
    if (dateInput) {
        dateInput.value = new Date().toISOString().split('T')[0];
    }

    // Event listeners
    $('#btn-history-load')?.addEventListener('click', () => {
        const date = $('#history-date')?.value;
        if (date) loadHistoryByDate(date);
    });

    $('#btn-history-today')?.addEventListener('click', () => {
        const today = new Date().toISOString().split('T')[0];
        if ($('#history-date')) $('#history-date').value = today;
        loadHistoryByDate(today);
    });

    $('#btn-history-search')?.addEventListener('click', () => {
        const query = $('#history-search')?.value;
        if (query) searchHistory(query);
    });

    $('#history-search')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const query = e.target.value;
            if (query) searchHistory(query);
        }
    });

    $('#btn-export-day-json')?.addEventListener('click', exportDayJSON);
    $('#btn-export-day-txt')?.addEventListener('click', exportDayTXT);
    $('#btn-consolidate')?.addEventListener('click', consolidateDay);
    $('#btn-process-llm')?.addEventListener('click', processWithLLM);
}

// ==========================================================================
// Init
// ==========================================================================

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initEventListeners();
    initTranscriptionListeners();
    initListenerControls();
    initFilesTab();
    initLogsTab();
    initHistoryTab();
    loadConfig();

    // Check systemd auto-start status
    checkSystemdAutoStart();

    // Check USB receiver auto-start after config is loaded
    setTimeout(checkAutoStart, 1000);

    // Auto-refresh system info every 30s
    setInterval(refreshSystemInfo, 30000);

    // Auto-refresh batch status every 60s
    setInterval(refreshBatchStatus, 60000);
});
