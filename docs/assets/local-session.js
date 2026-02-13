const QUESTION_COUNT = 20;

const EQUAL_TEMPERAMENT = "equal_temperament";
const PITCH_MODULE_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6"];

const TEMPERAMENT_OPTIONS = [
  { id: EQUAL_TEMPERAMENT, label: "Equal" },
];

const KEY_OPTIONS = [
  { id: "C", label: "1=C" },
  { id: "C#/Db", label: "1=C#/Db" },
  { id: "D", label: "1=D" },
  { id: "D#/Eb", label: "1=D#/Eb" },
  { id: "E", label: "1=E" },
  { id: "F", label: "1=F" },
  { id: "F#/Gb", label: "1=F#/Gb" },
  { id: "G", label: "1=G" },
  { id: "G#/Ab", label: "1=G#/Ab" },
  { id: "A", label: "1=A" },
  { id: "A#/Bb", label: "1=A#/Bb" },
  { id: "B", label: "1=B" },
];

const KEY_OFFSETS = new Map(KEY_OPTIONS.map((entry, index) => [entry.id, index]));

const MALE_DO_C = 130.8;
const FEMALE_DO_C = 261.6;

const GENDER_OPTIONS = [
  { id: "male", label: "Male", baseDoAtC: MALE_DO_C },
  { id: "female", label: "Female", baseDoAtC: FEMALE_DO_C },
];

const GENDER_BASE_DO = {
  male: MALE_DO_C,
  female: FEMALE_DO_C,
};

const INSTRUMENT_OPTIONS = [
  { id: "piano", label: "Piano" },
  { id: "guitar", label: "Guitar" },
];

const CHROMA_NOTES = [
  { token: "1", display: "1", degree: 1, accidental: "natural", semitone: 0 },
  {
    token: "#1",
    display: "#1/b2",
    degree: 1,
    accidental: "sharp",
    semitone: 1,
    enharmonicDegree: 2,
    enharmonicAccidental: "flat",
  },
  { token: "2", display: "2", degree: 2, accidental: "natural", semitone: 2 },
  {
    token: "#2",
    display: "#2/b3",
    degree: 2,
    accidental: "sharp",
    semitone: 3,
    enharmonicDegree: 3,
    enharmonicAccidental: "flat",
  },
  { token: "3", display: "3", degree: 3, accidental: "natural", semitone: 4 },
  { token: "4", display: "4", degree: 4, accidental: "natural", semitone: 5 },
  {
    token: "#4",
    display: "#4/b5",
    degree: 4,
    accidental: "sharp",
    semitone: 6,
    enharmonicDegree: 5,
    enharmonicAccidental: "flat",
  },
  { token: "5", display: "5", degree: 5, accidental: "natural", semitone: 7 },
  {
    token: "#5",
    display: "#5/b6",
    degree: 5,
    accidental: "sharp",
    semitone: 8,
    enharmonicDegree: 6,
    enharmonicAccidental: "flat",
  },
  { token: "6", display: "6", degree: 6, accidental: "natural", semitone: 9 },
  {
    token: "#6",
    display: "#6/b7",
    degree: 6,
    accidental: "sharp",
    semitone: 10,
    enharmonicDegree: 7,
    enharmonicAccidental: "flat",
  },
  { token: "7", display: "7", degree: 7, accidental: "natural", semitone: 11 },
];

const NOTE_BY_TOKEN = new Map(CHROMA_NOTES.map((note) => [note.token, note]));

