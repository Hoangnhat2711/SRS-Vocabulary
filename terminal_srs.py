#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BASE_LEVEL_WEIGHTS = {1: 45, 2: 25, 3: 15, 4: 10, 5: 5}
LEVEL_ONE_TARGET = 10
RECENT_HISTORY_WINDOW = 5
MODE_BALANCE_STEP = 10
MODE_HISTORY_WINDOW = 10
DEFAULT_VI_TO_EN_RATIO = 70
STATE_VERSION = 2
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VOCAB_DIR_NAME = "vocab_sets"
DEFAULT_LOG_DIR_NAME = "logs"
DEFAULT_VOCAB_FILE = "Từ vựng.txt"
DEFAULT_SELECTION_FILE = "selected_vocab_set.json"
COMMAND_HELP = "`:quit` thoát | `:stats` xem tiến độ | `:help` xem trợ giúp"


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


class QuitSession(Exception):
    pass



def ensure_storage_dirs(base_dir: Path = BASE_DIR) -> Tuple[Path, Path]:
    vocab_dir = base_dir / DEFAULT_VOCAB_DIR_NAME
    log_dir = base_dir / DEFAULT_LOG_DIR_NAME
    vocab_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return vocab_dir, log_dir


def list_vocab_files(vocab_dir: Optional[Path] = None) -> List[Path]:
    if vocab_dir is None:
        vocab_dir, _ = ensure_storage_dirs()
    return sorted([path for path in vocab_dir.glob("*.txt") if path.is_file()], key=lambda item: item.name.casefold())


def list_vocab_names(vocab_dir: Optional[Path] = None) -> List[str]:
    return [path.name for path in list_vocab_files(vocab_dir)]


def state_slug_for_vocab(vocab_path: Path) -> str:
    slug = re.sub(r"[^\w.-]+", "_", vocab_path.stem, flags=re.UNICODE).strip("._")
    return slug or "vocab"


def state_path_for_vocab(vocab_path: Path, log_dir: Optional[Path] = None) -> Path:
    if log_dir is None:
        _, log_dir = ensure_storage_dirs()
    return log_dir / f"{state_slug_for_vocab(vocab_path)}.state.json"


def selection_config_path(log_dir: Optional[Path] = None) -> Path:
    if log_dir is None:
        _, log_dir = ensure_storage_dirs()
    return log_dir / DEFAULT_SELECTION_FILE


def load_selected_vocab_name(log_dir: Optional[Path] = None) -> Optional[str]:
    config_path = selection_config_path(log_dir)
    if not config_path.exists():
        return None
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return None
    selected = payload.get("selected_vocab")
    return selected if isinstance(selected, str) and selected.strip() else None


def save_selected_vocab_name(filename: str, log_dir: Optional[Path] = None) -> None:
    config_path = selection_config_path(log_dir)
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump({"selected_vocab": filename}, handle, ensure_ascii=False, indent=2)


def resolve_vocab_path(
    file_arg: Optional[str] = None,
    vocab_dir: Optional[Path] = None,
    log_dir: Optional[Path] = None,
) -> Path:
    if vocab_dir is None or log_dir is None:
        default_vocab_dir, default_log_dir = ensure_storage_dirs()
        vocab_dir = vocab_dir or default_vocab_dir
        log_dir = log_dir or default_log_dir

    if file_arg:
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
            f"Không tìm thấy file .txt nào trong thư mục `{vocab_dir}`. Hãy thêm bộ từ vựng vào đó trước."
        )

    selected = load_selected_vocab_name(log_dir)
    if selected:
        selected_path = vocab_dir / selected
        if selected_path.exists() and selected_path.is_file():
            return selected_path.resolve()

    preferred = vocab_dir / DEFAULT_VOCAB_FILE
    chosen = preferred if preferred.exists() else available[0]
    save_selected_vocab_name(chosen.name, log_dir)
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

    a_compact = compact_answer(answer)
    t_compact = compact_answer(target)
    if a_compact == t_compact:
        return True, True

    if not a_compact or not t_compact:
        return False, False

    distance = levenshtein(a_compact, t_compact)
    allowed = 1 if len(t_compact) <= 8 else 2
    ratio = SequenceMatcher(None, a_compact, t_compact).ratio()
    if distance <= allowed and ratio >= 0.80:
        return True, True
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
            }
            for entry in vocab
        },
    }


