const API_BASE = "/api/v1";
const AUDIO_DEBUG_ENABLED = new URLSearchParams(window.location.search).get("audio_debug") === "1";

const NOTE_GAP_MS = 250;
const SETTINGS_VERSION = 5;
const MAX_CENTS_ERROR = 10;
const MAX_POLYPHONY = 10;
const SAMPLE_PRELOAD_CONCURRENCY = 4;
const AUDIO_DEBUG_LOG_LIMIT = 40;
const AUDIO_UNLOCK_TIMEOUT_MS = 800;
const AUDIO_UNLOCK_RECREATE_FAILURE_THRESHOLD = 2;
const FULL_KEYBOARD_EXIT_HOLD_MS = 400;

const NATURAL_DEGREE_TO_SEMITONE = {
  1: 0,
  2: 2,
  3: 4,
  4: 5,
  5: 7,
  6: 9,
  7: 11,
};

const LS_SETTINGS = "tonicEar.settings";
const LS_HISTORY = "tonicEar.history";
const LS_MODULE_STATS = "tonicEar.moduleStats";

const state = {
  meta: null,
  moduleMap: new Map(),
  session: null,
  currentIndex: 0,
  answers: [],
  currentAnswered: false,
  sequenceInput: [],
  selectedAccidental: "natural",
  settings: null,
  audioCtx: null,
  audioUnlocked: false,
  audioUnlockPromise: null,
  isPlaying: false,
  audioManifest: null,
  audioManifestInstrument: null,
  audioAssetVersion: null,
  sampleById: new Map(),
  sampleBufferCache: new Map(),
  sampleFetchPromises: new Map(),
  keyboardTonePlan: null,
  activeVoices: [],
  audioDebugLines: [],
  audioUnlockFailures: 0,
  audioUnlockPendingGesture: false,
  lastAudioDebugMessage: "",
  lastAudioSessionType: null,
  keyboardMode: "compact",
  touchOctaveUpActive: false,
  touchOctaveDownActive: false,
  touchOctaveShift: 0,
  octaveExitHoldTimer: null,
  fullKeyboardPointerTargets: new Map(),
};

const ui = {};

window.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheElements();
  if (ui.fullKeyboardOverlay) {
    ui.fullKeyboardOverlay.setAttribute("aria-hidden", "true");
  }
  bindStaticEvents();
  setupAudioDebugPanel();

  try {
    await loadMeta();
    hydrateSettings();
    await ensureManifestForInstrument(state.settings.instrument);
    renderSettingsControls();
    renderModuleGrid();
    renderHistory();
    switchView("dashboardView");
    window.history.replaceState({ view: "dashboardView" }, "");
    window.addEventListener("popstate", handlePopState);
  } catch (error) {
    showGlobalError(error.message || "Failed to initialize app");
  }
}

function cacheElements() {
  ui.globalError = document.getElementById("globalError");

  ui.dashboardView = document.getElementById("dashboardView");
  ui.quizView = document.getElementById("quizView");
  ui.resultView = document.getElementById("resultView");

  ui.genderSelect = document.getElementById("genderSelect");
  ui.instrumentSelect = document.getElementById("instrumentSelect");
  ui.keySelect = document.getElementById("keySelect");
  ui.temperamentSelect = document.getElementById("temperamentSelect");
  ui.showVisualHints = document.getElementById("showVisualHints");
  ui.quizShowVisualHints = document.getElementById("quizShowVisualHints");

  ui.moduleGrid = document.getElementById("moduleGrid");
  ui.historyList = document.getElementById("historyList");

  ui.quizModuleTitle = document.getElementById("quizModuleTitle");
  ui.quizProgress = document.getElementById("quizProgress");
  ui.promptText = document.getElementById("promptText");
  ui.visualHintContainer = document.getElementById("visualHintContainer");
  ui.answerArea = document.getElementById("answerArea");
  ui.feedbackText = document.getElementById("feedbackText");
  ui.repeatBtn = document.getElementById("repeatBtn");
  ui.showAnswerBtn = document.getElementById("showAnswerBtn");
  ui.nextBtn = document.getElementById("nextBtn");

  ui.scoreLine = document.getElementById("scoreLine");
  ui.scoreDetail = document.getElementById("scoreDetail");
  ui.mistakeList = document.getElementById("mistakeList");
  ui.headerHomeBtn = document.getElementById("headerHomeBtn");

  ui.backToDashboardBtn = document.getElementById("backToDashboardBtn");
  ui.backToHomeBtn = document.getElementById("backToHomeBtn");
  ui.retryModuleBtn = document.getElementById("retryModuleBtn");
  ui.resetProgressBtn = document.getElementById("resetProgressBtn");
  ui.touchKeyboardPanel = document.getElementById("touchKeyboardPanel");
  ui.touchKeyboardButtons = document.getElementById("touchKeyboardButtons");
  ui.touchKeyboardHint = document.getElementById("touchKeyboardHint");
  ui.openFullKeyboardBtn = document.getElementById("openFullKeyboardBtn");
  ui.fullKeyboardOverlay = document.getElementById("fullKeyboardOverlay");
  ui.fullKeyboardButtons = document.getElementById("fullKeyboardButtons");
  ui.fullKeyboardOctUp = document.getElementById("fullKeyboardOctUp");
  ui.fullKeyboardOctDown = document.getElementById("fullKeyboardOctDown");

  ui.audioDebugPanel = document.getElementById("audioDebugPanel");
  ui.audioDebugStatus = document.getElementById("audioDebugStatus");
  ui.audioDebugLog = document.getElementById("audioDebugLog");
  ui.audioDebugUnlockBtn = document.getElementById("audioDebugUnlockBtn");
  ui.audioDebugWebToneBtn = document.getElementById("audioDebugWebToneBtn");
  ui.audioDebugSampleBtn = document.getElementById("audioDebugSampleBtn");
}

function bindStaticEvents() {
  ui.moduleGrid.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-module-id]");
    if (!button) {
      return;
    }
    const moduleId = button.dataset.moduleId;
    void startSessionFromUserGesture(moduleId);
  });

  ui.instrumentSelect.addEventListener("change", () => {
    void onSettingsChange();
  });
  ui.genderSelect.addEventListener("change", () => {
    void onSettingsChange();
  });
  ui.keySelect.addEventListener("change", () => {
    void onSettingsChange();
  });
  ui.temperamentSelect.addEventListener("change", () => {
    void onSettingsChange();
  });

  ui.showVisualHints.addEventListener("change", () => {
    setVisualHints(ui.showVisualHints.checked);
  });

  ui.quizShowVisualHints.addEventListener("change", () => {
    setVisualHints(ui.quizShowVisualHints.checked);
    if (state.session) {
      renderVisualHints(currentQuestion());
    }
  });

  ui.repeatBtn.addEventListener("click", () => {
    void playCurrentQuestion();
  });

  ui.showAnswerBtn.addEventListener("click", () => {
    revealAnswer();
  });

  ui.headerHomeBtn.addEventListener("click", () => {
    goHomeView();
  });

  window.addEventListener("keydown", handleGlobalToneKeydown);
  armAudioUnlockListeners();

  ui.touchKeyboardButtons.addEventListener("pointerdown", handleTouchKeyboardPointerDown);
  if (ui.openFullKeyboardBtn) {
    ui.openFullKeyboardBtn.addEventListener("click", () => {
      openFullKeyboardMode();
    });
  }
  if (ui.fullKeyboardOverlay) {
    ui.fullKeyboardOverlay.addEventListener("pointerdown", handleFullKeyboardPointerDown);
  }
  window.addEventListener("pointerup", handleFullKeyboardPointerUp);
  window.addEventListener("pointercancel", handleFullKeyboardPointerUp);

  if (!window.PointerEvent) {
    ui.touchKeyboardButtons.addEventListener("touchstart", handleTouchKeyboardPointerDown, {
      passive: false,
    });
  }

  ui.nextBtn.addEventListener("click", () => {
    if (!state.currentAnswered) {
      return;
    }

    if (state.currentIndex === state.session.questions.length - 1) {
      finishSession();
      return;
    }

    state.currentIndex += 1;
    renderCurrentQuestion();
  });

  ui.backToDashboardBtn.addEventListener("click", () => {
    state.session = null;
    navigateToView("dashboardView");
    renderModuleGrid();
    renderHistory();
  });

  ui.backToHomeBtn.addEventListener("click", () => {
    state.session = null;
    navigateToView("dashboardView");
    renderModuleGrid();
    renderHistory();
  });

  ui.retryModuleBtn.addEventListener("click", () => {
    if (!state.session) {
      return;
    }
    void startSessionFromUserGesture(state.session.settings.moduleId);
  });

  ui.resetProgressBtn.addEventListener("click", () => {
    const confirmed = window.confirm("Reset local progress and history?");
    if (!confirmed) {
      return;
    }
    localStorage.removeItem(LS_HISTORY);
    localStorage.removeItem(LS_MODULE_STATS);
    renderModuleGrid();
    renderHistory();
  });
}

