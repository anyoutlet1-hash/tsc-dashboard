"""
Resumo de vendas do dia — TSC Shop
"""

import requests
from datetime import date, timedelta
from auth import get_valid_token
from collections import Counter

BASE = "https://api.mercadolibre.com"
USER_ID = 48980675


def run():
    token = get_valid_token()
    headers = {"Authorization": f"Bearer {token}"}

    hoje = date.today().strftime("%Y-%m-%dT00:00:00.000-03:00")

    todos = []
    offset = 0
    while True:
        r = requests.get(f"{BASE}/orders/search", headers=headers, params={
            "seller": USER_ID,
            "order.date_created.from": hoje,
            "limit": 50,
            "offset": offset,
        }).json()
        results = r.get("results", [])
        todos.extend(results)
        total = r.get("paging", {}).get("total", 0)
        offset += 50
        if offset >= total:
            break

    pagos = [o for o in todos if o.get("status") == "paid"]
    cancelados = [o for o in todos if o.get("status") == "cancelled"]
    valor = sum(o.get("total_amount", 0) for o in pagos)
    itens = sum(sum(i.get("quantity", 1) for i in o.get("order_items", [])) for o in pagos)

    print(f"\n{'='*40}")
    print(f"  TSC Shop — Vendas de hoje ({date.today().strftime('%d/%m/%Y')})")
    print(f"{'='*40}")
    print(f"  Pedidos pagos   : {len(pagos)}")
    print(f"  Itens vendidos  : {itens}")
    print(f"  Valor total     : R$ {valor:,.2f}")
    print(f"  Ticket medio    : R$ {valor/len(pagos):.2f}" if pagos else "  Sem vendas hoje")
    print(f"  Cancelados      : {len(cancelados)}")
    print(f"{'='*40}")

    print("\n  Top 5 produtos:")
    produtos = Counter()
    for o in pagos:
        for i in o.get("order_items", []):
            titulo = i.get("item", {}).get("title", "?")[:35]
            produtos[titulo] += i.get("quantity", 1)
    for titulo, qtd in produtos.most_common(5):
        print(f"    {qtd}x {titulo}")
    print()


if __name__ == "__main__":
    run()
