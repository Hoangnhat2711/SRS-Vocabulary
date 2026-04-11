#!/usr/bin/env python3
from __future__ import annotations

# Compatibility patches for older/local Python environments.
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

import hashlib
import json
import os
import random
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

BASE_LEVEL_WEIGHTS = {1: 45, 2: 25, 3: 15, 4: 10, 5: 5}
LEVEL_ONE_TARGET = 10
RECENT_HISTORY_WINDOW = 5
LEVEL_HISTORY_WINDOW = 20
LEVEL_WEIGHT_FLOOR = 0.15
LEVEL_WEIGHT_EXPONENT = 1.35
RELAPSE_BOOST_WINDOW = 6
RELAPSE_BOOST_WEIGHT = 18
MODE_BALANCE_STEP = 10
MODE_HISTORY_WINDOW = 10
DEFAULT_VI_TO_EN_RATIO = 70
STATE_VERSION = 2
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VOCAB_DIR_NAME = "vocab_sets"
DEFAULT_LOG_DIR_NAME = "logs"
DEFAULT_VOCAB_FILE = "All_Tests.json"
DEFAULT_SELECTION_FILE = "selected_vocab_set.json"
COMBINED_VOCAB_FILE = "All_Tests.json"
DEFAULT_APP_STATE_FILE = "app_state.json"


@dataclass
class VocabEntry:
    wid: str
    word: str
    pos: str
    meaning_vi: str
    meaning_en: str
    example_1: str
    example_2: str
    phonetic: str
    notes: str


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


def ensure_storage_dirs(base_dir: Path = BASE_DIR) -> Tuple[Path, Path]:
    vocab_dir = base_dir / DEFAULT_VOCAB_DIR_NAME
    log_dir = base_dir / DEFAULT_LOG_DIR_NAME
    vocab_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return vocab_dir, log_dir


def list_vocab_files(vocab_dir: Optional[Path] = None) -> List[Path]:
    if vocab_dir is None:
        vocab_dir, _ = ensure_storage_dirs()
    return sorted(
        [path for path in vocab_dir.iterdir() if path.is_file() and path.suffix.casefold() in {".json"}],
        key=lambda item: item.name.casefold(),
    )


def list_combined_vocab_names(vocab_path: Path) -> List[str]:
    if vocab_path.suffix.casefold() != ".json" or not vocab_path.exists():
        return []
    try:
        with vocab_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []

    tests = payload.get("tests") if isinstance(payload, dict) else None
    names: List[str] = []
    if isinstance(tests, list):
        for item in tests:
            if not isinstance(item, dict):
                continue
            test_name = str(item.get("test", "")).strip()
            if test_name:
                names.append(test_name)
    return names


def logical_vocab_name(vocab_path: Path, requested_name: Optional[str] = None, log_dir: Optional[Path] = None) -> str:
    if vocab_path.name == COMBINED_VOCAB_FILE:
        chosen = (requested_name or load_selected_vocab_name(log_dir) or "").strip() if log_dir is not None else (requested_name or "").strip()
        candidates = list_combined_vocab_names(vocab_path)
        if chosen in candidates:
            return chosen
        if candidates:
            return candidates[0]
    return vocab_path.name


def list_vocab_names(vocab_dir: Optional[Path] = None) -> List[str]:
    names: List[str] = []
    for vocab_path in list_vocab_files(vocab_dir):
        if vocab_path.name == COMBINED_VOCAB_FILE:
            combined_names = list_combined_vocab_names(vocab_path)
            if combined_names:
                names.extend(combined_names)
                continue
        names.append(vocab_path.name)
    return names


def state_slug_for_vocab(vocab_path: Path) -> str:
    slug = re.sub(r"[^\w.-]+", "_", vocab_path.stem, flags=re.UNICODE).strip("._")
    return slug or "vocab"


def state_path_for_vocab(vocab_path: Path, log_dir: Optional[Path] = None) -> Path:
    if log_dir is None:
        _, log_dir = ensure_storage_dirs()
    return app_state_path(log_dir)


