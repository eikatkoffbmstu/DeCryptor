from flask import Flask, render_template, request, jsonify
from collections import Counter
import re

app = Flask(__name__)

# Частоты букв русского языка (по убыванию)
RU_FREQ = "оеаинтсрвлкмдпуяыьгзбчйхжшюцщэфъё"
EN_FREQ = "etaoinshrdlucmfwypvbgkjqxz"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    text = data.get("text", "")

    # Достаём все числа (с ведущими нулями), игнорируем знаки препинания
    tokens = re.findall(r"\d+", text)
    counter = Counter(tokens)

    # Сортируем числа: сначала по частоте (убыв), потом по числовому значению
    sorted_tokens = sorted(counter.keys(), key=lambda t: (-counter[t], int(t)))

    # Черновое сопоставление по частоте с русскими буквами
    suggestion = {}
    for i, tok in enumerate(sorted_tokens):
        if i < len(RU_FREQ):
            suggestion[tok] = RU_FREQ[i]
        else:
            suggestion[tok] = "?"

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
    mapping = data.get("mapping", {})  # {"01": " ", "20": "и", ...}

    # Заменяем числа на буквы, сохраняя пробелы/точки/переносы как есть
    def replace_token(match):
        tok = match.group(0)
        return mapping.get(tok, f"[{tok}]")

    # Проходим по тексту: числа -> буквы, остальное (пробелы, точки) оставляем
    result = re.sub(r"\d+", replace_token, text)
    return jsonify({"result": result})


if __name__ == "__main__":
    app.run(debug=True)