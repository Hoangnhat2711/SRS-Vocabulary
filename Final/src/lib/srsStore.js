import { createEntriesFromPayload, buildInitialState, cardPayload, cloneDeep, currentModeBalance, ensureStateDefaults, evaluateAnswer, listCombinedVocabNames, nextCard, progressPayload, resultPayload, sessionPayload, setModeBalance, vocabProgressPayload, vocabSignature, applyResult, commitAppearance } from './srsCore'

const STORAGE_KEY = 'srs-vocabulary-react-state-v2'
const vocabModules = import.meta.glob('../../vocab_sets/*.json', { eager: true })

function modulePayload(moduleValue) {
    return moduleValue?.default ?? moduleValue
}

function moduleName(path) {
    return path.split('/').pop()
}

const VOCAB_SOURCES = Object.entries(vocabModules).map(([path, value]) => ({
    path,
    name: moduleName(path),
    payload: modulePayload(value),
}))

function defaultRootState() {
    return {
        selected_vocab: null,
        vocab_states: {},
        pending_cards: {},
    }
}

function ensureRootStateShape(rootState) {
    const next = rootState && typeof rootState === 'object' ? rootState : defaultRootState()
    next.selected_vocab ??= null
    next.vocab_states ??= {}
    next.pending_cards ??= {}
    if (typeof next.vocab_states !== 'object' || Array.isArray(next.vocab_states)) next.vocab_states = {}
    if (typeof next.pending_cards !== 'object' || Array.isArray(next.pending_cards)) next.pending_cards = {}
    return next
}

function readRootState() {
    if (typeof window === 'undefined') {
        return defaultRootState()
    }

    try {
        const raw = window.localStorage.getItem(STORAGE_KEY)
        if (!raw) return defaultRootState()
        return ensureRootStateShape(JSON.parse(raw))
    } catch {
        return defaultRootState()
    }
}

function writeRootState(rootState) {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ensureRootStateShape(rootState)))
}

function listSourceNames() {
    const names = []

    VOCAB_SOURCES.forEach((source) => {
        const combinedNames = listCombinedVocabNames(source.payload)
        if (combinedNames.length) {
            names.push(...combinedNames)
        } else {
            names.push(source.name)
        }
    })

    return names
}

function resolveSelection(requestedName = null) {
    const available = listSourceNames()
    const preferredName = requestedName && available.includes(requestedName)
        ? requestedName
        : available[0] ?? null

    if (!preferredName) {
        throw new Error('Không tìm thấy file JSON nào trong thư mục vocab_sets.')
    }

    for (const source of VOCAB_SOURCES) {
        const combinedNames = listCombinedVocabNames(source.payload)
        if (combinedNames.includes(preferredName)) {
            const vocab = createEntriesFromPayload(source.payload, preferredName)
            return {
                sourceName: source.name,
                selectedName: preferredName,
                payload: source.payload,
                vocab,
                vocabMap: Object.fromEntries(vocab.map((entry) => [entry.wid, entry])),
                vocabSets: available,
            }
        }

        if (source.name === preferredName) {
            const vocab = createEntriesFromPayload(source.payload, source.name)
            return {
                sourceName: source.name,
                selectedName: source.name,
                payload: source.payload,
                vocab,
                vocabMap: Object.fromEntries(vocab.map((entry) => [entry.wid, entry])),
                vocabSets: available,
            }
        }
    }

    throw new Error(`Không tìm thấy bộ từ vựng: ${preferredName}`)
}

function loadContext(requestedSelection = null) {
    const root = readRootState()
    const resolved = resolveSelection(requestedSelection ?? root.selected_vocab)
    const signature = vocabSignature(resolved.vocab)
    const stateKey = resolved.selectedName

    root.selected_vocab = stateKey

    let state = root.vocab_states[stateKey]
    if (!state || typeof state !== 'object' || state.vocab_signature !== signature) {
        state = buildInitialState(signature, resolved.vocab)
    } else {
        state = ensureStateDefaults(cloneDeep(state))
    }

    root.vocab_states[stateKey] = state
    writeRootState(root)

    return {
        root,
        state,
        stateKey,
        ...resolved,
    }
}

function previewContextForSelection(rootState, requestedSelection) {
    const resolved = resolveSelection(requestedSelection)
    const signature = vocabSignature(resolved.vocab)
    const stateKey = resolved.selectedName

    let state = rootState.vocab_states[stateKey]
    if (!state || typeof state !== 'object' || state.vocab_signature !== signature) {
        state = buildInitialState(signature, resolved.vocab)
    } else {
        state = ensureStateDefaults(cloneDeep(state))
    }

    return {
        state,
        stateKey,
        ...resolved,
    }
}

function persistContext(context, nextPendingCard = undefined) {
    const root = ensureRootStateShape(context.root)
    root.selected_vocab = context.stateKey
    root.vocab_states[context.stateKey] = context.state

    if (nextPendingCard !== undefined) {
        if (nextPendingCard) {
            root.pending_cards[context.stateKey] = nextPendingCard
        } else {
            delete root.pending_cards[context.stateKey]
        }
    }

    writeRootState(root)
}

function randomToken() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID()
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function ensurePendingCard(context) {
    const current = context.root.pending_cards?.[context.stateKey]
    if (current && context.vocabMap[current.wid] && !context.state.words[current.wid]?.excluded) {
        return current
    }

    const next = nextCard(context.state, context.vocabMap)
    if (!next) {
        persistContext(context, null)
        return null
    }

    const pendingCard = {
        token: randomToken(),
        ...next,
    }

    persistContext(context, pendingCard)
    context.root.pending_cards[context.stateKey] = pendingCard
    return pendingCard
}

