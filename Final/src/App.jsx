import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  getCard as getCardLocal,
  getModeBalance as getModeBalanceLocal,
  getStatus as getStatusLocal,
  getVocabProgress as getVocabProgressLocal,
  resetProgress as resetProgressLocal,
  selectVocabSet as selectVocabSetLocal,
  submitAnswer as submitAnswerLocal,
  updateModeBalance as updateModeBalanceLocal,
} from './lib/srsStore'
import './App.css'

const STATS_META = [
  ['B1', 'level-b1', 'Từ yếu nhất'],
  ['B2', 'level-b2', 'Đang hình thành'],
  ['B3', 'level-b3', 'Bắt đầu quen'],
  ['B4', 'level-b4', 'Khá chắc'],
  ['B5', 'level-b5', 'Đã rất chắc'],
  ['Chưa mở', 'level-pending', 'Chưa học'],
]

async function apiFetch(path, options = {}) {
  const method = String(options.method || 'GET').toUpperCase()
  let payload = {}

  if (options.body != null) {
    payload = typeof options.body === 'string'
      ? JSON.parse(options.body)
      : options.body
  }

  try {
    switch (`${method} ${path}`) {
      case 'GET /api/status':
        return await getStatusLocal()
      case 'GET /api/card':
        return await getCardLocal()
      case 'GET /api/vocab-sets':
        return await getStatusLocal().then((data) => data.vocab_sets)
      case 'GET /api/vocab-progress':
        return await getVocabProgressLocal()
      case 'GET /api/mode-balance':
        return await getModeBalanceLocal()
      case 'POST /api/mode-balance':
        return await updateModeBalanceLocal(payload)
      case 'POST /api/vocab-sets/select':
        return await selectVocabSetLocal(payload)
      case 'POST /api/reset':
        return await resetProgressLocal()
      case 'POST /api/answer':
        return await submitAnswerLocal(payload)
      default:
        throw new Error(`Route nội bộ chưa được hỗ trợ: ${method} ${path}`)
    }
  } catch (error) {
    throw new Error(error?.message || 'Không thể xử lý dữ liệu học trên frontend.')
  }
}