function setupAudioDebugPanel() {
  if (!ui.audioDebugPanel || !ui.audioDebugStatus || !ui.audioDebugLog) {
    return;
  }

  if (!AUDIO_DEBUG_ENABLED) {
    ui.audioDebugPanel.classList.add("hidden");
    return;
  }

  ui.audioDebugPanel.classList.remove("hidden");
  setAudioDebugStatus("Audio debug active. Use buttons below on iPhone.");
  appendAudioDebugLog("Audio debug enabled");
  appendAudioDebugLog(`UA: ${navigator.userAgent}`);
  appendAudioDebugLog(`Secure context: ${window.isSecureContext ? "yes" : "no"}`);

  if (ui.audioDebugUnlockBtn) {
    ui.audioDebugUnlockBtn.addEventListener("click", () => {
      void runAudioDebugUnlock();
    });
  }

  if (ui.audioDebugWebToneBtn) {
    ui.audioDebugWebToneBtn.addEventListener("click", () => {
      void runAudioDebugWebTone();
    });
  }

  if (ui.audioDebugSampleBtn) {
    ui.audioDebugSampleBtn.addEventListener("click", () => {
      void runAudioDebugSample();
    });
  }
}

async function loadMeta() {
  const response = await fetch(`${API_BASE}/meta`);
  if (!response.ok) {
    throw new Error("Failed to load app metadata");
  }

  const meta = await response.json();
  state.meta = meta;
  state.moduleMap = new Map(meta.modules.map((module) => [module.id, module]));
}

function isInstrumentSupported(instrumentId) {
  return Boolean(state.meta?.instruments?.some((instrument) => instrument.id === instrumentId));
}

function manifestPathForInstrument(instrumentId) {
  return `/assets/audio/${instrumentId}/manifest.json`;
}

async function loadAudioManifest(instrumentId) {
  if (!isInstrumentSupported(instrumentId)) {
    throw new Error(`Unsupported instrument '${instrumentId}'`);
  }

  const response = await fetch(manifestPathForInstrument(instrumentId), { cache: "no-cache" });
  if (!response.ok) {
    throw new Error(`Failed to load ${instrumentId} audio manifest`);
  }

  const manifest = await response.json();
  if (!Array.isArray(manifest.samples) || manifest.samples.length === 0) {
    throw new Error(`${instrumentId} manifest is missing sample entries`);
  }

  state.audioManifest = manifest;
  state.sampleById = new Map(manifest.samples.map((item) => [item.id, item]));
  state.audioManifestInstrument = instrumentId;
  state.audioAssetVersion = String(manifest.buildId ?? manifest.version ?? "0");
}

async function ensureManifestForInstrument(instrumentId) {
  if (state.audioManifest && state.audioManifestInstrument === instrumentId) {
    return;
  }
  await loadAudioManifest(instrumentId);
}

function resetAudioPlaybackState() {
  for (const voice of state.activeVoices) {
    try {
      voice.stop();
    } catch {
      // Ignore race where voice already ended.
    }
    try {
      voice.disconnect();
    } catch {
      // Ignore disconnected voice.
    }
  }
  state.activeVoices = [];
  state.sampleBufferCache.clear();
  state.sampleFetchPromises.clear();
  state.keyboardTonePlan = null;
}

function hydrateSettings() {
  const saved = readStorage(LS_SETTINGS, {});
  const isCurrentVersion = saved.version === SETTINGS_VERSION;

  if (!isCurrentVersion) {
    state.settings = {
      version: SETTINGS_VERSION,
      instrument: state.meta.defaults.instrument,
      gender: state.meta.defaults.gender,
      key: state.meta.defaults.key,
      temperament: state.meta.defaults.temperament,
      showVisualHints: state.meta.defaults.showVisualHints,
    };
    persistSettings();
    return;
  }

  state.settings = {
    version: SETTINGS_VERSION,
    instrument: isInstrumentSupported(saved.instrument)
      ? saved.instrument
      : state.meta.defaults.instrument,
    gender: saved.gender || state.meta.defaults.gender,
    key: saved.key || state.meta.defaults.key,
    temperament: saved.temperament || state.meta.defaults.temperament,
    showVisualHints:
      typeof saved.showVisualHints === "boolean"
        ? saved.showVisualHints
        : state.meta.defaults.showVisualHints,
  };
}

function renderSettingsControls() {
  renderSelect(ui.instrumentSelect, state.meta.instruments, state.settings.instrument);
  renderSelect(ui.genderSelect, state.meta.genders, state.settings.gender);
  renderSelect(ui.keySelect, state.meta.keys, state.settings.key);
  renderSelect(ui.temperamentSelect, state.meta.temperaments, state.settings.temperament);

  ui.showVisualHints.checked = state.settings.showVisualHints;
  ui.quizShowVisualHints.checked = state.settings.showVisualHints;
  renderTouchKeyboardHint();
}

function renderSelect(element, options, selectedId) {
  element.innerHTML = "";

  for (const option of options) {
    const opt = document.createElement("option");
    opt.value = option.id;
    opt.textContent = option.label;
    if (option.id === selectedId) {
      opt.selected = true;
    }
    element.appendChild(opt);
  }
}

async function onSettingsChange() {
  const previousInstrument = state.settings.instrument;
  const nextInstrument = ui.instrumentSelect.value;

  state.settings.version = SETTINGS_VERSION;
  state.settings.instrument = nextInstrument;
  state.settings.gender = ui.genderSelect.value;
  state.settings.key = ui.keySelect.value;
  state.settings.temperament = ui.temperamentSelect.value;

  if (nextInstrument !== previousInstrument) {
    try {
      await loadAudioManifest(nextInstrument);
      resetAudioPlaybackState();
    } catch (error) {
      state.settings.instrument = previousInstrument;
      ui.instrumentSelect.value = previousInstrument;
      persistSettings();
      showGlobalError(error.message || "Failed to switch instrument");
      return;
    }
  } else {
    state.keyboardTonePlan = null;
  }

  persistSettings();
  renderTouchKeyboardHint();
  renderModuleGrid();
  renderHistory();
  hideGlobalError();
  void preloadKeyboardSamplesIfPossible();
}

function renderTouchKeyboardHint() {
  if (!ui.touchKeyboardHint) {
    return;
  }
  const instrumentLabel = getInstrumentLabel(state.settings?.instrument);
  ui.touchKeyboardHint.textContent = `Tap 1-7 to play one-shot ${instrumentLabel.toLowerCase()} notes`;
}

function setVisualHints(enabled) {
  state.settings.version = SETTINGS_VERSION;
  state.settings.showVisualHints = enabled;
  ui.showVisualHints.checked = enabled;
  ui.quizShowVisualHints.checked = enabled;
  persistSettings();
}

function persistSettings() {
  writeStorage(LS_SETTINGS, state.settings);
}

function getCurrentInstrumentId() {
  return ui.instrumentSelect?.value || state.settings?.instrument || state.meta?.defaults?.instrument || "piano";
}

function getInstrumentLabel(instrumentId) {
  const resolved = instrumentId || "piano";
  return state.meta?.instruments?.find((item) => item.id === resolved)?.label || resolved;
}

function moduleStatsStorageKey(moduleId, instrumentId) {
  return `${moduleId}::${instrumentId || "piano"}`;
}

