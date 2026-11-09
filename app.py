import os
import sqlite3
from flask import Flask, g, session, redirect, request, render_template, url_for, flash, abort

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("TRAJECT_DB", os.path.join(APP_DIR, "traject.db"))

app = Flask(__name__)
app.secret_key = "traject-design-dev-key"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = lambda cursor, row: {d[0]: v for d, v in zip(cursor.description, row)}
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def init_db(seed=False):
    db = sqlite3.connect(DB_PATH)
    with open(os.path.join(APP_DIR, "schema.sql"), encoding="utf-8") as f:
        db.executescript(f.read())
    if seed:
        _seed(db)
    db.commit()
    db.close()


def _seed(db):
    if db.execute("SELECT COUNT(*) FROM gebruiker").fetchone()[0] > 0:
        return
    db.executemany(
        "INSERT INTO gebruiker (naam, rol) VALUES (?, ?)",
        [
            ("Anne Onderwijsontwerper", "ontwerper"),
            ("Bert Docent", "docent"),
            ("Sanne Student", "student"),
            ("Joris Student", "student"),
        ],
    )
    cur = db.execute(
        "INSERT INTO traject (naam, omschrijving) VALUES (?, ?)",
        ("Mbo-ICT leertraject (demo)", "Voorbeeldleertraject met modules, onderwijsproducten en leerdoelen."),
    )
    traject_id = cur.lastrowid
    db.execute(
        "INSERT INTO traject_deelnemer (traject_id, student_id) SELECT ?, id FROM gebruiker WHERE rol = 'student'",
        (traject_id,),
    )

    def add_module(naam, omschrijving, max_sbu, behaalregel, drempel, modus):
        cur = db.execute(
            "INSERT INTO module (traject_id, naam, omschrijving, max_sbu, behaalregel, drempel_percentage, afhankelijkheid_modus) "
            "VALUES (?,?,?,?,?,?,?)",
            (traject_id, naam, omschrijving, max_sbu, behaalregel, drempel, modus),
        )
        return cur.lastrowid

    m1 = add_module("Basis programmeren", "Grondslagen van programmeren", 60, "percentage", 80, "alle")
    m2 = add_module("Databases", "Ontwerp en gebruik van databases", 40, "percentage", 75, "alle")
    m3 = add_module("Webdevelopment", "Frontend en backend basics", 80, "doelen", 0, "minstens_een")
    db.executemany(
        "INSERT INTO module_afhankelijkheid (module_id, vereist_module_id) VALUES (?,?)",
        [(m2, m1), (m3, m1), (m3, m2)],
    )

    md1 = db.execute(
        "INSERT INTO module_doel (module_id, soort, omschrijving) VALUES (?,?,?)",
        (m1, "leerdoel", "De student kan een programma lezen en uitleggen"),
    ).lastrowid
    md2 = db.execute(
        "INSERT INTO module_doel (module_id, soort, omschrijving) VALUES (?,?,?)",
        (m1, "leeruitkomst", "De student bouwt een werkend consoleprogramma"),
    ).lastrowid
    db.execute(
        "INSERT INTO module_doel (module_id, soort, omschrijving) VALUES (?,?,?)",
        (m2, "leeruitkomst", "De student normaliseert een datamodel tot 3NF"),
    )
    db.execute(
        "INSERT INTO module_doel (module_id, soort, omschrijving) VALUES (?,?,?)",
        (m3, "leerdoel", "De student kent de principes van HTTP en REST"),
    )
    db.execute(
        "INSERT INTO module_doel (module_id, soort, omschrijving) VALUES (?,?,?)",
        (m3, "leeruitkomst", "De student levert een werkende webapplicatie op"),
    )

    p1 = db.execute(
        "INSERT INTO onderwijsproduct (module_id, naam, omschrijving, sbu) VALUES (?,?,?,?)",
        (m1, "Les 1: variabelen en types", "Inleiding met opdrachten", 10),
    ).lastrowid
    p2 = db.execute(
        "INSERT INTO onderwijsproduct (module_id, naam, omschrijving, sbu) VALUES (?,?,?,?)",
        (m1, "Les 2: condities en loops", "Praktijkopdracht", 15),
    ).lastrowid
    p3 = db.execute(
        "INSERT INTO onderwijsproduct (module_id, naam, omschrijving, sbu) VALUES (?,?,?,?)",
        (m1, "Project: consoleapplicatie", "Afsluitend project", 25),
    ).lastrowid
    db.execute(
        "INSERT INTO product_doel (product_id, soort, omschrijving, module_doel_id) VALUES (?,?,?,?)",
        (p1, "leerdoel", "De student benoemt datatypes correct", md1),
    )
    db.execute(
        "INSERT INTO product_doel (product_id, soort, omschrijving, module_doel_id) VALUES (?,?,?,?)",
        (p3, "leeruitkomst", "De student levert een werkend consoleprogramma op", md2),
    )


