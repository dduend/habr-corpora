import sqlite3
from flask import Flask, render_template, request, redirect, session
from database_search import ProcessingUserRequest, GettingDataFromDB


app = Flask(__name__)
app.secret_key = 'секретик'


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/help")
def help_page():
    return render_template("help.html")


@app.route("/results", methods=["GET"])
def results_page():
    if not request.args:
        return redirect("/")

    path_to_db = "habr_corpus.db"
    q = request.args.get("query")

    if q:
        conn = sqlite3.connect(path_to_db)
        my = ProcessingUserRequest(q)
        new_q = my.process_query()

        if type(new_q) == str:
            error = new_q
            results = ""
        else:
            data = GettingDataFromDB(new_q, conn)
            ids = data.get_sentences_idxs()
            results = data.get_sentences_text_with_metainfo(ids)
            error = ""

    else:
        results = ""
        error = ""

    return render_template("results.html", query=q, results=results, error=error)


@app.route("/clear_results")
def clear_results():
    # очищаем результаты из сессии
    session.pop("results", None)
    session.pop("error", None)
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)