function renderModuleGrid() {
  const stats = readStorage(LS_MODULE_STATS, {});
  const selectedInstrument = getCurrentInstrumentId();

  const sortedModules = [...state.meta.modules].sort(
    (a, b) => a.recommendedOrder - b.recommendedOrder,
  );

  ui.moduleGrid.innerHTML = "";

  for (const module of sortedModules) {
    const card = document.createElement("article");
    card.className = "module-card";

    const title = document.createElement("h3");
    title.textContent = module.title;

    const sub = document.createElement("p");
    sub.className = "subtle";
    sub.textContent = `${module.id} | Type: ${module.questionType}`;

    const orderBadge = document.createElement("span");
    orderBadge.className = "chip";
    orderBadge.textContent = `Recommended #${module.recommendedOrder}`;

    const statsRow = document.createElement("p");
    statsRow.className = "subtle";
    const moduleStat = stats[moduleStatsStorageKey(module.id, selectedInstrument)];
    if (moduleStat) {
      statsRow.textContent = `Attempts: ${moduleStat.attempts} | Best: ${moduleStat.bestAccuracy.toFixed(1)}%`;
    } else {
      statsRow.textContent = "Attempts: 0 | Best: --";
    }

    const button = document.createElement("button");
    button.className = "btn btn-primary";
    button.type = "button";
    button.dataset.moduleId = module.id;
    button.textContent = "Start";

    card.append(title, sub, orderBadge, statsRow, button);
    ui.moduleGrid.appendChild(card);
  }
}

function renderHistory() {
  const history = readStorage(LS_HISTORY, []);
  const selectedInstrument = getCurrentInstrumentId();
  const selectedLabel = getInstrumentLabel(selectedInstrument);
  const filteredHistory = history.filter((item) => (item.instrument || "piano") === selectedInstrument);

  if (!filteredHistory.length) {
    ui.historyList.innerHTML = `<p class="subtle">No training history yet for ${selectedLabel}.</p>`;
    return;
  }

  ui.historyList.innerHTML = "";
  for (const item of filteredHistory.slice(0, 8)) {
    const row = document.createElement("div");
    row.className = "history-row";

    const left = document.createElement("div");
    const instrumentLabel = getInstrumentLabel(item.instrument || "piano");
    left.innerHTML = `<strong>${item.moduleId}</strong> <span class="subtle">${item.moduleTitle}</span> <span class="subtle">(${instrumentLabel})</span>`;

    const right = document.createElement("div");
    const date = new Date(item.completedAt);
    right.className = "subtle";
    right.textContent = `${item.accuracy.toFixed(1)}% | ${date.toLocaleString()}`;

    row.append(left, right);
    ui.historyList.appendChild(row);
  }
}

async function startSessionFromUserGesture(moduleId) {
  try {
    await unlockAudioPipeline();
  } catch {
    // Continue starting the session; playback paths will retry unlock.
  }
  await startSession(moduleId);
}