function vocabSetsPayload(context) {
    return {
        selected: context.stateKey,
        sets: context.vocabSets,
    }
}

function catalogItemPayload(snapshot, selectedName) {
    const summary = progressPayload(snapshot.state)
    const metas = Object.values(snapshot.state.words)
    const startedWords = metas.filter((meta) => meta.status !== 'pending' && !meta.excluded).length
    const excludedWords = metas.filter((meta) => meta.excluded).length
    const masteredWords = metas.filter((meta) => meta.level === 5 && !meta.excluded).length
    const activeWords = Math.max(0, snapshot.vocab.length - excludedWords)
    const completionPercent = activeWords > 0
        ? Math.round((masteredWords / activeWords) * 100)
        : 100

    return {
        name: snapshot.stateKey,
        source_name: snapshot.sourceName,
        total_words: snapshot.vocab.length,
        started_words: startedWords,
        excluded_words: excludedWords,
        mastered_words: masteredWords,
        active_words: activeWords,
        completion_percent: completionPercent,
        summary,
        is_current: snapshot.stateKey === selectedName,
    }
}

export async function getStatus() {
    const context = loadContext()
    return {
        session: sessionPayload(context.state, context.vocab, context.stateKey),
        vocab_sets: vocabSetsPayload(context),
    }
}

export async function getCard() {
    const context = loadContext()
    const card = ensurePendingCard(context)

    if (!card) {
        return {
            done: true,
            message: 'Không còn thẻ để học.',
            session: sessionPayload(context.state, context.vocab, context.stateKey),
        }
    }

    return {
        done: false,
        card: cardPayload(card, context.state, context.vocabMap),
        session: sessionPayload(context.state, context.vocab, context.stateKey),
    }
}

export async function getVocabSets() {
    const context = loadContext()
    return vocabSetsPayload(context)
}

export async function getVocabCatalog() {
    const root = ensureRootStateShape(readRootState())
    const names = listSourceNames()
    const selectedName = names.includes(root.selected_vocab) ? root.selected_vocab : (names[0] ?? null)

    return {
        selected: selectedName,
        items: names.map((name) => catalogItemPayload(previewContextForSelection(root, name), selectedName)),
    }
}

export async function getVocabProgress() {
    const context = loadContext()
    return vocabProgressPayload(context.state, context.vocab, context.stateKey)
}

export async function toggleWordExcluded(payload) {
    const context = loadContext()
    const wid = String(payload?.wid ?? '').trim()

    if (!wid || !context.state.words[wid]) {
        throw new Error('Không tìm thấy từ cần cập nhật.')
    }

    const excluded = Boolean(payload?.excluded)
    context.state.words[wid].excluded = excluded

    const currentPendingCard = context.root.pending_cards?.[context.stateKey]
    const shouldClearPendingCard = excluded && currentPendingCard?.wid === wid

    persistContext(context, shouldClearPendingCard ? null : undefined)

    return {
        message: excluded ? 'Đã loại bỏ từ khỏi chương trình học.' : 'Đã đưa từ quay lại chương trình học.',
        wid,
        excluded,
        session: sessionPayload(context.state, context.vocab, context.stateKey),
        vocab_progress: vocabProgressPayload(context.state, context.vocab, context.stateKey),
        current_card_cleared: shouldClearPendingCard,
    }
}

export async function getModeBalance() {
    const context = loadContext()
    return currentModeBalance(context.state)
}

export async function updateModeBalance(payload) {
    const context = loadContext()
    const modeBalance = setModeBalance(context.state, payload.vi_to_en_ratio)
    persistContext(context)

    return {
        message: 'Đã cập nhật tỷ lệ giữa điền chữ và flashcard.',
        mode_balance: modeBalance,
        session: sessionPayload(context.state, context.vocab, context.stateKey),
    }
}

export async function selectVocabSet(payload) {
    const context = loadContext(payload.filename)
    persistContext(context, null)

    return {
        message: `Đã chuyển sang bộ \`${context.sourceName}\`.`,
        session: sessionPayload(context.state, context.vocab, context.stateKey),
        vocab_sets: vocabSetsPayload(context),
    }
}

export async function resetProgress() {
    const context = loadContext()
    context.state = buildInitialState(vocabSignature(context.vocab), context.vocab)
    persistContext(context, null)

    return {
        message: 'Đã reset tiến độ học.',
        session: sessionPayload(context.state, context.vocab, context.stateKey),
    }
}

export async function submitAnswer(payload) {
    const context = loadContext()
    const pendingCard = context.root.pending_cards?.[context.stateKey]

    if (!pendingCard) {
        throw new Error('Hiện không có thẻ nào đang chờ trả lời.')
    }

    if (payload.token !== pendingCard.token) {
        throw new Error('Thẻ hiện tại đã thay đổi. Hãy tải lại câu hỏi mới.')
    }

    const evaluation = evaluateAnswer(pendingCard, payload, context.vocabMap)
    applyResult(context.state, pendingCard.wid, pendingCard, evaluation)
    commitAppearance(context.state, pendingCard.wid, pendingCard.mode, pendingCard.level)
    persistContext(context, null)

    return {
        result: resultPayload(pendingCard, evaluation, context.vocabMap),
        session: sessionPayload(context.state, context.vocab, context.stateKey),
    }
}

export async function getHealth() {
    const context = loadContext()
    return {
        ok: true,
        words: context.vocab.length,
        progress: progressPayload(context.state),
    }
}

export async function clearAllProgress() {
    if (typeof window !== 'undefined') {
        window.localStorage.removeItem(STORAGE_KEY)
    }
    return getStatus()
}
