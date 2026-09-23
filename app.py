from flask import Flask, render_template, request, jsonify
from collections import Counter
import re

app = Flask(__name__)

# Частоты букв в русском языке (в порядке убывания, примерно)
RU_FREQ = "оеаинтсрвлкмдпуяызьгбчйхжшюцщэфъ"
# Английский вариант
EN_FREQ = "etaoinshrdlucmfwypvbgkjqxz"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    text = data.get("text", "")
    lang = data.get("lang", "ru")

    # Считаем частоты цифр и пробелов
    symbols = re.findall(r"[0-9 ]", text)
    counter = Counter(symbols)

    freq_order = RU_FREQ if lang == "ru" else EN_FREQ

    # Сортируем символы по частоте (по убыванию)
    sorted_symbols = [s for s, _ in counter.most_common()]

    # Черновое сопоставление: самый частый символ -> самая частая буква
    suggestion = {}
    for i, sym in enumerate(sorted_symbols):
        if i < len(freq_order):
            suggestion[sym] = freq_order[i]
        else:
            suggestion[sym] = "?"

    return jsonify({
        "counts": dict(counter),
        "sorted_symbols": sorted_symbols,
        "suggestion": suggestion
    })


@app.route("/decode", methods=["POST"])
def decode():
    data = request.get_json()
    text = data.get("text", "")
    mapping = data.get("mapping", {})  # {"0": "о", "1": "е", ...}

    result = []
    for ch in text:
        if ch in mapping and mapping[ch]:
            result.append(mapping[ch])
        else:
            result.append(ch)
    return jsonify({"result": "".join(result)})


if __name__ == "__main__":
    app.run(debug=True)