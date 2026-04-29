"""Investigación de prospecto: scrapea web + extrae JSON estructurado con LLM.

Para cada empresa con `ia_fit='fit'` y web disponible: home + 3 páginas internas
(`/contacto`, `/servicios`, etc.) con httpx; fallback a playwright si la home necesita JS.
Guarda el JSON resultante en `companies.research_data`.

Pendiente de implementar en Fase 1. Ver `tasks/todo.md` §8.4.
"""