async function startSession(moduleId) {
  hideGlobalError();

  const payload = {
    moduleId,
    instrument: ui.instrumentSelect.value,
    gender: ui.genderSelect.value,
    key: ui.keySelect.value,
    temperament: ui.temperamentSelect.value,
  };

  try {
    const previousManifestInstrument = state.audioManifestInstrument;
    await ensureManifestForInstrument(payload.instrument);
    if (previousManifestInstrument && previousManifestInstrument !== payload.instrument) {
      resetAudioPlaybackState();
    }

    state.settings.instrument = payload.instrument;
    state.settings.gender = payload.gender;
    state.settings.key = payload.key;
    state.settings.temperament = payload.temperament;
    persistSettings();

    const response = await fetch(`${API_BASE}/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}));
      const detail = errorBody.detail || "Failed to start session";
      throw new Error(detail);
    }

    state.session = await response.json();
    state.currentIndex = 0;
    state.answers = new Array(state.session.questions.length).fill(null);
    state.currentAnswered = false;

    try {
      const context = await ensureAudioContextRunning();
      const warmupIds = collectSessionWarmupSampleIds(state.session);
      await preloadSampleIds(context, warmupIds);
      void preloadKeyboardSamplesIfPossible();
    } catch {
      // Warmup failures are non-fatal; playback paths retry on demand.
    }
    navigateToView("quizView");
    renderCurrentQuestion();
  } catch (error) {
    showGlobalError(error.message || "Failed to start session");
  }
}

function currentQuestion() {
  if (!state.session) {
    return null;
  }
  return state.session.questions[state.currentIndex] || null;
}

function renderCurrentQuestion() {
  const question = currentQuestion();
  if (!question) {
    return;
  }

  state.currentAnswered = false;
  state.sequenceInput = [];
  state.selectedAccidental = "natural";

  ui.quizModuleTitle.textContent = state.session.settings.moduleTitle;
  ui.quizProgress.textContent = `Question ${state.currentIndex + 1} / ${state.session.questions.length}`;
  ui.promptText.textContent = question.promptText;
  setFeedback("", "info");
  ui.nextBtn.disabled = true;
  ui.nextBtn.textContent = state.currentIndex === state.session.questions.length - 1 ? "Finish" : "Next";
  ui.showAnswerBtn.classList.add("hidden");
  ui.showAnswerBtn.disabled = true;

  renderVisualHints(question);
  renderAnswerArea(question);

  window.setTimeout(() => {
    void playCurrentQuestion();
  }, 80);
}

function renderVisualHints(question) {
  ui.visualHintContainer.innerHTML = "";

  if (!state.settings.showVisualHints || question.type === "single_note") {
    ui.visualHintContainer.classList.add("hidden");
    return;
  }

  ui.visualHintContainer.classList.remove("hidden");

  const lane = document.createElement("div");
  lane.className = "pitch-lane";

  for (let degree = 1; degree <= 7; degree += 1) {
    const guide = document.createElement("div");
    guide.className = "pitch-guide";
    guide.style.bottom = `${mapDegreeToY(degree)}%`;

    const guideLabel = document.createElement("span");
    guideLabel.textContent = String(degree);
    guide.appendChild(guideLabel);
    lane.appendChild(guide);
  }

  const count = question.notes.length;
  question.notes.forEach((note, index) => {
    const marker = document.createElement("div");
    marker.className = "pitch-dot";
    marker.style.left = `${((index + 1) / (count + 1)) * 100}%`;
    marker.style.bottom = `${mapNoteToY(note)}%`;
    marker.textContent = formatNoteLabel(note);
    lane.appendChild(marker);
  });

  ui.visualHintContainer.appendChild(lane);
}

function renderAnswerArea(question) {
  ui.answerArea.innerHTML = "";

  if (question.type === "compare_two") {
    renderCompareAnswer(question);
    return;
  }

  if (question.type === "sort_three" || question.type === "sort_four") {
    renderSortAnswer(question);
    return;
  }

  if (question.type === "interval_scale") {
    renderIntervalAnswer(question);
    return;
  }

  if (question.type === "single_note") {
    renderSingleNoteAnswer(question);
    return;
  }

  ui.answerArea.innerHTML = `<p class="subtle">Unsupported question type.</p>`;
}

function renderCompareAnswer(question) {
  const wrap = document.createElement("div");
  wrap.className = "button-row";

  for (const choice of question.choices) {
    const button = document.createElement("button");
    button.className = "btn";
    button.type = "button";
    button.textContent = choice.label;
    button.addEventListener("click", () => {
      submitAnswer(choice.id);
    });
    wrap.appendChild(button);
  }

  ui.answerArea.appendChild(wrap);
}

function renderSortAnswer(question) {
  const count = question.choices.positions.length;

  const helper = document.createElement("p");
  helper.className = "subtle";
  helper.textContent = "Tap the note positions in low-to-high order.";

  const sequence = document.createElement("div");
  sequence.className = "sequence-preview";
  sequence.textContent = "Your order: --";

  const buttons = document.createElement("div");
  buttons.className = "button-row";
  for (const item of question.choices.positions) {
    const button = document.createElement("button");
    button.className = "btn";
    button.type = "button";
    button.textContent = item;
    button.addEventListener("click", () => {
      if (state.sequenceInput.includes(item)) {
        return;
      }
      state.sequenceInput.push(item);
      sequence.textContent = `Your order: ${state.sequenceInput.join("-")}`;
      submitButton.disabled = state.sequenceInput.length !== count;
    });
    buttons.appendChild(button);
  }

  const controlRow = document.createElement("div");
  controlRow.className = "button-row";

  const clearButton = document.createElement("button");
  clearButton.className = "btn btn-ghost";
  clearButton.type = "button";
  clearButton.textContent = "Clear";
  clearButton.addEventListener("click", () => {
    state.sequenceInput = [];
    sequence.textContent = "Your order: --";
    submitButton.disabled = true;
  });

  const submitButton = document.createElement("button");
  submitButton.className = "btn btn-primary sort-submit";
  submitButton.type = "button";
  submitButton.textContent = "Submit Order";
  submitButton.disabled = true;
  submitButton.addEventListener("click", () => {
    if (state.sequenceInput.length !== count) {
      return;
    }
    submitAnswer(state.sequenceInput.join("-"));
  });

  controlRow.append(clearButton, submitButton);
  ui.answerArea.append(helper, sequence, buttons, controlRow);
}

function renderIntervalAnswer(question) {
  const wrap = document.createElement("div");
  wrap.className = "button-row";

  for (const option of question.choices) {
    const button = document.createElement("button");
    button.className = "btn";
    button.type = "button";
    button.textContent = option;
    button.addEventListener("click", () => {
      submitAnswer(option);
    });
    wrap.appendChild(button);
  }

  ui.answerArea.appendChild(wrap);
}

function renderSingleNoteAnswer(question) {
  const degreesWrap = document.createElement("div");
  degreesWrap.className = "button-row";

  const heading = document.createElement("p");
  heading.className = "subtle";
  heading.textContent = "Choose the movable-do number.";

  if (question.choices.requiresAccidental) {
    const accidentalWrap = document.createElement("div");
    accidentalWrap.className = "button-row";

    const accidentalMap = {
      flat: "b",
      natural: "natural",
      sharp: "#",
    };

    for (const accidental of question.choices.accidentals) {
      const button = document.createElement("button");
      button.className = "btn btn-ghost";
      button.type = "button";
      button.textContent = accidentalMap[accidental];
      button.dataset.accidental = accidental;
      if (accidental === state.selectedAccidental) {
        button.classList.add("is-active");
      }
      button.addEventListener("click", () => {
        state.selectedAccidental = accidental;
        accidentalWrap.querySelectorAll("button").forEach((item) => {
          item.classList.remove("is-active");
        });
        button.classList.add("is-active");
      });
      accidentalWrap.appendChild(button);
    }

    ui.answerArea.append(heading, accidentalWrap);
  } else {
    state.selectedAccidental = "natural";
    ui.answerArea.appendChild(heading);
  }

  for (const degree of question.choices.degrees) {
    const button = document.createElement("button");
    button.className = "btn";
    button.type = "button";
    button.textContent = degree;
    button.addEventListener("click", () => {
      submitAnswer({
        degree,
        accidental: state.selectedAccidental,
      });
    });
    degreesWrap.appendChild(button);
  }

  ui.answerArea.appendChild(degreesWrap);
}

function submitAnswer(answer) {
  const question = currentQuestion();
  if (!question) {
    return;
  }

  const correct = isCorrect(question.correctAnswer, answer);
  const existingRecord = state.answers[state.currentIndex];

  if (!existingRecord) {
    state.answers[state.currentIndex] = {
      questionIndex: state.currentIndex + 1,
      question,
      userAnswer: answer,
      correctAnswer: question.correctAnswer,
      isCorrect: correct,
    };

    state.currentAnswered = true;
    ui.nextBtn.disabled = false;

    if (correct) {
      setFeedback("Correct on first attempt.", "good");
      disableAnswerButtons();
      return;
    }

    ui.showAnswerBtn.classList.remove("hidden");
    ui.showAnswerBtn.disabled = false;
    setFeedback(
      "First attempt incorrect. Score is locked. You can repeat and try again, or click Show Answer.",
      "bad",
    );
    prepareRetryInput(question);
    return;
  }

  if (correct) {
    setFeedback("Practice attempt correct. First-attempt score remains locked.", "good");
    disableAnswerButtons();
    return;
  }

  setFeedback("Still incorrect. Keep trying, repeat audio, or click Show Answer.", "bad");
  prepareRetryInput(question);
}

function disableAnswerButtons() {
  ui.answerArea.querySelectorAll("button").forEach((button) => {
    button.disabled = true;
  });
}

function revealAnswer() {
  const question = currentQuestion();
  if (!question || !state.currentAnswered) {
    return;
  }
  setFeedback(`Correct answer: ${formatAnswer(question.correctAnswer)}`, "info");
}

function setFeedback(message, tone) {
  ui.feedbackText.classList.remove("good", "bad", "info", "is-empty");

  if (!message) {
    ui.feedbackText.classList.add("is-empty");
    ui.feedbackText.innerHTML = "&nbsp;";
    return;
  }

  ui.feedbackText.classList.add(tone);
  ui.feedbackText.textContent = message;
}

function prepareRetryInput(question) {
  if (question.type !== "sort_three" && question.type !== "sort_four") {
    return;
  }

  state.sequenceInput = [];
  const sequence = ui.answerArea.querySelector(".sequence-preview");
  if (sequence) {
    sequence.textContent = "Your order: --";
  }

  const submitButton = ui.answerArea.querySelector(".sort-submit");
  if (submitButton) {
    submitButton.disabled = true;
  }
}

function isCorrect(correctAnswer, userAnswer) {
  if (typeof correctAnswer === "string") {
    return String(userAnswer) === correctAnswer;
  }

  if (!correctAnswer || typeof correctAnswer !== "object") {
    return false;
  }

  const normalizedUser = normalizeAnswer(userAnswer);
  const validAnswers = [
    {
      degree: String(correctAnswer.degree),
      accidental: correctAnswer.accidental,
    },
  ];

  if (Array.isArray(correctAnswer.accepted)) {
    for (const item of correctAnswer.accepted) {
      validAnswers.push({
        degree: String(item.degree),
        accidental: item.accidental,
      });
    }
  }

  return validAnswers.some(
    (item) => item.degree === normalizedUser.degree && item.accidental === normalizedUser.accidental,
  );
}

function normalizeAnswer(answer) {
  if (typeof answer === "string") {
    return { degree: answer, accidental: "natural" };
  }

  return {
    degree: String(answer.degree),
    accidental: answer.accidental || "natural",
  };
}

function formatAnswer(answer) {
  if (typeof answer === "string") {
    return answer;
  }

  const symbolMap = {
    flat: "b",
    natural: "",
    sharp: "#",
  };

  const primary = `${symbolMap[answer.accidental] ?? ""}${answer.degree}`;

  if (!Array.isArray(answer.accepted) || answer.accepted.length === 0) {
    return primary;
  }

  const accepted = answer.accepted.map((item) => `${symbolMap[item.accidental] ?? ""}${item.degree}`);
  return `${primary} (or ${accepted.join(" / ")})`;
}

function finishSession() {
  const firstAttempts = state.answers.filter((item) => item);
  const total = firstAttempts.length;
  const correctCount = firstAttempts.filter((item) => item.isCorrect).length;
  const accuracy = total === 0 ? 0 : (correctCount / total) * 100;

  const wrongItems = firstAttempts.filter((item) => !item.isCorrect);

  saveSessionResult(accuracy);
  renderResult(correctCount, total, accuracy, wrongItems);
  navigateToView("resultView");
}

function saveSessionResult(accuracy) {
  const settings = state.session.settings;
  const instrument = settings.instrument || "piano";

  const history = readStorage(LS_HISTORY, []);
  history.unshift({
    moduleId: settings.moduleId,
    moduleTitle: settings.moduleTitle,
    instrument,
    accuracy,
    completedAt: new Date().toISOString(),
  });
  writeStorage(LS_HISTORY, history.slice(0, 100));

  const stats = readStorage(LS_MODULE_STATS, {});
  const statsKey = moduleStatsStorageKey(settings.moduleId, instrument);
  const current = stats[statsKey] || {
    attempts: 0,
    bestAccuracy: 0,
    lastAccuracy: 0,
    updatedAt: null,
  };

  current.attempts += 1;
  current.bestAccuracy = Math.max(current.bestAccuracy, accuracy);
  current.lastAccuracy = accuracy;
  current.updatedAt = new Date().toISOString();

  stats[statsKey] = current;
  writeStorage(LS_MODULE_STATS, stats);
}

function renderResult(correctCount, total, accuracy, wrongItems) {
  ui.scoreLine.textContent = `Score: ${correctCount} / ${total} (${accuracy.toFixed(1)}%)`;
  const temperamentLabel =
    state.meta?.temperaments.find((item) => item.id === state.session.settings.temperament)?.label ||
    state.session.settings.temperament;
  const instrumentLabel = getInstrumentLabel(state.session.settings.instrument || "piano");
  ui.scoreDetail.textContent =
    `Module: ${state.session.settings.moduleId} | Instrument: ${instrumentLabel} | ` +
    `Key: 1=${state.session.settings.key} | Temperament: ${temperamentLabel}`;

  ui.mistakeList.innerHTML = "";

  if (wrongItems.length === 0) {
    ui.mistakeList.innerHTML = `<p class="subtle">No mistakes this round.</p>`;
    return;
  }

  for (const item of wrongItems) {
    const card = document.createElement("article");
    card.className = "mistake-card";

    const title = document.createElement("h3");
    title.textContent = `Question ${item.questionIndex}`;

    const prompt = document.createElement("p");
    prompt.className = "subtle";
    prompt.textContent = item.question.promptText;

    const yourAnswer = document.createElement("p");
    yourAnswer.innerHTML = `<strong>Your answer:</strong> ${formatAnswer(item.userAnswer)}`;

    const rightAnswer = document.createElement("p");
    rightAnswer.innerHTML = `<strong>Correct answer:</strong> ${formatAnswer(item.correctAnswer)}`;

    const replay = document.createElement("button");
    replay.className = "btn";
    replay.type = "button";
    replay.textContent = "Replay";
    replay.addEventListener("click", () => {
      void playNotes(item.question.notes);
    });

    card.append(title, prompt, yourAnswer, rightAnswer, replay);
    ui.mistakeList.appendChild(card);
  }
}

function appendAudioDebugLog(message) {
  if (!AUDIO_DEBUG_ENABLED || !ui.audioDebugLog) {
    return;
  }
  if (message === state.lastAudioDebugMessage) {
    return;
  }
  state.lastAudioDebugMessage = message;
  const now = new Date();
  const timestamp = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(
    now.getSeconds(),
  ).padStart(2, "0")}`;
  state.audioDebugLines.unshift(`[${timestamp}] ${message}`);
  if (state.audioDebugLines.length > AUDIO_DEBUG_LOG_LIMIT) {
    state.audioDebugLines = state.audioDebugLines.slice(0, AUDIO_DEBUG_LOG_LIMIT);
  }
  ui.audioDebugLog.textContent = state.audioDebugLines.join("\n");
}

function setAudioDebugStatus(message) {
  if (!AUDIO_DEBUG_ENABLED || !ui.audioDebugStatus) {
    return;
  }
  ui.audioDebugStatus.textContent = message;
}

async function runAudioDebugUnlock() {
  try {
    setAudioDebugStatus("Unlocking audio...");
    const unlocked = await unlockAudioPipeline();
    const context = getOrCreateAudioContext();
    if (unlocked && context.state === "running") {
      setAudioDebugStatus(
        `Unlock ok | Context: ${context.state} | Primed: ${state.audioUnlocked ? "yes" : "no"} | Failures: ${state.audioUnlockFailures}`,
      );
      appendAudioDebugLog(`Unlock succeeded; context state is '${context.state}'`);
    } else {
      setAudioDebugStatus(
        `Unlock pending user gesture | Context: ${context.state} | Failures: ${state.audioUnlockFailures}`,
      );
      appendAudioDebugLog("Unlock pending next user gesture");
    }
  } catch (error) {
    const message = error?.message || "Unlock failed";
    setAudioDebugStatus(message);
    appendAudioDebugLog(`Unlock failed: ${message}`);
  }
}

async function runAudioDebugWebTone() {
  try {
    appendAudioDebugLog("WebAudio test tone requested (880Hz)");
    const context = await ensureAudioContextRunning();
    const gainNode = context.createGain();
    gainNode.gain.value = 0.25;
    gainNode.connect(context.destination);

    const oscillator = context.createOscillator();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    oscillator.connect(gainNode);

    const now = context.currentTime + 0.01;
    oscillator.start(now);
    oscillator.stop(now + 0.35);
    appendAudioDebugLog("WebAudio test tone scheduled");
  } catch (error) {
    appendAudioDebugLog(`WebAudio test failed: ${error?.message || "unknown error"}`);
    if (!isAudioUnlockPendingError(error)) {
      showGlobalError(error.message || "WebAudio test failed");
    }
  }
}

async function runAudioDebugSample() {
  try {
    appendAudioDebugLog("Sample test requested (m069)");
    const context = await ensureAudioContextRunning();
    await ensureSampleBuffer(context, "m069");
    scheduleRawSample(context, "m069", context.currentTime + 0.01);
    appendAudioDebugLog("Sample m069 playback scheduled");
  } catch (error) {
    appendAudioDebugLog(`Sample test failed: ${error?.message || "unknown error"}`);
    if (!isAudioUnlockPendingError(error)) {
      showGlobalError(error.message || "Sample playback test failed");
    }
  }
}

function configureAudioSessionIfSupported() {
  try {
    const audioSession = navigator.audioSession;
    if (!audioSession) {
      return;
    }
    if (audioSession.type !== "playback") {
      audioSession.type = "playback";
    }
    if (state.lastAudioSessionType !== audioSession.type) {
      state.lastAudioSessionType = audioSession.type;
      appendAudioDebugLog(`navigator.audioSession.type='${audioSession.type}'`);
    }
  } catch (error) {
    appendAudioDebugLog(`navigator.audioSession failed: ${error?.message || "unknown error"}`);
  }
}

async function resumeAudioContextWithTimeout(context, label = "primary") {
  if (context.state === "running") {
    return;
  }

  const resumeResult = context.resume();
  if (resumeResult && typeof resumeResult.then === "function") {
    await Promise.race([
      resumeResult,
      new Promise((_, reject) => {
        window.setTimeout(() => {
          reject(new Error(`AudioContext resume timed out (${label})`));
        }, AUDIO_UNLOCK_TIMEOUT_MS);
      }),
    ]);
    return;
  }

  // Legacy path: give Safari a short window to transition state.
  await new Promise((resolve) => window.setTimeout(resolve, 40));
  if (context.state !== "running") {
    throw new Error(`AudioContext resume did not enter running state (${label})`);
  }
}

function createAudioUnlockPendingError() {
  const error = new Error("Audio unlock pending user gesture");
  error.name = "AudioUnlockPendingError";
  return error;
}

function isAudioUnlockPendingError(error) {
  return error?.name === "AudioUnlockPendingError";
}

async function recreateAudioContext() {
  const previous = state.audioCtx;
  state.audioCtx = null;
  state.audioUnlocked = false;

  if (previous && previous.state !== "closed") {
    try {
      await previous.close();
      appendAudioDebugLog("Previous AudioContext closed");
    } catch (error) {
      appendAudioDebugLog(`AudioContext close failed: ${error?.message || "unknown error"}`);
    }
  }

  const fresh = getOrCreateAudioContext();
  appendAudioDebugLog("Created fresh AudioContext");
  return fresh;
}

function getOrCreateAudioContext() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) {
    throw new Error("WebAudio API is not available in this browser");
  }

  if (!state.audioCtx) {
    state.audioCtx = new AudioContextClass({ latencyHint: "interactive" });
  }
  return state.audioCtx;
}