def app_state_path(log_dir: Optional[Path] = None) -> Path:
    if log_dir is None:
        _, log_dir = ensure_storage_dirs()
    return log_dir / DEFAULT_APP_STATE_FILE


def load_app_state(log_dir: Optional[Path] = None) -> Dict:
    path = app_state_path(log_dir)
    if not path.exists():
        return {"selected_vocab": None, "vocab_states": {}}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {"selected_vocab": None, "vocab_states": {}}
    if not isinstance(payload, dict):
        return {"selected_vocab": None, "vocab_states": {}}
    payload.setdefault("selected_vocab", None)
    payload.setdefault("vocab_states", {})
    if not isinstance(payload["vocab_states"], dict):
        payload["vocab_states"] = {}
    return payload


def save_app_state(payload: Dict, log_dir: Optional[Path] = None) -> None:
    path = app_state_path(log_dir)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def load_selected_vocab_name(log_dir: Optional[Path] = None) -> Optional[str]:
    payload = load_app_state(log_dir)
    selected = payload.get("selected_vocab")
    return selected if isinstance(selected, str) and selected.strip() else None


def save_selected_vocab_name(filename: str, log_dir: Optional[Path] = None) -> None:
    payload = load_app_state(log_dir)
    payload["selected_vocab"] = filename
    payload.setdefault("vocab_states", {})
    save_app_state(payload, log_dir)