const DIFFICULTY_LEVELS = {
  L1: {
    id: "L1_TRIAD",
    label: "Triad Notes",
    tokens: ["1", "3", "5"],
    display: "1,3,5",
  },
  L2: {
    id: "L2_PENTA",
    label: "Pentatonic Expansion",
    tokens: ["1", "2", "3", "5", "6"],
    display: "1,2,3,5,6",
  },
  L3: {
    id: "L3_HEPTA",
    label: "Heptatonic",
    tokens: ["1", "2", "3", "4", "5", "6", "7"],
    display: "1,2,3,4,5,6,7",
  },
  L4: {
    id: "L4_CHROMA",
    label: "Chromatic",
    tokens: ["1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7"],
    display: "1,#1/b2,2,#2/b3,3,4,#4/b5,5,#5/b6,6,#6/b7,7",
  },
  L5: {
    id: "L5_WHOLE_TONE",
    label: "Whole-Tone Proximity",
    tokens: ["1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7"],
    display: "L5 uses close-note drills (1 whole tone / 2 semitones)",
  },
  L6: {
    id: "L6_SEMITONE",
    label: "Semitone Proximity",
    tokens: ["1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7"],
    display: "L6 uses closest-note drills (1 semitone)",
  },
};

function buildModules() {
  const modules = [];
  let order = 1;

  for (const level of PITCH_MODULE_LEVELS) {
    modules.push({
      id: `M2-${level}`,
      title: `Two Notes: Higher or Lower (${level})`,
      questionType: "compare_two",
      level,
      recommendedOrder: order,
    });
    order += 1;
  }

  for (const level of PITCH_MODULE_LEVELS) {
    modules.push({
      id: `M3-${level}`,
      title: `Three Notes: Sort Low to High (${level})`,
      questionType: "sort_three",
      level,
      recommendedOrder: order,
    });
    order += 1;
  }

  for (const level of PITCH_MODULE_LEVELS) {
    modules.push({
      id: `M4-${level}`,
      title: `Four Notes: Sort Low to High (${level})`,
      questionType: "sort_four",
      level,
      recommendedOrder: order,
    });
    order += 1;
  }

  for (const level of ["L1", "L2", "L3"]) {
    modules.push({
      id: `MI-${level}`,
      title: `Two Notes: Scale-Step Distance (${level})`,
      questionType: "interval_scale",
      level,
      recommendedOrder: order,
    });
    order += 1;
  }

  for (const level of ["L1", "L2", "L3", "L4"]) {
    modules.push({
      id: `MS-${level}`,
      title: `Single Note Guess (${level})`,
      questionType: "single_note",
      level,
      recommendedOrder: order,
    });
    order += 1;
  }

  return modules;
}

const MODULES = buildModules();
const MODULE_MAP = new Map(MODULES.map((module) => [module.id, module]));

function roundTo(value, digits = 4) {
  const scale = 10 ** digits;
  return Math.round(value * scale) / scale;
}

function randomChoice(values) {
  if (!Array.isArray(values) || values.length === 0) {
    throw new Error("Cannot choose from an empty list");
  }
  const index = Math.floor(Math.random() * values.length);
  return values[index];
}

function shuffleInPlace(values) {
  for (let index = values.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [values[index], values[swapIndex]] = [values[swapIndex], values[index]];
  }
  return values;
}

function sampleWithoutReplacement(values, count) {
  if (!Array.isArray(values)) {
    throw new Error("Expected array for sampling");
  }
  if (count > values.length) {
    throw new Error(`Cannot sample ${count} elements from list of ${values.length}`);
  }
  const copy = [...values];
  shuffleInPlace(copy);
  return copy.slice(0, count);
}

function calculateDoFrequency(gender, keyId) {
  if (!Object.hasOwn(GENDER_BASE_DO, gender)) {
    throw new Error(`Unknown gender '${gender}'`);
  }
  if (!KEY_OFFSETS.has(keyId)) {
    throw new Error(`Unknown key '${keyId}'`);
  }
  const baseDo = GENDER_BASE_DO[gender];
  const semitoneShift = KEY_OFFSETS.get(keyId);
  return baseDo * (2 ** (semitoneShift / 12));
}

function noteFrequency(semitone, doFrequency, temperament) {
  if (temperament !== EQUAL_TEMPERAMENT) {
    throw new Error(`Unsupported temperament '${temperament}'`);
  }
  return doFrequency * (2 ** (semitone / 12));
}

function getNotePool(level) {
  const definition = DIFFICULTY_LEVELS[level];
  if (!definition) {
    throw new Error(`Unknown level '${level}'`);
  }
  return definition.tokens.map((token) => NOTE_BY_TOKEN.get(token));
}