async function ensureAudioContextRunning() {
  let context = getOrCreateAudioContext();
  if (context.state === "running") {
    return context;
  }
  configureAudioSessionIfSupported();
  let unlocked = await unlockAudioPipeline();
  // unlockAudioPipeline may recreate AudioContext on iOS; always re-read the latest instance.
  context = state.audioCtx || context;
  if (!unlocked || context.state !== "running") {
    appendAudioDebugLog(`Context state after unlock is '${context.state}', retrying unlock once`);
    unlocked = await unlockAudioPipeline();
    context = state.audioCtx || context;
  }
  if (context.state !== "running") {
    if (!unlocked || state.audioUnlockPendingGesture) {
      throw createAudioUnlockPendingError();
    }
    throw new Error("Audio context is not running");
  }
  return context;
}

function warmAudioPipelineOnce() {
  if (state.audioUnlocked) {
    removeAudioUnlockListeners();
    return;
  }
  void unlockAudioPipeline()
    .then(() => {
      if (state.audioUnlocked) {
        void preloadKeyboardSamplesIfPossible();
        removeAudioUnlockListeners();
      }
    })
    .catch(() => {
      // Keep listeners active for the next user gesture.
    });
}

function armAudioUnlockListeners() {
  const options = { capture: true };
  window.addEventListener("pointerup", warmAudioPipelineOnce, options);
  window.addEventListener("touchend", warmAudioPipelineOnce, options);
  window.addEventListener("click", warmAudioPipelineOnce, options);
  window.addEventListener("keydown", warmAudioPipelineOnce, options);
}