def resolve_vocab_path(
    file_arg: Optional[str] = None,
    vocab_dir: Optional[Path] = None,
    log_dir: Optional[Path] = None,
) -> Path:
    if vocab_dir is None or log_dir is None:
        default_vocab_dir, default_log_dir = ensure_storage_dirs()
        vocab_dir = vocab_dir or default_vocab_dir
        log_dir = log_dir or default_log_dir

    combined_path = vocab_dir / COMBINED_VOCAB_FILE

    if file_arg:
        if combined_path.exists() and combined_path.is_file() and file_arg.strip() in list_combined_vocab_names(combined_path):
            return combined_path.resolve()

        raw = Path(file_arg)
        candidates = []
        if raw.is_absolute() or raw.parent != Path("."):
            candidates.append(raw)
        candidates.append(vocab_dir / raw.name)
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        raise FileNotFoundError(f"Không tìm thấy file từ vựng: {file_arg}")

    available = list_vocab_files(vocab_dir)
    if not available:
        raise FileNotFoundError(
            f"Không tìm thấy file .json nào trong thư mục `{vocab_dir}`. Hãy thêm bộ từ vựng vào đó trước."
        )

    selected = load_selected_vocab_name(log_dir)
    if selected:
        if combined_path.exists() and combined_path.is_file() and selected in list_combined_vocab_names(combined_path):
            return combined_path.resolve()
        selected_path = vocab_dir / selected
        if selected_path.exists() and selected_path.is_file():
            return selected_path.resolve()

    preferred = vocab_dir / DEFAULT_VOCAB_FILE
    chosen = preferred if preferred.exists() else available[0]
    save_selected_vocab_name(logical_vocab_name(chosen, log_dir=log_dir), log_dir)
    return chosen.resolve()


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def normalize_answer(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("’", "'").replace("`", "'")
    text = re.sub(r"\s+", " ", text)
    return text


def compact_answer(text: str) -> str:
    return re.sub(r"[\s\-_'\"]+", "", normalize_answer(text))


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def match_english_answer(answer: str, target: str) -> Tuple[bool, bool]:
    a_norm = normalize_answer(answer)
    t_norm = normalize_answer(target)
    if a_norm == t_norm:
        return True, False
    return False, False


def parse_definition(raw: str) -> Tuple[str, str, str]:
    raw = raw.strip()
    match = re.match(r"^\(([^)]*)\)\s*(.*?)\s*=\s*(.*)$", raw)
    if match:
        return match.group(1).strip(), match.group(2).strip(), match.group(3).strip()

    if "=" in raw:
        left, right = raw.split("=", 1)
        left = left.strip()
        pos = ""
        pos_match = re.match(r"^\(([^)]*)\)\s*(.*)$", left)
        if pos_match:
            pos = pos_match.group(1).strip()
            left = pos_match.group(2).strip()
        return pos, left, right.strip()

    return "", raw, ""


def load_vocab(vocab_path: Path) -> List[VocabEntry]:
    if vocab_path.suffix.casefold() == ".json":
        with vocab_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise ValueError(f"File JSON không có mảng 'items' hợp lệ: {vocab_path.name}")

        selected_name = load_selected_vocab_name(LOG_DIR)
        tests = payload.get("tests") if isinstance(payload, dict) else None
        is_combined = isinstance(tests, list) and bool(tests)
        if is_combined and selected_name and selected_name != vocab_path.name:
            filtered_items = []
            for item in items:
                if isinstance(item, dict) and str(item.get("test", "")).strip() == selected_name:
                    filtered_items.append(item)
            items = filtered_items

        entries: List[VocabEntry] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue
            word = normalize_spaces(str(item.get("word", "")))
            if not word:
                continue
            entries.append(
                VocabEntry(
                    wid=f"{index}:{word.lower()}",
                    word=word,
                    pos=str(item.get("pos", "")).strip(),
                    meaning_vi=normalize_spaces(str(item.get("meaning_vi", ""))),
                    meaning_en=normalize_spaces(str(item.get("meaning_en", ""))),
                    example_1=str(item.get("example_1", "")).strip(),
                    example_2=str(item.get("example_2", "")).strip(),
                    phonetic=str(item.get("phonetic", "")).strip(),
                    notes=str(item.get("notes", "")).strip(),
                )
            )
        return entries

    entries: List[VocabEntry] = []
    with vocab_path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            while len(parts) < 6:
                parts.append("")
            word = normalize_spaces(parts[0])
            pos, meaning_vi, meaning_en = parse_definition(parts[1])
            entries.append(
                VocabEntry(
                    wid=f"{index}:{word.lower()}",
                    word=word,
                    pos=pos,
                    meaning_vi=meaning_vi,
                    meaning_en=meaning_en,
                    example_1=parts[2].strip(),
                    example_2=parts[3].strip(),
                    phonetic=parts[4].strip(),
                    notes=parts[5].strip(),
                )
            )
    return entries


def vocab_signature(vocab: List[VocabEntry]) -> str:
    joined = "\n".join(
        f"{entry.wid}|{entry.word}|{entry.meaning_vi}|{entry.meaning_en}|{entry.example_1}|{entry.example_2}|{entry.notes}"
        for entry in vocab
    )
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def build_initial_state(signature: str, vocab: List[VocabEntry]) -> Dict:
    return {
        "version": STATE_VERSION,
        "vocab_signature": signature,
        "turn": 0,
        "recent_history": [],
        "review_level_history": [],
        "review_mode_history": [],
        "settings": {
            "vi_to_en_ratio": DEFAULT_VI_TO_EN_RATIO,
        },
        "words": {
            entry.wid: {
                "status": "pending",
                "level": None,
                "times_seen": 0,
                "last_seen_turn": None,
                "last_mode": None,
                "relapse_until_turn": None,
            }
            for entry in vocab
        },
    }


def normalize_vi_to_en_ratio(value: Optional[int]) -> int:
    try:
        numeric = int(value if value is not None else DEFAULT_VI_TO_EN_RATIO)
    except (TypeError, ValueError):
        numeric = DEFAULT_VI_TO_EN_RATIO
    numeric = max(0, min(100, numeric))
    return int((numeric + MODE_BALANCE_STEP / 2) // MODE_BALANCE_STEP * MODE_BALANCE_STEP)


def ensure_state_defaults(state: Dict) -> Dict:
    state.setdefault("recent_history", [])
    state.setdefault("review_level_history", [])
    state.setdefault("review_mode_history", [])
    settings = state.setdefault("settings", {})
    settings["vi_to_en_ratio"] = normalize_vi_to_en_ratio(settings.get("vi_to_en_ratio"))
    state["version"] = STATE_VERSION
    return state


def load_state(state_path: Path, vocab: List[VocabEntry]) -> Dict:
    signature = vocab_signature(vocab)
    log_dir = state_path.parent
    selected_name = load_selected_vocab_name(log_dir) or "__default__"
    payload = load_app_state(log_dir)
    state = payload.get("vocab_states", {}).get(selected_name)
    if not isinstance(state, dict):
        return build_initial_state(signature, vocab)
    if state.get("vocab_signature") != signature:
        print("Phát hiện trạng thái cũ không còn khớp danh sách từ hiện tại. Hệ thống sẽ tạo trạng thái mới.")
        return build_initial_state(signature, vocab)
    return ensure_state_defaults(state)


def save_state(state_path: Path, state: Dict) -> None:
    ensure_state_defaults(state)
    log_dir = state_path.parent
    selected_name = load_selected_vocab_name(log_dir) or "__default__"
    payload = load_app_state(log_dir)
    payload["selected_vocab"] = selected_name
    payload.setdefault("vocab_states", {})
    payload["vocab_states"][selected_name] = state
    save_app_state(payload, log_dir)


def reset_state(state_path: Path, vocab: List[VocabEntry]) -> Dict:
    state = build_initial_state(vocab_signature(vocab), vocab)
    save_state(state_path, state)
    return state


def current_mode_balance(state: Dict) -> Dict[str, int]:
    ensure_state_defaults(state)
    vi_to_en_ratio = normalize_vi_to_en_ratio(state["settings"].get("vi_to_en_ratio"))
    return {
        "vi_to_en_ratio": vi_to_en_ratio,
        "en_to_vi_ratio": 100 - vi_to_en_ratio,
        "window": MODE_HISTORY_WINDOW,
    }


def set_mode_balance(state: Dict, vi_to_en_ratio: int) -> Dict[str, int]:
    ensure_state_defaults(state)
    state["settings"]["vi_to_en_ratio"] = normalize_vi_to_en_ratio(vi_to_en_ratio)
    return current_mode_balance(state)


def level_counts(state: Dict) -> Tuple[Dict[int, int], int]:
    counts = {level: 0 for level in range(1, 6)}
    pending = 0
    for meta in state["words"].values():
        if meta["status"] == "pending":
            pending += 1
        else:
            counts[int(meta["level"])] += 1
    return counts, pending


def progress_line(state: Dict, preview_new_word: bool = False) -> str:
    counts, pending = level_counts(state)
    if preview_new_word and pending > 0:
        counts[1] += 1
        pending -= 1
    return (
        f"Tiến độ: B1 {counts[1]} | B2 {counts[2]} | B3 {counts[3]} | "
        f"B4 {counts[4]} | B5 {counts[5]} | Chưa mở {pending}"
    )


def weighted_choice(items: List[Tuple[int, int]]) -> int:
    total = sum(weight for _, weight in items)
    pick = random.uniform(0, total)
    current = 0.0
    for value, weight in items:
        current += weight
        if pick <= current:
            return value
    return items[-1][0]


def dynamic_level_targets(available_levels: List[int]) -> Dict[int, int]:
    if not available_levels:
        return {}
    total_weight = sum(BASE_LEVEL_WEIGHTS[level] for level in available_levels)
    raw_targets = {
        level: LEVEL_HISTORY_WINDOW * BASE_LEVEL_WEIGHTS[level] / total_weight
        for level in available_levels
    }
    targets = {level: int(raw_targets[level]) for level in available_levels}
    remainder = LEVEL_HISTORY_WINDOW - sum(targets.values())
    ranked_levels = sorted(
        available_levels,
        key=lambda level: (raw_targets[level] - targets[level], BASE_LEVEL_WEIGHTS[level], -level),
        reverse=True,
    )
    for level in ranked_levels[:remainder]:
        targets[level] += 1
    return targets


def current_review_level_block(state: Dict) -> List[int]:
    history = [level for level in state.get("review_level_history", []) if level in {1, 2, 3, 4, 5}]
    remainder = len(history) % LEVEL_HISTORY_WINDOW
    return history[-remainder:] if remainder else []


def choose_review_mode(state: Dict) -> str:
    balance = current_mode_balance(state)
    history = [mode for mode in state.get("review_mode_history", []) if mode in {"vi_to_en", "en_to_vi"}]
    window_history = history[-MODE_HISTORY_WINDOW:]

    candidates = []
    for mode in ["vi_to_en", "en_to_vi"]:
        candidate_history = (window_history + [mode])[-MODE_HISTORY_WINDOW:]
        total = len(candidate_history)
        vi_count = sum(1 for item in candidate_history if item == "vi_to_en")
        en_count = total - vi_count
        target_vi = total * balance["vi_to_en_ratio"] / 100.0
        target_en = total * balance["en_to_vi_ratio"] / 100.0
        deviation = abs(vi_count - target_vi) + abs(en_count - target_en)
        candidates.append((mode, deviation))

    best_score = min(score for _, score in candidates)
    best_modes = [mode for mode, score in candidates if score == best_score]
    if len(best_modes) == 1:
        return best_modes[0]
    return "vi_to_en" if random.uniform(0, 100) <= balance["vi_to_en_ratio"] else "en_to_vi"


def pick_pending_word(state: Dict) -> str:
    pending_ids = [wid for wid, meta in state["words"].items() if meta["status"] == "pending"]
    return random.choice(pending_ids)


def choose_level(state: Dict) -> Optional[int]:
    counts, _ = level_counts(state)
    available_levels = [level for level in range(1, 6) if counts[level] > 0]
    if not available_levels:
        return None

    block_history = current_review_level_block(state)
    block_counts = {level: 0 for level in range(1, 6)}
    for level in block_history:
        block_counts[level] += 1

    dynamic_targets = dynamic_level_targets(available_levels)
    weighted_levels = []
    for level in available_levels:
        shortage = max(0.0, dynamic_targets.get(level, 0) - block_counts[level])
        weight = LEVEL_WEIGHT_FLOOR + (shortage ** LEVEL_WEIGHT_EXPONENT)
        weighted_levels.append((level, max(1, int(weight * 100))))
    return weighted_choice(weighted_levels)


def word_selection_weight(state: Dict, wid: str) -> int:
    meta = state["words"][wid]
    last_seen_turn = meta.get("last_seen_turn")
    turns_since_seen = state["turn"] + 1 if last_seen_turn is None else max(1, state["turn"] - int(last_seen_turn))
    times_seen = max(1, int(meta.get("times_seen", 0) or 0))
    fairness_bonus = max(0, 6 - times_seen)
    relapse_until_turn = meta.get("relapse_until_turn")
    relapse_bonus = RELAPSE_BOOST_WEIGHT if relapse_until_turn is not None and state["turn"] <= int(relapse_until_turn) else 0
    return max(1, turns_since_seen * 3 + fairness_bonus + relapse_bonus)


def weighted_pick_word(state: Dict, pool: List[str]) -> str:
    weighted_pool = [(wid, word_selection_weight(state, wid)) for wid in pool]
    total = sum(weight for _, weight in weighted_pool)
    pick = random.uniform(0, total)
    current = 0.0
    for wid, weight in weighted_pool:
        current += weight
        if pick <= current:
            return wid
    return weighted_pool[-1][0]


def choose_word_for_level(state: Dict, level: int) -> Optional[str]:
    candidates = [wid for wid, meta in state["words"].items() if meta["status"] == "active" and meta["level"] == level]
    if not candidates:
        return None
    recent = set(state["recent_history"][-RECENT_HISTORY_WINDOW:])
    filtered = [wid for wid in candidates if wid not in recent]
    pool = filtered or candidates
    return weighted_pick_word(state, pool)


def next_card(state: Dict, vocab_map: Dict[str, VocabEntry]) -> Optional[Dict]:
    ensure_state_defaults(state)
    counts, pending = level_counts(state)
    if pending > 0 and counts[1] < LEVEL_ONE_TARGET:
        wid = pick_pending_word(state)
        return {"kind": "intro", "mode": "intro", "wid": wid, "level": 1}

    level = choose_level(state)
    if level is None:
        return None
    wid = choose_word_for_level(state, level)
    if wid is None:
        return None
    return {"kind": "review", "mode": choose_review_mode(state), "wid": wid, "level": level}


def commit_appearance(state: Dict, wid: str, mode: str, asked_level: Optional[int] = None) -> None:
    ensure_state_defaults(state)
    state["turn"] += 1
    meta = state["words"][wid]
    meta["times_seen"] += 1
    meta["last_seen_turn"] = state["turn"]
    meta["last_mode"] = mode
    state["recent_history"].append(wid)
    if len(state["recent_history"]) > 50:
        state["recent_history"] = state["recent_history"][-50:]
    if mode in {"vi_to_en", "en_to_vi"}:
        level = asked_level if asked_level in {1, 2, 3, 4, 5} else meta.get("level")
        if level in {1, 2, 3, 4, 5}:
            state["review_level_history"].append(level)
            if len(state["review_level_history"]) > 200:
                state["review_level_history"] = state["review_level_history"][-200:]
        state["review_mode_history"].append(mode)
        if len(state["review_mode_history"]) > 100:
            state["review_mode_history"] = state["review_mode_history"][-100:]


def format_examples(entry: VocabEntry) -> List[str]:
    examples = []
    if entry.example_1:
        examples.append(entry.example_1)
    if entry.example_2:
        examples.append(entry.example_2)
    return examples


def short_answer(entry: VocabEntry) -> str:
    parts = [entry.word]
    if entry.meaning_vi:
        parts.append(entry.meaning_vi)
    return " = ".join(parts)


def apply_result(state: Dict, wid: str, card: Dict, result: Dict) -> None:
    meta = state["words"][wid]
    old_level = meta.get("level")
    if card["kind"] == "intro" and meta["status"] == "pending":
        meta["status"] = "active"
        meta["level"] = 1
    meta["level"] = result["new_level"]
    if old_level in {1, 2, 3, 4, 5} and result["new_level"] < old_level:
        meta["relapse_until_turn"] = state["turn"] + RELAPSE_BOOST_WINDOW
    else:
        meta["relapse_until_turn"] = None


VOCAB_DIR, LOG_DIR = ensure_storage_dirs(BASE_DIR)
LEGACY_HTML_PATH = BASE_DIR / "srs_study_v2.html"
DIST_DIR = BASE_DIR / "dist"
DIST_INDEX_PATH = DIST_DIR / "index.html"

app = FastAPI(title="SRS Vocabulary API", version="2.0.0")
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


def word_progress_payload(index: int, entry: VocabEntry, state: Dict) -> Dict:
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
        "selected_vocab": logical_vocab_name(ACTIVE_VOCAB_PATH, log_dir=LOG_DIR),
        "total_words": len(VOCAB),
        "summary": progress_payload(state),
        "items": [word_progress_payload(index, entry, state) for index, entry in enumerate(VOCAB, start=1)],
    }


def mode_balance_payload(state: Dict) -> Dict:
    return current_mode_balance(state)


def session_payload(state: Dict) -> Dict:
    return {
        "turn": state["turn"],
        "total_words": len(VOCAB),
        "selected_vocab": logical_vocab_name(ACTIVE_VOCAB_PATH, log_dir=LOG_DIR),
        "progress": progress_payload(state),
        "mode_balance": mode_balance_payload(state),
    }


def vocab_sets_payload() -> Dict:
    return {
        "selected": logical_vocab_name(ACTIVE_VOCAB_PATH, log_dir=LOG_DIR),
        "sets": list_vocab_names(VOCAB_DIR),
    }


def activate_vocab_set(filename: Optional[str] = None) -> None:
    global ACTIVE_VOCAB_PATH, STATE_PATH, VOCAB, VOCAB_MAP, STATE, PENDING_CARD
    vocab_path = resolve_vocab_path(filename, vocab_dir=VOCAB_DIR, log_dir=LOG_DIR)
    save_selected_vocab_name(logical_vocab_name(vocab_path, filename, LOG_DIR), LOG_DIR)
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
        "submitted_answer": answer,
        "old_level": 1,
        "new_level": 1,
        "status": "correct" if correct else "wrong",
        "headline": f"Đúng: {entry.word}." if correct else f"Sai: đáp án đúng là {entry.word}.",
        "note": (
            f"Bạn viết sai nhẹ nhưng vẫn được chấp nhận. Cách viết chuẩn là `{entry.word}`; từ vẫn ở B1."
            if typo
            else "Đây là lượt làm quen đầu tiên nên từ vẫn ở B1."
        ),
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
        "submitted_answer": answer,
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
        "submitted_answer": None,
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
        "typo": evaluation.get("typo", False),
        "typo_notice": (
            f"Bạn nhập \"{evaluation.get('submitted_answer', '')}\". Hệ thống vẫn chấp nhận vì đây chỉ là sai chính tả nhẹ trong mức cho phép. Cách viết chuẩn là {entry.word}."
            if evaluation.get("typo")
            else None
        ),
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


def persist_state_or_raise(state_path: Path, state: Dict) -> None:
    try:
        save_state(state_path, state)
    except OSError as exc:
        if getattr(exc, "errno", None) == 28:
            raise HTTPException(
                status_code=507,
                detail="Không thể lưu thay đổi vì ổ đĩa đã đầy. Hãy giải phóng dung lượng rồi thử lại.",
            ) from exc
        raise HTTPException(status_code=500, detail=f"Không thể lưu thay đổi: {exc}") from exc


def frontend_response(requested_path: Optional[str] = None) -> FileResponse:
    clean_path = (requested_path or "").lstrip("/")
    if DIST_DIR.exists():
        dist_root = DIST_DIR.resolve()
        if clean_path:
            candidate = (DIST_DIR / clean_path).resolve()
            try:
                candidate.relative_to(dist_root)
            except ValueError as exc:
                raise HTTPException(status_code=404, detail="Đường dẫn giao diện không hợp lệ.") from exc
            if candidate.exists() and candidate.is_file():
                return FileResponse(candidate)
            if Path(clean_path).suffix:
                raise HTTPException(status_code=404, detail="Không tìm thấy tài nguyên giao diện.")
        if DIST_INDEX_PATH.exists():
            return FileResponse(DIST_INDEX_PATH)

    if LEGACY_HTML_PATH.exists():
        return FileResponse(LEGACY_HTML_PATH)

    raise HTTPException(
        status_code=404,
        detail=(
            "Không tìm thấy giao diện trong thư mục Final. "
            "Hãy chạy `npm run build` để tạo dist hoặc dùng `npm run dev` để chạy giao diện phát triển."
        ),
    )


@app.get("/")
def home() -> FileResponse:
    return frontend_response()


@app.get("/srs_study.html")
def study_html() -> FileResponse:
    return home()


@app.get("/srs_study_v2.html")
def study_html_v2() -> FileResponse:
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


@app.get("/{asset_path:path}")
def frontend_assets(asset_path: str) -> FileResponse:
    if asset_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Không tìm thấy API.")
    return frontend_response(asset_path)


@app.exception_handler(HTTPException)
def http_error(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8010"))
    uvicorn.run("srs_fastapi_main:app", host=host, port=port, reload=False)
