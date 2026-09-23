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
    """Загружаем словарь один раз при старте."""
    global WORDS
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                w = line.strip().lower()
                # Только буквы, длина 2+ (однобуквенные не считаем)
                if len(w) >= 2 and w.isalpha():
                    WORDS.add(w)
        print(f"[dict] Загружено слов: {len(WORDS)}")
    except FileNotFoundError:
        print(f"[dict] Файл {path} не найден — брутфорс будет грубым")

load_dictionary()


# ================== БАЗОВЫЕ РОУТЫ ==================

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

    result = re.sub(r"\d+", replace_token, text)
    return jsonify({"result": result})


# ================== БРУТФОРС ==================

def score_text(mapping, tokens):
    """
    Оцениваем качество mapping:
    - Собираем текст
    - Разбиваем на слова (по числу-пробелу)
    - Считаем, сколько слов из 2+ букв есть в словаре
    - Возвращаем: (кол-во слов в словаре, кол-во уникальных слов, длина текста буквами)
    """
    # Определяем, какое число = пробел (то, которое mapping[tok] == ' ')
    space_tok = None
    for k, v in mapping.items():
        if v == ' ':
            space_tok = k
            break
    if space_tok is None:
        return (0, 0, 0)

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

    good = 0
    unique = set()
    for w in words:
        if len(w) >= 2:
            unique.add(w)
            if w in WORDS:
                good += 1

    return (good, len(unique), len(words))


def brute_force(tokens, time_limit=8.0):
    """
    Имитация отжига / жадный подъём.
    Перебираем буквы для каждого числа, оставляем улучшения.
    """
    start = time.time()

    # Уникальные числа
    unique_toks = sorted(set(tokens), key=lambda t: int(t))
    if len(unique_toks) > 33:
        unique_toks = unique_toks[:33]

    # Начальное приближение: по частоте
    freq = Counter(tokens)
    sorted_by_freq = sorted(unique_toks, key=lambda t: -freq[t])

    # Пробел — самое частое число (обычно это 01, но проверим гипотезу через частоту)
    # Ставим пробел на самое частое
    best_mapping = {}
    letters = list(RU_FREQ)
    for i, tok in enumerate(sorted_by_freq):
        if i < len(letters):
            best_mapping[tok] = letters[i]

    # Оценка
    best_score = score_text(best_mapping, tokens)[0]
    best_result = dict(best_mapping)

    # Локальный поиск
    improvements = 0
    letters_pool = list(RU_FREQ)
    while time.time() - start < time_limit:
        # Случайно выбираем: поменять букву у одного числа
        # или поменять буквы двух чисел местами
        mode = random.choice(["swap", "reassign"])

        candidate = dict(best_result)

        if mode == "swap":
            a, b = random.sample(unique_toks, 2)
            candidate[a], candidate[b] = candidate.get(b, '?'), candidate.get(a, '?')
        else:  # reassign
            tok = random.choice(unique_toks)
            candidate[tok] = random.choice(letters_pool)

        sc = score_text(candidate, tokens)[0]
        if sc > best_score:
            best_score = sc
            best_result = candidate
            improvements += 1

    good, unique_w, total_w = score_text(best_result, tokens)
    return {
        "mapping": best_result,
        "score": good,
        "unique_words": unique_w,
        "total_words": total_w,
        "improvements": improvements,
        "dict_size": len(WORDS),
        "elapsed": round(time.time() - start, 2),
    }


@app.route("/bruteforce", methods=["POST"])
def bruteforce():
    data = request.get_json()
    text = data.get("text", "")
    time_limit = float(data.get("time_limit", 8.0))
    time_limit = min(max(time_limit, 2.0), 30.0)  # 2..30 сек

    tokens = re.findall(r"\d+", text)
    if not tokens:
        return jsonify({"error": "Нет чисел в тексте"})

    result = brute_force(tokens, time_limit=time_limit)

    # Расшифрованный текст
    def replace_token(match):
        tok = match.group(0)
        return result["mapping"].get(tok, f"[{tok}]")

    result["decoded"] = re.sub(r"\d+", replace_token, text)
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)