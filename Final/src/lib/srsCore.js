export const BASE_LEVEL_WEIGHTS = { 1: 45, 2: 25, 3: 15, 4: 10, 5: 5 }
export const LEVEL_ONE_TARGET = 10
export const RECENT_HISTORY_WINDOW = 5
export const LEVEL_HISTORY_WINDOW = 20
export const LEVEL_WEIGHT_FLOOR = 0.15
export const LEVEL_WEIGHT_EXPONENT = 1.35
export const RELAPSE_BOOST_WINDOW = 6
export const RELAPSE_BOOST_WEIGHT = 18
export const MODE_BALANCE_STEP = 10
export const MODE_HISTORY_WINDOW = 10
export const DEFAULT_VI_TO_EN_RATIO = 70
export const STATE_VERSION = 2

export const MODE_LABELS = {
    intro: 'Làm quen từ mới',
    vi_to_en: 'Việt -> Anh',
    en_to_vi: 'Anh -> Việt',
}

export function cloneDeep(value) {
    if (typeof structuredClone === 'function') {
        return structuredClone(value)
    }
    return JSON.parse(JSON.stringify(value))
}

export function normalizeSpaces(text) {
    return String(text ?? '').replace(/\s+/g, ' ').trim()
}

export function normalizeAnswer(text) {
    return String(text ?? '')
        .trim()
        .toLowerCase()
        .replace(/[’`]/g, "'")
        .replace(/\s+/g, ' ')
}

export function matchEnglishAnswer(answer, target) {
    return normalizeAnswer(answer) === normalizeAnswer(target)
}

export function listCombinedVocabNames(payload) {
    if (!payload || typeof payload !== 'object' || !Array.isArray(payload.tests)) {
        return []
    }

    return payload.tests
        .map((item) => String(item?.test ?? '').trim())
        .filter(Boolean)
}

export function createEntriesFromPayload(payload, selectedName = null) {
    const combinedNames = listCombinedVocabNames(payload)
    let items = Array.isArray(payload?.items) ? payload.items : []

    if (combinedNames.length && selectedName && combinedNames.includes(selectedName)) {
        items = items.filter((item) => String(item?.test ?? '').trim() === selectedName)
    }

    return items
        .map((item, index) => {
            const word = normalizeSpaces(item?.word)
            if (!word) return null

            return {
                wid: `${index + 1}:${word.toLowerCase()}`,
                word,
                pos: String(item?.pos ?? '').trim(),
                meaning_vi: normalizeSpaces(item?.meaning_vi),
                meaning_en: normalizeSpaces(item?.meaning_en),
                example_1: String(item?.example_1 ?? '').trim(),
                example_2: String(item?.example_2 ?? '').trim(),
                phonetic: String(item?.phonetic ?? '').trim(),
                notes: String(item?.notes ?? '').trim(),
            }
        })
        .filter(Boolean)
}

export function vocabSignature(vocab) {
    return vocab
        .map((entry) => [
            entry.wid,
            entry.word,
            entry.meaning_vi,
            entry.meaning_en,
            entry.example_1,
            entry.example_2,
            entry.notes,
        ].join('|'))
        .join('\n')
}

export function buildInitialState(signature, vocab) {
    return {
        version: STATE_VERSION,
        vocab_signature: signature,
        turn: 0,
        recent_history: [],
        review_level_history: [],
        review_mode_history: [],
        settings: {
            vi_to_en_ratio: DEFAULT_VI_TO_EN_RATIO,
        },
        words: Object.fromEntries(
            vocab.map((entry) => [entry.wid, {
                status: 'pending',
                level: null,
                excluded: false,
                times_seen: 0,
                last_seen_turn: null,
                last_mode: null,
                relapse_until_turn: null,
            }]),
        ),
    }
}

export function normalizeViToEnRatio(value) {
    let numeric = Number.isFinite(Number(value)) ? Number(value) : DEFAULT_VI_TO_EN_RATIO
    numeric = Math.max(0, Math.min(100, numeric))
    return Math.round(numeric / MODE_BALANCE_STEP) * MODE_BALANCE_STEP
}

export function ensureStateDefaults(state) {
    const nextState = state ?? {}
    nextState.recent_history ??= []
    nextState.review_level_history ??= []
    nextState.review_mode_history ??= []
    nextState.settings ??= {}
    nextState.words ??= {}
    Object.values(nextState.words).forEach((meta) => {
        meta.excluded ??= false
    })
    nextState.settings.vi_to_en_ratio = normalizeViToEnRatio(nextState.settings.vi_to_en_ratio)
    nextState.version = STATE_VERSION
    return nextState
}

export function levelCounts(state) {
    const counts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }
    let pending = 0
    let excluded = 0

    Object.values(state.words).forEach((meta) => {
        if (meta.excluded) {
            excluded += 1
            return
        }

        if (meta.status === 'pending') {
            pending += 1
        } else if ([1, 2, 3, 4, 5].includes(Number(meta.level))) {
            counts[Number(meta.level)] += 1
        }
    })

    return { counts, pending, excluded }
}

export function progressLine(state, previewNewWord = false) {
    const { counts, pending: originalPending } = levelCounts(state)
    let pending = originalPending

    if (previewNewWord && pending > 0) {
        counts[1] += 1
        pending -= 1
    }

    return `Tiến độ: B1 ${counts[1]} | B2 ${counts[2]} | B3 ${counts[3]} | B4 ${counts[4]} | B5 ${counts[5]} | Chưa mở ${pending}`
}

export function progressPayload(state, previewNewWord = false) {
    const { counts, pending: originalPending, excluded } = levelCounts(state)
    let pending = originalPending

    if (previewNewWord && pending > 0) {
        counts[1] += 1
        pending -= 1
    }

    return {
        b1: counts[1],
        b2: counts[2],
        b3: counts[3],
        b4: counts[4],
        b5: counts[5],
        pending,
        excluded,
        line: progressLine(state, previewNewWord),
    }
}

export function currentModeBalance(state) {
    ensureStateDefaults(state)
    const viToEnRatio = normalizeViToEnRatio(state.settings.vi_to_en_ratio)
    return {
        vi_to_en_ratio: viToEnRatio,
        en_to_vi_ratio: 100 - viToEnRatio,
        window: MODE_HISTORY_WINDOW,
    }
}

export function setModeBalance(state, viToEnRatio) {
    ensureStateDefaults(state)
    state.settings.vi_to_en_ratio = normalizeViToEnRatio(viToEnRatio)
    return currentModeBalance(state)
}

function weightedChoice(items, random = Math.random) {
    const total = items.reduce((sum, [, weight]) => sum + weight, 0)
    let pick = random() * total

    for (const [value, weight] of items) {
        pick -= weight
        if (pick <= 0) return value
    }

    return items[items.length - 1][0]
}

export function dynamicLevelTargets(availableLevels) {
    if (!availableLevels.length) return {}

    const totalWeight = availableLevels.reduce((sum, level) => sum + BASE_LEVEL_WEIGHTS[level], 0)
    const rawTargets = Object.fromEntries(
        availableLevels.map((level) => [level, (LEVEL_HISTORY_WINDOW * BASE_LEVEL_WEIGHTS[level]) / totalWeight]),
    )
    const targets = Object.fromEntries(availableLevels.map((level) => [level, Math.floor(rawTargets[level])]))
    const remainder = LEVEL_HISTORY_WINDOW - Object.values(targets).reduce((sum, value) => sum + value, 0)

    availableLevels
        .slice()
        .sort((a, b) => {
            const aScore = rawTargets[a] - targets[a]
            const bScore = rawTargets[b] - targets[b]
            if (bScore !== aScore) return bScore - aScore
            if (BASE_LEVEL_WEIGHTS[b] !== BASE_LEVEL_WEIGHTS[a]) return BASE_LEVEL_WEIGHTS[b] - BASE_LEVEL_WEIGHTS[a]
            return a - b
        })
        .slice(0, remainder)
        .forEach((level) => {
            targets[level] += 1
        })

    return targets
}

export function currentReviewLevelBlock(state) {
    const history = (state.review_level_history ?? []).filter((level) => [1, 2, 3, 4, 5].includes(level))
    const remainder = history.length % LEVEL_HISTORY_WINDOW
    return remainder ? history.slice(-remainder) : []
}

export function chooseReviewMode(state, random = Math.random) {
    const balance = currentModeBalance(state)
    const history = (state.review_mode_history ?? []).filter((mode) => ['vi_to_en', 'en_to_vi'].includes(mode))
    const windowHistory = history.slice(-MODE_HISTORY_WINDOW)

    const candidates = ['vi_to_en', 'en_to_vi'].map((mode) => {
        const candidateHistory = [...windowHistory, mode].slice(-MODE_HISTORY_WINDOW)
        const total = candidateHistory.length
        const viCount = candidateHistory.filter((item) => item === 'vi_to_en').length
        const enCount = total - viCount
        const targetVi = (total * balance.vi_to_en_ratio) / 100
        const targetEn = (total * balance.en_to_vi_ratio) / 100
        const deviation = Math.abs(viCount - targetVi) + Math.abs(enCount - targetEn)
        return { mode, deviation }
    })

    const bestScore = Math.min(...candidates.map((item) => item.deviation))
    const bestModes = candidates.filter((item) => item.deviation === bestScore).map((item) => item.mode)

    if (bestModes.length === 1) return bestModes[0]
    return random() * 100 <= balance.vi_to_en_ratio ? 'vi_to_en' : 'en_to_vi'
}

export function pickPendingWord(state, random = Math.random) {
    const pendingIds = Object.entries(state.words)
        .filter(([, meta]) => meta.status === 'pending' && !meta.excluded)
        .map(([wid]) => wid)

    if (!pendingIds.length) return null
    return pendingIds[Math.floor(random() * pendingIds.length)]
}

export function chooseLevel(state, random = Math.random) {
    const { counts } = levelCounts(state)
    const availableLevels = [1, 2, 3, 4, 5].filter((level) => counts[level] > 0)
    if (!availableLevels.length) return null

    const blockHistory = currentReviewLevelBlock(state)
    const blockCounts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }
    blockHistory.forEach((level) => {
        blockCounts[level] += 1
    })

    const targets = dynamicLevelTargets(availableLevels)
    const weightedLevels = availableLevels.map((level) => {
        const shortage = Math.max(0, (targets[level] ?? 0) - blockCounts[level])
        const weight = LEVEL_WEIGHT_FLOOR + (shortage ** LEVEL_WEIGHT_EXPONENT)
        return [level, Math.max(1, Math.floor(weight * 100))]
    })

    return weightedChoice(weightedLevels, random)
}

export function wordSelectionWeight(state, wid) {
    const meta = state.words[wid]
    const lastSeenTurn = meta.last_seen_turn
    const turnsSinceSeen = lastSeenTurn == null ? state.turn + 1 : Math.max(1, state.turn - Number(lastSeenTurn))
    const timesSeen = Math.max(1, Number(meta.times_seen ?? 0))
    const fairnessBonus = Math.max(0, 6 - timesSeen)
    const relapseBonus = meta.relapse_until_turn != null && state.turn <= Number(meta.relapse_until_turn)
        ? RELAPSE_BOOST_WEIGHT
        : 0

    return Math.max(1, turnsSinceSeen * 3 + fairnessBonus + relapseBonus)
}

export function weightedPickWord(state, pool, random = Math.random) {
    const weightedPool = pool.map((wid) => [wid, wordSelectionWeight(state, wid)])
    return weightedChoice(weightedPool, random)
}

export function chooseWordForLevel(state, level, random = Math.random) {
    const candidates = Object.entries(state.words)
        .filter(([, meta]) => meta.status === 'active' && Number(meta.level) === level && !meta.excluded)
        .map(([wid]) => wid)

    if (!candidates.length) return null

    const recent = new Set((state.recent_history ?? []).slice(-RECENT_HISTORY_WINDOW))
    const filtered = candidates.filter((wid) => !recent.has(wid))
    const pool = filtered.length ? filtered : candidates
    return weightedPickWord(state, pool, random)
}

export function nextCard(state, vocabMap, random = Math.random) {
    ensureStateDefaults(state)
    const { counts, pending } = levelCounts(state)

    if (pending > 0 && counts[1] < LEVEL_ONE_TARGET) {
        const wid = pickPendingWord(state, random)
        if (!wid) return null
        return { kind: 'intro', mode: 'intro', wid, level: 1 }
    }

    const level = chooseLevel(state, random)
    if (level == null) return null

    const wid = chooseWordForLevel(state, level, random)
    if (!wid || !vocabMap[wid]) return null

    return { kind: 'review', mode: chooseReviewMode(state, random), wid, level }
}

export function commitAppearance(state, wid, mode, askedLevel = null) {
    ensureStateDefaults(state)
    state.turn += 1

    const meta = state.words[wid]
    meta.times_seen += 1
    meta.last_seen_turn = state.turn
    meta.last_mode = mode

    state.recent_history.push(wid)
    if (state.recent_history.length > 50) {
        state.recent_history = state.recent_history.slice(-50)
    }

    if (['vi_to_en', 'en_to_vi'].includes(mode)) {
        const level = [1, 2, 3, 4, 5].includes(askedLevel) ? askedLevel : meta.level
        if ([1, 2, 3, 4, 5].includes(level)) {
            state.review_level_history.push(level)
            if (state.review_level_history.length > 200) {
                state.review_level_history = state.review_level_history.slice(-200)
            }
        }

        state.review_mode_history.push(mode)
        if (state.review_mode_history.length > 100) {
            state.review_mode_history = state.review_mode_history.slice(-100)
        }
    }
}

export function formatExamples(entry) {
    return [entry.example_1, entry.example_2].filter(Boolean)
}

export function shortAnswer(entry) {
    return [entry.word, entry.meaning_vi].filter(Boolean).join(' = ')
}

export function applyResult(state, wid, card, result) {
    const meta = state.words[wid]
    const oldLevel = meta.level

    if (card.kind === 'intro' && meta.status === 'pending') {
        meta.status = 'active'
        meta.level = 1
    }

    meta.level = result.new_level
    if ([1, 2, 3, 4, 5].includes(oldLevel) && result.new_level < oldLevel) {
        meta.relapse_until_turn = state.turn + RELAPSE_BOOST_WINDOW
    } else {
        meta.relapse_until_turn = null
    }
}

export function wordProgressPayload(index, entry, state) {
    const meta = state.words[entry.wid]
    const isPending = meta.status === 'pending'

    return {
        index,
        wid: entry.wid,
        word: entry.word,
        meaning_vi: entry.meaning_vi,
        meaning_en: entry.meaning_en,
        pos: entry.pos,
        phonetic: entry.phonetic,
        notes: entry.notes,
        excluded: Boolean(meta.excluded),
        status: meta.status,
        status_label: isPending ? 'Chưa mở' : 'Đã mở',
        opened: !isPending,
        level: isPending ? null : meta.level,
        level_label: isPending ? 'Chưa mở' : `B${meta.level}`,
        times_seen: meta.times_seen,
        last_seen_turn: meta.last_seen_turn,
        last_mode: meta.last_mode,
        last_mode_label: meta.last_mode ? MODE_LABELS[meta.last_mode] : null,
    }
}

export function vocabProgressPayload(state, vocab, selectedVocab) {
    return {
        selected_vocab: selectedVocab,
        total_words: vocab.length,
        summary: progressPayload(state),
        items: vocab.map((entry, index) => wordProgressPayload(index + 1, entry, state)),
    }
}

export function sessionPayload(state, vocab, selectedVocab) {
    return {
        turn: state.turn,
        total_words: vocab.length,
        selected_vocab: selectedVocab,
        progress: progressPayload(state),
        mode_balance: currentModeBalance(state),
    }
}

export function cardPayload(card, state, vocabMap) {
    const entry = vocabMap[card.wid]
    const appearance = state.words[entry.wid].times_seen + 1
    const preview = card.kind === 'intro'

    const payload = {
        token: card.token,
        wid: card.wid,
        kind: card.kind,
        mode: card.mode,
        mode_label: MODE_LABELS[card.mode],
        level: card.level,
        appearance,
        upcoming_turn: state.turn + 1,
        progress: progressPayload(state, preview),
        word: entry.word,
        meaning_vi: entry.meaning_vi,
        meaning_en: entry.meaning_en,
        examples: formatExamples(entry),
        pos: entry.pos,
        phonetic: entry.phonetic,
        notes: entry.notes,
    }

    if (card.mode === 'intro') {
        payload.prompt_label = 'Nhập lại từ tiếng Anh'
        payload.input_placeholder = 'Nhập lại từ tiếng Anh'
    } else if (card.mode === 'vi_to_en') {
        payload.prompt_vi = entry.meaning_vi
        payload.prompt_label = 'Nhập từ tiếng Anh'
        payload.input_placeholder = 'Nhập từ tiếng Anh'
    } else {
        payload.choice_hint = 'Tự nhớ nghĩa tiếng Việt rồi chọn mức độ bạn nhớ.'
        payload.choices = [
            { value: 'up', label: 'Lên 1 bậc' },
            { value: 'keep', label: 'Giữ nguyên' },
            { value: 'down', label: 'Xuống 1 bậc' },
        ]
    }

    return payload
}

export function evaluateIntro(card, payload, vocabMap) {
    const entry = vocabMap[card.wid]
    const answer = payload.answer ?? ''
    const correct = matchEnglishAnswer(answer, entry.word)

    return {
        correct,
        typo: false,
        submitted_answer: answer,
        old_level: 1,
        new_level: 1,
        status: correct ? 'correct' : 'wrong',
        headline: correct ? `Đúng: ${entry.word}.` : `Sai: đáp án đúng là ${entry.word}.`,
        note: 'Đây là lượt làm quen đầu tiên nên từ vẫn ở B1.',
    }
}

export function evaluateViToEn(card, payload, vocabMap) {
    const entry = vocabMap[card.wid]
    const answer = payload.answer ?? ''
    const correct = matchEnglishAnswer(answer, entry.word)
    const oldLevel = card.level
    const newLevel = correct ? Math.min(5, oldLevel + 1) : Math.max(1, oldLevel - 1)

    return {
        correct,
        typo: false,
        submitted_answer: answer,
        old_level: oldLevel,
        new_level: newLevel,
        status: correct ? 'correct' : 'wrong',
        headline: correct ? `Đúng: ${entry.word}.` : `Sai: đáp án đúng là ${entry.word}.`,
        note: correct
            ? (newLevel === oldLevel ? `Từ vẫn ở B${newLevel}.` : `Từ đi từ B${oldLevel} lên B${newLevel}.`)
            : (newLevel === oldLevel
                ? `Đáp án đúng là \`${entry.word}\`; từ vẫn ở B${newLevel}.`
                : `Đáp án đúng là \`${entry.word}\`; từ đi từ B${oldLevel} xuống B${newLevel}.`),
    }
}