function StatCard({ label, value, className, note }) {
  return (
    <div className={`stat-card ${className}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-divider" />
      <div className="stat-value">{value}</div>
      <div className="stat-note">{note}</div>
    </div>
  )
}

function SupportPanel({ card, revealAll }) {
  const showFull = revealAll || card?.mode === 'intro'
  const examples = card?.examples || []

  if (!card) return null

  let shortcutText = 'Space / Enter / → / ↑ để qua câu tiếp theo sau khi hiện kết quả.'
  if (card.mode === 'intro' || card.mode === 'vi_to_en') {
    shortcutText = 'Nhấn Enter trong ô nhập để gửi đáp án. Sau khi có kết quả, dùng Space / Enter / → / ↑ để sang câu kế tiếp.'
  } else if (card.mode === 'en_to_vi') {
    shortcutText = '← hoặc ↓ để xuống bậc · Enter để giữ nguyên · → hoặc ↑ để lên bậc. Khi kết quả hiện ra, dùng Space / Enter / → / ↑ để qua câu tiếp theo.'
  }

  return (
    <aside className="support-panel">
      <section className="support-section">
        <h3>Thông tin nhanh</h3>
        <div className="detail-grid">
          {showFull && card.meaning_en ? (
            <div className="detail-item">
              <span className="detail-label">Nghĩa Anh</span>
              <div className="detail-value">{card.meaning_en}</div>
            </div>
          ) : null}

          {card.pos ? (
            <div className="detail-item">
              <span className="detail-label">Từ loại</span>
              <div className="detail-value">{card.pos}</div>
            </div>
          ) : null}

          {card.phonetic ? (
            <div className="detail-item">
              <span className="detail-label">Phiên âm</span>
              <div className="detail-value">{card.phonetic}</div>
            </div>
          ) : null}

          {card.notes ? (
            <div className="detail-item wide">
              <span className="detail-label">Ghi chú</span>
              <div className="detail-value">{card.notes}</div>
            </div>
          ) : null}

          {!showFull && !card.pos && !card.phonetic && !card.notes ? (
            <div className="detail-item wide">
              <span className="detail-label">Ẩn đáp án</span>
              <div className="detail-value">Từ đúng và nghĩa sẽ hiện đầy đủ sau khi bạn trả lời hoặc ở lượt làm quen từ mới.</div>
            </div>
          ) : null}
        </div>
      </section>

      <section className="support-section">
        <h3>Ví dụ &amp; phím tắt</h3>
        <div className="examples-list">
          {examples.length ? (
            examples.map((example, index) => (
              <div className="example-item" key={`${example}-${index}`}>
                <span className="detail-label">Ví dụ {index + 1}</span>
                <div>{example}</div>
              </div>
            ))
          ) : (
            <div className="example-item">Không có ví dụ bổ sung cho thẻ này.</div>
          )}
        </div>

        <div className="detail-item wide">
          <span className="detail-label">Phím tắt</span>
          <div className="detail-value">{shortcutText}</div>
        </div>
      </section>
    </aside>
  )
}

function ResultBox({ result, onNext }) {
  if (!result) return null

  const levelState = result.new_level === result.old_level
    ? `B${result.new_level}`
    : `B${result.old_level} → B${result.new_level}`

  const typoCallout = result.typo ? (
    <div className="typo-callout">
      <div className="typo-callout-head">⚠ Sai nhẹ nhưng chấp nhận</div>
      <div className="typo-callout-body">{result.typo_notice || 'Bạn viết chưa chuẩn chính tả, nhưng hệ thống vẫn chấp nhận vì lỗi nằm trong mức cho phép.'}</div>
    </div>
  ) : null

  return (
    <div className={`inline-result show ${result.status}`} id="inlineResultBox">
      <div className="result-top">
        <div className="result-title">
          <h3>{result.headline || 'Kết quả'}</h3>
          <p>{result.note || ''}</p>
        </div>
        <button className="btn btn-primary" onClick={onNext}>Space / Enter / → / ↑ · Câu tiếp theo</button>
      </div>

      {typoCallout}

      <div className="result-grid">
        <div className="result-item">
          <label>Từ đúng</label>
          <div>{result.correct_word}</div>
        </div>
        <div className="result-item">
          <label>Bậc</label>
          <div>{levelState}</div>
        </div>
        <div className="result-item">
          <label>Nghĩa Việt</label>
          <div>{result.meaning_vi || ''}</div>
        </div>
        <div className="result-item">
          <label>Chế độ</label>
          <div>{result.mode_label || ''}</div>
        </div>
      </div>
    </div>
  )
}

function ProgressDrawer({ open, data, filter, onFilterChange, drawerRef }) {
  if (!open) return <section ref={drawerRef} className="workspace drawer" id="vocabProgressDrawer" />

  if (!data) {
    return (
      <section ref={drawerRef} className="workspace drawer show" id="vocabProgressDrawer">
        <div className="drawer-head">
          <div>
            <h3>Đang tải bảng theo dõi từ vựng...</h3>
            <p>Hệ thống đang lấy dữ liệu tiến độ chi tiết của từng từ.</p>
          </div>
        </div>
      </section>
    )
  }

  const summary = data.summary || {}
  const allItems = data.items || []
  const filteredItems = allItems.filter((item) => {
    if (filter === 'all') return true
    if (filter === 'pending') return !item.opened
    if (filter === 'b1') return item.opened && item.level === 1
    if (filter === 'b2') return item.opened && item.level === 2
    if (filter === 'b3') return item.opened && item.level === 3
    if (filter === 'b4') return item.opened && item.level === 4
    if (filter === 'b5') return item.opened && item.level === 5
    return true
  })

  return (
    <section ref={drawerRef} className="workspace drawer show" id="vocabProgressDrawer">
      <div className="drawer-head">
        <div>
          <h3>Theo dõi từ vựng · {data.selected_vocab || ''}</h3>
          <p>Bảng đầy đủ để xem từng từ đã mở hay chưa, đang ở bậc nào và đã xuất hiện bao nhiêu lần. Đang hiển thị {filteredItems.length}/{allItems.length} từ.</p>
        </div>

        <div className="drawer-summary">
          {[
            ['all', `Tất cả ${allItems.length}`],
            ['b1', `B1 ${summary.b1 ?? 0}`],
            ['b2', `B2 ${summary.b2 ?? 0}`],
            ['b3', `B3 ${summary.b3 ?? 0}`],
            ['b4', `B4 ${summary.b4 ?? 0}`],
            ['b5', `B5 ${summary.b5 ?? 0}`],
            ['pending', `Chưa mở ${summary.pending ?? 0}`],
          ].map(([value, label]) => (
            <button
              type="button"
              key={value}
              className={`mini-chip ${filter === value ? 'active' : ''}`}
              onClick={() => onFilterChange(value)}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <table className="vocab-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Từ</th>
              <th>Nghĩa Việt</th>
              <th>Trạng thái</th>
              <th>Bậc</th>
              <th>Số lần hỏi</th>
              <th>Lượt gần nhất</th>
              <th>Chế độ gần nhất</th>
              <th>Ghi chú</th>
            </tr>
          </thead>
          <tbody>
            {filteredItems.length ? filteredItems.map((item) => {
              const levelClass = item.opened ? `level-${item.level}` : 'level-none'
              const statusClass = item.opened ? 'status-open' : 'status-pending'
              return (
                <tr key={item.wid}>
                  <td>{item.index}</td>
                  <td>
                    <div className="table-word">{item.word}</div>
                    <div className="table-sub">{item.pos || ''}</div>
                  </td>
                  <td>{item.meaning_vi || ''}</td>
                  <td><span className={`status-pill ${statusClass}`}>{item.status_label}</span></td>
                  <td><span className={`level-pill ${levelClass}`}>{item.level_label}</span></td>
                  <td>{item.times_seen ?? 0}</td>
                  <td>{item.last_seen_turn ?? '—'}</td>
                  <td>{item.last_mode_label || '—'}</td>
                  <td>{item.notes || ''}</td>
                </tr>
              )
            }) : (
              <tr>
                <td colSpan="9">Không có từ nào khớp bộ lọc hiện tại.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function EmptyState({ message }) {
  return (
    <div className="empty-state">
      <div className="empty-card">
        <h2>Phiên học hiện chưa có thẻ</h2>
        <p>{message}</p>
        <div className="footnote">Tải lại dữ liệu, đổi bộ từ vựng hoặc reset nếu bạn muốn bắt đầu lại.</div>
      </div>
    </div>
  )
}

function App() {
  const drawerRef = useRef(null)
  const [session, setSession] = useState(null)
  const [currentCard, setCurrentCard] = useState(null)
  const [result, setResult] = useState(null)
  const [answerValue, setAnswerValue] = useState('')
  const [vocabSets, setVocabSets] = useState([])
  const [selectedVocab, setSelectedVocab] = useState('')
  const [modeBalance, setModeBalance] = useState({ vi_to_en_ratio: 70, en_to_vi_ratio: 30 })
  const [modeRatioDraft, setModeRatioDraft] = useState(70)
  const [vocabProgressOpen, setVocabProgressOpen] = useState(false)
  const [vocabProgressData, setVocabProgressData] = useState(null)
  const [vocabProgressFilter, setVocabProgressFilter] = useState('all')
  const [overviewCollapsed, setOverviewCollapsed] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [doneMessage, setDoneMessage] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  const applySession = useCallback((nextSession) => {
    setSession(nextSession || null)
    if (nextSession?.selected_vocab) setSelectedVocab(nextSession.selected_vocab)
    if (nextSession?.mode_balance) {
      setModeBalance(nextSession.mode_balance)
      setModeRatioDraft(nextSession.mode_balance.vi_to_en_ratio)
    }
  }, [])

  const loadVocabProgress = useCallback(async (force = false) => {
    if (!force && vocabProgressData) return
    const data = await apiFetch('/api/vocab-progress')
    setVocabProgressData(data)
  }, [vocabProgressData])

  const loadCard = useCallback(async () => {
    setIsSubmitting(false)
    setResult(null)
    setErrorMessage('')
    const data = await apiFetch('/api/card')
    applySession(data.session)

    if (vocabProgressOpen) {
      loadVocabProgress(true).catch(() => { })
    }

    if (data.done) {
      setCurrentCard(null)
      setDoneMessage(data.message || 'Hiện tại chưa có thẻ nào để học.')
      setAnswerValue('')
      return
    }

    setDoneMessage('')
    setCurrentCard(data.card)
    setAnswerValue('')
  }, [applySession, loadVocabProgress, vocabProgressOpen])

  const bootstrap = useCallback(async () => {
    try {
      const status = await apiFetch('/api/status')
      applySession(status.session)
      setSelectedVocab(status.vocab_sets?.selected || '')
      setVocabSets(status.vocab_sets?.sets || [])
      await loadCard()
    } catch (error) {
      setErrorMessage(error.message || 'Không tải được giao diện học.')
    }
  }, [applySession, loadCard])

  useEffect(() => {
    bootstrap()
  }, [bootstrap])

  useEffect(() => {
    if (!vocabProgressOpen) return

    const frame = window.requestAnimationFrame(() => {
      drawerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })

    return () => window.cancelAnimationFrame(frame)
  }, [vocabProgressOpen, vocabProgressData])

  useEffect(() => {
    const onKeyDown = (event) => {
      const hasResult = Boolean(result)

      if (hasResult && ['Space', 'Enter', 'ArrowRight', 'ArrowUp'].includes(event.code === 'Space' ? 'Space' : event.key)) {
        event.preventDefault()
        loadCard().catch((error) => setErrorMessage(error.message || 'Không tải được câu tiếp theo.'))
        return
      }

      if (!currentCard || currentCard.mode !== 'en_to_vi' || isSubmitting || hasResult) return

      if (['ArrowLeft', 'ArrowDown'].includes(event.key)) {
        event.preventDefault()
        submitChoice('down')
      } else if (event.key === 'Enter') {
        event.preventDefault()
        submitChoice('keep')
      } else if (['ArrowRight', 'ArrowUp'].includes(event.key)) {
        event.preventDefault()
        submitChoice('up')
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [currentCard, isSubmitting, loadCard, result])

  const stats = useMemo(() => {
    const progress = session?.progress
    if (!progress) return []
    return STATS_META.map(([label, className, note]) => ({
      label,
      className,
      note,
      value: label === 'Chưa mở'
        ? progress.pending ?? 0
        : progress[label.toLowerCase()] ?? 0,
    }))
  }, [session])

  const fillPercent = useMemo(() => {
    const total = session?.total_words || 0
    const pending = session?.progress?.pending || 0
    if (!total) return 0
    return Math.max(0, Math.min(100, Math.round(((total - pending) / total) * 100)))
  }, [session])

  const answerInputClass = useMemo(() => {
    if (!result) return ''
    if (result.status === 'correct') return 'answered-correct'
    if (result.status === 'wrong') return 'answered-wrong'
    return ''
  }, [result])

  async function submitAnswer(payload) {
    if (!currentCard || isSubmitting) return
    setIsSubmitting(true)

    try {
      const data = await apiFetch('/api/answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      applySession(data.session)
      setResult(data.result)
      if (vocabProgressOpen) {
        loadVocabProgress(true).catch(() => { })
      }
    } catch (error) {
      setErrorMessage(error.message || 'Không gửi được đáp án.')
      setIsSubmitting(false)
      await loadCard()
    } finally {
      setIsSubmitting(false)
    }
  }

  function submitTextAnswer() {
    submitAnswer({ token: currentCard?.token, answer: answerValue })
  }

  function submitChoice(choice) {
    submitAnswer({ token: currentCard?.token, choice })
  }

  async function switchVocabSet(filename) {
    if (!filename || filename === selectedVocab) return
    setErrorMessage('')
    setResult(null)
    setCurrentCard(null)

    try {
      const data = await apiFetch('/api/vocab-sets/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename }),
      })
      applySession(data.session)
      setSelectedVocab(data.session.selected_vocab)
      setVocabSets(data.vocab_sets?.sets || vocabSets)
      setVocabProgressData(null)
      if (vocabProgressOpen) {
        await loadVocabProgress(true)
      }
      await loadCard()
    } catch (error) {
      setErrorMessage(error.message || 'Không chuyển được bộ từ vựng.')
    }
  }

  async function resetSession() {
    const firstOk = window.confirm('Bạn có chắc muốn reset toàn bộ tiến độ học không?')
    if (!firstOk) return
    const secondOk = window.confirm('Xác nhận lần nữa: toàn bộ tiến độ của bộ từ hiện tại sẽ bị xóa và không thể hoàn tác.')
    if (!secondOk) return

    try {
      const data = await apiFetch('/api/reset', { method: 'POST' })
      applySession(data.session)
      setVocabProgressData(null)
      if (vocabProgressOpen) {
        await loadVocabProgress(true)
      }
      await loadCard()
    } catch (error) {
      setErrorMessage(error.message || 'Không reset được tiến độ.')
    }
  }

  async function commitModeBalance() {
    try {
      const data = await apiFetch('/api/mode-balance', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ vi_to_en_ratio: modeRatioDraft }),
      })
      setModeBalance(data.mode_balance)
      setModeRatioDraft(data.mode_balance.vi_to_en_ratio)
      applySession(data.session)
    } catch (error) {
      setErrorMessage(error.message || 'Không cập nhật được tỷ lệ học.')
      setModeRatioDraft(modeBalance.vi_to_en_ratio)
    }
  }

  async function toggleDrawer() {
    const nextOpen = !vocabProgressOpen
    setVocabProgressOpen(nextOpen)
    if (nextOpen) {
      setVocabProgressFilter('all')
      setVocabProgressData(null)
      try {
        await loadVocabProgress(true)
      } catch (error) {
        setErrorMessage(error.message || 'Không tải được bảng theo dõi từ vựng.')
      }
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-shell">
          <div className="brand-mark" aria-hidden="true">
            <span></span>
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div className="brand">
            <h1>SRS Vocabulary</h1>
            <p>Không gian học từ vựng lặp lại ngắt quãng, tối ưu cho ôn tập hằng ngày và theo dõi tiến độ rõ ràng.</p>
          </div>
        </div>

        <div className="toolbar">
          <label className="select-wrap">
            <span>Bộ từ vựng</span>
            <select value={selectedVocab} onChange={(event) => switchVocabSet(event.target.value)}>
              {vocabSets.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </label>
          <div className="toolbar-actions">
            <button className="btn btn-danger" id="resetBtn" onClick={resetSession}>Reset tiến độ</button>
          </div>
        </div>
      </header>

      {errorMessage ? <div className="error-banner">{errorMessage}</div> : null}

      <section className={`overview ${overviewCollapsed ? 'collapsed' : ''}`}>
        <div className="overview-summary">
          <div className="stats-grid" id="statsGrid">
            {stats.map((item) => (
              <StatCard key={item.label} {...item} />
            ))}
          </div>
          <div className="overview-summary-actions">
            <button className="btn btn-ghost" id="toggleProgressBtn" onClick={toggleDrawer}>Theo dõi từ vựng</button>
            <button className="btn btn-ghost overview-toggle-btn" id="toggleOverviewSectionBtn" type="button" aria-expanded={!overviewCollapsed} onClick={() => setOverviewCollapsed((value) => !value)}>
              <span className="overview-toggle-icon" aria-hidden="true">▾</span>
              <span>{overviewCollapsed ? 'Hiện chi tiết' : 'Thu gọn'}</span>
            </button>
          </div>
        </div>

        <div className="overview-collapsible">
          <div className="overview-grid">
            <div className="overview-left">
              <div className="progress-strip">
                <div className="progress-head">
                  <strong id="progressLine">{session?.progress?.line || 'Đang tải tiến độ...'}</strong>
                  <div className="progress-head-right">
                    <span id="sessionMeta">{session ? `Tổng lượt đã học ${session.turn} · Tổng số từ ${session.total_words}` : ''}</span>
                  </div>
                </div>

                <div className="track">
                  <div className="fill" id="progressFill" style={{ width: `${fillPercent}%` }} />
                </div>

                <div className="progress-foot" id="progressFoot">
                  {session
                    ? `Đã mở ${(session.total_words || 0) - (session.progress?.pending || 0)}/${session.total_words} từ · B5 ${session.progress?.b5 || 0}/${session.total_words} · Trọng tâm hiện tại B1+B2 = ${(session.progress?.b1 || 0) + (session.progress?.b2 || 0)}`
                    : 'Đang đồng bộ dữ liệu phiên học...'}
                </div>
              </div>

              <div className="mode-balance" id="modeBalanceBox">
                <div className="mode-balance-panel">
                  <div className="mode-balance-head">
                    <span className="mode-balance-title">Chọn kiểu luyện tập ưu tiên</span>
                    <span className="mode-balance-value">{modeRatioDraft}% / {100 - modeRatioDraft}%</span>
                  </div>
                  <div className="mode-balance-legend">
                    <span className="mode-balance-side practice">Điền chữ</span>
                    <span className="mode-balance-side flashcards">Flashcard</span>
                  </div>
                  <div className="mode-balance-track">
                    <input
                      className="mode-slider"
                      id="modeBalanceSlider"
                      type="range"
                      min="0"
                      max="100"
                      step="10"
                      value={modeRatioDraft}
                      style={{ '--mode-split': `${modeRatioDraft}%` }}
                      onChange={(event) => setModeRatioDraft(Number(event.target.value || 0))}
                      onMouseUp={commitModeBalance}
                      onTouchEnd={commitModeBalance}
                    />
                  </div>
                </div>
              </div>
            </div>

            <aside className="overview-help">
              <div className="overview-help-title">Cách hoạt động</div>
              <div className="overview-help-text">Khu này giúp bạn hiểu nhanh cách học và cách hệ thống sắp xếp câu hỏi.</div>
              <div className="overview-help-list">
                <div className="overview-help-item">
                  <strong>B1 → B5</strong>
                  <span>B1 là mới hoặc rất yếu, B5 là đã nhớ vững.</span>
                </div>
                <div className="overview-help-item">
                  <strong>Lên / xuống bậc</strong>
                  <span>Trả lời tốt thì lên bậc, sai hoặc nhớ kém thì bị giữ hoặc hạ.</span>
                </div>
                <div className="overview-help-item">
                  <strong>Điền chữ / Flashcard</strong>
                  <span>Điền chữ để kéo đáp án ra. Flashcard để nhìn từ rồi tự đánh giá mức nhớ.</span>
                </div>
                <div className="overview-help-item">
                  <strong>Tỷ lệ mode</strong>
                  <span>Kéo thanh về bên nào thì mode bên đó sẽ xuất hiện nhiều hơn trong các lượt ôn kế tiếp.</span>
                </div>
              </div>
            </aside>
          </div>
        </div>
      </section>

      <ProgressDrawer
        open={vocabProgressOpen}
        data={vocabProgressData}
        filter={vocabProgressFilter}
        onFilterChange={setVocabProgressFilter}
        drawerRef={drawerRef}
      />

      <section className="workspace">
        <div id="studyArea">
          {currentCard ? (
            <div className="study-view">
              <section className="focus-panel">
                <div className="focus-top">
                  <div className="meta-row">
                    <span className="badge accent">{currentCard.mode_label}</span>
                    <span className={`badge level-b${currentCard.level}`}>Bậc {currentCard.level}</span>
                    <span className="badge warn">Lần {currentCard.appearance}</span>
                    <span className="badge success">Lượt {currentCard.upcoming_turn}</span>
                  </div>
                </div>

                <div className="focus-body">
                  <div className="hero-card">
                    <div className="hero-kicker">
                      {currentCard.mode === 'intro' ? 'Làm quen từ mới' : currentCard.mode === 'vi_to_en' ? 'Gợi ý tiếng Việt' : 'Kiểm tra Anh → Việt'}
                    </div>
                    <h2 className={currentCard.mode === 'en_to_vi' ? 'single-line' : ''}>
                      {currentCard.mode === 'intro'
                        ? 'Làm quen nhanh rồi nhập lại từ'
                        : currentCard.mode === 'vi_to_en'
                          ? 'Nhớ từ tiếng Anh rồi nhập đáp án'
                          : 'Tự nhớ nghĩa rồi tự đánh giá mức độ nhớ'}
                    </h2>
                    <p>
                      {currentCard.mode === 'intro'
                        ? 'Đây là lượt đầu tiên. Bạn được nhìn từ và nghĩa trước rồi nhập lại chính tả để bắt đầu tạo dấu nhớ.'
                        : currentCard.mode === 'vi_to_en'
                          ? 'Tự nhớ đáp án rồi trả lời thật dứt khoát để hệ thống cập nhật bậc chính xác hơn.'
                          : 'Tự nhớ nghĩa tiếng Việt trước, sau đó tự đánh giá mức độ nhớ để cập nhật bậc phù hợp.'}
                    </p>
                    <div className="prompt-panel">
                      {currentCard.mode === 'intro'
                        ? `${currentCard.word} = ${currentCard.meaning_vi || ''}`
                        : currentCard.mode === 'vi_to_en'
                          ? currentCard.prompt_vi
                          : currentCard.word}
                    </div>
                  </div>

                  {currentCard.mode === 'en_to_vi' ? (
                    <div className="answer-area">
                      <div className="choice-grid">
                        <button className="btn btn-down choice-card" data-choice="down" disabled={isSubmitting || Boolean(result)} onClick={() => submitChoice('down')}>
                          <strong>Xuống 1 bậc</strong>
                          <span>← hoặc ↓ · Chưa nhớ hoặc nhớ sai.</span>
                        </button>
                        <button className="btn btn-keep choice-card" data-choice="keep" disabled={isSubmitting || Boolean(result)} onClick={() => submitChoice('keep')}>
                          <strong>Giữ nguyên</strong>
                          <span>Enter · Nhớ mơ hồ, chưa đủ chắc.</span>
                        </button>
                        <button className="btn btn-up choice-card" data-choice="up" disabled={isSubmitting || Boolean(result)} onClick={() => submitChoice('up')}>
                          <strong>Lên 1 bậc</strong>
                          <span>→ hoặc ↑ · Nhớ chắc và phản xạ tốt.</span>
                        </button>
                      </div>
                      <div className="assist-text">
                        <span>Hướng hỏi này dùng để tự kiểm tra nghĩa và tự đánh giá độ chắc của trí nhớ.</span>
                        <span>Dùng phím mũi tên hoặc Enter để thao tác nhanh.</span>
                      </div>
                    </div>
                  ) : (
                    <div className="answer-area">
                      <div className="answer-row">
                        <input
                          id="answerInput"
                          className={answerInputClass}
                          type="text"
                          placeholder={currentCard.mode === 'intro' ? 'Nhập lại từ tiếng Anh' : 'Nhập từ tiếng Anh'}
                          autoComplete="off"
                          value={answerValue}
                          disabled={isSubmitting || Boolean(result)}
                          onChange={(event) => setAnswerValue(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' && !result) {
                              submitTextAnswer()
                            }
                          }}
                        />
                        <button className="btn btn-primary" id="submitAnswerBtn" disabled={isSubmitting || Boolean(result)} onClick={submitTextAnswer}>
                          {currentCard.mode === 'intro' ? 'Xác nhận' : 'Kiểm tra'}
                        </button>
                      </div>
                      <div className="assist-text">
                        <span>
                          {currentCard.mode === 'intro'
                            ? 'Hãy nhìn từ, nghĩa và ví dụ ở khung bên phải rồi gõ lại thật chuẩn.'
                            : 'Ưu tiên nhớ chủ động: nhìn nghĩa Việt và tự kéo từ tiếng Anh ra khỏi trí nhớ.'}
                        </span>
                        <span>Phím Enter để gửi đáp án.</span>
                      </div>
                    </div>
                  )}
                </div>

                <ResultBox result={result} onNext={() => loadCard().catch((error) => setErrorMessage(error.message || 'Không tải được câu tiếp theo.'))} />
              </section>

              <SupportPanel card={currentCard} revealAll={Boolean(result)} />
            </div>
          ) : (
            <EmptyState message={errorMessage || doneMessage || 'Đang tải giao diện học...'} />
          )}
        </div>
      </section>
    </div>
  )
}

export default App