# ---------- bedrijfslogica ----------

def product_voldoende(beoordeling, module):
    return beoordeling is not None and beoordeling["cijfer"] >= module["voldoende_cijfer"]


def module_status(module, student_id=None):
    """Berekent de status van een module: niet_gestart / bezig / behaald / geblokkeerd."""
    db_mod = module
    vereisten = query(
        "SELECT m.* FROM module_afhankelijkheid a JOIN module m ON m.id = a.vereist_module_id WHERE a.module_id = ?",
        (module["id"],),
    )
    if student_id is not None and vereisten:
        behaalde = {v["id"] for v in vereisten if module_status(v, student_id) == "behaald"}
        if db_mod["afhankelijkheid_modus"] == "alle":
            open_vereisten = [v for v in vereisten if v["id"] not in behaalde]
        else:
            open_vereisten = vereisten if not behaalde else []
        if open_vereisten:
            return "geblokkeerd"

    if student_id is None:
        return "niet_gestart"

    producten = query("SELECT * FROM onderwijsproduct WHERE module_id = ?", (module["id"],))
    beoordelingen = {
        b["product_id"]: b
        for b in query("SELECT * FROM beoordeling WHERE student_id = ?", (student_id,))
    }

    if db_mod["behaalregel"] == "doelen":
        doelen = query("SELECT id FROM module_doel WHERE module_id = ?", (module["id"],))
        if doelen:
            voldoende_doelen = {
                r["module_doel_id"]
                for r in query(
                    "SELECT module_doel_id FROM module_doel_beoordeling "
                    "WHERE student_id = ? AND voldoende = 1",
                    (student_id,),
                )
            }
            if all(d["id"] in voldoende_doelen for d in doelen):
                return "behaald"
        else:
            return "niet_gestart"
    else:
        if not producten:
            return "niet_gestart"
        voldoende_count = sum(
            1 for p in producten if product_voldoende(beoordelingen.get(p["id"]), db_mod)
        )
        if 100 * voldoende_count / len(producten) >= db_mod["drempel_percentage"]:
            return "behaald"

    heeft_resultaat = any(p["id"] in beoordelingen for p in producten)
    if db_mod["behaalregel"] == "doelen":
        heeft_resultaat = heeft_resultaat or query(
            "SELECT 1 FROM module_doel_beoordeling mdb "
            "JOIN module_doel md ON md.id = mdb.module_doel_id "
            "WHERE mdb.student_id = ? AND md.module_id = ? LIMIT 1",
            (student_id, module["id"]),
            one=True,
        )
    return "bezig" if heeft_resultaat else "niet_gestart"


STATUS_LABEL = {
    "niet_gestart": "Niet gestart",
    "bezig": "Bezig",
    "behaald": "Behaald",
    "geblokkeerd": "Geblokkeerd",
}


def module_sbu_info(module_id):
    """Som van SBU van onderwijsproducten en max SBU van de module."""
    max_sbu = query("SELECT max_sbu FROM module WHERE id = ?", (module_id,), one=True)["max_sbu"]
    totaal = query(
        "SELECT COALESCE(SUM(sbu), 0) AS s FROM onderwijsproduct WHERE module_id = ?", (module_id,), one=True
    )["s"]
    return totaal, max_sbu, totaal > max_sbu


