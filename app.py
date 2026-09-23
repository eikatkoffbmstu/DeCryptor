from flask import Flask, render_template, request, jsonify
from collections import Counter
import re
import random
import time

app = Flask(__name__)

RU_FREQ = "оеаинтсрвлкмдпуяыьгзбчйхжшюцщэфъё"


# ================== ЗАГРУЗКА СЛОВАРЯ ==================
WORDS = set()


def load_dictionary(path="data/russian.txt"):
    global WORDS
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                if len(w) >= 2 and w.isalpha():
                    WORDS.add(w)
        print(f"[dict] Загружено слов: {len(WORDS)}")
    except FileNotFoundError:
        print(f"[dict] Файл {path} не найден — брутфорс будет грубым")


load_dictionary()


COMMON_BIGRAMS = {
    "ст", "но", "то", "на", "ен", "ов", "ни", "ра", "во", "ко",
    "ро", "по", "ос", "го", "ер", "ре", "не", "ал", "ли", "ол",
    "ка", "та", "от", "пр", "ло", "ан", "ин", "ти", "ор", "ет",
    "те", "ль", "ат", "ит", "ны", "ла", "ар", "од", "ру",
    "мо", "де", "ск", "чи", "ел", "ва", "ей", "ак", "ри",
}


DICT_TRIGRAMS = set()


def build_dict_trigrams():
    global DICT_TRIGRAMS
    t0 = time.time()
    for w in WORDS:
        for i in range(len(w) - 2):
            DICT_TRIGRAMS.add(w[i:i + 3])
    print(f"[dict] Триграмм в словаре: {len(DICT_TRIGRAMS)} (за {time.time() - t0:.1f} сек)")


build_dict_trigrams()


# ================== ПАРСИНГ ШИФРОТЕКСТА ==================

# Разделители слов: пробел, точка, запятая, |, /, -, перенос строки и т.п.
WORD_SEPARATORS = set(" .,;:!?|/\\\n\t\r")


def parse_tokens(text):
    """
    Разбивает текст на токены:
    - числа ("01", "23", ...) — буквы
    - разделители (" ", ".", "|", ...) — границы слов
    Возвращает список: [("num", "01"), ("sep", " "), ("num", "18"), ...]
    """
    tokens = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            tokens.append(("num", text[i:j]))
            i = j
        elif ch in WORD_SEPARATORS:
            # Схлопываем несколько подряд идущих разделителей в один " "
            tokens.append(("sep", " "))
            i += 1
            while i < len(text) and text[i] in WORD_SEPARATORS:
                i += 1
        else:
            # Прочие символы игнорируем
            i += 1
    return tokens


# ================== НЕЧЁТКОЕ СРАВНЕНИЕ ==================

def ngrams(word, n=3):
    if len(word) < n:
        return {word} if word else set()
    return {word[i:i + n] for i in range(len(word) - n + 1)}


def partial_match_score(word, min_overlap=0.4):
    if len(word) < 2:
        return 0.0

    if word in WORDS:
        return 1.0

    word_trigrams = ngrams(word, 3)
    if word_trigrams and DICT_TRIGRAMS:
        hits = sum(1 for tg in word_trigrams if tg in DICT_TRIGRAMS)
        overlap = hits / len(word_trigrams)
        if overlap >= min_overlap:
            return overlap

    if len(word) <= 4:
        bg = ngrams(word, 2)
        if bg:
            bg_hits = sum(1 for b in bg if b in COMMON_BIGRAMS)
            bg_ratio = bg_hits / len(bg)
            if bg_ratio >= 0.5:
                return bg_ratio * 0.7

    return 0.0


# ================== СКОРИНГ И РАЗБОР СЛОВ ==================

def build_words(mapping, tokens):
    """
    Из списка токенов и mapping строит список слов.
    tokens: список ("num", "01") / ("sep", " ")
    mapping: {"01": "к", "18": "р", ...}
    """
    words = []
    current = []
    for kind, val in tokens:
        if kind == "sep":
            if current:
                words.append("".join(current))
                current = []
        else:  # num
            ch = mapping.get(val, "?")
            current.append(ch)
    if current:
        words.append("".join(current))
    return words


def extract_words(mapping, tokens):
    """Список слов с оценкой."""
    words = build_words(mapping, tokens)
    result = []
    for w in words:
        if len(w) < 2:
            continue
        s = partial_match_score(w)
        if s >= 1.0:
            status = "exact"
        elif s >= 0.4:
            status = "partial"
        else:
            status = "miss"
        result.append({"word": w, "score": round(s, 2), "status": status})
    return result


def score_text(mapping, tokens):
    """Оценка mapping. Возвращает (total_score, exact, partial, total)."""
    words = build_words(mapping, tokens)
    total_score = 0.0
    exact = 0
    partial = 0
    total = 0
    for w in words:
        if len(w) < 2:
            continue
        total += 1
        s = partial_match_score(w)
        if s >= 1.0:
            exact += 1
            total_score += 3.0
        elif s >= 0.4:
            partial += 1
            total_score += s * 2.0
        else:
            total_score -= 0.1 * len(w)
    return (total_score, exact, partial, total)


