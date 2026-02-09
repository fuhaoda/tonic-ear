const API_BASE = "/api/v1";
const PIANO_MANIFEST_PATH = "/assets/audio/piano/manifest.json";

const NOTE_GAP_MS = 250;
const SETTINGS_VERSION = 4;
const MAX_CENTS_ERROR = 10;
const MAX_POLYPHONY = 5;

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
  sampleById: new Map(),
  sampleBufferCache: new Map(),
  sampleFetchPromises: new Map(),
  sampleLoadPromise: null,
  keyboardTonePlan: null,
  activeVoices: [],
};

const ui = {};

window.addEventListener("DOMContentLoaded", init);

async function init() {
  cacheElements();
  bindStaticEvents();

  try {
    await loadMeta();
    await loadAudioManifest();
    hydrateSettings();
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
  ui.touchKeyboardButtons = document.getElementById("touchKeyboardButtons");
}

function bindStaticEvents() {
  ui.moduleGrid.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-module-id]");
    if (!button) {
      return;
    }
    const moduleId = button.dataset.moduleId;
    void startSession(moduleId);
  });

  ui.genderSelect.addEventListener("change", onSettingsChange);
  ui.keySelect.addEventListener("change", onSettingsChange);
  ui.temperamentSelect.addEventListener("change", onSettingsChange);

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
    void startSession(state.session.settings.moduleId);
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

async function loadMeta() {
  const response = await fetch(`${API_BASE}/meta`);
  if (!response.ok) {
    throw new Error("Failed to load app metadata");
  }

  const meta = await response.json();
  state.meta = meta;
  state.moduleMap = new Map(meta.modules.map((module) => [module.id, module]));
}

async function loadAudioManifest() {
  const response = await fetch(PIANO_MANIFEST_PATH, { cache: "no-cache" });
  if (!response.ok) {
    throw new Error("Failed to load piano audio manifest");
  }

  const manifest = await response.json();
  if (!Array.isArray(manifest.samples) || manifest.samples.length === 0) {
    throw new Error("Piano manifest is missing sample entries");
  }

  state.audioManifest = manifest;
  state.sampleById = new Map(manifest.samples.map((item) => [item.id, item]));
}