function buildDifficultyMetadata() {
  return Object.entries(DIFFICULTY_LEVELS).map(([level, info]) => ({
    level,
    id: info.id,
    label: info.label,
    displayNotes: info.display,
    tokens: [...info.tokens],
  }));
}

function buildNotePayload(note, doFrequency, temperament) {
  const payload = {
    token: note.token,
    label: note.display,
    degree: note.degree,
    accidental: note.accidental,
    semitone: note.semitone,
    frequency: roundTo(noteFrequency(note.semitone, doFrequency, temperament), 4),
  };

  if (
    Number.isInteger(note.enharmonicDegree) &&
    typeof note.enharmonicAccidental === "string"
  ) {
    payload.enharmonic = {
      degree: note.enharmonicDegree,
      accidental: note.enharmonicAccidental,
    };
  }

  return payload;
}

function resolveNotePoolLevel(module) {
  if (module.questionType === "sort_four" && module.level === "L1") {
    return "L2";
  }
  return module.level;
}

function intervalConstraintForLevel(level) {
  if (level === "L5") {
    return 2;
  }
  if (level === "L6") {
    return 1;
  }
  return null;
}

function buildVisualHints(notes) {
  const semitones = notes.map((note) => note.semitone);
  const minSemitone = Math.min(...semitones);
  const maxSemitone = Math.max(...semitones);

  if (maxSemitone === minSemitone) {
    return notes.map((_, index) => ({ index: index + 1, height: 50.0 }));
  }

  return notes.map((note, index) => {
    const normalized = (note.semitone - minSemitone) / (maxSemitone - minSemitone);
    return { index: index + 1, height: roundTo(10 + normalized * 80, 2) };
  });
}

function pickCompareNotes(notesPool, intervalStep) {
  if (intervalStep === null) {
    return sampleWithoutReplacement(notesPool, 2);
  }

  const validPairs = [];
  for (let leftIndex = 0; leftIndex < notesPool.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < notesPool.length; rightIndex += 1) {
      const left = notesPool[leftIndex];
      const right = notesPool[rightIndex];
      if (Math.abs(left.semitone - right.semitone) === intervalStep) {
        validPairs.push([left, right]);
      }
    }
  }

  if (!validPairs.length) {
    return sampleWithoutReplacement(notesPool, 2);
  }

  const picked = [...randomChoice(validPairs)];
  shuffleInPlace(picked);
  return picked;
}

function pickSortNotes(notesPool, noteCount, intervalStep) {
  if (intervalStep === null) {
    return sampleWithoutReplacement(notesPool, noteCount);
  }

  const noteBySemitone = new Map(notesPool.map((note) => [note.semitone, note]));
  const semitoneValues = [...noteBySemitone.keys()].sort((left, right) => left - right);
  const validSequences = [];

  for (const start of semitoneValues) {
    const sequence = [];
    let valid = true;
    for (let index = 0; index < noteCount; index += 1) {
      const semitone = start + intervalStep * index;
      if (!noteBySemitone.has(semitone)) {
        valid = false;
        break;
      }
      sequence.push(semitone);
    }
    if (valid) {
      validSequences.push(sequence);
    }
  }

  if (!validSequences.length) {
    return sampleWithoutReplacement(notesPool, noteCount);
  }

  const selected = randomChoice(validSequences);
  const picked = selected.map((semitone) => noteBySemitone.get(semitone));
  shuffleInPlace(picked);
  return picked;
}

function buildNotePayloads(notes, doFrequency, temperament, mapTargetFrequency) {
  return notes.map((note) => {
    const payload = buildNotePayload(note, doFrequency, temperament);
    if (typeof mapTargetFrequency === "function") {
      const mapping = mapTargetFrequency(payload.frequency);
      if (mapping && typeof mapping.sampleId === "string") {
        payload.sampleId = mapping.sampleId;
      }
      if (mapping && Number.isFinite(mapping.midi)) {
        payload.midi = mapping.midi;
      }
    }
    return payload;
  });
}

