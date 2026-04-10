#!/usr/bin/env python3
from __future__ import annotations

# Compatibility patches for this local Python 3.10.0a1 environment.
from dataclasses import dataclass as _orig_dataclass
import dataclasses
import types
import typing


def _compat_dataclass(*args, **kwargs):
    kwargs.pop("slots", None)
    kwargs.pop("kw_only", None)
    return _orig_dataclass(*args, **kwargs)


dataclasses.dataclass = _compat_dataclass
if not hasattr(types, "UnionType") and hasattr(types, "Union"):
    types.UnionType = types.Union

try:
    import typing_extensions as _typing_extensions

    for _name in ["ParamSpec", "TypeAlias", "TypeGuard", "Self", "Required", "NotRequired", "LiteralString"]:
        if not hasattr(typing, _name) and hasattr(_typing_extensions, _name):
            setattr(typing, _name, getattr(_typing_extensions, _name))
except Exception:
    pass

from pathlib import Path
from threading import Lock
from typing import Dict, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from terminal_srs import (
    DEFAULT_VOCAB_FILE,
    apply_result,
    commit_appearance,
    current_mode_balance,
    ensure_storage_dirs,
    format_examples,
    level_counts,
    list_vocab_names,
    load_selected_vocab_name,
    load_state,
    load_vocab,
    match_english_answer,
    next_card,
    progress_line,
    reset_state,
    resolve_vocab_path,
    save_selected_vocab_name,
    save_state,
    set_mode_balance,
    short_answer,
    state_path_for_vocab,
)

BASE_DIR = Path(__file__).resolve().parent
VOCAB_DIR, LOG_DIR = ensure_storage_dirs(BASE_DIR)
HTML_PATH = BASE_DIR / "srs_study_v2.html"

