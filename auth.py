"""
Fluxo OAuth2 do Mercado Livre.
Abre o navegador para autorização e pede que o usuário cole a URL de retorno.
"""

import json
import webbrowser
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import requests

from config import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, TOKEN_FILE

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"


def authorize():
    """Inicia o fluxo OAuth2 e retorna os tokens."""
    url = (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )

    print(f"\nAbrindo navegador para autorização do Mercado Livre...")
    print(f"\nSe o navegador não abrir, acesse manualmente:\n{url}\n")
    webbrowser.open(url)

    print("Após autorizar, você será redirecionado para https://tscshop.com.br")
    print("(a página pode não carregar — isso é normal)\n")
    callback_url = input("Cole aqui a URL completa da barra do navegador: ").strip()

    params = parse_qs(urlparse(callback_url).query)
    if "code" not in params:
        raise RuntimeError("Código de autorização não encontrado na URL. Tente novamente.")

    code = params["code"][0]
    print("Código obtido. Trocando por tokens de acesso...")
    return _exchange_code(code)


def _exchange_code(code):
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    tokens = resp.json()
    tokens["expires_at"] = (
        datetime.now() + timedelta(seconds=tokens["expires_in"])
    ).isoformat()
    _save(tokens)
    print("Tokens salvos com sucesso.")
    return tokens


def refresh():
    tokens = load()
    if not tokens or "refresh_token" not in tokens:
        raise RuntimeError("Sem refresh_token. Execute authorize() primeiro.")
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": tokens["refresh_token"],
        },
    )
    resp.raise_for_status()
    new_tokens = resp.json()
    new_tokens["expires_at"] = (
        datetime.now() + timedelta(seconds=new_tokens["expires_in"])
    ).isoformat()
    _save(new_tokens)
    return new_tokens


def get_valid_token():
    """Retorna um access_token válido, renovando se necessário."""
    tokens = load()
    if not tokens:
        raise RuntimeError("Não autenticado. Execute: py auth.py")
    expires_at = datetime.fromisoformat(tokens["expires_at"])
    if datetime.now() >= expires_at - timedelta(minutes=5):
        tokens = refresh()
    return tokens["access_token"]


def load():
    import os
    # Tenta arquivo local primeiro
    try:
        with open(TOKEN_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        pass
    # Fallback: variáveis de ambiente (Railway/nuvem)
    refresh_token = os.environ.get("ML_REFRESH_TOKEN")
    if refresh_token:
        return {
            "access_token": os.environ.get("ML_ACCESS_TOKEN", ""),
            "refresh_token": refresh_token,
            "expires_at": "2000-01-01T00:00:00",  # força renovação
        }
    return None


def _save(tokens):
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


if __name__ == "__main__":
    authorize()
    print("\nAutenticação concluída! Agora execute: py tsc_shop.py")
