"""Modelos de domínio do lex-rag (normas e dispositivos)."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


class TipoDispositivo(StrEnum):
    artigo = "artigo"
    paragrafo = "paragrafo"
    inciso = "inciso"
    alinea = "alinea"
    # Documento sem articulação, cujo texto inteiro é um dispositivo só — o
    # enunciado de Súmula Vinculante (ver ingest/jurisprudencia.py).
    enunciado = "enunciado"
    # Anexo sem articulação (tabela, quadro, código por incisos), servido como
    # texto em partes: ``anexo_i``, ``anexo_i_p2``... Anexo articulado não usa
    # este tipo — seus artigos entram como ``artigo`` com o path prefixado
    # (``anexo_i_art_3``). Ver ``html_parser._ANEXO_MARK``.
    anexo = "anexo"


class Dispositivo(BaseModel):
    """Um dispositivo no nível de artigo (caput + parágrafos/incisos inlinados)."""

    path: str  # ex.: "art_37", "art_5_A", "anexo_i_art_3", "anexo_ii", "enunciado"
    label: str  # ex.: "Art. 37", "Art. 5º-A", "Anexo II", "Enunciado"
    tipo: TipoDispositivo = TipoDispositivo.artigo
    texto: str  # texto literal
    parent_label: str = ""  # ex.: "TÍTULO III - CAPÍTULO VII - Da Administração Pública"
    vigente: bool = True
    revogado_por: str | None = None


class Norma(BaseModel):
    """Um documento do corpus: norma federal ou enunciado jurisprudencial."""

    urn_lex: str
    tipo: str  # "constituicao" | "lei_complementar" | "lei" | "codigo" | "decreto"
    #           | "regimento" | "resolucao" | "sumula_vinculante" | "sumula_stf"
    numero: str | None = None
    data: date | None = None
    epigrafe: str  # ex.: "Constituição Federal de 1988"
    ementa: str = ""
    url_canonica: str = ""
    dispositivos: list[Dispositivo] = Field(default_factory=list)

    def vigentes(self) -> list[Dispositivo]:
        return [d for d in self.dispositivos if d.vigente]