function getPossibleIntervalDistances(notesPool) {
  const distances = new Set();
  for (let leftIndex = 0; leftIndex < notesPool.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < notesPool.length; rightIndex += 1) {
      const distance = Math.abs(notesPool[leftIndex].degree - notesPool[rightIndex].degree);
      if (distance > 0) {
        distances.add(distance);
      }
    }
  }
  return [...distances].sort((left, right) => left - right);
}

function generateCompareQuestion(module, questionNumber, notesPool, doFrequency, temperament, instrument, mapTargetFrequency) {
  const intervalStep = intervalConstraintForLevel(module.level);
  const picked = pickCompareNotes(notesPool, intervalStep);
  const notePayloads = buildNotePayloads(picked, doFrequency, temperament, mapTargetFrequency);
  const correctAnswer = picked[0].semitone > picked[1].semitone ? "first_higher" : "second_higher";

  return {
    id: `${module.id}-Q${questionNumber}`,
    type: module.questionType,
    notes: notePayloads,
    visualHints: buildVisualHints(picked),
    choices: [
      { id: "first_higher", label: "First note is higher" },
      { id: "second_higher", label: "Second note is higher" },
    ],
    correctAnswer,
    promptText: "Listen to two notes. Which one is higher?",
  };
}

function generateSortQuestion(
  module,
  questionNumber,
  notesPool,
  doFrequency,
  temperament,
  instrument,
  mapTargetFrequency,
  noteCount,
) {
  const intervalStep = intervalConstraintForLevel(module.level);
  const picked = pickSortNotes(notesPool, noteCount, intervalStep);
  const notePayloads = buildNotePayloads(picked, doFrequency, temperament, mapTargetFrequency);
  const sortedIndices = [...Array(noteCount).keys()].sort(
    (left, right) => picked[left].semitone - picked[right].semitone,
  );

  return {
    id: `${module.id}-Q${questionNumber}`,
    type: module.questionType,
    notes: notePayloads,
    visualHints: buildVisualHints(picked),
    choices: {
      positions: [...Array(noteCount).keys()].map((index) => String(index + 1)),
      format: "index_sequence",
    },
    correctAnswer: sortedIndices.map((index) => String(index + 1)).join("-"),
    promptText: `Listen to ${noteCount} notes. Sort from low to high.`,
  };
}

function generateIntervalQuestion(module, questionNumber, notesPool, doFrequency, temperament, instrument, mapTargetFrequency) {
  const picked = sampleWithoutReplacement(notesPool, 2);
  const notePayloads = buildNotePayloads(picked, doFrequency, temperament, mapTargetFrequency);
  const distance = Math.abs(picked[0].degree - picked[1].degree);
  const possibleDistances = getPossibleIntervalDistances(notesPool);

  return {
    id: `${module.id}-Q${questionNumber}`,
    type: module.questionType,
    notes: notePayloads,
    visualHints: buildVisualHints(picked),
    choices: possibleDistances.map((item) => String(item)),
    correctAnswer: String(distance),
    promptText: "How many scale steps apart are these two notes?",
  };
}

function generateSingleNoteQuestion(module, questionNumber, notesPool, doFrequency, temperament, instrument, mapTargetFrequency) {
  const picked = randomChoice(notesPool);
  const notePayload = buildNotePayloads([picked], doFrequency, temperament, mapTargetFrequency)[0];

  const correctAnswer = {
    degree: String(picked.degree),
    accidental: picked.accidental,
  };

  if (
    Number.isInteger(picked.enharmonicDegree) &&
    typeof picked.enharmonicAccidental === "string"
  ) {
    correctAnswer.accepted = [
      {
        degree: String(picked.enharmonicDegree),
        accidental: picked.enharmonicAccidental,
      },
    ];
  }

  return {
    id: `${module.id}-Q${questionNumber}`,
    type: module.questionType,
    notes: [notePayload],
    visualHints: [],
    choices: {
      degrees: ["1", "2", "3", "4", "5", "6", "7"],
      accidentals: module.level === "L4" ? ["flat", "natural", "sharp"] : ["natural"],
      requiresAccidental: module.level === "L4",
    },
    correctAnswer,
    promptText: "Listen to one note. Choose the movable-do number.",
  };
}

