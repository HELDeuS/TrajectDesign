PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS gebruiker (
  id INTEGER PRIMARY KEY,
  naam TEXT NOT NULL,
  rol TEXT NOT NULL CHECK (rol IN ('ontwerper','docent','student'))
);

CREATE TABLE IF NOT EXISTS traject (
  id INTEGER PRIMARY KEY,
  naam TEXT NOT NULL,
  omschrijving TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS module (
  id INTEGER PRIMARY KEY,
  traject_id INTEGER NOT NULL REFERENCES traject(id) ON DELETE CASCADE,
  naam TEXT NOT NULL,
  omschrijving TEXT DEFAULT '',
  max_sbu REAL NOT NULL DEFAULT 0,
  behaalregel TEXT NOT NULL DEFAULT 'percentage' CHECK (behaalregel IN ('percentage','doelen')),
  drempel_percentage INTEGER NOT NULL DEFAULT 80,
  voldoende_cijfer REAL NOT NULL DEFAULT 5.5,
  afhankelijkheid_modus TEXT NOT NULL DEFAULT 'alle' CHECK (afhankelijkheid_modus IN ('alle','minstens_een'))
);

CREATE TABLE IF NOT EXISTS module_afhankelijkheid (
  module_id INTEGER NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  vereist_module_id INTEGER NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  PRIMARY KEY (module_id, vereist_module_id),
  CHECK (module_id <> vereist_module_id)
);

CREATE TABLE IF NOT EXISTS module_doel (
  id INTEGER PRIMARY KEY,
  module_id INTEGER NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  soort TEXT NOT NULL CHECK (soort IN ('leerdoel','leeruitkomst')),
  omschrijving TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS onderwijsproduct (
  id INTEGER PRIMARY KEY,
  module_id INTEGER NOT NULL REFERENCES module(id) ON DELETE CASCADE,
  naam TEXT NOT NULL,
  omschrijving TEXT DEFAULT '',
  sbu REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS product_doel (
  id INTEGER PRIMARY KEY,
  product_id INTEGER NOT NULL REFERENCES onderwijsproduct(id) ON DELETE CASCADE,
  soort TEXT NOT NULL CHECK (soort IN ('leerdoel','leeruitkomst')),
  omschrijving TEXT NOT NULL,
  module_doel_id INTEGER REFERENCES module_doel(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS beoordeling (
  id INTEGER PRIMARY KEY,
  student_id INTEGER NOT NULL REFERENCES gebruiker(id) ON DELETE CASCADE,
  product_id INTEGER NOT NULL REFERENCES onderwijsproduct(id) ON DELETE CASCADE,
  cijfer REAL NOT NULL,
  docent_id INTEGER REFERENCES gebruiker(id) ON DELETE SET NULL,
  datum TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  UNIQUE (student_id, product_id)
);

CREATE TABLE IF NOT EXISTS product_doel_beoordeling (
  student_id INTEGER NOT NULL REFERENCES gebruiker(id) ON DELETE CASCADE,
  product_doel_id INTEGER NOT NULL REFERENCES product_doel(id) ON DELETE CASCADE,
  voldoende INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (student_id, product_doel_id)
);

CREATE TABLE IF NOT EXISTS module_doel_beoordeling (
  student_id INTEGER NOT NULL REFERENCES gebruiker(id) ON DELETE CASCADE,
  module_doel_id INTEGER NOT NULL REFERENCES module_doel(id) ON DELETE CASCADE,
  voldoende INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (student_id, module_doel_id)
);

CREATE TABLE IF NOT EXISTS traject_deelnemer (
  traject_id INTEGER NOT NULL REFERENCES traject(id) ON DELETE CASCADE,
  student_id INTEGER NOT NULL REFERENCES gebruiker(id) ON DELETE CASCADE,
  PRIMARY KEY (traject_id, student_id)
);
