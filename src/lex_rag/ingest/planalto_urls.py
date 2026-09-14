"""Resolução de URL e conferência de data das páginas do Planalto.

O Planalto **não** deriva a URL do número da lei. O mesmo diploma pode estar em
``leis/l6404compilada.htm``, ``leis/leis_2001/l10257.htm`` ou
``_ato2004-2006/2004/lei/l10.973.htm``. Pior: em várias leis antigas o
``l{n}.htm`` é o texto *original* e o consolidado (com as alterações
posteriores) está sob outro sufixo — indexar a página errada serviria texto
revogado como vigente. Daí ``variantes_url`` listar os candidatos **do
consolidado para o simples**: quem chama testa em ordem e fica com o primeiro
que baixa e parseia.

``conferir_data`` fecha o outro flanco: o URN-LEX carrega a data de promulgação,
então data errada é URN errado — e silencioso. A conferência é contra a
epígrafe impressa na própria página.

Funções puras (testáveis offline); o download fica com quem chama.
"""

from __future__ import annotations

import html
import re
from datetime import date

BASE = "https://www.planalto.gov.br/ccivil_03/"

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

# Faixas dos diretórios `_ato{inicio}-{fim}` usados a partir de 2004.
_BUCKETS = {2004: 2006, 2007: 2010, 2011: 2014, 2015: 2018, 2019: 2022, 2023: 2026}

_SUFIXOS = ("compilado", "compilada", "consol", "cons", "")


def numero_pontuado(numero: str) -> str:
    """``"10973"`` → ``"10.973"`` (o Planalto usa as duas grafias na URL)."""
    return f"{int(numero):,}".replace(",", ".")


_ROTULO = {"lei": "Lei", "decreto.lei": "Decreto-Lei", "decreto": "Decreto"}


def epigrafe(especie: str, numero: str, d: date, apelido: str = "") -> str:
    """Epígrafe canônica: ``Lei nº 9.279, de 14 de maio de 1996 (apelido)``."""
    rotulo = _ROTULO.get(especie, "Lei")
    dia = "1º" if d.day == 1 else str(d.day)
    texto = f"{rotulo} nº {numero_pontuado(numero)}, de {dia} de {MESES[d.month - 1]} de {d.year}"
    return f"{texto} ({apelido})" if apelido else texto


def _dirs_decreto(ano: int) -> list[str]:
    """Diretórios candidatos dos decretos, que mudam por faixa de ano.

    Levantado contra o portal: de 2004 em diante valem os mesmos ``_ato``
    das leis; 1999-2003 se dividem entre ``decreto/{ano}/`` (Dec. 4.382/2002) e
    ``decreto/`` (Dec. 3.298/1999); 1990-1994 entre ``decreto/1990-1994/``
    (Dec. 592/1992) e ``decreto/`` (Dec. 678/1992); antes disso o consolidado
    fica em ``decreto/`` (Dec. 70.235/1972 → ``d70235compilado.htm``) ou em
    ``decreto/antigos/`` (Dec. 20.910/1932).
    """
    if ano >= 2004:
        ini = next(i for i in _BUCKETS if i <= ano <= _BUCKETS[i])
        return [f"_ato{ini}-{_BUCKETS[ini]}/{ano}/decreto/"]
    if ano >= 1999:
        return [f"decreto/{ano}/", "decreto/"]
    if ano >= 1990:
        return ["decreto/", "decreto/1990-1994/"]
    return ["decreto/", "decreto/antigos/"]


def _stems(prefixo: str, numero: str) -> list[str]:
    """Radicais do arquivo. Números de 1 a 3 dígitos são zerados à esquerda até
    4 (``Lei 605`` → ``l0605.htm``, ``DL 37`` → ``del0037.htm``) — convenção do
    Planalto para as normas antigas de numeração baixa."""
    formas = [numero, numero.zfill(4)] if len(numero) < 4 else [numero]
    return [f"{prefixo}{n}" for n in dict.fromkeys(formas)]


