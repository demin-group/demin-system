"""Pipeline de embeddings del Knowledge Base.

Toma documentos de `kb_documents`, los trocea (chunks ~500 tokens, overlap 50),
genera embedding por chunk con Voyage AI (`voyage-multilingual-2`, 1024 dim),
inserta en `kb_chunks`. Reembed completo si el documento cambia (borra chunks
viejos, crea nuevos).

Pendiente de implementar en Fase 1. Ver `tasks/todo.md` §7.2.
"""