app = FastAPI(title="SRS Vocabulary API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE_LOCK = Lock()
ACTIVE_VOCAB_PATH = resolve_vocab_path(vocab_dir=VOCAB_DIR, log_dir=LOG_DIR)
STATE_PATH = state_path_for_vocab(ACTIVE_VOCAB_PATH, LOG_DIR)
VOCAB = load_vocab(ACTIVE_VOCAB_PATH)
VOCAB_MAP = {entry.wid: entry for entry in VOCAB}
STATE = load_state(STATE_PATH, VOCAB)
PENDING_CARD: Optional[Dict] = None


class AnswerPayload(BaseModel):
    token: str
    answer: Optional[str] = None
    choice: Optional[str] = None



class SelectVocabPayload(BaseModel):
    filename: str


class ModeBalancePayload(BaseModel):
    vi_to_en_ratio: int


MODE_LABELS = {
    "intro": "Làm quen từ mới",
    "vi_to_en": "Việt -> Anh",
    "en_to_vi": "Anh -> Việt",
}


def word_progress_payload(index: int, entry, state: Dict) -> Dict:
    meta = state["words"][entry.wid]
    is_pending = meta["status"] == "pending"
    last_mode = meta.get("last_mode")
    return {
        "index": index,
        "wid": entry.wid,
        "word": entry.word,
        "meaning_vi": entry.meaning_vi,
        "meaning_en": entry.meaning_en,
        "pos": entry.pos,
        "phonetic": entry.phonetic,
        "notes": entry.notes,
        "status": meta["status"],
        "status_label": "Chưa mở" if is_pending else "Đã mở",
        "opened": not is_pending,
        "level": None if is_pending else meta["level"],
        "level_label": "Chưa mở" if is_pending else f"B{meta['level']}",
        "times_seen": meta["times_seen"],
        "last_seen_turn": meta["last_seen_turn"],
        "last_mode": last_mode,
        "last_mode_label": MODE_LABELS.get(last_mode) if last_mode else None,
    }


def vocab_progress_payload(state: Dict) -> Dict:
    return {
        "selected_vocab": ACTIVE_VOCAB_PATH.name,
        "total_words": len(VOCAB),
        "summary": progress_payload(state),
        "items": [word_progress_payload(index, entry, state) for index, entry in enumerate(VOCAB, start=1)],
    }


def mode_balance_payload(state: Dict) -> Dict:
    return current_mode_balance(state)


def progress_payload(state: Dict, preview_new_word: bool = False) -> Dict:
    counts, pending = level_counts(state)
    if preview_new_word and pending > 0:
        counts[1] += 1
        pending -= 1
    return {
        "b1": counts[1],
        "b2": counts[2],
        "b3": counts[3],
        "b4": counts[4],
        "b5": counts[5],
        "pending": pending,
        "line": progress_line(state, preview_new_word=preview_new_word),
    }


def session_payload(state: Dict) -> Dict:
    return {
        "turn": state["turn"],
        "total_words": len(VOCAB),
        "selected_vocab": ACTIVE_VOCAB_PATH.name,
        "progress": progress_payload(state),
        "mode_balance": mode_balance_payload(state),
    }


def vocab_sets_payload() -> Dict:
    return {
        "selected": ACTIVE_VOCAB_PATH.name,
        "sets": list_vocab_names(VOCAB_DIR),
    }


def activate_vocab_set(filename: Optional[str] = None) -> None:
    global ACTIVE_VOCAB_PATH, STATE_PATH, VOCAB, VOCAB_MAP, STATE, PENDING_CARD
    vocab_path = resolve_vocab_path(filename, vocab_dir=VOCAB_DIR, log_dir=LOG_DIR)
    save_selected_vocab_name(vocab_path.name, LOG_DIR)
    ACTIVE_VOCAB_PATH = vocab_path
    STATE_PATH = state_path_for_vocab(ACTIVE_VOCAB_PATH, LOG_DIR)
    VOCAB = load_vocab(ACTIVE_VOCAB_PATH)
    VOCAB_MAP = {entry.wid: entry for entry in VOCAB}
    STATE = load_state(STATE_PATH, VOCAB)
    PENDING_CARD = None


def ensure_pending_card() -> Optional[Dict]:
    global PENDING_CARD
    if PENDING_CARD is not None:
        return PENDING_CARD
    card = next_card(STATE, VOCAB_MAP)
    if card is None:
        return None
    PENDING_CARD = {"token": str(uuid4()), **card}
    return PENDING_CARD


def card_payload(card: Dict) -> Dict:
    entry = VOCAB_MAP[card["wid"]]
    appearance = STATE["words"][entry.wid]["times_seen"] + 1
    preview = card["kind"] == "intro"
    payload = {
        "token": card["token"],
        "kind": card["kind"],
        "mode": card["mode"],
        "mode_label": MODE_LABELS[card["mode"]],
        "level": card["level"],
        "appearance": appearance,
        "upcoming_turn": STATE["turn"] + 1,
        "progress": progress_payload(STATE, preview_new_word=preview),
        "word": entry.word,
        "meaning_vi": entry.meaning_vi,
        "meaning_en": entry.meaning_en,
        "examples": format_examples(entry),
        "pos": entry.pos,
        "phonetic": entry.phonetic,
        "notes": entry.notes,
    }

    if card["mode"] == "intro":
        payload.update(
            {
                "prompt_label": "Nhập lại từ tiếng Anh",
                "input_placeholder": "Nhập lại từ tiếng Anh",
            }
        )
    elif card["mode"] == "vi_to_en":
        payload.update(
            {
                "prompt_vi": entry.meaning_vi,
                "prompt_label": "Nhập từ tiếng Anh",
                "input_placeholder": "Nhập từ tiếng Anh",
            }
        )
    else:
        payload.update(
            {
                "word": entry.word,
                "choice_hint": "Tự nhớ nghĩa tiếng Việt rồi chọn mức độ bạn nhớ.",
                "choices": [
                    {"value": "up", "label": "Lên 1 bậc"},
                    {"value": "keep", "label": "Giữ nguyên"},
                    {"value": "down", "label": "Xuống 1 bậc"},
                ],
            }
        )

    return payload


def evaluate_intro(card: Dict, payload: AnswerPayload) -> Dict:
    entry = VOCAB_MAP[card["wid"]]
    answer = payload.answer or ""
    correct, typo = match_english_answer(answer, entry.word)
    return {
        "correct": correct,
        "typo": typo,
        "old_level": 1,
        "new_level": 1,
        "status": "correct" if correct else "wrong",
        "headline": f"Đúng: {entry.word}." if correct else f"Sai: đáp án đúng là {entry.word}.",
        "note": "Đây là lượt làm quen đầu tiên nên từ vẫn ở B1.",
    }


def evaluate_vi_to_en(card: Dict, payload: AnswerPayload) -> Dict:
    entry = VOCAB_MAP[card["wid"]]
    answer = payload.answer or ""
    correct, typo = match_english_answer(answer, entry.word)
    old_level = card["level"]
    new_level = min(5, old_level + 1) if correct else max(1, old_level - 1)

    if correct:
        if typo:
            note = f"Viết chuẩn là `{entry.word}`."
        elif new_level == old_level:
            note = f"Từ vẫn ở B{new_level}."
        else:
            note = f"Từ đi từ B{old_level} lên B{new_level}."
        headline = f"Đúng: {entry.word}."
        status = "correct"
    else:
        if new_level == old_level:
            note = f"Đáp án đúng là `{entry.word}`; từ vẫn ở B{new_level}."
        else:
            note = f"Đáp án đúng là `{entry.word}`; từ đi từ B{old_level} xuống B{new_level}."
        headline = f"Sai: đáp án đúng là {entry.word}."
        status = "wrong"

    return {
        "correct": correct,
        "typo": typo,
        "old_level": old_level,
        "new_level": new_level,
        "status": status,
        "headline": headline,
        "note": note,
    }


def evaluate_en_to_vi(card: Dict, payload: AnswerPayload) -> Dict:
    entry = VOCAB_MAP[card["wid"]]
    choice = (payload.choice or "").strip().lower()
    mapping = {"u": "up", "up": "up", "k": "keep", "keep": "keep", "d": "down", "down": "down"}
    if choice not in mapping:
        raise HTTPException(status_code=400, detail="Lựa chọn không hợp lệ. Hãy dùng up, keep hoặc down.")

    choice = mapping[choice]
    old_level = card["level"]
    if choice == "up":
        new_level = min(5, old_level + 1)
        headline = f"Lên bậc: {short_answer(entry)}."
        note = f"Bạn tự đánh giá nhớ chắc; từ đi từ B{old_level} lên B{new_level}."
        status = "correct"
    elif choice == "keep":
        new_level = old_level
        headline = f"Giữ nguyên: {short_answer(entry)}."
        note = "Bạn tự đánh giá nhớ lơ mơ; từ giữ nguyên bậc."
        status = "neutral"
    else:
        new_level = max(1, old_level - 1)
        headline = f"Xuống bậc: {short_answer(entry)}."
        if new_level == old_level:
            note = "Bạn tự đánh giá chưa nhớ; từ vẫn ở B1."
        else:
            note = f"Bạn tự đánh giá chưa nhớ; từ đi từ B{old_level} xuống B{new_level}."
        status = "wrong"

    return {
        "correct": choice == "up",
        "typo": False,
        "old_level": old_level,
        "new_level": new_level,
        "status": status,
        "headline": headline,
        "note": note,
    }


def evaluate_answer(card: Dict, payload: AnswerPayload) -> Dict:
    if card["mode"] == "intro":
        return evaluate_intro(card, payload)
    if card["mode"] == "vi_to_en":
        return evaluate_vi_to_en(card, payload)
    return evaluate_en_to_vi(card, payload)


def result_payload(card: Dict, evaluation: Dict) -> Dict:
    entry = VOCAB_MAP[card["wid"]]
    return {
        "status": evaluation["status"],
        "headline": evaluation["headline"],
        "note": evaluation["note"],
        "correct_word": entry.word,
        "meaning_vi": entry.meaning_vi,
        "meaning_en": entry.meaning_en,
        "examples": format_examples(entry),
        "notes": entry.notes,
        "old_level": evaluation["old_level"],
        "new_level": evaluation["new_level"],
        "mode": card["mode"],
        "mode_label": MODE_LABELS[card["mode"]],
    }


def persist_state_or_raise(state_path, state: Dict) -> None:
    try:
        save_state(state_path, state)
    except OSError as exc:
        if getattr(exc, "errno", None) == 28:
            raise HTTPException(
                status_code=507,
                detail="Không thể lưu thay đổi vì ổ đĩa đã đầy. Hãy giải phóng dung lượng rồi thử lại.",
            ) from exc
        raise HTTPException(status_code=500, detail=f"Không thể lưu thay đổi: {exc}") from exc


@app.get("/")
def home() -> FileResponse:
    if not HTML_PATH.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file giao diện HTML.")
    return FileResponse(HTML_PATH)


@app.get("/srs_study.html")
def study_html() -> FileResponse:
    return home()


@app.get("/api/status")
def api_status() -> Dict:
    with STATE_LOCK:
        return {
            "session": session_payload(STATE),
            "vocab_sets": vocab_sets_payload(),
        }


@app.get("/api/vocab-sets")
def api_vocab_sets() -> Dict:
    with STATE_LOCK:
        return vocab_sets_payload()


@app.get("/api/vocab-progress")
def api_vocab_progress() -> Dict:
    with STATE_LOCK:
        return vocab_progress_payload(STATE)


@app.get("/api/mode-balance")
def api_mode_balance() -> Dict:
    with STATE_LOCK:
        return mode_balance_payload(STATE)


@app.post("/api/mode-balance")
def api_set_mode_balance(payload: ModeBalancePayload) -> Dict:
    with STATE_LOCK:
        balance = set_mode_balance(STATE, payload.vi_to_en_ratio)
        persist_state_or_raise(STATE_PATH, STATE)
        return {
            "message": "Đã cập nhật tỷ lệ giữa điền chữ và flashcard.",
            "mode_balance": balance,
            "session": session_payload(STATE),
        }


@app.post("/api/vocab-sets/select")
def api_select_vocab_set(payload: SelectVocabPayload) -> Dict:
    with STATE_LOCK:
        activate_vocab_set(payload.filename)
        return {
            "message": f"Đã chuyển sang bộ `{ACTIVE_VOCAB_PATH.name}`.",
            "session": session_payload(STATE),
            "vocab_sets": vocab_sets_payload(),
        }


@app.post("/api/reset")
def api_reset() -> Dict:
    global STATE, PENDING_CARD
    with STATE_LOCK:
        STATE = reset_state(STATE_PATH, VOCAB)
        PENDING_CARD = None
        return {
            "message": "Đã reset tiến độ học.",
            "session": session_payload(STATE),
        }


@app.get("/api/card")
def api_card() -> Dict:
    with STATE_LOCK:
        card = ensure_pending_card()
        if card is None:
            return {
                "done": True,
                "message": "Không còn thẻ để học.",
                "session": session_payload(STATE),
            }
        return {
            "done": False,
            "card": card_payload(card),
            "session": session_payload(STATE),
        }


@app.post("/api/answer")
def api_answer(payload: AnswerPayload) -> Dict:
    global PENDING_CARD
    with STATE_LOCK:
        if PENDING_CARD is None:
            raise HTTPException(status_code=409, detail="Hiện không có thẻ nào đang chờ trả lời.")
        if payload.token != PENDING_CARD["token"]:
            raise HTTPException(status_code=409, detail="Thẻ hiện tại đã thay đổi. Hãy tải lại câu hỏi mới.")

        evaluation = evaluate_answer(PENDING_CARD, payload)
        apply_result(STATE, PENDING_CARD["wid"], PENDING_CARD, evaluation)
        commit_appearance(STATE, PENDING_CARD["wid"], PENDING_CARD["mode"], PENDING_CARD.get("level"))
        persist_state_or_raise(STATE_PATH, STATE)

        response = {
            "result": result_payload(PENDING_CARD, evaluation),
            "session": session_payload(STATE),
        }
        PENDING_CARD = None
        return response


@app.get("/api/health")
def api_health() -> Dict:
    return {"ok": True, "words": len(VOCAB)}


@app.exception_handler(HTTPException)
def http_error(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import os
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("srs_fastapi:app", host=host, port=port, reload=False)
