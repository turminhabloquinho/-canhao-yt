"""Robo de postagem Instagram (Velisse). Le ig/fila.json, posta o que ja venceu, renova o token."""
import json, os, sys, time, base64, datetime
import requests

RAIZ = os.path.dirname(os.path.abspath(__file__))
FILA = os.path.join(RAIZ, "fila.json")
PUB = os.path.join(RAIZ, "publicados.json")
G = "https://graph.instagram.com/v25.0"
REPO = os.environ.get("GITHUB_REPOSITORY", "turminhabloquinho/-canhao-yt")
TOKEN = os.environ.get("IG_TOKEN", "").strip()
USER = os.environ.get("IG_USER_ID", "").strip()


def carregar(p, padrao):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else padrao


def postar(item):
    url = f"https://raw.githubusercontent.com/{REPO}/main/{item['arquivo']}"
    r = requests.post(f"{G}/{USER}/media", data={
        "media_type": "REELS", "video_url": url, "caption": item["legenda"],
        "share_to_feed": "true", "access_token": TOKEN}, timeout=60)
    r.raise_for_status()
    cid = r.json()["id"]
    for _ in range(40):  # ate ~10 min processando
        time.sleep(15)
        s = requests.get(f"{G}/{cid}", params={"fields": "status_code", "access_token": TOKEN}, timeout=30).json()
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {s}")
    else:
        raise RuntimeError("timeout processando video")
    p = requests.post(f"{G}/{USER}/media_publish", data={"creation_id": cid, "access_token": TOKEN}, timeout=60)
    p.raise_for_status()
    return p.json()["id"]


def renovar_token():
    """Renova o token de 60 dias e grava de volta no segredo IG_TOKEN do GitHub."""
    pat = os.environ.get("GH_PAT", "").strip()
    if not pat:
        print("sem GH_PAT: token nao renovado"); return
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": TOKEN}, timeout=30)
    if r.status_code != 200:
        print("renovacao falhou:", r.text[:200]); return
    novo = r.json()["access_token"]
    from nacl import encoding, public
    h = {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json"}
    k = requests.get(f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", headers=h, timeout=30).json()
    sb = public.SealedBox(public.PublicKey(k["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(sb.encrypt(novo.encode())).decode()
    u = requests.put(f"https://api.github.com/repos/{REPO}/actions/secrets/IG_TOKEN", headers=h,
                     json={"encrypted_value": enc, "key_id": k["key_id"]}, timeout=30)
    print("token renovado, segredo atualizado:", u.status_code)


def main():
    if not TOKEN or not USER:
        print("IG_TOKEN/IG_USER_ID ausentes: nada a fazer"); return 0
    fila = carregar(FILA, [])
    pub = carregar(PUB, {})
    hoje = datetime.datetime.utcnow().date().isoformat()
    falhou = False
    for item in fila:
        chave = item["arquivo"]
        if chave in pub or item["data"] > hoje:
            continue
        try:
            pub[chave] = {"id": postar(item), "em": datetime.datetime.utcnow().isoformat()}
            print("postado:", chave)
        except Exception as e:
            print("FALHA", chave, e); falhou = True
        json.dump(pub, open(PUB, "w", encoding="utf-8"), indent=1)
    renovar_token()
    return 1 if falhou else 0


if __name__ == "__main__":
    sys.exit(main())