# ================== БРУТФОРС ==================

def brute_force(tokens, time_limit=8.0):
    start = time.time()

    # Уникальные числа
    numbers = [val for kind, val in tokens if kind == "num"]
    unique_toks = sorted(set(numbers), key=lambda t: int(t))
    if len(unique_toks) > 33:
        unique_toks = unique_toks[:33]

    freq = Counter(numbers)
    sorted_by_freq = sorted(unique_toks, key=lambda t: -freq[t])

    print(f"[brute] Токенов: {len(tokens)}, чисел: {len(numbers)}, уникальных: {len(unique_toks)}")
    print(f"[brute] Словарь: {len(WORDS)} слов, триграмм: {len(DICT_TRIGRAMS)}")

    # Начальное сопоставление по частоте
    letters = list(RU_FREQ)
    best_mapping = {}
    for i, tok in enumerate(sorted_by_freq):
        if i < len(letters):
            best_mapping[tok] = letters[i]

    # Все числа получают букву
    for tok in unique_toks:
        if tok not in best_mapping:
            best_mapping[tok] = random.choice(letters)

    best_score, *_ = score_text(best_mapping, tokens)
    best_result = dict(best_mapping)
    print(f"[brute] Стартовый скор: {best_score:.2f}")

    improvements = 0
    letters_pool = list(RU_FREQ)

    if len(unique_toks) < 2:
        total_score, exact, partial, total = score_text(best_result, tokens)
        return {
            "mapping": best_result,
            "score": round(total_score, 2),
            "exact_words": exact,
            "partial_words": partial,
            "total_words": total,
            "improvements": 0,
            "dict_size": len(WORDS),
            "trigram_size": len(DICT_TRIGRAMS),
            "elapsed": round(time.time() - start, 2),
            "words": extract_words(best_result, tokens),
        }

    while time.time() - start < time_limit:
        mode = random.choice(["swap", "reassign"])
        candidate = dict(best_result)

        if mode == "swap" and len(unique_toks) >= 2:
            a, b = random.sample(unique_toks, 2)
            candidate[a], candidate[b] = candidate.get(b, '?'), candidate.get(a, '?')
        else:
            tok = random.choice(unique_toks)
            candidate[tok] = random.choice(letters_pool)

        sc, *_ = score_text(candidate, tokens)
        if sc > best_score:
            best_score = sc
            best_result = candidate
            improvements += 1

    total_score, exact, partial, total = score_text(best_result, tokens)
    print(f"[brute] Финал: скор={total_score:.2f}, exact={exact}, partial={partial}, "
          f"total={total}, улучшений={improvements}")

    return {
        "mapping": best_result,
        "score": round(total_score, 2),
        "exact_words": exact,
        "partial_words": partial,
        "total_words": total,
        "improvements": improvements,
        "dict_size": len(WORDS),
        "trigram_size": len(DICT_TRIGRAMS),
        "elapsed": round(time.time() - start, 2),
        "words": extract_words(best_result, tokens),
    }


# ================== РОУТЫ ==================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    text = data.get("text", "")
    tokens = parse_tokens(text)

    numbers = [val for kind, val in tokens if kind == "num"]
    counter = Counter(numbers)
    sorted_nums = sorted(counter.keys(), key=lambda t: (-counter[t], int(t)))

    suggestion = {}
    for i, tok in enumerate(sorted_nums):
        suggestion[tok] = RU_FREQ[i] if i < len(RU_FREQ) else "?"

    words = build_words(suggestion, tokens)  # только для info

    return jsonify({
        "counts": dict(counter),
        "sorted_tokens": sorted_nums,
        "suggestion": suggestion,
        "total": len(numbers),
        "unique": len(counter),
    })


@app.route("/decode", methods=["POST"])
def decode():
    data = request.get_json()
    text = data.get("text", "")
    mapping = data.get("mapping", {})

    tokens = parse_tokens(text)
    parts = []
    for kind, val in tokens:
        if kind == "sep":
            parts.append(" ")
        else:
            parts.append(mapping.get(val, f"[{val}]"))

    return jsonify({"result": "".join(parts)})


@app.route("/bruteforce", methods=["POST"])
def bruteforce():
    data = request.get_json()
    text = data.get("text", "")
    time_limit = float(data.get("time_limit", 8.0))
    time_limit = min(max(time_limit, 2.0), 30.0)

    tokens = parse_tokens(text)
    numbers = [val for kind, val in tokens if kind == "num"]
    if not numbers:
        return jsonify({"error": "Нет чисел в тексте"})

    result = brute_force(tokens, time_limit=time_limit)

    # Расшифрованный текст
    parts = []
    for kind, val in tokens:
        if kind == "sep":
            parts.append(" ")
        else:
            parts.append(result["mapping"].get(val, f"[{val}]"))
    result["decoded"] = "".join(parts)

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)