def traject_graf(traject_id, student_id=None):
    """Modules met status en layout (laag op langste pad van vereisten)."""
    modules = query("SELECT * FROM module WHERE traject_id = ?", (traject_id,))
    ids = [m["id"] for m in modules]
    afh = {m["id"]: [] for m in modules}
    if ids:
        for row in query(
            f"SELECT module_id, vereist_module_id FROM module_afhankelijkheid WHERE module_id IN ({','.join('?'*len(ids))})",
            ids,
        ):
            afh[row["module_id"]].append(row["vereist_module_id"])

    diepte = {}

    def bereken(mid, bezocht):
        if mid in diepte:
            return diepte[mid]
        if mid in bezocht:
            return 0
        vereisten = afh.get(mid, [])
        if not vereisten:
            diepte[mid] = 0
        else:
            diepte[mid] = 1 + max(bereken(v, bezocht | {mid}) for v in vereisten)
        return diepte[mid]

    for m in modules:
        bereken(m["id"], set())

    nodes = []
    for m in modules:
        totaal, max_sbu, overschreden = module_sbu_info(m["id"])
        nodes.append(
            {
                "module": m,
                "diepte": diepte[m["id"]],
                "status": STATUS_LABEL[module_status(m, student_id)] if student_id else None,
                "status_key": module_status(m, student_id) if student_id else None,
                "vereisten": afh[m["id"]],
                "sbu_totaal": totaal,
                "max_sbu": max_sbu,
                "sbu_overschreden": overschreden,
            }
        )
    return nodes


# ---------- sessie / login ----------

@app.before_request
def check_gebruiker():
    if request.endpoint in ("static", "login"):
        return
    if not session.get("gebruiker_id"):
        return redirect(url_for("login"))
    g.gebruiker = query("SELECT * FROM gebruiker WHERE id = ?", (session["gebruiker_id"],), one=True)
    if g.gebruiker is None:
        session.clear()
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    gebruikers = query("SELECT * FROM gebruiker ORDER BY rol, naam")
    if request.method == "POST":
        g_id = request.form.get("gebruiker_id", type=int)
        gebruiker = query("SELECT * FROM gebruiker WHERE id = ?", (g_id,), one=True)
        if gebruiker:
            session["gebruiker_id"] = gebruiker["id"]
            return redirect(url_for("index"))
        flash("Onbekende gebruiker.")
    return render_template("login.html", gebruikers=gebruikers)


@app.route("/uitloggen")
def uitloggen():
    session.clear()
    return redirect(url_for("login"))


# ---------- ontwerper: trajecten ----------

@app.route("/")
def index():
    trajecten = query("SELECT * FROM traject ORDER BY naam")
    data = []
    for t in trajecten:
        n_modules = query("SELECT COUNT(*) AS c FROM module WHERE traject_id = ?", (t["id"],), one=True)["c"]
        data.append({"traject": t, "aantal_modules": n_modules})
    return render_template("index.html", trajecten=data)


@app.route("/traject/nieuw", methods=["POST"])
def traject_nieuw():
    naam = request.form.get("naam", "").strip()
    if naam:
        t_id = execute("INSERT INTO traject (naam, omschrijving) VALUES (?,?)",
                       (naam, request.form.get("omschrijving", "").strip()))
        return redirect(url_for("traject_detail", traject_id=t_id))
    flash("Vul een naam in.")
    return redirect(url_for("index"))


@app.route("/traject/<int:traject_id>")
def traject_detail(traject_id):
    traject = query("SELECT * FROM traject WHERE id = ?", (traject_id,), one=True)
    if not traject:
        abort(404)
    nodes = traject_graf(traject_id)
    nodes.sort(key=lambda n: n["diepte"])
    modules_index = {m["id"]: m for m in query("SELECT * FROM module WHERE traject_id = ?", (traject_id,))}
    deelnemers = query(
        "SELECT g.* FROM traject_deelnemer d JOIN gebruiker g ON g.id = d.student_id WHERE d.traject_id = ? ORDER BY g.naam",
        (traject_id,),
    )
    alle_studenten = query("SELECT * FROM gebruiker WHERE rol = 'student' ORDER BY naam")
    return render_template("traject.html", traject=traject, nodes=nodes, modules_index=modules_index,
                           deelnemers=deelnemers, alle_studenten=alle_studenten)


@app.route("/traject/<int:traject_id>/update", methods=["POST"])
def traject_update(traject_id):
    execute("UPDATE traject SET naam = ?, omschrijving = ? WHERE id = ?",
            (request.form.get("naam", "").strip(), request.form.get("omschrijving", "").strip(), traject_id))
    return redirect(url_for("traject_detail", traject_id=traject_id))


