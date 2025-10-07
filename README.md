# App de Pedidos por Regional → ERON → Moléculas (Streamlit + SQLite)

**Lista para subir a GitHub.** Corre en local con:

```bash
pip install -r requirements.txt
streamlit run app_pedidos_streamlit.py
```

## Funciones clave
- Selección dependiente **Regional → ERON**.
- Catálogo de **moléculas/medicamentos** con búsqueda por texto.
- **Carrito** con CRUD (agregar, editar cantidades en línea, eliminar).
- **Autoguardado** en SQLite (no se pierde el pedido).
- **Exportar** pedido a **CSV** o **Excel**.
- **Cargar catálogos** (moleculas y regional↔ERON) desde Excel/CSV.
- Reabrir pedidos previos desde la barra lateral.

## Datos
Al primer arranque la app **siembra** la BD usando los CSV en `data/`:

- `data/sample_catalogos.csv`
- `data/sample_regionales_eron.csv`

Puedes reemplazarlos dentro de la app en la pestaña **Catálogos**.