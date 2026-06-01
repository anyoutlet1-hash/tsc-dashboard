"""
Dashboard TSC Shop — Promoções
Execute: py dashboard.py
Acesse: http://localhost:5000
"""

import time
import json
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests as req
from flask import Flask, jsonify, render_template_string

from auth import get_valid_token

app = Flask(__name__)

BASE = "https://api.mercadolibre.com"
USER_ID = 48980675
MAX_WORKERS = 10

_token_cache = None


def _headers():
    global _token_cache
    if not _token_cache:
        _token_cache = get_valid_token()
    return {"Authorization": f"Bearer {_token_cache}"}


def _get(path, params=None, retries=3):
    for attempt in range(retries):
        try:
            r = req.get(f"{BASE}{path}", headers=_headers(), params=params, timeout=15)
            if r.status_code == 401:
                global _token_cache
                _token_cache = None
                _headers()
                continue
            if r.status_code == 429:
                time.sleep(2 ** (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            if attempt == retries - 1:
                return None
            time.sleep(1)


def _fetch_item_promos(item_id):
    data = _get(f"/seller-promotions/items/{item_id}", params={"app_version": "v2"})
    started, pending, price_matching = [], [], []
    if data:
        items = data if isinstance(data, list) else data.get("results", [])
        for p in items:
            s = p.get("status")
            if p.get("type") == "PRICE_MATCHING" and s in ("started", "candidate"):
                price_matching.append(p)
            if s == "started":
                started.append(p)
            elif s in ("pending", "candidate"):
                pending.append(p)
    return item_id, started, pending, price_matching


def carregar_dados():
    # Promoções do seller
    promos_started, promos_pending = {}, {}
    offset = 0
    while True:
        data = _get(f"/seller-promotions/users/{USER_ID}", params={"app_version": "v2", "limit": 50, "offset": offset})
        if not data:
            break
        results = data.get("results", [])
        if not results:
            break
        for p in results:
            pid = p.get("id")
            st = p.get("status")
            if st in ("started", "candidate"):
                promos_started[pid] = p
            elif st == "pending":
                promos_pending[pid] = p
        if len(results) < 50:
            break
        offset += 50

    # Todos os itens
    todos = []
    params = {"search_type": "scan", "limit": 100}
    while True:
        data = _get(f"/users/{USER_ID}/items/search", params=params)
        if not data:
            break
        ids = data.get("results", [])
        todos.extend(ids)
        scroll_id = data.get("scroll_id")
        if not scroll_id or not ids:
            break
        params = {"search_type": "scan", "scroll_id": scroll_id, "limit": 100}

    # Promos por item (paralelo)
    item_promos_started = defaultdict(list)
    item_promos_pending = defaultdict(list)
    item_price_matching = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_fetch_item_promos, iid): iid for iid in todos}
        for f in as_completed(futures):
            item_id, started, pending, price_matching = f.result()
            for p in started:
                item_promos_started[item_id].append(p)
            for p in pending:
                item_promos_pending[item_id].append(p)
            if price_matching:
                item_price_matching[item_id] = price_matching[0]

    # Merge seller-level
    all_seller_promos = {**promos_started, **promos_pending}
    for item_id, promos in item_promos_started.items():
        for p in promos:
            pid = p.get("id")
            if pid and pid in all_seller_promos:
                seller_p = all_seller_promos[pid]
                if not p.get("finish_date") and seller_p.get("finish_date"):
                    p["finish_date"] = seller_p["finish_date"]

    for pid, promo in promos_started.items():
        for i in promo.get("items", []):
            iid = i.get("item_id") or i.get("id")
            if iid and promo not in item_promos_started[iid]:
                item_promos_started[iid].append(promo)

    # Títulos
    titulos = {}
    for i in range(0, len(todos), 20):
        batch = todos[i:i+20]
        data = _get("/items", params={"ids": ",".join(batch), "attributes": "id,title,price,catalog_listing,catalog_product_id"})
        if data:
            for item in (data if isinstance(data, list) else []):
                body = item.get("body", item)
                if body:
                    titulos[body.get("id")] = {
                        "title": body.get("title", ""),
                        "price": body.get("price", 0),
                        "catalog_listing": body.get("catalog_listing", False),
                        "catalog_product_id": body.get("catalog_product_id", ""),
                    }

    # Montar rows
    rows = []
    for item_id, promos in item_promos_started.items():
        info = titulos.get(item_id, {})
        titulo = info.get("title", item_id)
        preco_orig = info.get("price", 0)

        datas_fim = []
        for p in promos:
            fd = p.get("finish_date") or p.get("end_time")
            if fd:
                try:
                    dt = datetime.fromisoformat(fd.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    datas_fim.append(dt)
                except Exception:
                    pass

        earliest_finish = min(datas_fim) if datas_fim else None
        latest_finish = max(datas_fim) if datas_fim else None

        pendentes = item_promos_pending.get(item_id, [])
        has_continuity = bool(pendentes) or len(set(str(d) for d in datas_fim)) > 1 or any(
            p.get("status") == "candidate" for p in promos
        )

        promo_names = [p.get("name") or p.get("type", "?") for p in promos]
        preco_promo = min((p.get("new_price") or p.get("offer_price") or preco_orig for p in promos), default=preco_orig)
        desconto = round((1 - preco_promo / preco_orig) * 100, 1) if preco_orig else 0
        proximas = [p.get("name") or p.get("type", "?") for p in pendentes]

        now = datetime.now(timezone.utc)
        dias_restantes = None
        if earliest_finish:
            dias_restantes = (earliest_finish - now).days

        rows.append({
            "item_id": item_id,
            "titulo": titulo,
            "promo_ativa": ", ".join(set(promo_names)),
            "preco_orig": preco_orig,
            "preco_promo": preco_promo,
            "desconto": desconto,
            "fim_promo": earliest_finish.strftime("%d/%m/%Y") if earliest_finish else "-",
            "cobertura_ate": latest_finish.strftime("%d/%m/%Y") if latest_finish else "-",
            "continuidade": "SIM" if has_continuity else "NAO",
            "proximas": ", ".join(proximas) if proximas else "-",
            "dias_restantes": dias_restantes,
            "_earliest": earliest_finish or datetime.max.replace(tzinfo=timezone.utc),
            "_catalog_product_id": info.get("catalog_product_id", ""),
            "_catalog_listing": info.get("catalog_listing", False),
        })

    # Deduplicar
    grupos = defaultdict(list)
    sem_catalogo_id = []
    for r in rows:
        if r["_catalog_product_id"]:
            grupos[r["_catalog_product_id"]].append(r)
        else:
            sem_catalogo_id.append(r)
    rows_dedup = sem_catalogo_id[:]
    for cpid, grupo in grupos.items():
        catalogo = [r for r in grupo if r["_catalog_listing"]]
        rows_dedup.append(catalogo[0] if catalogo else grupo[0])

    rows_dedup.sort(key=lambda x: x["_earliest"])

    # Itens sem promoção vendidos 30d
    data_30d = (date.today() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00.000-03:00")
    itens_vendidos_30d = set()
    offset_v = 0
    while True:
        data_v = _get("/orders/search", params={"seller": USER_ID, "order.date_created.from": data_30d, "order.status": "paid", "limit": 50, "offset": offset_v})
        if not data_v:
            break
        orders = data_v.get("results", [])
        for o in orders:
            for oi in o.get("order_items", []):
                iid = oi.get("item", {}).get("id")
                if iid:
                    itens_vendidos_30d.add(iid)
        total_v = data_v.get("paging", {}).get("total", 0)
        offset_v += 50
        if offset_v >= total_v:
            break

    itens_com_promo = set(item_promos_started.keys())
    sem_promo = [
        {"item_id": iid, "titulo": titulos.get(iid, {}).get("title", iid), "preco": titulos.get(iid, {}).get("price", 0)}
        for iid in itens_vendidos_30d if iid not in itens_com_promo
    ]
    sem_promo.sort(key=lambda x: x["titulo"])

    return {
        "atualizado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "total_em_promo": len(rows_dedup),
        "com_continuidade": sum(1 for r in rows_dedup if r["continuidade"] == "SIM"),
        "sem_continuidade": sum(1 for r in rows_dedup if r["continuidade"] == "NAO"),
        "sem_promo_count": len(sem_promo),
        "promocoes": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows_dedup],
        "sem_promo": sem_promo[:50],
    }


HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TSC Shop — Promoções</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #f0f2f5; color: #333; }
  header { background: #1a1a2e; color: white; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 20px; font-weight: 600; }
  #atualizado { font-size: 13px; color: #aaa; margin-top: 4px; }
  .btn { background: #e94560; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600; transition: background 0.2s; }
  .btn:hover { background: #c73652; }
  .btn:disabled { background: #888; cursor: not-allowed; }
  .cards { display: flex; gap: 16px; padding: 20px 24px; flex-wrap: wrap; }
  .card { background: white; border-radius: 10px; padding: 20px 24px; flex: 1; min-width: 160px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .card .label { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
  .card .valor { font-size: 32px; font-weight: 700; }
  .card.azul .valor { color: #1a73e8; }
  .card.verde .valor { color: #34a853; }
  .card.vermelho .valor { color: #ea4335; }
  .card.cinza .valor { color: #777; }
  .section { padding: 0 24px 24px; }
  .section h2 { font-size: 16px; font-weight: 600; margin-bottom: 12px; color: #444; }
  table { width: 100%; border-collapse: collapse; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); font-size: 13px; }
  th { background: #1a1a2e; color: white; padding: 10px 12px; text-align: left; font-weight: 600; white-space: nowrap; }
  td { padding: 9px 12px; border-bottom: 1px solid #f0f0f0; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #f8f9ff; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
  .badge.sim { background: #e6f4ea; color: #2e7d32; }
  .badge.nao { background: #fce8e6; color: #c62828; }
  .badge.aviso { background: #fff3e0; color: #e65100; }
  .spinner { display: none; width: 18px; height: 18px; border: 3px solid #fff; border-top-color: transparent; border-radius: 50%; animation: spin 0.7s linear infinite; margin-left: 8px; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .tabs { display: flex; gap: 8px; margin-bottom: 12px; }
  .tab { padding: 7px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; border: 1px solid #ddd; background: white; }
  .tab.active { background: #1a1a2e; color: white; border-color: #1a1a2e; }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .filtro { margin-bottom: 12px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .filtro input { padding: 7px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; width: 280px; }
  .filtro select { padding: 7px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; }
  .alerta-row td { background: #fff5f5 !important; }
  #loading-msg { text-align: center; padding: 40px; color: #888; font-size: 14px; display: none; }
</style>
</head>
<body>
<header>
  <div>
    <h1>TSC Shop — Promoções</h1>
    <div id="atualizado">Clique em Atualizar para carregar os dados</div>
  </div>
  <button class="btn" id="btn-atualizar" onclick="atualizar()">
    Atualizar <span class="spinner" id="spinner"></span>
  </button>
</header>

<div class="cards">
  <div class="card azul"><div class="label">Em Promoção</div><div class="valor" id="c-total">—</div></div>
  <div class="card verde"><div class="label">Com Continuidade</div><div class="valor" id="c-sim">—</div></div>
  <div class="card vermelho"><div class="label">Sem Continuidade</div><div class="valor" id="c-nao">—</div></div>
  <div class="card cinza"><div class="label">Vendidos sem Promo (30d)</div><div class="valor" id="c-sem">—</div></div>
</div>

<div class="section">
  <div class="tabs">
    <div class="tab active" onclick="trocarAba('promo')">Participando</div>
    <div class="tab" onclick="trocarAba('alerta')">Sem Continuidade</div>
    <div class="tab" onclick="trocarAba('sem')">Sem Promoção</div>
  </div>

  <div id="loading-msg">Carregando dados, aguarde (pode levar 2-3 minutos)...</div>

  <div id="tab-promo" class="tab-content active">
    <div class="filtro">
      <input type="text" id="busca-promo" placeholder="Filtrar por título ou ID..." oninput="filtrarTabela('tabela-promo','busca-promo')">
      <select id="filtro-cont" onchange="filtrarTabela('tabela-promo','busca-promo')">
        <option value="">Todos</option>
        <option value="SIM">Com continuidade</option>
        <option value="NAO">Sem continuidade</option>
      </select>
    </div>
    <table id="tabela-promo">
      <thead><tr>
        <th>Item ID</th><th>Título</th><th>Promoção</th>
        <th>Preço Orig</th><th>Preço Promo</th><th>Desc %</th>
        <th>Fim</th><th>Cobertura Até</th><th>Dias Rest.</th><th>Continuidade</th>
      </tr></thead>
      <tbody id="tbody-promo"><tr><td colspan="10" style="text-align:center;color:#aaa;padding:30px">Clique em Atualizar</td></tr></tbody>
    </table>
  </div>

  <div id="tab-alerta" class="tab-content">
    <table id="tabela-alerta">
      <thead><tr>
        <th>Item ID</th><th>Título</th><th>Promoção Ativa</th>
        <th>Preço Orig</th><th>Preço Promo</th><th>Desc %</th><th>Fim Cobertura</th>
      </tr></thead>
      <tbody id="tbody-alerta"><tr><td colspan="7" style="text-align:center;color:#aaa;padding:30px">Clique em Atualizar</td></tr></tbody>
    </table>
  </div>

  <div id="tab-sem" class="tab-content">
    <div class="filtro">
      <input type="text" id="busca-sem" placeholder="Filtrar por título ou ID..." oninput="filtrarTabela('tabela-sem','busca-sem')">
    </div>
    <table id="tabela-sem">
      <thead><tr><th>Item ID</th><th>Título</th><th>Preço Atual</th></tr></thead>
      <tbody id="tbody-sem"><tr><td colspan="3" style="text-align:center;color:#aaa;padding:30px">Clique em Atualizar</td></tr></tbody>
    </table>
  </div>
</div>

<script>
let dadosGlobais = null;

function trocarAba(aba) {
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  const abas = ['promo','alerta','sem'];
  const idx = abas.indexOf(aba);
  document.querySelectorAll('.tab')[idx].classList.add('active');
  document.getElementById('tab-' + aba).classList.add('active');
}

function fmt(v) { return 'R$ ' + parseFloat(v||0).toFixed(2).replace('.',','); }

function renderizar(dados) {
  document.getElementById('c-total').textContent = dados.total_em_promo;
  document.getElementById('c-sim').textContent = dados.com_continuidade;
  document.getElementById('c-nao').textContent = dados.sem_continuidade;
  document.getElementById('c-sem').textContent = dados.sem_promo_count;
  document.getElementById('atualizado').textContent = 'Atualizado em: ' + dados.atualizado_em;

  // Tabela principal
  const tb = document.getElementById('tbody-promo');
  tb.innerHTML = '';
  dados.promocoes.forEach(r => {
    const alerta = r.continuidade === 'NAO' && r.dias_restantes !== null && r.dias_restantes <= 3;
    const tr = document.createElement('tr');
    if (alerta) tr.className = 'alerta-row';
    const diasCell = r.dias_restantes !== null
      ? `<span class="badge ${r.dias_restantes <= 3 ? 'aviso' : 'sim'}">${r.dias_restantes}d</span>`
      : '-';
    const contBadge = `<span class="badge ${r.continuidade === 'SIM' ? 'sim' : 'nao'}">${r.continuidade}</span>`;
    tr.innerHTML = `<td><a href="https://www.mercadolivre.com.br/anuncio/${r.item_id}" target="_blank">${r.item_id}</a></td>
      <td>${r.titulo}</td><td>${r.promo_ativa}</td>
      <td>${fmt(r.preco_orig)}</td><td>${fmt(r.preco_promo)}</td>
      <td>${r.desconto}%</td><td>${r.fim_promo}</td><td>${r.cobertura_ate}</td>
      <td>${diasCell}</td><td>${contBadge}</td>`;
    tb.appendChild(tr);
  });

  // Tabela alerta
  const ta = document.getElementById('tbody-alerta');
  ta.innerHTML = '';
  const alertas = dados.promocoes.filter(r => r.continuidade === 'NAO');
  if (!alertas.length) {
    ta.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#2e7d32;padding:30px">Todos com continuidade!</td></tr>';
  } else {
    alertas.forEach(r => {
      const tr = document.createElement('tr');
      tr.className = 'alerta-row';
      tr.innerHTML = `<td><a href="https://www.mercadolivre.com.br/anuncio/${r.item_id}" target="_blank">${r.item_id}</a></td>
        <td>${r.titulo}</td><td>${r.promo_ativa}</td>
        <td>${fmt(r.preco_orig)}</td><td>${fmt(r.preco_promo)}</td>
        <td>${r.desconto}%</td><td>${r.cobertura_ate}</td>`;
      ta.appendChild(tr);
    });
  }

  // Tabela sem promoção
  const ts = document.getElementById('tbody-sem');
  ts.innerHTML = '';
  dados.sem_promo.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td><a href="https://www.mercadolivre.com.br/anuncio/${r.item_id}" target="_blank">${r.item_id}</a></td>
      <td>${r.titulo}</td><td>${fmt(r.preco)}</td>`;
    ts.appendChild(tr);
  });
}

function filtrarTabela(tabId, inputId) {
  const busca = document.getElementById(inputId).value.toLowerCase();
  const filtCont = document.getElementById('filtro-cont');
  const filtContVal = filtCont ? filtCont.value : '';
  const rows = document.querySelectorAll('#' + tabId + ' tbody tr');
  rows.forEach(tr => {
    const txt = tr.textContent.toLowerCase();
    const contMatch = !filtContVal || txt.includes(filtContVal.toLowerCase());
    tr.style.display = txt.includes(busca) && contMatch ? '' : 'none';
  });
}

async function atualizar() {
  const btn = document.getElementById('btn-atualizar');
  const spinner = document.getElementById('spinner');
  const loadMsg = document.getElementById('loading-msg');
  btn.disabled = true;
  spinner.style.display = 'inline-block';
  loadMsg.style.display = 'block';
  try {
    const res = await fetch('/api/dados');
    const dados = await res.json();
    dadosGlobais = dados;
    renderizar(dados);
  } catch(e) {
    alert('Erro ao carregar dados: ' + e.message);
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    loadMsg.style.display = 'none';
  }
}
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/dados")
def api_dados():
    dados = carregar_dados()
    return jsonify(dados)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    print(f"\nDashboard TSC Shop iniciando na porta {port}...")
    app.run(debug=False, host="0.0.0.0", port=port)