def variantes_url(especie: str, numero: str, ano: int) -> list[str]:
    """URLs candidatas no Planalto, do texto consolidado para o texto simples."""
    if especie == "decreto.lei":
        dirs, stems = ["decreto-lei/"], _stems("del", numero)
    elif especie == "decreto":
        # O portal responde 301 de qualquer grafia maiúscula para o arquivo em
        # minúsculas, então só as minúsculas entram na lista — a variante
        # maiúscula custaria um salto de redirecionamento e nada mais.
        dirs, stems = _dirs_decreto(ano), _stems("d", numero)
    else:
        stems = list(dict.fromkeys([*_stems("l", numero), f"l{numero_pontuado(numero)}"]))
        if ano <= 1998:
            dirs = ["leis/"]
        elif ano <= 2003:  # 1999-2003 se espalham por três diretórios
            dirs = [f"leis/{ano}/", f"leis/leis_{ano}/", "leis/"]
        else:
            ini = next(i for i in _BUCKETS if i <= ano <= _BUCKETS[i])
            dirs = [f"_ato{ini}-{_BUCKETS[ini]}/{ano}/lei/"]
    return [
        BASE + d + stem + suf + ".htm"
        for d in dirs
        for suf in _SUFIXOS
        for stem in stems
    ]


# "LEI No 6.830, DE 22 DE SETEMBRO DE 1980" — o Planalto alterna "Nº" e "N o",
# separa os termos com &nbsp; e nem sempre repete o "DE" antes do ano.
_CORPO_EPIGRAFE = (
    r"\s*N\s*[ºo°.]{0,2}\s*([\d.]+)\s*,?\s*"
    r"DE\s+(\d{1,2})[ºo°]?\s+(?:DE\s+)?([A-ZÇÃa-zçã]+)\s+(?:DE\s+)?(\d{4})"
)

# O rótulo é escolhido pela espécie porque a página de um decreto traz, logo
# abaixo da própria epígrafe, a referência à lei que ele regulamenta ("...
# Regulamenta a Lei nº 14.133, de 1º de abril de 2021"). Um padrão que casasse
# "LEI" em qualquer página acharia essa referência primeiro nos decretos cuja
# epígrafe escapasse do padrão, e o lote seria rejeitado por "data divergente"
# com um número de lei plausível — a pior forma de erro, a que parece certa.
_ROTULO_EPIGRAFE = {
    "lei": r"LEI",
    "decreto.lei": r"DECRETO[\s\-]*LEI",
    "decreto": r"DECRETO(?![\s\-]*LEI)",
}
_EPIGRAFE_PAGINA = re.compile(r"(?:LEI|DECRETO[\s\-]*LEI)" + _CORPO_EPIGRAFE, re.IGNORECASE)


def conferir_data(pagina: str, numero: str, d: date, especie: str | None = None) -> str:
    """Confere número e data declarados contra a epígrafe impressa na página.

    Devolve ``"ok"``, ``"epigrafe nao localizada"`` (inconclusivo) ou
    ``"DIVERGE (...)"``. A busca fica nos primeiros milhares de caracteres para
    não confundir a epígrafe com uma *referência* a outra lei no corpo do texto.

    ``especie`` restringe o rótulo aceito; omitida, vale o par histórico
    LEI/DECRETO-LEI.
    """
    padrao = _EPIGRAFE_PAGINA
    if especie in _ROTULO_EPIGRAFE:
        padrao = re.compile(f"(?:{_ROTULO_EPIGRAFE[especie]}){_CORPO_EPIGRAFE}", re.IGNORECASE)
    # As páginas misturam caractere literal e entidade ("Nº" e "N&ordm;"), e
    # separam os termos da epígrafe com &nbsp;. unescape resolve os dois casos;
    # o split() normaliza o \xa0 resultante junto com o resto do espaço.
    texto = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", pagina)).split())
    m = padrao.search(texto[:6000])
    if not m:
        return "epigrafe nao localizada"
    mes = next((i + 1 for i, s in enumerate(MESES) if s.startswith(m.group(3).lower()[:4])), 0)
    if (m.group(1).replace(".", "") == numero and int(m.group(2)) == d.day
            and mes == d.month and int(m.group(4)) == d.year):
        return "ok"
    return f"DIVERGE (pagina: {m.group(1)} de {m.group(2)}/{mes}/{m.group(4)})"