@app.route("/traject/<int:traject_id>/verwijder", methods=["POST"])
def traject_verwijder(traject_id):
    execute("DELETE FROM traject WHERE id = ?", (traject_id,))
    return redirect(url_for("index"))


@app.route("/traject/<int:traject_id>/deelnemer", methods=["POST"])
def traject_deelnemer_toevoegen(traject_id):
    student_id = request.form.get("student_id", type=int)
    if student_id:
        execute("INSERT OR IGNORE INTO traject_deelnemer (traject_id, student_id) VALUES (?,?)",
                (traject_id, student_id))
    return redirect(url_for("traject_detail", traject_id=traject_id))


@app.route("/traject/<int:traject_id>/deelnemer/<int:student_id>/verwijder", methods=["POST"])
def traject_deelnemer_verwijder(traject_id, student_id):
    execute("DELETE FROM traject_deelnemer WHERE traject_id = ? AND student_id = ?", (traject_id, student_id))
    return redirect(url_for("traject_detail", traject_id=traject_id))


@app.route("/traject/<int:traject_id>/module/nieuw", methods=["POST"])
def module_nieuw(traject_id):
    naam = request.form.get("naam", "").strip()
    if not naam:
        flash("Vul een modulenaam in.")
        return redirect(url_for("traject_detail", traject_id=traject_id))
    m_id = execute(
        "INSERT INTO module (traject_id, naam, omschrijving, max_sbu, behaalregel, drempel_percentage, voldoende_cijfer, afhankelijkheid_modus) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (traject_id, naam, request.form.get("omschrijving", "").strip(),
         request.form.get("max_sbu", 0, type=float),
         request.form.get("behaalregel", "percentage"),
         request.form.get("drempel_percentage", 80, type=int),
         request.form.get("voldoende_cijfer", 5.5, type=float),
         request.form.get("afhankelijkheid_modus", "alle")),
    )
    return redirect(url_for("module_detail", module_id=m_id))


# ---------- ontwerper: module ----------

@app.route("/module/<int:module_id>")
def module_detail(module_id):
    module = query("SELECT * FROM module WHERE id = ?", (module_id,), one=True)
    if not module:
        abort(404)
    traject = query("SELECT * FROM traject WHERE id = ?", (module["traject_id"],), one=True)
    doelen = query("SELECT * FROM module_doel WHERE module_id = ? ORDER BY soort, omschrijving", (module_id,))
    producten = query("SELECT * FROM onderwijsproduct WHERE module_id = ? ORDER BY naam", (module_id,))
    for p in producten:
        p_doelen = query("SELECT * FROM product_doel WHERE product_id = ? ORDER BY soort, omschrijving", (p["id"],))
        p["doelen"] = p_doelen
    afh = query(
        "SELECT m.* FROM module_afhankelijkheid a JOIN module m ON m.id = a.vereist_module_id WHERE a.module_id = ?",
        (module_id,),
    )
    andere_modules = query(
        "SELECT * FROM module WHERE traject_id = ? AND id <> ? ORDER BY naam",
        (module["traject_id"], module_id),
    )
    sbu_totaal, max_sbu, overschreden = module_sbu_info(module_id)
    return render_template("module.html", module=module, traject=traject, doelen=doelen,
                           producten=producten, afhankelijkheden=afh, andere_modules=andere_modules,
                           sbu_totaal=sbu_totaal, sbu_overschreden=overschreden)


@app.route("/module/<int:module_id>/update", methods=["POST"])
def module_update(module_id):
    execute(
        "UPDATE module SET naam = ?, omschrijving = ?, max_sbu = ?, behaalregel = ?, drempel_percentage = ?, voldoende_cijfer = ?, afhankelijkheid_modus = ? WHERE id = ?",
        (request.form.get("naam", "").strip(), request.form.get("omschrijving", "").strip(),
         request.form.get("max_sbu", 0, type=float), request.form.get("behaalregel", "percentage"),
         request.form.get("drempel_percentage", 80, type=int),
         request.form.get("voldoende_cijfer", 5.5, type=float),
         request.form.get("afhankelijkheid_modus", "alle"), module_id),
    )
    return redirect(url_for("module_detail", module_id=module_id))


