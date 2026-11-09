"""Automatische tests voor de kernregels van TrajectDesign.

Uitvoeren:  python test_regels.py  (of: python -m pytest test_regels.py)
Elke test gebruikt een verse, tijdelijke database met demogegevens.
"""
import os
import tempfile
import unittest

import app as traject_app


class TrajectTestCase(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        traject_app.DB_PATH = self.db_path
        traject_app.init_db(seed=True)
        self.client = traject_app.app.test_client()
        self.client.set_env = None  # expliciet: geen env-afhankelijkheid

    def login(self, gebruiker_id):
        r = self.client.post("/login", data={"gebruiker_id": gebruiker_id}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

    def sql(self, q, args=()):
        import sqlite3
        db = sqlite3.connect(self.db_path)
        db.row_factory = lambda c, row: {d[0]: v for d, v in zip(c.description, row)}
        out = db.execute(q, args).fetchall()
        db.commit()
        db.close()
        return out

    # ---------- basis ----------

    def test_login_en_rollen(self):
        self.assertEqual(self.client.get("/").status_code, 302)  # redirect naar /login
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.login(1)  # ontwerper
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertIn(b"Leertrajecten", self.client.get("/").data)

    def test_seed_data_aanwezig(self):
        self.assertGreaterEqual(len(self.sql("SELECT * FROM traject")), 1)
        self.assertGreaterEqual(len(self.sql("SELECT * FROM module")), 3)
        self.assertGreaterEqual(len(self.sql("SELECT * FROM onderwijsproduct")), 3)
        self.assertGreaterEqual(len(self.sql("SELECT * FROM module_doel")), 5)

    # ---------- ontwerper: opslag ----------

    def test_module_en_product_opslag_en_persistentie(self):
        self.login(1)
        r = self.client.post("/traject/1/module/nieuw", data={
            "naam": "Nettestmodule", "max_sbu": "30", "behaalregel": "doelen",
            "drempel_percentage": "70", "voldoende_cijfer": "6.0",
            "afhankelijkheid_modus": "minstens_een"}, follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        mod = self.sql("SELECT * FROM module WHERE naam = 'Nettestmodule'")
        self.assertEqual(len(mod), 1)
        mid = mod[0]["id"]
        self.client.post(f"/module/{mid}/product/nieuw", data={"naam": "Les A", "sbu": "12"}, follow_redirects=True)
        self.client.post(f"/module/{mid}/doel/nieuw", data={"soort": "leerdoel", "omschrijving": "Doel X"}, follow_redirects=True)
        # persistentie: opnieuw lezen via nieuwe verbinding
        rows = self.sql("SELECT * FROM onderwijsproduct WHERE module_id = ?", (mid,))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sbu"], 12.0)
        self.assertEqual(len(self.sql("SELECT * FROM module_doel WHERE module_id = ?", (mid,))), 1)

    def test_sbu_waarschuwing_bij_overschrijding(self):
        self.login(1)
        self.client.post("/traject/1/module/nieuw", data={"naam": "SBUmod", "max_sbu": "10"},
                         follow_redirects=True)
        mid = self.sql("SELECT id FROM module WHERE naam = 'SBUmod'")[0]["id"]
        self.client.post(f"/module/{mid}/product/nieuw", data={"naam": "Grote les", "sbu": "25"},
                         follow_redirects=True)
        r = self.client.get(f"/module/{mid}")
        self.assertIn(b"overschrijden de maximale SBU", r.data)
        r = self.client.get("/traject/1")
        self.assertIn(b"maximale SBU overschreden", r.data)

    def test_product_doel_koppeling_aan_module_doel(self):
        self.login(1)
        pd = self.sql("SELECT * FROM product_doel WHERE module_doel_id IS NOT NULL")
        self.assertGreaterEqual(len(pd), 1)
        # koppeling verbreken en opnieuw zetten
        pid = pd[0]["id"]
        self.client.post(f"/product/doel/{pid}/koppel", data={"module_doel_id": ""})
        self.assertIsNone(self.sql("SELECT module_doel_id FROM product_doel WHERE id = ?", (pid,))[0]["module_doel_id"])
        md_id = self.sql("SELECT id FROM module_doel LIMIT 1")[0]["id"]
        self.client.post(f"/product/doel/{pid}/koppel", data={"module_doel_id": str(md_id)})
        self.assertEqual(self.sql("SELECT module_doel_id FROM product_doel WHERE id = ?", (pid,))[0]["module_doel_id"], md_id)

    # ---------- behaalregels ----------

    def test_behaalregel_percentage(self):
        # module 1: 80% van 3 producten voldoende, cijfer >= 5.5
        self.login(2)  # docent
        for pid, cijfer in ((1, "8.0"), (2, "6.0"), (3, "4.0")):
            self.client.post("/docent/beoordeling", data={
                "student_id": 3, "product_id": pid, "traject_id": 1, "cijfer": cijfer})
        self.login(3)  # student
        html = self.client.get("/mijn/traject/1").data.decode()
        self.assertIn("s-bezig", html)  # 2 van 3 = 67% < 80% drempel
        self.assertNotIn(">Behaald<", html)
        self.login(2)
        self.client.post("/docent/beoordeling", data={
            "student_id": 3, "product_id": 3, "traject_id": 1, "cijfer": "5.5"})
        self.login(3)
        html = self.client.get("/mijn/traject/1").data.decode()
        self.assertIn(">Behaald<", html)

    def test_behaalregel_doelen_productresultaten_tellen_niet_mee(self):
        # module 3: behaalregel 'doelen', vereist module 1 (behaald via percentage)
        self.login(2)
        for pid, cijfer in ((1, "8.0"), (2, "6.0"), (3, "6.0")):
            self.client.post("/docent/beoordeling", data={
                "student_id": 3, "product_id": pid, "traject_id": 1, "cijfer": cijfer})
        # module 3 heeft geen productresultaten; doelen 4 en 5 markeren als voldoende
        for did in (4, 5):
            self.client.post("/docent/module-doel", data={
                "student_id": 3, "module_doel_id": did, "traject_id": 1, "voldoende": "on"})
        self.login(3)
        html = self.client.get("/mijn/traject/1").data.decode()
        self.assertIn(">Behaald<", html)

    def test_onvoldoende_doelen_geen_behaling(self):
        self.login(2)
        self.client.post("/docent/module-doel", data={
            "student_id": 3, "module_doel_id": 4, "traject_id": 1, "voldoende": "on"})
        self.login(3)
        html = self.client.get("/mijn/traject/1").data.decode()
        self.assertNotIn(">Behaald<", html)

    # ---------- afhankelijkheden ----------

    def test_vereisten_blokkeren_module(self):
        self.login(3)
        html = self.client.get("/mijn/traject/1").data.decode()
        self.assertIn("s-geblokkeerd", html)

    def test_vereisten_worden_geopend_na_behaling(self):
        self.login(2)
        for pid, cijfer in ((1, "8.0"), (2, "6.0"), (3, "6.0")):
            self.client.post("/docent/beoordeling", data={
                "student_id": 3, "product_id": pid, "traject_id": 1, "cijfer": cijfer})
        self.login(3)
        html = self.client.get("/mijn/traject/1").data.decode()
        self.assertNotIn("s-geblokkeerd", html)

    def test_minstens_een_afhankelijkheid(self):
        # module 3 vereist module 1 en 2 met modus 'minstens_een'
        self.login(2)
        # alleen module 1 behaald (80% van 3 producten)
        for pid, cijfer in ((1, "8.0"), (2, "6.0"), (3, "6.0")):
            self.client.post("/docent/beoordeling", data={
                "student_id": 3, "product_id": pid, "traject_id": 1, "cijfer": cijfer})
        self.login(1)
        m3 = self.sql("SELECT * FROM module WHERE id = 3")[0]
        self.assertEqual(m3["afhankelijkheid_modus"], "minstens_een")
        # module 3 mag nu zichtbaar/niet geblokkeerd zijn voor de student
        self.login(3)
        html = self.client.get("/mijn/traject/1").data.decode()
        self.assertNotIn("s-geblokkeerd", html)

    # ---------- docent ----------

    def test_beoordeling_opslaan_en_cijfer_correctie(self):
        self.login(2)
        self.client.post("/docent/beoordeling", data={
            "student_id": 3, "product_id": 1, "traject_id": 1, "cijfer": "7,5"})
        row = self.sql("SELECT * FROM beoordeling WHERE student_id = 3 AND product_id = 1")
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["cijfer"], 7.5)
        # corrigeren
        self.client.post("/docent/beoordeling", data={
            "student_id": 3, "product_id": 1, "traject_id": 1, "cijfer": "4.2"})
        row = self.sql("SELECT cijfer FROM beoordeling WHERE student_id = 3 AND product_id = 1")
        self.assertEqual(row[0]["cijfer"], 4.2)
        # leeg cijfer = beoordeling verwijderen
        self.client.post("/docent/beoordeling", data={
            "student_id": 3, "product_id": 1, "traject_id": 1, "cijfer": ""})
        self.assertEqual(len(self.sql("SELECT * FROM beoordeling WHERE student_id = 3 AND product_id = 1")), 0)

    def test_product_doel_beoordeling_blijft_bestaan(self):
        self.login(2)
        self.client.post("/docent/product-doel", data={
            "student_id": 3, "product_doel_id": 1, "traject_id": 1, "voldoende": "on"})
        row = self.sql("SELECT voldoende FROM product_doel_beoordeling WHERE student_id = 3 AND product_doel_id = 1")
        self.assertEqual(row[0]["voldoende"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
