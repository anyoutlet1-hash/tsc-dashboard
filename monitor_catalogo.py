"""
Monitor de catálogo — TSC Shop
Verifica se algum concorrente está ganhando o buy box
em anúncios de catálogo das marcas TSC, Ziphome e Ranchero.
Envia e-mail quando encontra perda.
"""

import smtplib
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from mercadolivre import _get, minha_conta
from config import GMAIL_USER, GMAIL_APP_PASSWORD, NOTIFY_EMAIL

MARCAS = ["ziphome", "tsc", "ranchero"]
MY_USER_ID = None  # preenchido em runtime


def get_user_id():
    global MY_USER_ID
    if MY_USER_ID is None:
        MY_USER_ID = minha_conta()["id"]
    return MY_USER_ID


def get_catalog_items_com_marca():
    """Retorna todos os itens ativos de catálogo com as marcas monitoradas."""
    user_id = get_user_id()
    offset = 0
    all_ids = []
    while True:
        r = _get(
            f"/users/{user_id}/items/search",
            params={"catalog_listing": "true", "status": "active", "limit": 100, "offset": offset},
        )
        ids = r.get("results", [])
        all_ids.extend(ids)
        if len(ids) < 100:
            break
        offset += 100

    # Busca detalhes em batch e filtra por marca
    marcados = []
    for i in range(0, len(all_ids), 20):
        batch = all_ids[i : i + 20]
        r2 = _get(
            "/items",
            params={"ids": ",".join(batch), "attributes": "id,title,catalog_product_id,permalink"},
        )
        for it in r2:
            body = it.get("body", {})
            title = body.get("title", "").lower()
            if any(m in title for m in MARCAS):
                marcados.append(body)

    return marcados


def verificar_perdas(items):
    """
    Para cada item, verifica se TSC está ganhando o buy box.
    Retorna lista de itens onde TSC está perdendo.
    """
    user_id = get_user_id()
    perdendo = []

    for item in items:
        prod_id = item.get("catalog_product_id")
        if not prod_id:
            continue
        try:
            sellers_data = _get(f"/products/{prod_id}/items", params={"limit": 10})
            results = sellers_data.get("results", [])
            if not results:
                continue

            # O primeiro resultado é o vencedor do buy box
            winner = results[0]
            winner_seller_id = winner.get("seller_id")
            winner_item_id = winner.get("item_id")

            if winner_seller_id != user_id:
                perdendo.append({
                    "item_id": item["id"],
                    "titulo": item.get("title", ""),
                    "permalink": item.get("permalink", ""),
                    "catalog_product_id": prod_id,
                    "winner_item_id": winner_item_id,
                    "winner_seller_id": winner_seller_id,
                    "winner_price": winner.get("price"),
                    "total_sellers": sellers_data.get("paging", {}).get("total", 0),
                })
        except Exception as e:
            print(f"  Erro ao verificar {item['id']}: {e}")

    return perdendo


def enviar_email(perdas):
    """Envia e-mail com lista de anúncios perdendo."""
    if not perdas:
        return

    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    subject = f"Perdendo Catalogo — {len(perdas)} anuncio(s) [{agora}]"

    linhas = []
    for p in perdas:
        linhas.append(
            f"• {p['titulo'][:60]}\n"
            f"  Seu anúncio : {p['item_id']}\n"
            f"  Ganhador    : {p['winner_item_id']} (seller {p['winner_seller_id']})\n"
            f"  Preço deles : R$ {p['winner_price']:.2f}\n"
            f"  Concorrentes: {p['total_sellers']}\n"
            f"  Link produto: https://www.mercadolivre.com.br/p/{p['catalog_product_id']}\n"
        )

    body = (
        f"Olá! Foram encontrados {len(perdas)} anúncio(s) onde a TSC Shop está perdendo o buy box do catálogo.\n\n"
        + "\n".join(linhas)
        + f"\nVerificação feita em: {agora}"
    )

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"  E-mail enviado para {NOTIFY_EMAIL} com {len(perdas)} perdas.")


def main():
    print(f"\n[{datetime.now().strftime('%d/%m/%Y %H:%M')}] Iniciando verificação de catálogo...")

    print("  Buscando anúncios de catálogo com as marcas monitoradas...")
    items = get_catalog_items_com_marca()
    print(f"  Encontrados: {len(items)} anúncios (TSC / Ziphome / Ranchero)")

    print("  Verificando buy box de cada produto...")
    perdas = verificar_perdas(items)

    if perdas:
        print(f"  ATENCAO: Perdendo em {len(perdas)} anuncio(s)!")
        for p in perdas:
            print(f"    - {p['titulo'][:50]} -> ganhador: {p['winner_item_id']}")
        enviar_email(perdas)
    else:
        print("  OK: Ganhando todos os catalogos monitorados!")

    print("  Concluído.\n")


if __name__ == "__main__":
    main()