function removeAudioUnlockListeners() {
  const options = { capture: true };
  window.removeEventListener("pointerup", warmAudioPipelineOnce, options);
  window.removeEventListener("touchend", warmAudioPipelineOnce, options);
  window.removeEventListener("click", warmAudioPipelineOnce, options);
  window.removeEventListener("keydown", warmAudioPipelineOnce, options);
}

async function unlockAudioPipeline() {
  let context = getOrCreateAudioContext();
  configureAudioSessionIfSupported();
  if (context.state === "running") {
    state.audioUnlocked = true;
    state.audioUnlockPendingGesture = false;
    state.audioUnlockFailures = 0;
    appendAudioDebugLog("AudioContext already running");
    return true;
  }

  if (!state.audioUnlockPromise) {
    state.audioUnlockPromise = (async () => {
      try {
        await resumeAudioContextWithTimeout(context, "primary");
      } catch (primaryError) {
        state.audioUnlockFailures += 1;
        state.audioUnlockPendingGesture = true;
        appendAudioDebugLog(`Primary resume failed: ${primaryError?.message || "unknown error"}`);
        if (state.audioUnlockFailures < AUDIO_UNLOCK_RECREATE_FAILURE_THRESHOLD) {
          return false;
        }
        try {
          context = await recreateAudioContext();
          configureAudioSessionIfSupported();
          await resumeAudioContextWithTimeout(context, "recreated");
        } catch (recreatedError) {
          state.audioUnlockFailures += 1;
          state.audioUnlockPendingGesture = true;
          appendAudioDebugLog(`Recreated resume failed: ${recreatedError?.message || "unknown error"}`);
          return false;
        }
      }

      configureAudioSessionIfSupported();
      primeAudioContextTick(context);
      state.audioUnlocked = true;
      state.audioUnlockPendingGesture = false;
      state.audioUnlockFailures = 0;
      appendAudioDebugLog(`AudioContext resumed: ${context.state}`);
      return true;
    })().finally(() => {
      state.audioUnlockPromise = null;
    });
  }

  return state.audioUnlockPromise;
}

async function preloadSampleIds(context, sampleIds) {
  const queue = Array.from(new Set(sampleIds)).filter((sampleId) => state.sampleById.has(sampleId));
  if (!queue.length) {
    return;
  }

  const workers = Array.from({ length: Math.min(SAMPLE_PRELOAD_CONCURRENCY, queue.length) }, async () => {
    while (queue.length) {
      const sampleId = queue.shift();
      if (!sampleId) {
        break;
      }
      await ensureSampleBuffer(context, sampleId);
    }
  });

  await Promise.all(workers);
}

function collectSessionWarmupSampleIds(session) {
  if (!session || !Array.isArray(session.questions) || !session.questions.length) {
    return getKeyboardSampleIds();
  }

  const firstQuestion = session.questions[0];
  const firstQuestionIds = collectSampleIdsForNotes(firstQuestion?.notes || []);
  return Array.from(new Set([...firstQuestionIds, ...getKeyboardSampleIds()]));
}

function collectSampleIdsForNotes(notes) {
  if (!Array.isArray(notes) || !notes.length) {
    return [];
  }

  const ids = [];
  for (const note of notes) {
    try {
      ids.push(resolveSampleIdForNote(note));
    } catch {
      // Ignore invalid note payload during warmup; playback will surface actionable errors.
    }
  }
  return ids;
}

function getKeyboardSampleIds() {
  const tonePlan = ensureKeyboardTonePlan();
  if (!tonePlan) {
    return [];
  }

  const ids = [];
  for (let degree = 1; degree <= 7; degree += 1) {
    const toneSpec = tonePlan.degreeMap.get(degree);
    if (!toneSpec) {
      continue;
    }
    const targetFrequency = clampFrequencyToSampleRange(toneSpec.frequency);
    const mapping = mapTargetHzToSample(targetFrequency);
    ids.push(mapping.sampleId);
  }
  return Array.from(new Set(ids));
}

function preloadKeyboardSamplesIfPossible() {
  if (!state.audioUnlocked || !state.audioCtx || state.audioCtx.state !== "running") {
    return Promise.resolve();
  }
  const sampleIds = getKeyboardSampleIds();
  if (!sampleIds.length) {
    return Promise.resolve();
  }
  return preloadSampleIds(state.audioCtx, sampleIds);
}

async function ensureSampleBuffer(context, sampleId) {
  const cached = state.sampleBufferCache.get(sampleId);
  if (cached) {
    return cached;
  }

  const inFlight = state.sampleFetchPromises.get(sampleId);
  if (inFlight) {
    return inFlight;
  }

  const promise = (async () => {
    const sample = state.sampleById.get(sampleId);
    if (!sample) {
      throw new Error(`Unknown sample '${sampleId}'`);
    }

    const response = await fetch(resolveSampleFileUrl(sample), { cache: "no-cache" });
    if (!response.ok) {
      throw new Error(`Failed to load sample '${sampleId}'`);
    }

    const encoded = await response.arrayBuffer();
    const decoded = await decodeAudioData(context, encoded);
    state.sampleBufferCache.set(sampleId, decoded);
    return decoded;
  })()
    .catch((error) => {
      state.sampleBufferCache.delete(sampleId);
      appendAudioDebugLog(`Sample ${sampleId} failed: ${error?.message || "unknown error"}`);
      throw error;
    })
    .finally(() => {
      state.sampleFetchPromises.delete(sampleId);
    });

  state.sampleFetchPromises.set(sampleId, promise);
  return promise;
}

function resolveSampleFileUrl(sample) {
  const separator = sample.file.includes("?") ? "&" : "?";
  const version = encodeURIComponent(
    `${state.audioManifestInstrument || "piano"}-${state.audioAssetVersion || "0"}`,
  );
  return `${sample.file}${separator}v=${version}`;
}

function decodeAudioData(context, encoded) {
  const clonedBuffer = encoded.slice(0);
  return new Promise((resolve, reject) => {
    const promiseLike = context.decodeAudioData(
      clonedBuffer,
      (buffer) => resolve(buffer),
      (error) => reject(error || new Error("Failed to decode audio sample")),
    );

    if (promiseLike && typeof promiseLike.then === "function") {
      promiseLike.then(resolve).catch(reject);
    }
  });
}

function primeAudioContextTick(context) {
  const gainNode = context.createGain();
  gainNode.gain.value = 0.00001;

  const oscillator = context.createOscillator();
  oscillator.type = "sine";
  oscillator.frequency.value = 880;
  oscillator.connect(gainNode);
  gainNode.connect(context.destination);

  const now = context.currentTime;
  oscillator.start(now);
  oscillator.stop(now + 0.01);
}

function mapTargetHzToSample(targetHz) {
  if (!Number.isFinite(targetHz) || targetHz <= 0) {
    throw new Error(`Invalid target frequency '${targetHz}'`);
  }
  if (!state.audioManifest || !Array.isArray(state.audioManifest.samples)) {
    throw new Error("Sample manifest is unavailable");
  }

  let nearestSample = null;
  let nearestCents = Number.POSITIVE_INFINITY;

  for (const sample of state.audioManifest.samples) {
    const centsError = 1200 * Math.log2(targetHz / sample.hz);
    const absCents = Math.abs(centsError);
    if (absCents < nearestCents) {
      nearestSample = sample;
      nearestCents = absCents;
    }
  }

  if (!nearestSample) {
    throw new Error(`No sample available for ${targetHz.toFixed(4)}Hz`);
  }

  const centsError = 1200 * Math.log2(targetHz / nearestSample.hz);
  return {
    sampleId: nearestSample.id,
    sampleHz: nearestSample.hz,
    centsError,
  };
}

