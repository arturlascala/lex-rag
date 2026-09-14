"""Testes do parser do quadro de LCs e do merge do registro gerado."""

from datetime import date

from lex_rag.ingest.quadro_lcp import extrair_lcps
from lex_rag.ingest.urn_mapper import REGISTRO, REGISTRO_CURADO

_QUADRO = """
<table>
  <tr>
    <td><a href="Lcp233.htm">Lei Complementar nº 233, de 1º.7.2026</a>
        Publicada no DOU de 2.7.2026</td>
    <td>Altera a Lei Complementar nº 79, de 7 de janeiro de 1994.
        Mensagem de veto</td>
  </tr>
  <tr>
    <td><a href="Lcp01-62.htm">Lei complementar nº 1, de 17.7.1962</a></td>
    <td>Complementa a organização do sistema parlamentar de Govêrno.</td>
  </tr>
  <tr>
    <td><a href="Lcp233.htm">Lei Complementar nº 233, de 1º.7.2026</a></td>
    <td>duplicata da mesma LC</td>
  </tr>
  <tr><td>linha sem link</td><td>ignorada</td></tr>
</table>
"""


def test_extrair_lcps_do_quadro():
    lcps = {m.slug: m for m in extrair_lcps(_QUADRO)}
    assert len(lcps) == 2  # duplicata e linha sem link ignoradas

    lc233 = lcps["lcp_233_2026"]
    assert lc233.urn_lex == "urn:lex:br:federal:lei.complementar:2026-07-01;233"
    assert lc233.epigrafe == "Lei Complementar nº 233, de 1º de julho de 2026"
    assert lc233.url_canonica == "https://www.planalto.gov.br/ccivil_03/leis/lcp/Lcp233.htm"
    assert lc233.ementa == "Altera a Lei Complementar nº 79, de 7 de janeiro de 1994."
    assert lc233.tipo == "lei_complementar"

    lc1_62 = lcps["lcp_1_1962"]  # série antiga (1962) não colide com a LC 1/1967
    assert lc1_62.data == date(1962, 7, 17)
    assert lc1_62.urn_lex == "urn:lex:br:federal:lei.complementar:1962-07-17;1"


def test_registro_mesclado_sem_duplicar_urn():
    urns = [m.urn_lex for m in REGISTRO.values()]
    assert len(urns) == len(set(urns))
    # curadas preservadas (a entrada com fixture vence a gerada)
    assert REGISTRO["lcp_95_1998"].fixture == "lcp_95_1998.html"
    for slug in REGISTRO_CURADO:
        assert REGISTRO[slug] is REGISTRO_CURADO[slug]


def test_registro_inclui_o_conjunto_das_lcs():
    # Depende do registro_lcp.json gerado por scripts/descobrir_lcps.py.
    lcs = [m for m in REGISTRO.values() if m.tipo == "lei_complementar"]
    assert len(lcs) >= 200