@app.route("/module/<int:module_id>/verwijder", methods=["POST"])
def module_verwijder(module_id):
    traject_id = query("SELECT traject_id FROM module WHERE id = ?", (module_id,), one=True)["traject_id"]
    execute("DELETE FROM module WHERE id = ?", (module_id,))
    return redirect(url_for("traject_detail", traject_id=traject_id))


@app.route("/module/<int:module_id>/doel/nieuw", methods=["POST"])
def module_doel_nieuw(module_id):
    omschrijving = request.form.get("omschrijving", "").strip()
    soort = request.form.get("soort", "leerdoel")
    if omschrijving:
        execute("INSERT INTO module_doel (module_id, soort, omschrijving) VALUES (?,?,?)",
                (module_id, soort, omschrijving))
    return redirect(url_for("module_detail", module_id=module_id))


@app.route("/module/doel/<int:doel_id>/verwijder", methods=["POST"])
def module_doel_verwijder(doel_id):
    module_id = query("SELECT module_id FROM module_doel WHERE id = ?", (doel_id,), one=True)["module_id"]
    execute("DELETE FROM module_doel WHERE id = ?", (doel_id,))
    return redirect(url_for("module_detail", module_id=module_id))


@app.route("/module/<int:module_id>/afhankelijkheid/nieuw", methods=["POST"])
def module_afhankelijkheid_nieuw(module_id):
    vereist = request.form.get("vereist_module_id", type=int)
    if vereist and vereist != module_id:
        execute("INSERT OR IGNORE INTO module_afhankelijkheid (module_id, vereist_module_id) VALUES (?,?)",
                (module_id, vereist))
    return redirect(url_for("module_detail", module_id=module_id))


@app.route("/module/<int:module_id>/afhankelijkheid/<int:vereist_id>/verwijder", methods=["POST"])
def module_afhankelijkheid_verwijder(module_id, vereist_id):
    execute("DELETE FROM module_afhankelijkheid WHERE module_id = ? AND vereist_module_id = ?",
            (module_id, vereist_id))
    return redirect(url_for("module_detail", module_id=module_id))


# ---------- ontwerper: onderwijsproduct ----------

@app.route("/module/<int:module_id>/product/nieuw", methods=["POST"])
def product_nieuw(module_id):
    naam = request.form.get("naam", "").strip()
    if naam:
        execute("INSERT INTO onderwijsproduct (module_id, naam, omschrijving, sbu) VALUES (?,?,?,?)",
                (module_id, naam, request.form.get("omschrijving", "").strip(),
                 request.form.get("sbu", 0, type=float)))
    return redirect(url_for("module_detail", module_id=module_id))


@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = query("SELECT * FROM onderwijsproduct WHERE id = ?", (product_id,), one=True)
    if not product:
        abort(404)
    module = query("SELECT * FROM module WHERE id = ?", (product["module_id"],), one=True)
    traject = query("SELECT * FROM traject WHERE id = ?", (module["traject_id"],), one=True)
    doelen = query("SELECT pd.*, md.omschrijving AS module_doel_omschrijving, md.soort AS module_doel_soort "
                   "FROM product_doel pd LEFT JOIN module_doel md ON md.id = pd.module_doel_id "
                   "WHERE pd.product_id = ? ORDER BY pd.soort, pd.omschrijving", (product_id,))
    module_doelen = query("SELECT * FROM module_doel WHERE module_id = ? ORDER BY soort, omschrijving", (module["id"],))
    return render_template("product.html", product=product, module=module, traject=traject,
                           doelen=doelen, module_doelen=module_doelen)


@app.route("/product/<int:product_id>/update", methods=["POST"])
def product_update(product_id):
    execute("UPDATE onderwijsproduct SET naam = ?, omschrijving = ?, sbu = ? WHERE id = ?",
            (request.form.get("naam", "").strip(), request.form.get("omschrijving", "").strip(),
             request.form.get("sbu", 0, type=float), product_id))
    return redirect(url_for("product_detail", product_id=product_id))


@app.route("/product/<int:product_id>/verwijder", methods=["POST"])
def product_verwijder(product_id):
    module_id = query("SELECT module_id FROM onderwijsproduct WHERE id = ?", (product_id,), one=True)["module_id"]
    execute("DELETE FROM onderwijsproduct WHERE id = ?", (product_id,))
    return redirect(url_for("module_detail", module_id=module_id))