function validateMapping(mapping, targetHz) {
  if (Math.abs(mapping.centsError) <= MAX_CENTS_ERROR) {
    return;
  }
  throw new Error(
    `Sample mapping exceeds ${MAX_CENTS_ERROR} cents at ${targetHz.toFixed(4)}Hz ` +
      `(got ${mapping.centsError.toFixed(4)} cents)`,
  );
}

async function playCurrentQuestion() {
  const question = currentQuestion();
  if (!question) {
    return;
  }
  await playNotes(question.notes);
}

async function playNotes(notes) {
  if (!Array.isArray(notes) || !notes.length || state.isPlaying) {
    return;
  }

  try {
    state.isPlaying = true;
    ui.repeatBtn.disabled = true;

    const context = await ensureAudioContextRunning();

    const start = context.currentTime + 0.03;
    const fullSampleDurationMs = getFullSampleDurationMs();
    const durationSec = fullSampleDurationMs / 1000;
    const gapSec = NOTE_GAP_MS / 1000;
    const sampleIds = Array.from(new Set(notes.map((note) => resolveSampleIdForNote(note))));

    await Promise.all(sampleIds.map((sampleId) => ensureSampleBuffer(context, sampleId)));

    for (let index = 0; index < notes.length; index += 1) {
      const note = notes[index];
      const sampleId = resolveSampleIdForNote(note);
      const at = start + index * (durationSec + gapSec);
      scheduleRawSample(context, sampleId, at);
    }

    const totalMs = notes.length * fullSampleDurationMs + (notes.length - 1) * NOTE_GAP_MS + 120;
    await sleep(totalMs);
  } catch (error) {
    if (!isAudioUnlockPendingError(error)) {
      showGlobalError(error.message || "Failed to play tones");
    }
  } finally {
    state.isPlaying = false;
    ui.repeatBtn.disabled = false;
  }
}

function resolveSampleIdForNote(note) {
  if (typeof note.sampleId === "string" && state.sampleById.has(note.sampleId)) {
    return note.sampleId;
  }

  const mapping = mapTargetHzToSample(note.frequency);
  validateMapping(mapping, note.frequency);
  return mapping.sampleId;
}

function scheduleRawSample(context, sampleId, startAt) {
  const buffer = state.sampleBufferCache.get(sampleId);
  if (!buffer) {
    throw new Error(`Decoded sample '${sampleId}' is unavailable`);
  }

  state.activeVoices = state.activeVoices.filter((voice) => voice && voice.__alive !== false);
  if (state.activeVoices.length >= MAX_POLYPHONY) {
    appendAudioDebugLog(`Voice limit reached (${MAX_POLYPHONY}), dropping ${sampleId}`);
    return;
  }

  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);
  source.__alive = true;

  const cleanup = () => {
    source.__alive = false;
    state.activeVoices = state.activeVoices.filter((voice) => voice !== source);
    try {
      source.disconnect();
    } catch {
      // Ignore disconnect errors on already-disconnected nodes.
    }
  };
  source.onended = cleanup;

  const maxLifetimeMs = Math.ceil((buffer.duration + 0.3) * 1000);
  window.setTimeout(cleanup, maxLifetimeMs);

  try {
    source.start(startAt);
  } catch (error) {
    cleanup();
    source.disconnect();
    throw error;
  }

  state.activeVoices.push(source);
}

function handleGlobalToneKeydown(event) {
  if (event.metaKey || event.altKey) {
    return;
  }

  const targetTag = (event.target?.tagName || "").toLowerCase();
  if (targetTag === "input" || targetTag === "textarea") {
    return;
  }

  const degree = resolveKeyboardDegree(event);
  if (degree === null) {
    if (event.key === "Home") {
      event.preventDefault();
      goHomeView();
    }
    return;
  }

  if (event.repeat) {
    return;
  }

  event.preventDefault();
  void playKeyboardDegree(degree, resolveOctaveShiftFromEvent(event));
}

function handleTouchKeyboardPointerDown(event) {
  if (state.keyboardMode === "full") {
    return;
  }

  const button = event.target.closest("button[data-degree]");
  if (!button) {
    return;
  }

  const degree = Number(button.dataset.degree);
  if (!Number.isInteger(degree) || degree < 1 || degree > 7) {
    return;
  }

  event.preventDefault();
  button.classList.add("is-pressed");
  window.setTimeout(() => {
    button.classList.remove("is-pressed");
  }, 140);

  void playKeyboardDegree(degree);
}

function isTouchKeyboardDevice() {
  return window.matchMedia("(hover: none), (pointer: coarse)").matches;
}

function openFullKeyboardMode() {
  if (!isTouchKeyboardDevice() || !ui.fullKeyboardOverlay) {
    return;
  }
  state.keyboardMode = "full";
  ui.fullKeyboardOverlay.classList.remove("hidden");
  ui.fullKeyboardOverlay.classList.add("is-open");
  ui.fullKeyboardOverlay.setAttribute("aria-hidden", "false");
  document.body.classList.add("keyboard-full-open");
}

function closeFullKeyboardMode() {
  if (!ui.fullKeyboardOverlay) {
    return;
  }
  clearDualOctaveExitHold();
  resetTouchOctaveState();
  clearFullKeyboardPointerTargets();
  state.keyboardMode = "compact";
  ui.fullKeyboardOverlay.classList.remove("is-open");
  ui.fullKeyboardOverlay.classList.add("hidden");
  ui.fullKeyboardOverlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("keyboard-full-open");
}

function clearFullKeyboardPointerTargets() {
  for (const pointerTarget of state.fullKeyboardPointerTargets.values()) {
    pointerTarget.button.classList.remove("is-pressed");
  }
  state.fullKeyboardPointerTargets.clear();
}

function resetTouchOctaveState() {
  state.touchOctaveUpActive = false;
  state.touchOctaveDownActive = false;
  state.touchOctaveShift = 0;
  ui.fullKeyboardOctUp?.classList.remove("is-pressed");
  ui.fullKeyboardOctDown?.classList.remove("is-pressed");
}

function updateTouchOctaveShift() {
  if (state.touchOctaveUpActive && state.touchOctaveDownActive) {
    state.touchOctaveShift = 0;
    return;
  }
  if (state.touchOctaveUpActive) {
    state.touchOctaveShift = 1;
    return;
  }
  if (state.touchOctaveDownActive) {
    state.touchOctaveShift = -1;
    return;
  }
  state.touchOctaveShift = 0;
}

function clearDualOctaveExitHold() {
  if (state.octaveExitHoldTimer) {
    window.clearTimeout(state.octaveExitHoldTimer);
    state.octaveExitHoldTimer = null;
  }
}

function maybeStartDualOctaveExitHold() {
  if (!state.touchOctaveUpActive || !state.touchOctaveDownActive) {
    clearDualOctaveExitHold();
    return;
  }
  if (state.octaveExitHoldTimer) {
    return;
  }
  state.octaveExitHoldTimer = window.setTimeout(() => {
    state.octaveExitHoldTimer = null;
    if (state.touchOctaveUpActive && state.touchOctaveDownActive) {
      closeFullKeyboardMode();
    }
  }, FULL_KEYBOARD_EXIT_HOLD_MS);
}

function handleFullKeyboardPointerDown(event) {
  if (state.keyboardMode !== "full") {
    return;
  }

  const button = event.target.closest("button");
  if (!button || !ui.fullKeyboardOverlay?.contains(button)) {
    return;
  }

  event.preventDefault();
  if (button.setPointerCapture && event.pointerId !== undefined) {
    try {
      button.setPointerCapture(event.pointerId);
    } catch {
      // Ignore capture failures on browsers that reject this call.
    }
  }

  const pointerId = event.pointerId;
  if (pointerId !== undefined && state.fullKeyboardPointerTargets.has(pointerId)) {
    return;
  }

  const degreeRaw = button.dataset.fullDegree;
  if (degreeRaw) {
    const degree = Number(degreeRaw);
    if (Number.isInteger(degree) && degree >= 1 && degree <= 7) {
      button.classList.add("is-pressed");
      if (pointerId !== undefined) {
        state.fullKeyboardPointerTargets.set(pointerId, { kind: "degree", button });
      }
      void playKeyboardDegree(degree, state.touchOctaveShift);
    }
    return;
  }

  const octaveRaw = button.dataset.octaveShift;
  if (!octaveRaw) {
    return;
  }

  const octaveShift = Number(octaveRaw);
  if (octaveShift !== 1 && octaveShift !== -1) {
    return;
  }

  button.classList.add("is-pressed");
  if (pointerId !== undefined) {
    state.fullKeyboardPointerTargets.set(pointerId, { kind: "octave", button, octaveShift });
  }
  if (octaveShift === 1) {
    state.touchOctaveUpActive = true;
  } else {
    state.touchOctaveDownActive = true;
  }
  updateTouchOctaveShift();
  maybeStartDualOctaveExitHold();
}

