"""SQLite: lembra cada vaga já vista, para cada execução só gastar IA com vaga nova."""
import json
import sqlite3

ESQUEMA = """
CREATE TABLE IF NOT EXISTS vagas (
    id INTEGER PRIMARY KEY, titulo TEXT, empresa TEXT, tipo_local TEXT, cidade TEXT,
    publicada TEXT, prazo TEXT, url TEXT, descricao TEXT, termo TEXT,
    vista_em TEXT, descarte TEXT
);
CREATE TABLE IF NOT EXISTS avaliacoes (
    id INTEGER PRIMARY KEY REFERENCES vagas(id), nota INTEGER, nivel TEXT, area TEXT,
    ingles TEXT, tem TEXT, falta TEXT, motivo TEXT, modelo TEXT, segundos REAL,
    tokens INTEGER, em TEXT
);
CREATE TABLE IF NOT EXISTS execucoes (
    em TEXT, coletadas INTEGER, novas INTEGER, descartadas INTEGER, avaliadas INTEGER,
    erros INTEGER, segundos REAL, tokens INTEGER
);
"""


def abrir(caminho: str) -> sqlite3.Connection:
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    colunas = {r["name"] for r in con.execute("PRAGMA table_info(vagas)")}
    if "similaridade" not in colunas:  # banco criado antes do funil
        con.execute("ALTER TABLE vagas ADD COLUMN similaridade REAL")
    if "fonte" not in colunas:
        con.execute("ALTER TABLE vagas ADD COLUMN fonte TEXT DEFAULT 'gupy'")
    return con


def ja_vista(con, vaga_id: int) -> bool:
    return con.execute("SELECT 1 FROM vagas WHERE id=?", (vaga_id,)).fetchone() is not None


def guardar_vaga(con, v: dict, descarte: str | None, agora: str):
    con.execute(
        "INSERT OR IGNORE INTO vagas (id,titulo,empresa,tipo_local,cidade,publicada,prazo,url,descricao,"
        "termo,vista_em,descarte,fonte) VALUES (:id,:titulo,:empresa,:tipo_local,:cidade,:publicada,"
        ":prazo,:url,:descricao,:termo,:vista_em,:descarte,:fonte)",
        {"fonte": "gupy", **v, "vista_em": agora, "descarte": descarte},
    )


def sem_similaridade(con) -> list[sqlite3.Row]:
    return con.execute("SELECT id, titulo, descricao FROM vagas WHERE descarte IS NULL AND similaridade IS NULL").fetchall()


def guardar_similaridades(con, pares: list[tuple[float, int]]):
    con.executemany("UPDATE vagas SET similaridade=? WHERE id=?", pares)


def pendentes(con) -> list[sqlite3.Row]:
    """Vagas que passaram nas regras e ainda não têm avaliação (inclui as que deram erro antes)."""
    return con.execute(
        "SELECT v.* FROM vagas v LEFT JOIN avaliacoes a ON a.id=v.id "
        "WHERE v.descarte IS NULL AND a.id IS NULL ORDER BY v.similaridade DESC, v.publicada DESC"
    ).fetchall()


def guardar_avaliacao(con, vaga_id: int, r: dict, modelo: str, segundos: float, tokens: int, agora: str):
    con.execute(
        "INSERT OR REPLACE INTO avaliacoes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (vaga_id, r["nota"], r["nivel"], r["area"], r["ingles"], json.dumps(r["tem"], ensure_ascii=False),
         json.dumps(r["falta"], ensure_ascii=False), r["motivo"], modelo, segundos, tokens, agora),
    )