@app.route("/product/<int:product_id>/doel/nieuw", methods=["POST"])
def product_doel_nieuw(product_id):
    omschrijving = request.form.get("omschrijving", "").strip()
    if omschrijving:
        koppeling = request.form.get("module_doel_id", type=int)
        execute("INSERT INTO product_doel (product_id, soort, omschrijving, module_doel_id) VALUES (?,?,?,?)",
                (product_id, request.form.get("soort", "leerdoel"), omschrijving, koppeling))
    return redirect(url_for("product_detail", product_id=product_id))


@app.route("/product/doel/<int:doel_id>/verwijder", methods=["POST"])
def product_doel_verwijder(doel_id):
    product_id = query("SELECT product_id FROM product_doel WHERE id = ?", (doel_id,), one=True)["product_id"]
    execute("DELETE FROM product_doel WHERE id = ?", (doel_id,))
    return redirect(url_for("product_detail", product_id=product_id))


@app.route("/product/doel/<int:doel_id>/koppel", methods=["POST"])
def product_doel_koppel(doel_id):
    product_id = query("SELECT product_id FROM product_doel WHERE id = ?", (doel_id,), one=True)["product_id"]
    execute("UPDATE product_doel SET module_doel_id = ? WHERE id = ?",
            (request.form.get("module_doel_id", type=int), doel_id))
    return redirect(url_for("product_detail", product_id=product_id))


# ---------- docent: beoordelen ----------

@app.route("/docent")
def docent_overzicht():
    trajecten = query(
        "SELECT t.*, COUNT(DISTINCT d.student_id) AS aantal_studenten FROM traject t "
        "LEFT JOIN traject_deelnemer d ON d.traject_id = t.id GROUP BY t.id ORDER BY t.naam"
    )
    return render_template("docent.html", trajecten=trajecten)


@app.route("/docent/traject/<int:traject_id>")
def docent_traject(traject_id):
    traject = query("SELECT * FROM traject WHERE id = ?", (traject_id,), one=True)
    studenten = query(
        "SELECT g.* FROM traject_deelnemer d JOIN gebruiker g ON g.id = d.student_id WHERE d.traject_id = ? ORDER BY g.naam",
        (traject_id,),
    )
    for s in studenten:
        modules = query("SELECT * FROM module WHERE traject_id = ?", (traject_id,))
        s["overzicht"] = [(m["naam"], STATUS_LABEL[module_status(m, s["id"])]) for m in modules]
    return render_template("docent_traject.html", traject=traject, studenten=studenten)


@app.route("/docent/student/<int:student_id>/traject/<int:traject_id>")
def docent_beoordeel(student_id, traject_id):
    traject = query("SELECT * FROM traject WHERE id = ?", (traject_id,), one=True)
    student = query("SELECT * FROM gebruiker WHERE id = ?", (student_id,), one=True)
    modules = query("SELECT * FROM module WHERE traject_id = ? ORDER BY naam", (traject_id,))
    info = []
    for m in modules:
        producten = query("SELECT * FROM onderwijsproduct WHERE module_id = ? ORDER BY naam", (m["id"],))
        for p in producten:
            p["beoordeling"] = query(
                "SELECT * FROM beoordeling WHERE student_id = ? AND product_id = ?",
                (student_id, p["id"]), one=True,
            )
            p["doelen"] = query("SELECT * FROM product_doel WHERE product_id = ? ORDER BY soort, omschrijving", (p["id"],))
            for pd in p["doelen"]:
                pd["beoordeling"] = query(
                    "SELECT voldoende FROM product_doel_beoordeling WHERE student_id = ? AND product_doel_id = ?",
                    (student_id, pd["id"]), one=True,
                )
        m["doelen"] = query("SELECT * FROM module_doel WHERE module_id = ? ORDER BY soort, omschrijving", (m["id"],))
        for md in m["doelen"]:
            md["beoordeling"] = query(
                "SELECT voldoende FROM module_doel_beoordeling WHERE student_id = ? AND module_doel_id = ?",
                (student_id, md["id"]), one=True,
            )
        info.append({"module": m, "producten": producten, "status": STATUS_LABEL[module_status(m, student_id)]})
    return render_template("beoordeel.html", traject=traject, student=student, modules=info)


