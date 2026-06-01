"""
Menu interativo de gerenciamento da TSC Shop.
"""

import sys
import mercadolivre as ml


def menu():
    opcoes = {
        "1": ("Resumo do dia", ml.resumo),
        "2": ("Listar anúncios", _listar_anuncios),
        "3": ("Ver perguntas pendentes", _ver_perguntas),
        "4": ("Responder pergunta", _responder),
        "5": ("Pedidos recentes", _pedidos),
        "6": ("Atualizar preço de anúncio", _atualizar_preco),
        "7": ("Pausar anúncio", _pausar),
        "8": ("Reativar anúncio", _reativar),
        "0": ("Sair", None),
    }

    while True:
        print("\n--- TSC Shop ---")
        for k, (label, _) in opcoes.items():
            print(f"  {k}. {label}")
        escolha = input("\nEscolha: ").strip()

        if escolha == "0":
            break
        if escolha not in opcoes:
            print("Opção inválida.")
            continue

        _, fn = opcoes[escolha]
        try:
            fn()
        except Exception as e:
            print(f"Erro: {e}")


def _listar_anuncios():
    data = ml.meus_anuncios(limit=20)
    ids = data.get("results", [])
    total = data.get("paging", {}).get("total", 0)
    print(f"\nTotal de anúncios: {total}")
    for item_id in ids[:20]:
        item = ml.detalhe_anuncio(item_id)
        status = item.get("status", "?")
        preco = item.get("price", 0)
        titulo = item.get("title", item_id)
        print(f"  [{status:8}] R$ {preco:>10.2f}  {item_id}  {titulo[:60]}")


def _ver_perguntas():
    data = ml.perguntas_pendentes()
    perguntas = data.get("questions", [])
    if not perguntas:
        print("Nenhuma pergunta pendente.")
        return
    for q in perguntas:
        print(f"\n  ID      : {q['id']}")
        print(f"  Anúncio : {q.get('item_id')}")
        print(f"  Pergunta: {q['text']}")


def _responder():
    qid = input("ID da pergunta: ").strip()
    texto = input("Resposta: ").strip()
    ml.responder_pergunta(int(qid), texto)
    print("Resposta enviada!")


def _pedidos():
    data = ml.pedidos_recentes(limit=10)
    pedidos = data.get("results", [])
    if not pedidos:
        print("Nenhum pedido recente.")
        return
    for p in pedidos:
        print(
            f"  {p['id']}  {p.get('status'):15}  R$ {p.get('total_amount', 0):>10.2f}"
            f"  {p.get('date_created', '')[:10]}"
        )


def _atualizar_preco():
    item_id = input("ID do anúncio: ").strip()
    preco = float(input("Novo preço (R$): ").replace(",", "."))
    ml.atualizar_preco(item_id, preco)
    print(f"Preço atualizado para R$ {preco:.2f}")


def _pausar():
    item_id = input("ID do anúncio: ").strip()
    ml.pausar_anuncio(item_id)
    print("Anúncio pausado.")


def _reativar():
    item_id = input("ID do anúncio: ").strip()
    ml.reativar_anuncio(item_id)
    print("Anúncio reativado.")


if __name__ == "__main__":
    menu()