export function evaluateEnToVi(card, payload, vocabMap) {
    const entry = vocabMap[card.wid]
    const rawChoice = String(payload.choice ?? '').trim().toLowerCase()
    const mapping = { u: 'up', up: 'up', k: 'keep', keep: 'keep', d: 'down', down: 'down' }
    const choice = mapping[rawChoice]

    if (!choice) {
        throw new Error('Lựa chọn không hợp lệ. Hãy dùng up, keep hoặc down.')
    }

    const oldLevel = card.level

    if (choice === 'up') {
        const newLevel = Math.min(5, oldLevel + 1)
        return {
            correct: true,
            typo: false,
            submitted_answer: null,
            old_level: oldLevel,
            new_level: newLevel,
            status: 'correct',
            headline: `Lên bậc: ${shortAnswer(entry)}.`,
            note: `Bạn tự đánh giá nhớ chắc; từ đi từ B${oldLevel} lên B${newLevel}.`,
        }
    }

    if (choice === 'keep') {
        return {
            correct: false,
            typo: false,
            submitted_answer: null,
            old_level: oldLevel,
            new_level: oldLevel,
            status: 'neutral',
            headline: `Giữ nguyên: ${shortAnswer(entry)}.`,
            note: 'Bạn tự đánh giá nhớ lơ mơ; từ giữ nguyên bậc.',
        }
    }

    const newLevel = Math.max(1, oldLevel - 1)
    return {
        correct: false,
        typo: false,
        submitted_answer: null,
        old_level: oldLevel,
        new_level: newLevel,
        status: 'wrong',
        headline: `Xuống bậc: ${shortAnswer(entry)}.`,
        note: newLevel === oldLevel
            ? 'Bạn tự đánh giá chưa nhớ; từ vẫn ở B1.'
            : `Bạn tự đánh giá chưa nhớ; từ đi từ B${oldLevel} xuống B${newLevel}.`,
    }
}

export function evaluateAnswer(card, payload, vocabMap) {
    if (card.mode === 'intro') return evaluateIntro(card, payload, vocabMap)
    if (card.mode === 'vi_to_en') return evaluateViToEn(card, payload, vocabMap)
    return evaluateEnToVi(card, payload, vocabMap)
}

export function resultPayload(card, evaluation, vocabMap) {
    const entry = vocabMap[card.wid]
    return {
        status: evaluation.status,
        headline: evaluation.headline,
        note: evaluation.note,
        typo: false,
        typo_notice: null,
        correct_word: entry.word,
        meaning_vi: entry.meaning_vi,
        meaning_en: entry.meaning_en,
        examples: formatExamples(entry),
        notes: entry.notes,
        old_level: evaluation.old_level,
        new_level: evaluation.new_level,
        mode: card.mode,
        mode_label: MODE_LABELS[card.mode],
    }
}
