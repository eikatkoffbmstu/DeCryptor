from flask import Flask, render_template, request, jsonify
from collections import Counter
import re
import random
import time

app = Flask(__name__)

# Частоты букв русского языка (по убыванию)
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


# ================== ЧАСТЫЕ БИГРАММЫ РУССКОГО ЯЗЫКА ==================
COMMON_BIGRAMS = {
    "ст", "но", "то", "на", "ен", "ов", "ни", "ра", "во", "ко",
    "ро", "по", "ос", "го", "ер", "ре", "не", "ал", "ли", "ол",
    "ка", "та", "от", "пр", "ло", "ан", "ин", "ти", "ор", "ет",
    "те", "ль", "ат", "ит", "ны", "ла", "ар", "од", "ру",
    "мо", "де", "ск", "чи", "ел", "ва", "ей", "ак", "ри",
}


# ================== ПРЕДВАРИТЕЛЬНЫЙ ИНДЕКС ТРИГРАММ ==================
DICT_TRIGRAMS = set()


def build_dict_trigrams():
    global DICT_TRIGRAMS
    t0 = time.time()
    for w in WORDS:
        for i in range(len(w) - 2):
            DICT_TRIGRAMS.add(w[i:i + 3])
    print(f"[dict] Триграмм в словаре: {len(DICT_TRIGRAMS)} (за {time.time() - t0:.1f} сек)")


build_dict_trigrams()


# ================== НЕЧЁТКОЕ СРАВНЕНИЕ ==================

def ngrams(word, n=3):
    """Все подстроки длины n."""
    if len(word) < n:
        return {word} if word else set()
    return {word[i:i + n] for i in range(len(word) - n + 1)}


def partial_match_score(word, min_overlap=0.4):
    """
    Возвращает 0..1 — насколько слово "узнаётся" в словаре.
    1.0 — если слово точно есть в словаре.
    0.4..0.99 — если ≥40% его триграмм встречаются в словарных словах.
    """
    if len(word) < 2:
        return 0.0

    # Точное совпадение — максимальный балл
    if word in WORDS:
        return 1.0

    # Проверяем по триграммам
    word_trigrams = ngrams(word, 3)
    if word_trigrams and DICT_TRIGRAMS:
        hits = sum(1 for tg in word_trigrams if tg in DICT_TRIGRAMS)
        overlap = hits / len(word_trigrams)
        if overlap >= min_overlap:
            return overlap

    # Для коротких слов — проверка по частым биграммам
    if len(word) <= 4:
        bg = ngrams(word, 2)
        if bg:
            bg_hits = sum(1 for b in bg if b in COMMON_BIGRAMS)
            bg_ratio = bg_hits / len(bg)
            if bg_ratio >= 0.5:
                return bg_ratio * 0.7

    return 0.0


# ================== СКОРИНГ ==================

def score_text(mapping, tokens):
    """
    Оценка качества сопоставления.
    Возвращает: (total_score, exact_words, partial_words, total_words)
    """
    # Ищем, какое число = пробел
    space_tok = None
    for k, v in mapping.items():
        if v == ' ':
            space_tok = k
            break
    if space_tok is None:
        return (0.0, 0, 0, 0)

    # Строим слова
    words = []
    current = []
    for tok in tokens:
        ch = mapping.get(tok, '?')
        if ch == ' ':
            if current:
                words.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        words.append("".join(current))

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

    print(f"[brute] Токенов: {len(tokens)}, уникальных: {len(set(tokens))}")
    print(f"[brute] Словарь: {len(WORDS)} слов, триграмм: {len(DICT_TRIGRAMS)}")

    unique_toks = sorted(set(tokens), key=lambda t: int(t))
    if len(unique_toks) > 33:
        unique_toks = unique_toks[:33]

    freq = Counter(tokens)
    sorted_by_freq = sorted(unique_toks, key=lambda t: -freq[t])

    # Пробел ставим на САМОЕ ЧАСТОЕ число
    space_tok = sorted_by_freq[0]

    # Остальные числа получают буквы из RU_FREQ
    letters = list(RU_FREQ)
    best_mapping = {space_tok: ' '}
    letter_idx = 0
    for tok in sorted_by_freq:
        if tok == space_tok:
            continue
        if letter_idx < len(letters):
            best_mapping[tok] = letters[letter_idx]
            letter_idx += 1

    best_score, *_ = score_text(best_mapping, tokens)
    best_result = dict(best_mapping)
    print(f"[brute] Стартовый скор: {best_score:.2f}, пробел = {space_tok}")

    improvements = 0
    letters_pool = list(RU_FREQ)
    modifiable = [t for t in unique_toks if t != space_tok]

    if len(modifiable) < 1:
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
            "space_token": space_tok,
        }

    while time.time() - start < time_limit:
        mode = random.choice(["swap", "reassign"])

        candidate = dict(best_result)

        if mode == "swap" and len(modifiable) >= 2:
            a, b = random.sample(modifiable, 2)
            candidate[a], candidate[b] = candidate.get(b, '?'), candidate.get(a, '?')
        else:
            tok = random.choice(modifiable)
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
        "space_token": space_tok,
    }


# ================== РОУТЫ ==================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    text = data.get("text", "")
    tokens = re.findall(r"\d+", text)
    counter = Counter(tokens)
    sorted_tokens = sorted(counter.keys(), key=lambda t: (-counter[t], int(t)))

    suggestion = {}
    for i, tok in enumerate(sorted_tokens):
        suggestion[tok] = RU_FREQ[i] if i < len(RU_FREQ) else "?"

    return jsonify({
        "counts": dict(counter),
        "sorted_tokens": sorted_tokens,
        "suggestion": suggestion,
        "total": len(tokens),
        "unique": len(counter),
    })


@app.route("/decode", methods=["POST"])
def decode():
    data = request.get_json()
    text = data.get("text", "")
    mapping = data.get("mapping", {})

    def replace_token(match):
        tok = match.group(0)
        return mapping.get(tok, f"[{tok}]")

    return jsonify({"result": re.sub(r"\d+", replace_token, text)})


@app.route("/bruteforce", methods=["POST"])
def bruteforce():
    data = request.get_json()
    text = data.get("text", "")
    time_limit = float(data.get("time_limit", 8.0))
    time_limit = min(max(time_limit, 2.0), 30.0)

    tokens = re.findall(r"\d+", text)
    if not tokens:
        return jsonify({"error": "Нет чисел в тексте"})

    result = brute_force(tokens, time_limit=time_limit)

    def replace_token(match):
        tok = match.group(0)
        return result["mapping"].get(tok, f"[{tok}]")

    result["decoded"] = re.sub(r"\d+", replace_token, text)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)