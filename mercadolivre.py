"""
Cliente da API do Mercado Livre para a TSC Shop.
"""

import requests
from auth import get_valid_token

BASE = "https://api.mercadolibre.com"


def _headers():
    return {"Authorization": f"Bearer {get_valid_token()}"}


def _get(path, params=None):
    r = requests.get(f"{BASE}{path}", headers=_headers(), params=params)
    r.raise_for_status()
    return r.json()


def _post(path, data):
    r = requests.post(f"{BASE}{path}", headers=_headers(), json=data)
    r.raise_for_status()
    return r.json()


# --- Conta ---

def minha_conta():
    return _get("/users/me")


# --- Anúncios ---

def meus_anuncios(limit=50, offset=0):
    user_id = minha_conta()["id"]
    return _get(
        f"/users/{user_id}/items/search",
        params={"limit": limit, "offset": offset},
    )


def detalhe_anuncio(item_id):
    return _get(f"/items/{item_id}")


def atualizar_preco(item_id, novo_preco):
    r = requests.put(
        f"{BASE}/items/{item_id}",
        headers=_headers(),
        json={"price": novo_preco},
    )
    r.raise_for_status()
    return r.json()


def pausar_anuncio(item_id):
    r = requests.put(
        f"{BASE}/items/{item_id}",
        headers=_headers(),
        json={"status": "paused"},
    )
    r.raise_for_status()
    return r.json()


def reativar_anuncio(item_id):
    r = requests.put(
        f"{BASE}/items/{item_id}",
        headers=_headers(),
        json={"status": "active"},
    )
    r.raise_for_status()
    return r.json()


# --- Perguntas ---

def perguntas_pendentes():
    user_id = minha_conta()["id"]
    return _get(
        "/questions/search",
        params={"seller_id": user_id, "status": "UNANSWERED"},
    )


def responder_pergunta(question_id, texto):
    return _post(f"/answers", {"question_id": question_id, "text": texto})


# --- Pedidos ---

def pedidos_recentes(limit=50):
    user_id = minha_conta()["id"]
    return _get(
        f"/orders/search/recent",
        params={"seller": user_id, "limit": limit},
    )


def detalhe_pedido(order_id):
    return _get(f"/orders/{order_id}")


def vendas_hoje():
    from datetime import date
    user_id = minha_conta()["id"]
    hoje = date.today().isoformat()
    params = {
        "seller": user_id,
        "order.date_created.from": f"{hoje}T00:00:00.000-03:00",
        "order.date_created.to": f"{hoje}T23:59:59.000-03:00",
        "limit": 50,
        "offset": 0,
    }
    primeiro = _get("/orders/search", params=params)
    total = primeiro.get("paging", {}).get("total", 0)
    resultados = list(primeiro.get("results", []))

    while len(resultados) < total:
        params["offset"] = len(resultados)
        pagina = _get("/orders/search", params=params)
        novos = pagina.get("results", [])
        if not novos:
            break
        resultados.extend(novos)

    return {"paging": {"total": total}, "results": resultados}


# --- Métricas rápidas ---

def resumo():
    conta = minha_conta()
    anuncios = meus_anuncios(limit=1)
    perguntas = perguntas_pendentes()
    vendas = vendas_hoje()

    total_anuncios = anuncios.get("paging", {}).get("total", 0)
    total_perguntas = perguntas.get("total", 0)
    total_vendas_hoje = vendas.get("paging", {}).get("total", 0)
    receita_hoje = sum(
        o.get("total_amount", 0) for o in vendas.get("results", [])
    )

    print(f"\n{'='*40}")
    print(f"  TSC Shop — Resumo do dia")
    print(f"{'='*40}")
    print(f"  Conta       : {conta.get('nickname')}")
    print(f"  Anúncios    : {total_anuncios}")
    print(f"  Perguntas   : {total_perguntas} sem resposta")
    print(f"  Vendas hoje : {total_vendas_hoje}")
    print(f"  Receita hoje: R$ {receita_hoje:,.2f}")
    print(f"{'='*40}\n")
