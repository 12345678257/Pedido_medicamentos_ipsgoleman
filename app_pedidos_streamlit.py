
# -*- coding: utf-8 -*-
import os, io, time, uuid, sqlite3, datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path("data/pedidos.db")
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(page_title="Pedidos Regional → ERON → Moléculas", page_icon="🛒", layout="wide")
st.title("🛒 Pedidos por Regional → ERON → Moléculas")

# =================== DB ===================
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS regional (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL
    );
    CREATE TABLE IF NOT EXISTS eron (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        regional_id INTEGER NOT NULL,
        UNIQUE(nombre, regional_id),
        FOREIGN KEY (regional_id) REFERENCES regional(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS molecula (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE NOT NULL,
        nombre TEXT NOT NULL,
        unidad_presentacion TEXT,
        activo INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS pedido (
        id TEXT PRIMARY KEY, -- uuid
        creado_en TEXT NOT NULL,
        usuario TEXT,
        regional_id INTEGER NOT NULL,
        eron_id INTEGER NOT NULL,
        estado TEXT NOT NULL DEFAULT 'EN_CURSO',
        FOREIGN KEY (regional_id) REFERENCES regional(id),
        FOREIGN KEY (eron_id) REFERENCES eron(id)
    );
    CREATE TABLE IF NOT EXISTS pedido_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id TEXT NOT NULL,
        molecula_id INTEGER NOT NULL,
        cantidad REAL NOT NULL,
        UNIQUE(pedido_id, molecula_id),
        FOREIGN KEY (pedido_id) REFERENCES pedido(id) ON DELETE CASCADE,
        FOREIGN KEY (molecula_id) REFERENCES molecula(id)
    );
    """)
    conn.commit()

def upsert_regional(conn, nombre: str):
    if not nombre: return None
    conn.execute("INSERT OR IGNORE INTO regional(nombre) VALUES (?)", (nombre,))
    conn.commit()
    rid = conn.execute("SELECT id FROM regional WHERE nombre=?", (nombre,)).fetchone()[0]
    return rid

def upsert_eron(conn, nombre: str, regional_id: int):
    if not nombre or not regional_id: return None
    conn.execute("INSERT OR IGNORE INTO eron(nombre, regional_id) VALUES (?,?)", (nombre, regional_id))
    conn.commit()
    row = conn.execute("SELECT id FROM eron WHERE nombre=? AND regional_id=?", (nombre, regional_id)).fetchone()
    return row[0] if row else None

def upsert_molecula(conn, codigo: str, nombre: str, unidad: str, activo: int=1):
    conn.execute("""
    INSERT INTO molecula(codigo, nombre, unidad_presentacion, activo)
    VALUES (?,?,?,?)
    ON CONFLICT(codigo) DO UPDATE SET
        nombre=excluded.nombre,
        unidad_presentacion=excluded.unidad_presentacion,
        activo=excluded.activo
    """, (codigo, nombre, unidad, int(activo)))
    conn.commit()

def list_regionales(conn):
    return [r[0] for r in conn.execute("SELECT nombre FROM regional ORDER BY nombre").fetchall()]

def list_eron_by_regional(conn, regional_nombre: str):
    q = """
    SELECT eron.nombre FROM eron
    JOIN regional ON regional.id = eron.regional_id
    WHERE regional.nombre = ?
    ORDER BY eron.nombre
    """
    return [r[0] for r in conn.execute(q, (regional_nombre,)).fetchall()]

def get_regional_id(conn, nombre: str):
    row = conn.execute("SELECT id FROM regional WHERE nombre=?", (nombre,)).fetchone()
    return row[0] if row else None

def get_eron_id(conn, nombre: str, regional_id: int):
    row = conn.execute("SELECT id FROM eron WHERE nombre=? AND regional_id=?", (nombre, regional_id)).fetchone()
    return row[0] if row else None

def search_moleculas(conn, texto: str, solo_activas=True, limit=200):
    like = f"%{texto.strip()}%" if texto else "%"
    q = """
    SELECT id, codigo, nombre, unidad_presentacion, activo
    FROM molecula
    WHERE (codigo LIKE ? OR nombre LIKE ?)
    """
    params = [like, like]
    if solo_activas:
        q += " AND activo=1"
    q += " ORDER BY nombre LIMIT ?"
    params.append(limit)
    return pd.read_sql_query(q, conn, params=params)

def ensure_seed(conn):
    # Seed only if empty
    if conn.execute("SELECT COUNT(*) FROM regional").fetchone()[0] == 0:
        reg_csv = DATA_DIR / "sample_regionales_eron.csv"
        if reg_csv.exists():
            df = pd.read_csv(reg_csv, dtype=str).fillna("")
            for reg, er in df[["regional","eron"]].itertuples(index=False):
                rid = upsert_regional(conn, reg.strip())
                upsert_eron(conn, er.strip(), rid)
    if conn.execute("SELECT COUNT(*) FROM molecula").fetchone()[0] == 0:
        mol_csv = DATA_DIR / "sample_catalogos.csv"
        if mol_csv.exists():
            dfm = pd.read_csv(mol_csv, dtype={"activo":"Int64"}).fillna("")
            for row in dfm.itertuples(index=False):
                upsert_molecula(conn,
                                str(row.codigo).strip(),
                                str(row.nombre).strip(),
                                str(row.unidad_presentacion).strip(),
                                int(row.activo) if pd.notna(row.activo) else 1)

def get_or_create_pedido(conn, usuario: str, regional_nombre: str, eron_nombre: str, pedido_id: str|None=None):
    # resolve ids
    rid = get_regional_id(conn, regional_nombre)
    if rid is None:
        rid = upsert_regional(conn, regional_nombre)
    eid = get_eron_id(conn, eron_nombre, rid)
    if eid is None:
        eid = upsert_eron(conn, eron_nombre, rid)

    if pedido_id:
        row = conn.execute("SELECT id FROM pedido WHERE id=?", (pedido_id,)).fetchone()
        if row:
            return pedido_id

    pid = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO pedido(id, creado_en, usuario, regional_id, eron_id, estado)
        VALUES(?,?,?,?,?, 'EN_CURSO')
    """, (pid, dt.datetime.utcnow().isoformat(), usuario, rid, eid))
    conn.commit()
    return pid

def list_pedidos(conn, limit=50):
    q = """
    SELECT p.id, p.creado_en, IFNULL(p.usuario,'' ) as usuario,
           r.nombre as regional, e.nombre as eron, p.estado
    FROM pedido p
    JOIN regional r ON r.id=p.regional_id
    JOIN eron e ON e.id=p.eron_id
    ORDER BY p.creado_en DESC
    LIMIT ?
    """
    return pd.read_sql_query(q, conn, params=(limit,))

def load_pedido_items(conn, pedido_id: str):
    q = """
    SELECT pi.id as item_id, m.codigo, m.nombre, m.unidad_presentacion, pi.cantidad, m.id as molecula_id
    FROM pedido_item pi
    JOIN molecula m ON m.id = pi.molecula_id
    WHERE pi.pedido_id = ?
    ORDER BY m.nombre
    """
    return pd.read_sql_query(q, conn, params=(pedido_id,))

def add_or_update_item(conn, pedido_id: str, molecula_id: int, cantidad: float):
    if cantidad <= 0:
        conn.execute("DELETE FROM pedido_item WHERE pedido_id=? AND molecula_id=?", (pedido_id, molecula_id))
        conn.commit()
        return
    conn.execute("""
        INSERT INTO pedido_item(pedido_id, molecula_id, cantidad)
        VALUES(?,?,?)
        ON CONFLICT(pedido_id, molecula_id) DO UPDATE SET
            cantidad=excluded.cantidad
    """, (pedido_id, molecula_id, cantidad))
    conn.commit()

def delete_item(conn, item_id: int):
    conn.execute("DELETE FROM pedido_item WHERE id=?", (item_id,))
    conn.commit()

def export_pedido(conn, pedido_id: str) -> pd.DataFrame:
    q = """
    SELECT p.id as order_id, p.creado_en, p.usuario,
           r.nombre as regional, e.nombre as eron,
           m.codigo, m.nombre, m.unidad_presentacion,
           pi.cantidad
    FROM pedido p
    JOIN regional r ON r.id=p.regional_id
    JOIN eron e ON e.id=p.eron_id
    JOIN pedido_item pi ON pi.pedido_id=p.id
    JOIN molecula m ON m.id=pi.molecula_id
    WHERE p.id=?
    ORDER BY m.nombre
    """
    return pd.read_sql_query(q, conn, params=(pedido_id,))

# =================== INIT ===================
conn = get_conn()
init_db(conn)
ensure_seed(conn)

# =================== Sidebar: pedidos ===================
with st.sidebar:
    st.header("📦 Pedido")
    pedidos_df = list_pedidos(conn, limit=100)
    opciones = ["(nuevo)"] + pedidos_df["id"].tolist()
    elegido = st.selectbox("Abrir pedido", opciones, index=0)
    usuario = st.text_input("Usuario (opcional)", value=st.session_state.get("usuario",""))
    st.session_state["usuario"] = usuario

# =================== Main Tabs ===================
tab_pedido, tab_catalogos = st.tabs(["📝 Crear/Editar Pedido", "🗂️ Catálogos"])

with tab_pedido:
    colA, colB = st.columns(2)
    # Regional → ERON
    regionales = list_regionales(conn)
    regional = colA.selectbox("Regional", regionales, index=0 if regionales else None, placeholder="Selecciona...")
    erones = list_eron_by_regional(conn, regional) if regional else []
    eron = colB.selectbox("ERON", erones, index=0 if erones else None, placeholder="Selecciona...")

    if elegido == "(nuevo)":
        st.info("Configura Regional y ERON y luego pulsa **Crear pedido**.")
        crear = st.button("➕ Crear pedido", disabled=not (regional and eron))
        if crear:
            pid = get_or_create_pedido(conn, usuario or "", regional, eron, pedido_id=None)
            st.session_state["pedido_id"] = pid
            st.rerun()
    else:
        st.session_state["pedido_id"] = elegido

    pid = st.session_state.get("pedido_id")
    if pid:
        st.success(f"Pedido activo: {pid}")
        # Buscador de moléculas
        st.subheader("🔎 Buscar y agregar moléculas")
        q = st.text_input("Buscar por código o nombre", value=st.session_state.get("q",""))
        st.session_state["q"] = q
        resultados = search_moleculas(conn, q, solo_activas=True, limit=400)
        if resultados.empty:
            st.warning("Sin resultados.")
        else:
            # Agregar cantidades
            st.caption("Escribe una cantidad y pulsa **Agregar/Actualizar** para cada ítem.")
            for i, row in resultados.iterrows():
                with st.expander(f"{row['nombre']} — [{row['codigo']}] ({row['unidad_presentacion']})", expanded=False):
                    c1, c2 = st.columns([1,1])
                    cant = c1.number_input("Cantidad", min_value=0.0, step=1.0, value=0.0, key=f"add_{row['id']}")
                    if c2.button("Agregar/Actualizar", key=f"btnadd_{row['id']}"):
                        add_or_update_item(conn, pid, int(row["id"]), float(cant))
                        st.toast("Guardado", icon="💾")
                        st.rerun()

        # Carrito
        st.subheader("🛒 Carrito del pedido")
        items = load_pedido_items(conn, pid)
        if items.empty:
            st.info("Aún no hay ítems en el pedido.")
        else:
            edit_df = items[["item_id","codigo","nombre","unidad_presentacion","cantidad"]].copy()
            edit_df = st.data_editor(
                edit_df,
                column_config={
                    "item_id": st.column_config.Column("ID", disabled=True),
                    "codigo": st.column_config.Column("Código", disabled=True),
                    "nombre": st.column_config.Column("Nombre", disabled=True),
                    "unidad_presentacion": st.column_config.Column("Unidad", disabled=True),
                    "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.0, step=1.0)
                },
                hide_index=True,
                key="carrito_editor",
            )
            # Detect changes vs DB and persist
            merged = items.merge(edit_df[["item_id","cantidad"]], on="item_id", suffixes=("","_new"))
            for _, r in merged.iterrows():
                if float(r["cantidad_new"]) != float(r["cantidad"]):
                    if r["cantidad_new"] <= 0:
                        delete_item(conn, int(r["item_id"]))
                    else:
                        add_or_update_item(conn, pid, int(r["molecula_id"]), float(r["cantidad_new"]))
            # Botones eliminar por fila
            del_cols = st.columns(len(items))
            for idx, (_, r) in enumerate(items.iterrows()):
                if del_cols[idx].button(f"🗑️ {r['codigo']}", key=f"del_{r['item_id']}"):
                    delete_item(conn, int(r["item_id"]))
                    st.toast("Ítem eliminado", icon="🗑️")
                    st.rerun()

            # Export
            st.subheader("⬇️ Exportar")
            dfexp = export_pedido(conn, pid)
            csv_bytes = dfexp.to_csv(index=False).encode("utf-8")
            xlsx_io = io.BytesIO()
            with pd.ExcelWriter(xlsx_io, engine="xlsxwriter") as writer:
                dfexp.to_excel(writer, index=False, sheet_name="pedido")
            xlsx_io.seek(0)
            st.download_button("CSV", csv_bytes, file_name=f"pedido_{pid}.csv", mime="text/csv")
            st.download_button("Excel (.xlsx)", xlsx_io, file_name=f"pedido_{pid}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

with tab_catalogos:
    st.subheader("📥 Cargar/Actualizar catálogos")
    st.caption("Puedes subir **Excel (.xlsx)** o **CSV** con los formatos:")
    with st.expander("Formato de Moléculas", expanded=False):
        st.code("codigo,nombre,unidad_presentacion,activo", language="text")
    with st.expander("Formato Regional↔ERON", expanded=False):
        st.code("regional,eron", language="text")

    cola, colb = st.columns(2)
    up_mol = cola.file_uploader("Subir catálogo de moléculas", type=["csv","xlsx"], key="up_mol")
    up_re = colb.file_uploader("Subir mapa Regional↔ERON", type=["csv","xlsx"], key="up_re")

    def read_any(file) -> pd.DataFrame:
        name = (file.name or "").lower()
        if name.endswith(".csv"):
            return pd.read_csv(file, dtype=str).fillna("")
        return pd.read_excel(file)

    if up_mol:
        df = read_any(up_mol)
        # normalizar columnas
        tmp = df.copy()
        tmp.columns = [str(c).strip().lower() for c in tmp.columns]
        need = {"codigo","nombre","unidad_presentacion"}
        if not need.issubset(set(tmp.columns)):
            st.error(f"Faltan columnas {need - set(tmp.columns)}")
        else:
            tmp["activo"] = tmp.get("activo", 1)
            tmp.to_csv(DATA_DIR/"sample_catalogos.csv", index=False, encoding="utf-8")
            # re-seed moleculas (upsert)
            for row in tmp.itertuples(index=False):
                upsert_molecula(conn,
                                str(getattr(row,'codigo')).strip(),
                                str(getattr(row,'nombre')).strip(),
                                str(getattr(row,'unidad_presentacion')).strip(),
                                int(getattr(row,'activo')) if pd.notna(getattr(row,'activo')) else 1)
            st.success("Catálogo de moléculas actualizado.")

    if up_re:
        df = read_any(up_re)
        tmp = df.copy()
        tmp.columns = [str(c).strip().lower() for c in tmp.columns]
        need = {"regional","eron"}
        if not need.issubset(set(tmp.columns)):
            st.error(f"Faltan columnas {need - set(tmp.columns)}")
        else:
            tmp.to_csv(DATA_DIR/"sample_regionales_eron.csv", index=False, encoding="utf-8")
            # actualizar tablas regional/eron
            for r,e in tmp[["regional","eron"]].itertuples(index=False):
                rid = upsert_regional(conn, str(r).strip())
                upsert_eron(conn, str(e).strip(), rid)
            st.success("Mapa Regional↔ERON actualizado.")