def load_state(state_path: Path, vocab: List[VocabEntry]) -> Dict:
    signature = vocab_signature(vocab)
    if not state_path.exists():
        return build_initial_state(signature, vocab)

    with state_path.open("r", encoding="utf-8") as handle:
        state = json.load(handle)

    if state.get("vocab_signature") != signature:
        print("Phát hiện trạng thái cũ không còn khớp danh sách từ hiện tại. Hệ thống sẽ tạo trạng thái mới.")
        return build_initial_state(signature, vocab)
    return ensure_state_defaults(state)


def save_state(state_path: Path, state: Dict) -> None:
    ensure_state_defaults(state)
    with state_path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)


def reset_state(state_path: Path, vocab: List[VocabEntry]) -> Dict:
    state = build_initial_state(vocab_signature(vocab), vocab)
    save_state(state_path, state)
    return state


def normalize_vi_to_en_ratio(value: Optional[int]) -> int:
    try:
        numeric = int(value if value is not None else DEFAULT_VI_TO_EN_RATIO)
    except (TypeError, ValueError):
        numeric = DEFAULT_VI_TO_EN_RATIO
    numeric = max(0, min(100, numeric))
    return int((numeric + MODE_BALANCE_STEP / 2) // MODE_BALANCE_STEP * MODE_BALANCE_STEP)


def ensure_state_defaults(state: Dict) -> Dict:
    state.setdefault("recent_history", [])
    state.setdefault("review_mode_history", [])
    settings = state.setdefault("settings", {})
    settings["vi_to_en_ratio"] = normalize_vi_to_en_ratio(settings.get("vi_to_en_ratio"))
    state["version"] = STATE_VERSION
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
    available = [(level, BASE_LEVEL_WEIGHTS[level]) for level in range(1, 6) if counts[level] > 0]
    if not available:
        return None
    return weighted_choice(available)


def choose_word_for_level(state: Dict, level: int) -> Optional[str]:
    candidates = [wid for wid, meta in state["words"].items() if meta["status"] == "active" and meta["level"] == level]
    if not candidates:
        return None
    recent = set(state["recent_history"][-RECENT_HISTORY_WINDOW:])
    filtered = [wid for wid in candidates if wid not in recent]
    pool = filtered or candidates
    return random.choice(pool)


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


def commit_appearance(state: Dict, wid: str, mode: str) -> None:
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


def show_word_details(entry: VocabEntry) -> None:
    print(f"- Từ: {entry.word}")
    if entry.pos:
        print(f"- Từ loại: {entry.pos}")
    if entry.meaning_vi:
        print(f"- Nghĩa Việt: {entry.meaning_vi}")
    if entry.meaning_en:
        print(f"- Nghĩa Anh: {entry.meaning_en}")
    if entry.phonetic:
        print(f"- Phiên âm: {entry.phonetic}")
    for idx, example in enumerate(format_examples(entry), start=1):
        print(f"- Ví dụ {idx}: {example}")
    if entry.notes:
        print(f"- Ghi chú: {entry.notes}")


def short_answer(entry: VocabEntry) -> str:
    parts = [entry.word]
    if entry.meaning_vi:
        parts.append(entry.meaning_vi)
    return " = ".join(parts)


def maybe_handle_common_command(raw: str, state: Dict, preview_new_word: bool = False) -> Optional[str]:
    command = raw.strip().lower()
    if command in {":quit", ":q", "q"}:
        raise QuitSession
    if command == ":stats":
        print(progress_line(state, preview_new_word=preview_new_word))
        return "repeat"
    if command == ":help":
        print(COMMAND_HELP)
        print("- Ở câu Việt -> Anh: nhập từ tiếng Anh rồi nhấn Enter.")
        print("- Ở câu Anh -> Việt: nhập `u` để lên 1 bậc, `k` để giữ nguyên, `d` để xuống 1 bậc.")
        return "repeat"
    return None


def prompt_intro(entry: VocabEntry, appearance: int, state: Dict) -> Dict:
    print("\n" + "=" * 72)
    print(f"Lượt kế tiếp: {state['turn'] + 1} | Bậc 1 | Lần xuất hiện {appearance} | Chế độ: Làm quen từ mới")
    print(progress_line(state, preview_new_word=True))
    print(f"Học từ mới: {entry.word} = {entry.meaning_vi}")
    show_word_details(entry)
    print(COMMAND_HELP)
    while True:
        raw = input("Nhập lại từ tiếng Anh: ").strip()
        handled = maybe_handle_common_command(raw, state, preview_new_word=True)
        if handled == "repeat":
            continue
        is_correct, typo = match_english_answer(raw, entry.word)
        return {
            "correct": is_correct,
            "typo": typo,
            "raw": raw,
            "old_level": 1,
            "new_level": 1,
            "note": "Đây là lượt làm quen đầu tiên nên từ vẫn ở B1.",
        }


def prompt_vi_to_en(entry: VocabEntry, level: int, appearance: int, state: Dict) -> Dict:
    print("\n" + "=" * 72)
    print(f"Lượt kế tiếp: {state['turn'] + 1} | Bậc {level} | Lần xuất hiện {appearance} | Chế độ: Việt -> Anh")
    print(progress_line(state))
    print(f"Gợi ý tiếng Việt: {entry.meaning_vi}")
    if entry.pos:
        print(f"Từ loại: {entry.pos}")
    print(COMMAND_HELP)
    while True:
        raw = input("Nhập từ tiếng Anh: ").strip()
        handled = maybe_handle_common_command(raw, state)
        if handled == "repeat":
            continue
        correct, typo = match_english_answer(raw, entry.word)
        old_level = level
        new_level = min(5, level + 1) if correct else max(1, level - 1)
        if correct:
            if typo:
                note = f"Viết chuẩn là `{entry.word}`."
            elif new_level == old_level:
                note = f"Từ vẫn ở B{new_level}."
            else:
                note = f"Từ đi từ B{old_level} lên B{new_level}."
        else:
            if new_level == old_level:
                note = f"Đáp án đúng là `{entry.word}`; từ vẫn ở B{new_level}."
            else:
                note = f"Đáp án đúng là `{entry.word}`; từ đi từ B{old_level} xuống B{new_level}."
        return {
            "correct": correct,
            "typo": typo,
            "raw": raw,
            "old_level": old_level,
            "new_level": new_level,
            "note": note,
        }


def prompt_en_to_vi(entry: VocabEntry, level: int, appearance: int, state: Dict) -> Dict:
    print("\n" + "=" * 72)
    print(f"Lượt kế tiếp: {state['turn'] + 1} | Bậc {level} | Lần xuất hiện {appearance} | Chế độ: Anh -> Việt")
    print(progress_line(state))
    print(f"Từ tiếng Anh: {entry.word}")
    if entry.pos:
        print(f"Từ loại: {entry.pos}")
    if entry.phonetic:
        print(f"Phiên âm: {entry.phonetic}")
    print("Tự nhớ nghĩa tiếng Việt rồi chọn:")
    print("- `u`: nhớ chắc -> lên 1 bậc")
    print("- `k`: nhớ lơ mơ -> giữ nguyên")
    print("- `d`: quên / nhớ sai -> xuống 1 bậc")
    print(COMMAND_HELP)
    while True:
        raw = input("Chọn `u`, `k`, hoặc `d`: ").strip().lower()
        handled = maybe_handle_common_command(raw, state)
        if handled == "repeat":
            continue
        if raw not in {"u", "k", "d"}:
            print("Lựa chọn không hợp lệ. Hãy nhập `u`, `k`, hoặc `d`.")
            continue
        old_level = level
        if raw == "u":
            new_level = min(5, level + 1)
            note = f"Bạn tự đánh giá nhớ chắc; từ đi từ B{old_level} lên B{new_level}."
            result = "Đúng"
        elif raw == "k":
            new_level = old_level
            note = "Bạn tự đánh giá nhớ lơ mơ; từ giữ nguyên bậc."
            result = "Giữ nguyên"
        else:
            new_level = max(1, level - 1)
            if new_level == old_level:
                note = "Bạn tự đánh giá chưa nhớ; từ vẫn ở B1."
            else:
                note = f"Bạn tự đánh giá chưa nhớ; từ đi từ B{old_level} xuống B{new_level}."
            result = "Sai"
        return {
            "correct": raw == "u",
            "typo": False,
            "raw": raw,
            "old_level": old_level,
            "new_level": new_level,
            "note": note,
            "result_label": result,
        }


def apply_result(state: Dict, wid: str, card: Dict, result: Dict) -> None:
    meta = state["words"][wid]
    if card["kind"] == "intro" and meta["status"] == "pending":
        meta["status"] = "active"
        meta["level"] = 1
    meta["level"] = result["new_level"]


def print_result(entry: VocabEntry, card: Dict, result: Dict, state: Dict) -> None:
    if card["mode"] == "en_to_vi":
        print(f"{result['result_label']}: {short_answer(entry)}.")
    elif result["correct"]:
        print(f"Đúng: {entry.word}.")
    else:
        print(f"Sai: đáp án đúng là {entry.word}.")
    print(f"Ghi nhớ: {result['note']}")
    if card["mode"] != "intro" and card["mode"] != "en_to_vi":
        print(f"Nghĩa Việt: {entry.meaning_vi}")
    if card["mode"] == "en_to_vi":
        print(f"Nghĩa Việt: {entry.meaning_vi}")
        if entry.meaning_en:
            print(f"Nghĩa Anh: {entry.meaning_en}")
    print(progress_line(state))


def run_session(vocab_path: Path, state_path: Path) -> None:
    vocab = load_vocab(vocab_path)
    vocab_map = {entry.wid: entry for entry in vocab}
    state = load_state(state_path, vocab)
    print(f"Đã nạp {len(vocab)} từ từ `{vocab_path.name}`.")
    print(COMMAND_HELP)

    while True:
        card = next_card(state, vocab_map)
        if card is None:
            print("Không còn từ nào để học trong phiên hiện tại.")
            save_state(state_path, state)
            return

        entry = vocab_map[card["wid"]]
        appearance = state["words"][entry.wid]["times_seen"] + 1
        try:
            if card["mode"] == "intro":
                result = prompt_intro(entry, appearance, state)
            elif card["mode"] == "vi_to_en":
                result = prompt_vi_to_en(entry, card["level"], appearance, state)
            else:
                result = prompt_en_to_vi(entry, card["level"], appearance, state)
        except QuitSession:
            save_state(state_path, state)
            print("Đã lưu tiến độ và thoát phiên học.")
            return

        apply_result(state, entry.wid, card, result)
        commit_appearance(state, entry.wid, card["mode"])
        save_state(state_path, state)
        print_result(entry, card, result, state)


def show_stats(vocab_path: Path, state_path: Path) -> None:
    vocab = load_vocab(vocab_path)
    state = load_state(state_path, vocab)
    print(f"Bộ từ vựng: {vocab_path.name}")
    print(f"Tổng số từ: {len(vocab)}")
    print(progress_line(state))
    print(f"Tổng số lượt đã học: {state['turn']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ôn từ vựng SRS trên terminal")
    parser.add_argument("--file", help="Tên file từ vựng trong thư mục vocab_sets hoặc đường dẫn đầy đủ")
    parser.add_argument("--reset", action="store_true", help="Xóa tiến độ của bộ hiện tại và tạo lại từ đầu")
    parser.add_argument("--stats", action="store_true", help="Chỉ in tiến độ hiện tại rồi thoát")
    parser.add_argument("--list", action="store_true", help="Liệt kê các bộ từ vựng hiện có")
    args = parser.parse_args()

    vocab_dir, log_dir = ensure_storage_dirs()

    if args.list:
        names = list_vocab_names(vocab_dir)
        if not names:
            print(f"Chưa có file .txt nào trong `{vocab_dir}`")
            return 0
        selected = load_selected_vocab_name(log_dir)
        print("Các bộ từ vựng hiện có:")
        for name in names:
            marker = " *" if name == selected else ""
            print(f"- {name}{marker}")
        return 0

    try:
        vocab_path = resolve_vocab_path(args.file, vocab_dir=vocab_dir, log_dir=log_dir)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    save_selected_vocab_name(vocab_path.name, log_dir)
    state_path = state_path_for_vocab(vocab_path, log_dir)
    vocab = load_vocab(vocab_path)

    if args.reset:
        reset_state(state_path, vocab)
        print(f"Đã reset tiến độ học cho bộ `{vocab_path.name}`.")
        if args.stats:
            show_stats(vocab_path, state_path)
            return 0

    if args.stats:
        show_stats(vocab_path, state_path)
        return 0

    try:
        run_session(vocab_path, state_path)
    except KeyboardInterrupt:
        print("\nĐã dừng phiên học.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