function hydrateSettings() {
  const saved = readStorage(LS_SETTINGS, {});
  const isCurrentVersion = saved.version === SETTINGS_VERSION;

  if (!isCurrentVersion) {
    state.settings = {
      version: SETTINGS_VERSION,
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
  renderSelect(ui.genderSelect, state.meta.genders, state.settings.gender);
  renderSelect(ui.keySelect, state.meta.keys, state.settings.key);
  renderSelect(ui.temperamentSelect, state.meta.temperaments, state.settings.temperament);

  ui.showVisualHints.checked = state.settings.showVisualHints;
  ui.quizShowVisualHints.checked = state.settings.showVisualHints;
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

function onSettingsChange() {
  state.settings.version = SETTINGS_VERSION;
  state.settings.gender = ui.genderSelect.value;
  state.settings.key = ui.keySelect.value;
  state.settings.temperament = ui.temperamentSelect.value;
  state.keyboardTonePlan = null;
  persistSettings();
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

function renderModuleGrid() {
  const stats = readStorage(LS_MODULE_STATS, {});

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
    const moduleStat = stats[module.id];
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

  if (!history.length) {
    ui.historyList.innerHTML = `<p class="subtle">No training history yet.</p>`;
    return;
  }

  ui.historyList.innerHTML = "";
  for (const item of history.slice(0, 8)) {
    const row = document.createElement("div");
    row.className = "history-row";

    const left = document.createElement("div");
    left.innerHTML = `<strong>${item.moduleId}</strong> <span class="subtle">${item.moduleTitle}</span>`;

    const right = document.createElement("div");
    const date = new Date(item.completedAt);
    right.className = "subtle";
    right.textContent = `${item.accuracy.toFixed(1)}% | ${date.toLocaleString()}`;

    row.append(left, right);
    ui.historyList.appendChild(row);
  }
}

async function startSession(moduleId) {
  hideGlobalError();

  const payload = {
    moduleId,
    gender: ui.genderSelect.value,
    key: ui.keySelect.value,
    temperament: ui.temperamentSelect.value,
  };

  state.settings.gender = payload.gender;
  state.settings.key = payload.key;
  state.settings.temperament = payload.temperament;
  persistSettings();

  try {
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

    await unlockAudioPipeline();
    void preloadAllSamples().catch(() => {
      // Warmup failures are non-fatal; playback paths retry on demand.
    });
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

  const history = readStorage(LS_HISTORY, []);
  history.unshift({
    moduleId: settings.moduleId,
    moduleTitle: settings.moduleTitle,
    accuracy,
    completedAt: new Date().toISOString(),
  });
  writeStorage(LS_HISTORY, history.slice(0, 100));

  const stats = readStorage(LS_MODULE_STATS, {});
  const current = stats[settings.moduleId] || {
    attempts: 0,
    bestAccuracy: 0,
    lastAccuracy: 0,
    updatedAt: null,
  };

  current.attempts += 1;
  current.bestAccuracy = Math.max(current.bestAccuracy, accuracy);
  current.lastAccuracy = accuracy;
  current.updatedAt = new Date().toISOString();

  stats[settings.moduleId] = current;
  writeStorage(LS_MODULE_STATS, stats);
}

function renderResult(correctCount, total, accuracy, wrongItems) {
  ui.scoreLine.textContent = `Score: ${correctCount} / ${total} (${accuracy.toFixed(1)}%)`;
  const temperamentLabel =
    state.meta?.temperaments.find((item) => item.id === state.session.settings.temperament)?.label ||
    state.session.settings.temperament;
  ui.scoreDetail.textContent = `Module: ${state.session.settings.moduleId} | Key: 1=${state.session.settings.key} | Temperament: ${temperamentLabel}`;

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
  const context = getOrCreateAudioContext();
  if (context.state === "running") {
    return context;
  }
  await unlockAudioPipeline();
  if (context.state !== "running") {
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
        removeAudioUnlockListeners();
      }
    })
    .catch(() => {
      // Keep listeners active for the next user gesture.
    });
}

function armAudioUnlockListeners() {
  const options = { capture: true };
  window.addEventListener("pointerdown", warmAudioPipelineOnce, options);
  window.addEventListener("touchstart", warmAudioPipelineOnce, options);
  window.addEventListener("click", warmAudioPipelineOnce, options);
  window.addEventListener("keydown", warmAudioPipelineOnce, options);
}

function removeAudioUnlockListeners() {
  const options = { capture: true };
  window.removeEventListener("pointerdown", warmAudioPipelineOnce, options);
  window.removeEventListener("touchstart", warmAudioPipelineOnce, options);
  window.removeEventListener("click", warmAudioPipelineOnce, options);
  window.removeEventListener("keydown", warmAudioPipelineOnce, options);
}

async function unlockAudioPipeline() {
  const context = getOrCreateAudioContext();
  if (context.state === "running") {
    state.audioUnlocked = true;
    return;
  }

  if (!state.audioUnlockPromise) {
    state.audioUnlockPromise = context
      .resume()
      .then(() => {
        primeAudioContextTick(context);
        state.audioUnlocked = true;
      })
      .finally(() => {
        state.audioUnlockPromise = null;
      });
  }

  await state.audioUnlockPromise;
}

async function preloadAllSamples() {
  if (state.sampleLoadPromise) {
    return state.sampleLoadPromise;
  }

  if (!state.audioManifest) {
    throw new Error("Piano manifest is not loaded");
  }

  state.sampleLoadPromise = (async () => {
    const context = getOrCreateAudioContext();
    await Promise.all(state.audioManifest.samples.map((sample) => ensureSampleBuffer(context, sample.id)));
  })();

  try {
    await state.sampleLoadPromise;
  } catch (error) {
    state.sampleLoadPromise = null;
    throw error;
  }
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
      throw new Error(`Unknown piano sample '${sampleId}'`);
    }

    const response = await fetch(sample.file, { cache: "force-cache" });
    if (!response.ok) {
      throw new Error(`Failed to load piano sample '${sampleId}'`);
    }

    const encoded = await response.arrayBuffer();
    const decoded = await decodeAudioData(context, encoded);
    state.sampleBufferCache.set(sampleId, decoded);
    return decoded;
  })()
    .catch((error) => {
      state.sampleBufferCache.delete(sampleId);
      throw error;
    })
    .finally(() => {
      state.sampleFetchPromises.delete(sampleId);
    });

  state.sampleFetchPromises.set(sampleId, promise);
  return promise;
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
    throw new Error("Piano sample manifest is unavailable");
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
    showGlobalError(error.message || "Failed to play tones");
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

  if (state.activeVoices.length >= MAX_POLYPHONY) {
    return;
  }

  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);

  source.onended = () => {
    state.activeVoices = state.activeVoices.filter((voice) => voice !== source);
  };

  state.activeVoices.push(source);
  source.start(startAt);
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
    showGlobalError(error.message || "Failed to play keyboard tone");
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

  return null;
}

function goHomeView() {
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
