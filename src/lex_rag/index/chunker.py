"""Chunking: 1 dispositivo = 1 chunk, com contexto embutido no texto a embedar.

O texto a embedar segue o padrão validado no smoke test:
``[epígrafe] [parent_label] Label: texto``. O payload guarda o **texto literal**
do dispositivo (sem paráfrase) e os metadados para citação e filtro.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from lex_rag.ingest.models import Dispositivo, Norma


@dataclass
class Chunk:
    id: str
    text: str  # texto com contexto, usado para gerar os embeddings
    payload: dict


def point_id(urn_lex: str, path: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{urn_lex}#{path}"))


def _embed_text(norma: Norma, disp: Dispositivo) -> str:
    ctx = f"[{norma.epigrafe}]"
    if disp.parent_label:
        ctx += f" [{disp.parent_label}]"
    return f"{ctx} {disp.label}: {disp.texto}"


def build_chunk(norma: Norma, disp: Dispositivo) -> Chunk:
    payload = {
        "urn_lex": norma.urn_lex,
        "epigrafe": norma.epigrafe,
        "tipo_norma": norma.tipo,
        "url_canonica": norma.url_canonica,
        "dispositivo_path": disp.path,
        "dispositivo_label": disp.label,
        "parent_label": disp.parent_label,
        "texto": disp.texto,
        "vigente": disp.vigente,
        "revogado_por": disp.revogado_por,
    }
    return Chunk(
        id=point_id(norma.urn_lex, disp.path),
        text=_embed_text(norma, disp),
        payload=payload,
    )


def build_chunks(norma: Norma) -> list[Chunk]:
    return [build_chunk(norma, d) for d in norma.dispositivos]
