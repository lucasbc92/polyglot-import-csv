#!/usr/bin/env python3
"""
crossref_verify.py — núcleo determinístico de verificação de referências.

Por que existe: um LLM não deve inventar citações. Em vez de o modelo "criar" a
entrada BibTeX a partir do que leu, este script obtém os metadados de uma fonte
autoritativa (Crossref / DOI). Se o trabalho não existe no Crossref, ele não é
adicionado — ponto final. Assim, toda referência no references.bib tem um DOI
real por trás.

Uso:
  # 1) Buscar candidatos reais por texto livre (título/tema):
  python crossref_verify.py search "polyglot persistence data import" --rows 6 --from-year 2023

  # 2) Obter BibTeX CANÔNICO a partir de um DOI confirmado:
  python crossref_verify.py bibtex 10.14778/3554821.3554886

Sem dependências externas (somente stdlib). Requer rede.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request

# Crossref pede um User-Agent com contato ("polite pool") — respostas mais
# rápidas e estáveis. Trocar o mailto se outra pessoa usar a skill.
UA = "tcc-referencias-verificadas/1.0 (mailto:lucasbcesario@gmail.com)"


def _get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _authors(item):
    out = []
    for a in item.get("author", []) or []:
        fam = a.get("family", "")
        giv = a.get("given", "")
        out.append((fam + ", " + giv).strip(", ").strip())
    return out


def _year(item):
    for k in ("published-print", "published-online", "issued", "created"):
        parts = (item.get(k) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            return parts[0][0]
    return None


def cmd_search(args):
    params = {
        "query.bibliographic": args.query,
        "rows": str(args.rows),
        "select": "DOI,title,author,issued,container-title,type,published-print,published-online",
    }
    if args.from_year:
        params["filter"] = f"from-pub-date:{args.from_year}-01-01"
    url = "https://api.crossref.org/works?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(_get(url))
    except Exception as e:  # noqa: BLE001
        print(f"ERRO na consulta Crossref: {e}", file=sys.stderr)
        return 2
    items = data.get("message", {}).get("items", [])
    if not items:
        print("Nenhum resultado no Crossref para essa consulta.")
        return 0
    for i, it in enumerate(items, 1):
        title = (it.get("title") or ["(sem título)"])[0]
        venue = (it.get("container-title") or [""])[0]
        authors = _authors(it)
        ashort = "; ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
        print(f"[{i}] {title}")
        print(f"     Autores: {ashort or '(n/d)'}")
        print(f"     Ano: {_year(it) or '(n/d)'} | Tipo: {it.get('type','')} | Veículo: {venue or '(n/d)'}")
        print(f"     DOI: {it.get('DOI','(n/d)')}")
        print()
    print("Próximo passo: confirme a aderência (abstract público via WebFetch) e, "
          "para os que entrarem, rode:  python crossref_verify.py bibtex <DOI>")
    return 0


def cmd_bibtex(args):
    doi = args.doi.strip()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    url = "https://doi.org/" + urllib.parse.quote(doi, safe="/().:-_")
    try:
        bib = _get(url, accept="application/x-bibtex")
    except Exception as e:  # noqa: BLE001
        print(f"ERRO: não foi possível obter BibTeX para o DOI '{doi}': {e}", file=sys.stderr)
        print("Se o DOI estiver correto e ainda assim falhar, NÃO invente a entrada — "
              "registre como não-verificado e siga em frente.", file=sys.stderr)
        return 2
    print(bib.strip())
    print()
    print(f"% Verificado via Crossref/DOI em https://doi.org/{doi}", )
    return 0


def main():
    p = argparse.ArgumentParser(description="Verificação de referências via Crossref/DOI.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="Buscar candidatos reais por texto livre.")
    s.add_argument("query")
    s.add_argument("--rows", type=int, default=5)
    s.add_argument("--from-year", type=int, default=None,
                   help="Filtrar por ano mínimo de publicação (ex.: 2023).")
    s.set_defaults(func=cmd_search)

    b = sub.add_parser("bibtex", help="Obter BibTeX canônico a partir de um DOI.")
    b.add_argument("doi")
    b.set_defaults(func=cmd_bibtex)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
