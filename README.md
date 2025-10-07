# Pedidos Mensuales Pro — Regional → ERON → Moléculas (Streamlit + SQLite)

**Highlights**
- Un **pedido por mes** (`YYYY-MM`) que admite **múltiples Regionales/ERON** en el mismo pedido.
- **UX profesional**: cabecera tipo toolbar, métricas, validaciones y acciones en lote.
- **Autosave** en SQLite. **Editar**, **eliminar**, **actualizar** cantidades sin perder nada.
- **Resumen** por Regional/ERON/Molécula + totales.
- **Importación rápida** por CSV (código,cantidad) para una Regional/ERON.
- **Exportar todo el mes** en 1 clic (CSV/XLSX) — no tienes que escoger IDs.
- **Borrar** el pedido del mes (soft guard: confirmación).

## Ejecutar
```bash
pip install -r requirements.txt
streamlit run app_pedidos_streamlit.py
```

## Catálogos
- Moléculas: `codigo,nombre,unidad_presentacion,activo`
- Regional↔ERON: `regional,eron`