@app.route("/docent/beoordeling", methods=["POST"])
def beoordeling_opslaan():
    student_id = request.form.get("student_id", type=int)
    product_id = request.form.get("product_id", type=int)
    traject_id = request.form.get("traject_id", type=int)
    cijfer_raw = request.form.get("cijfer", "").strip().replace(",", ".")
    if cijfer_raw:
        cijfer = float(cijfer_raw)
        execute(
            "INSERT INTO beoordeling (student_id, product_id, cijfer, docent_id) VALUES (?,?,?,?) "
            "ON CONFLICT (student_id, product_id) DO UPDATE SET cijfer = excluded.cijfer, docent_id = excluded.docent_id, datum = excluded.datum",
            (student_id, product_id, cijfer, g.gebruiker["id"]),
        )
    else:
        execute("DELETE FROM beoordeling WHERE student_id = ? AND product_id = ?", (student_id, product_id))
    return redirect(url_for("docent_beoordeel", student_id=student_id, traject_id=traject_id))


@app.route("/docent/product-doel", methods=["POST"])
def product_doel_beoordelen():
    student_id = request.form.get("student_id", type=int)
    doel_id = request.form.get("product_doel_id", type=int)
    traject_id = request.form.get("traject_id", type=int)
    voldoende = 1 if request.form.get("voldoende") else 0
    execute(
        "INSERT INTO product_doel_beoordeling (student_id, product_doel_id, voldoende) VALUES (?,?,?) "
        "ON CONFLICT (student_id, product_doel_id) DO UPDATE SET voldoende = excluded.voldoende",
        (student_id, doel_id, voldoende),
    )
    return redirect(url_for("docent_beoordeel", student_id=student_id, traject_id=traject_id))


@app.route("/docent/module-doel", methods=["POST"])
def module_doel_beoordelen():
    student_id = request.form.get("student_id", type=int)
    doel_id = request.form.get("module_doel_id", type=int)
    traject_id = request.form.get("traject_id", type=int)
    voldoende = 1 if request.form.get("voldoende") else 0
    execute(
        "INSERT INTO module_doel_beoordeling (student_id, module_doel_id, voldoende) VALUES (?,?,?) "
        "ON CONFLICT (student_id, module_doel_id) DO UPDATE SET voldoende = excluded.voldoende",
        (student_id, doel_id, voldoende),
    )
    return redirect(url_for("docent_beoordeel", student_id=student_id, traject_id=traject_id))


# ---------- student ----------

@app.route("/mijn")
def student_trajecten():
    trajecten = query(
        "SELECT t.* FROM traject_deelnemer d JOIN traject t ON t.id = d.traject_id WHERE d.student_id = ? ORDER BY t.naam",
        (g.gebruiker["id"],),
    )
    return render_template("student_trajecten.html", trajecten=trajecten)


@app.route("/mijn/traject/<int:traject_id>")
def student_traject_detail(traject_id):
    traject = query("SELECT * FROM traject WHERE id = ?", (traject_id,), one=True)
    deelnemer = query("SELECT 1 FROM traject_deelnemer WHERE traject_id = ? AND student_id = ?",
                      (traject_id, g.gebruiker["id"]), one=True)
    if not deelnemer and g.gebruiker["rol"] != "ontwerper":
        abort(403)
    nodes = traject_graf(traject_id, g.gebruiker["id"])
    nodes.sort(key=lambda n: n["diepte"])
    modules_index = {m["id"]: m for m in query("SELECT * FROM module WHERE traject_id = ?", (traject_id,))}
    modules = []
    for n in nodes:
        m = n["module"]
        producten = query("SELECT * FROM onderwijsproduct WHERE module_id = ? ORDER BY naam", (m["id"],))
        for p in producten:
            p["beoordeling"] = query(
                "SELECT * FROM beoordeling WHERE student_id = ? AND product_id = ?",
                (g.gebruiker["id"], p["id"]), one=True,
            )
        modules.append({"node": n, "producten": producten})
    return render_template("student_traject.html", traject=traject, modules=modules, modules_index=modules_index)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db(seed=True)
    app.run(host=os.environ.get("HOST", "0.0.0.0"), debug=bool(os.environ.get("DEBUG")), port=int(os.environ.get("PORT", 5000)))