function generateQuestion(module, questionNumber, notesPool, doFrequency, temperament, instrument, mapTargetFrequency) {
  if (module.questionType === "compare_two") {
    return generateCompareQuestion(
      module,
      questionNumber,
      notesPool,
      doFrequency,
      temperament,
      instrument,
      mapTargetFrequency,
    );
  }

  if (module.questionType === "sort_three") {
    return generateSortQuestion(
      module,
      questionNumber,
      notesPool,
      doFrequency,
      temperament,
      instrument,
      mapTargetFrequency,
      3,
    );
  }

  if (module.questionType === "sort_four") {
    return generateSortQuestion(
      module,
      questionNumber,
      notesPool,
      doFrequency,
      temperament,
      instrument,
      mapTargetFrequency,
      4,
    );
  }

  if (module.questionType === "interval_scale") {
    return generateIntervalQuestion(
      module,
      questionNumber,
      notesPool,
      doFrequency,
      temperament,
      instrument,
      mapTargetFrequency,
    );
  }

  if (module.questionType === "single_note") {
    return generateSingleNoteQuestion(
      module,
      questionNumber,
      notesPool,
      doFrequency,
      temperament,
      instrument,
      mapTargetFrequency,
    );
  }

  throw new Error(`Unsupported question type '${module.questionType}'`);
}

function createSessionId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `local-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function validateInput(moduleId, gender, key, temperament, instrument) {
  if (!MODULE_MAP.has(moduleId)) {
    throw new Error(`Unknown module '${moduleId}'`);
  }
  if (!Object.hasOwn(GENDER_BASE_DO, gender)) {
    throw new Error(`Unknown gender '${gender}'`);
  }
  if (!KEY_OFFSETS.has(key)) {
    throw new Error(`Unknown key '${key}'`);
  }
  if (temperament !== EQUAL_TEMPERAMENT) {
    throw new Error(`Unknown temperament '${temperament}'`);
  }
  if (!INSTRUMENT_OPTIONS.some((item) => item.id === instrument)) {
    throw new Error(`Unknown instrument '${instrument}'`);
  }
}

export function buildMeta() {
  return {
    genders: GENDER_OPTIONS,
    keys: KEY_OPTIONS,
    temperaments: TEMPERAMENT_OPTIONS,
    instruments: INSTRUMENT_OPTIONS,
    difficulties: buildDifficultyMetadata(),
    modules: MODULES,
    defaults: {
      gender: "male",
      key: "C",
      temperament: EQUAL_TEMPERAMENT,
      instrument: "piano",
      showVisualHints: false,
      questionCount: QUESTION_COUNT,
    },
  };
}

export function generateSession(options = {}) {
  const moduleId = options.moduleId;
  const gender = options.gender;
  const key = options.key;
  const temperament = options.temperament;
  const instrument = options.instrument || "piano";
  const mapTargetFrequency = options.mapTargetFrequency;

  validateInput(moduleId, gender, key, temperament, instrument);

  const module = MODULE_MAP.get(moduleId);
  const effectiveLevel = resolveNotePoolLevel(module);
  const notesPool = getNotePool(effectiveLevel);
  const doFrequency = calculateDoFrequency(gender, key);

  const questions = [];
  for (let index = 0; index < QUESTION_COUNT; index += 1) {
    questions.push(
      generateQuestion(
        module,
        index + 1,
        notesPool,
        doFrequency,
        temperament,
        instrument,
        mapTargetFrequency,
      ),
    );
  }

  return {
    sessionId: createSessionId(),
    settings: {
      moduleId,
      moduleTitle: module.title,
      level: module.level,
      effectiveNotePoolLevel: effectiveLevel,
      questionType: module.questionType,
      gender,
      key,
      temperament,
      instrument,
      questionCount: QUESTION_COUNT,
      doFrequency: roundTo(doFrequency, 4),
    },
    questions,
  };
}

export { EQUAL_TEMPERAMENT };