function handleFullKeyboardPointerUp(event) {
  if (!state.fullKeyboardPointerTargets.size) {
    return;
  }

  const pointerId = event.pointerId;
  if (pointerId === undefined) {
    return;
  }

  const pointerTarget = state.fullKeyboardPointerTargets.get(pointerId);
  if (!pointerTarget) {
    return;
  }

  pointerTarget.button.classList.remove("is-pressed");
  state.fullKeyboardPointerTargets.delete(pointerId);

  if (pointerTarget.kind !== "octave") {
    return;
  }

  if (pointerTarget.octaveShift === 1) {
    state.touchOctaveUpActive = false;
  } else if (pointerTarget.octaveShift === -1) {
    state.touchOctaveDownActive = false;
  }
  updateTouchOctaveShift();
  maybeStartDualOctaveExitHold();
}

async function playKeyboardDegree(degree, octaveShift = 0) {
  try {
    const keyboardPlan = ensureKeyboardTonePlan();
    const toneSpec = keyboardPlan?.degreeMap.get(degree);
    if (!toneSpec) {
      return;
    }

    const targetFrequency = clampFrequencyToSampleRange(
      toneSpec.frequency * (2 ** octaveShift),
    );
    const mapping = mapTargetHzToSample(targetFrequency);

    const context = await ensureAudioContextRunning();
    await ensureSampleBuffer(context, mapping.sampleId);
    scheduleRawSample(context, mapping.sampleId, context.currentTime + 0.001);
  } catch (error) {
    if (!isAudioUnlockPendingError(error)) {
      showGlobalError(error.message || "Failed to play keyboard tone");
    }
  }
}

function getFullSampleDurationMs() {
  const durationMs = Number(state.audioManifest?.durationMs);
  if (Number.isFinite(durationMs) && durationMs > 0) {
    return durationMs;
  }
  return 1000;
}

function ensureKeyboardTonePlan() {
  const toneContext = getToneContext();
  if (!toneContext) {
    return null;
  }

  const signature = `${toneContext.gender}|${toneContext.key}|${toneContext.temperament}`;
  if (state.keyboardTonePlan && state.keyboardTonePlan.signature === signature) {
    return state.keyboardTonePlan;
  }

  const degreeMap = new Map();

  for (let degree = 1; degree <= 7; degree += 1) {
    const semitone = NATURAL_DEGREE_TO_SEMITONE[degree];
    const frequency = toneContext.doFrequency * (2 ** (semitone / 12));
    degreeMap.set(degree, { frequency });
  }

  state.keyboardTonePlan = {
    signature,
    degreeMap,
  };
  return state.keyboardTonePlan;
}

function resolveOctaveShiftFromEvent(event) {
  const up = Boolean(event.shiftKey);
  const down = Boolean(event.ctrlKey);
  if (up && down) {
    return 0;
  }
  if (up) {
    return 1;
  }
  if (down) {
    return -1;
  }
  return 0;
}

function clampFrequencyToSampleRange(frequency) {
  if (!state.audioManifest || !Array.isArray(state.audioManifest.samples) || !state.audioManifest.samples.length) {
    return frequency;
  }
  let minHz = Number.POSITIVE_INFINITY;
  let maxHz = Number.NEGATIVE_INFINITY;
  for (const sample of state.audioManifest.samples) {
    if (sample.hz < minHz) {
      minHz = sample.hz;
    }
    if (sample.hz > maxHz) {
      maxHz = sample.hz;
    }
  }
  if (!Number.isFinite(minHz) || !Number.isFinite(maxHz)) {
    return frequency;
  }
  return Math.min(maxHz, Math.max(minHz, frequency));
}

function getToneContext() {
  if (!state.meta) {
    return null;
  }

  const gender = ui.genderSelect?.value || state.settings?.gender || state.meta.defaults.gender;
  const key = ui.keySelect?.value || state.settings?.key || state.meta.defaults.key;
  const temperament =
    ui.temperamentSelect?.value || state.settings?.temperament || state.meta.defaults.temperament;

  const genderOption = state.meta.genders.find((item) => item.id === gender);
  if (!genderOption) {
    return null;
  }

  const keyIndex = state.meta.keys.findIndex((item) => item.id === key);
  if (keyIndex < 0) {
    return null;
  }

  const doFrequency = genderOption.baseDoAtC * (2 ** (keyIndex / 12));
  return { gender, key, doFrequency, temperament };
}

function resolveKeyboardDegree(event) {
  if (/^[1-7]$/.test(event.key)) {
    return Number(event.key);
  }

  const code = event.code || "";
  const match = /^(Digit|Numpad)([1-7])$/.exec(code);
  if (match) {
    return Number(match[2]);
  }

  const alternativeMap = {
    KeyM: 1,
    Comma: 2,
    Period: 3,
    KeyJ: 4,
    KeyK: 5,
    KeyL: 6,
    KeyU: 7,
  };
  const mapped = alternativeMap[code];
  if (mapped) {
    return mapped;
  }

  return null;
}

function goHomeView() {
  closeFullKeyboardMode();
  state.session = null;
  navigateToView("dashboardView");
  renderModuleGrid();
  renderHistory();
}

function switchView(viewId) {
  const views = [ui.dashboardView, ui.quizView, ui.resultView];

  for (const view of views) {
    if (view.id === viewId) {
      view.classList.remove("hidden");
      view.classList.add("active");
    } else {
      view.classList.add("hidden");
      view.classList.remove("active");
    }
  }
}

function navigateToView(viewId) {
  if (viewId !== "dashboardView") {
    closeFullKeyboardMode();
  }
  switchView(viewId);
  window.history.pushState({ view: viewId }, "");
}

function handlePopState(event) {
  const targetView = event.state?.view || "dashboardView";

  if ((targetView === "quizView" || targetView === "resultView") && !state.session) {
    switchView("dashboardView");
    window.history.replaceState({ view: "dashboardView" }, "");
    renderModuleGrid();
    renderHistory();
    return;
  }

  if (targetView === "dashboardView") {
    state.session = null;
    renderModuleGrid();
    renderHistory();
  } else {
    closeFullKeyboardMode();
  }

  switchView(targetView);
}

function formatNoteLabel(note) {
  if (note.accidental === "sharp") {
    return `#${note.degree}`;
  }
  if (note.accidental === "flat") {
    return `b${note.degree}`;
  }
  return String(note.degree);
}

function mapDegreeToY(degree) {
  const clamped = Math.max(1, Math.min(7, degree));
  return 14 + ((clamped - 1) / 6) * 72;
}

function mapNoteToY(note) {
  const naturalIndex = Math.max(1, Math.min(7, Number(note.degree))) - 1;
  let scalePosition = naturalIndex;

  if (note.accidental === "sharp") {
    scalePosition += 0.5;
  } else if (note.accidental === "flat") {
    scalePosition -= 0.5;
  }

  const clampedPosition = Math.max(0, Math.min(6, scalePosition));
  return 14 + (clampedPosition / 6) * 72;
}

function readStorage(key, fallback) {
  try {
    const value = localStorage.getItem(key);
    if (!value) {
      return fallback;
    }
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function writeStorage(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function showGlobalError(message) {
  appendAudioDebugLog(`Global error: ${message}`);
  ui.globalError.textContent = message;
  ui.globalError.classList.remove("hidden");
}

function hideGlobalError() {
  ui.globalError.classList.add("hidden");
  ui.globalError.textContent = "";
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
