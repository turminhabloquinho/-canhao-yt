"""Robô da Velisse: publica os Shorts da fila no YouTube e copia as vendas do Stripe para a planilha.

Substitui os cenários do Make. Roda no GitHub Actions (ver .github/workflows/velisse-*.yml) ou no PC.

  python velisse/velisse_bot.py auth                         # 1x no PC: gera o token do Google (YouTube + Planilhas)
  python velisse/velisse_bot.py publicar 15 --url URL        # baixa o vídeo da linha N=15 da fila e agenda no YouTube
  python velisse/velisse_bot.py publicar 15                  # usa velisse/fila/15.mp4
  python velisse/velisse_bot.py pedidos                      # copia vendas novas do Stripe para a planilha

Segredos (no GitHub: Settings > Secrets and variables > Actions):
  VELISSE_GOOGLE_TOKEN  conteúdo do token gerado pelo comando auth
  STRIPE_API_KEY        chave restrita do Stripe (somente leitura de Checkout Sessions)
"""
import argparse, datetime, json, os, sys, tempfile, urllib.request
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PASTA = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(PASTA, "config.json"), encoding="utf-8"))
ESCOPOS = ["https://www.googleapis.com/auth/youtube", "https://www.googleapis.com/auth/spreadsheets"]
TOKEN = os.path.join(PASTA, "token.json")
SEGREDO = os.path.join(PASTA, "client_secret.json")
UTC = datetime.timezone.utc


# ---------- Google ----------
def auth():
    from google_auth_oauthlib.flow import Flow
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")
    flow = Flow.from_client_secrets_file(SEGREDO, ESCOPOS, redirect_uri="http://localhost:8080/")
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print("1) Abra o link, entre com a conta DONA do canal Velisse (glownest.business10) e autorize:\n\n" + url)
    print("\n2) A página final NÃO carrega (localhost). Copie o endereço inteiro dela e cole aqui:")
    flow.fetch_token(authorization_response=input("> ").strip())
    open(TOKEN, "w").write(flow.credentials.to_json())
    print("\nok: velisse/token.json criado. Copie TODO o conteúdo dele para o segredo VELISSE_GOOGLE_TOKEN no GitHub.")


def credenciais():
    bruto = os.environ.get("VELISSE_GOOGLE_TOKEN") or (open(TOKEN).read() if os.path.exists(TOKEN) else "")
    if not bruto:
        sys.exit("faltou o token do Google: rode 'auth' no PC ou configure o segredo VELISSE_GOOGLE_TOKEN")
    cred = Credentials.from_authorized_user_info(json.loads(bruto), ESCOPOS)
    if not cred.valid:
        cred.refresh(Request())
    return cred


def planilha(cred):
    return build("sheets", "v4", credentials=cred).spreadsheets().values()


# ---------- Publicar Shorts ----------
def quando_publicar(texto_data, forcado=None):
    """'05/11/2026 20:00 ET' (horário de Nova York) -> datetime UTC. Nunca no passado."""
    agora = datetime.datetime.now(UTC)
    if forcado:
        alvo = datetime.datetime.fromisoformat(forcado.replace("Z", "+00:00"))
    else:
        d = texto_data.replace("ET", "").strip()
        alvo = datetime.datetime.strptime(d, "%d/%m/%Y %H:%M").replace(tzinfo=ZoneInfo(CFG["fuso_fila"])).astimezone(UTC)
    if alvo < agora + datetime.timedelta(minutes=20):
        alvo = (agora + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
    return alvo


def descricao(base):
    if CFG["site"] in base:
        return base
    return f"{base}\n\nShop with free shipping anywhere in the USA: {CFG['site']}\n\n{CFG['aviso_ia']} {CFG['hashtags']}"[:4900]


def publicar(n, url=None, quando=None, forcar=False):
    cred = credenciais()
    linha = n + 1  # linha 1 = cabeçalho
    faixa = f"'{CFG['aba_fila']}'!A{linha}:J{linha}"
    v = planilha(cred).get(spreadsheetId=CFG["planilha_id"], range=faixa).execute().get("values", [[]])[0]
    v += [""] * (10 - len(v))
    _, data, _, titulo, desc, tags, *_resto = v
    if v[9] and not forcar:
        print(f"N={n} já tem ID no YouTube ({v[9]}); nada a fazer. Use --forcar para enviar de novo.")
        return
    if not titulo:
        sys.exit(f"linha {linha} da fila está vazia")

    arquivo_local = os.path.join(PASTA, "fila", f"{n}.mp4")
    if url:
        arquivo = os.path.join(tempfile.gettempdir(), f"velisse_{n}.mp4")
        urllib.request.urlretrieve(url, arquivo)
    elif os.path.exists(arquivo_local):
        arquivo = arquivo_local
    else:
        sys.exit(f"sem vídeo: passe --url ou coloque velisse/fila/{n}.mp4")

    alvo = quando_publicar(data, quando)
    yt = build("youtube", "v3", credentials=cred)
    corpo = {
        "snippet": {"title": titulo[:100], "description": descricao(desc),
                    "tags": [t.strip() for t in tags.split(",") if t.strip()][:30],
                    "categoryId": CFG["categoria_youtube"],
                    "defaultLanguage": CFG["idioma"], "defaultAudioLanguage": CFG["idioma"]},
        "status": {"privacyStatus": "private", "publishAt": alvo.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
    }
    req = yt.videos().insert(part="snippet,status", body=corpo,
                             media_body=MediaFileUpload(arquivo, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    planilha(cred).update(spreadsheetId=CFG["planilha_id"], range=f"'{CFG['aba_fila']}'!J{linha}",
                          valueInputOption="RAW", body={"values": [[vid]]}).execute()
    if arquivo == arquivo_local:
        os.remove(arquivo_local)
    print(f"ok: N={n} '{titulo}' programado para {alvo:%d/%m %H:%M} UTC -> https://youtu.be/{vid}")


# ---------- Pedidos do Stripe ----------
def stripe(caminho, **params):
    chave = os.environ.get("STRIPE_API_KEY") or sys.exit("faltou o segredo STRIPE_API_KEY")
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(f"https://api.stripe.com/v1/{caminho}?{qs}", headers={"Authorization": f"Bearer {chave}"})
    return json.load(urllib.request.urlopen(req))


def pedidos(dias=3):
    cred = credenciais()
    aba = f"'{CFG['aba_pedidos']}'"
    ja = {r[0] for r in planilha(cred).get(spreadsheetId=CFG["planilha_id"], range=f"{aba}!F2:F").execute().get("values", []) if r}
    desde = int((datetime.datetime.now(UTC) - datetime.timedelta(days=dias)).timestamp())
    novas, cursor = [], None
    while True:
        extra = {"starting_after": cursor} if cursor else {}
        r = stripe("checkout/sessions", limit=100, **{"created[gte]": desde}, status="complete", **extra)
        for s in r["data"]:
            if s["id"] in ja or s.get("payment_status") != "paid":
                continue
            cli = s.get("customer_details") or {}
            env = (s.get("collected_information") or {}).get("shipping_details") or s.get("shipping_details") or {}
            end = env.get("address") or cli.get("address") or {}
            endereco = ", ".join(x for x in [end.get("line1"), end.get("line2"), end.get("city"), end.get("state"),
                                             end.get("postal_code"), end.get("country")] if x)
            itens = stripe(f"checkout/sessions/{s['id']}/line_items", limit=10)["data"]
            produto = " + ".join(f"{i['quantity']}x {i['description']}" for i in itens)
            data = datetime.datetime.fromtimestamp(s["created"], ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
            novas.append([data, env.get("name") or cli.get("name", ""), cli.get("email", ""), endereco, cli.get("phone", "") or "",
                          s["id"], "", f"{produto} ({s.get('payment_link') or ''})", (s.get("amount_total") or 0) / 100])
        if not r.get("has_more"):
            break
        cursor = r["data"][-1]["id"]
    if novas:
        planilha(cred).append(spreadsheetId=CFG["planilha_id"], range=f"{aba}!A:I", valueInputOption="USER_ENTERED",
                              insertDataOption="INSERT_ROWS", body={"values": novas}).execute()
    print(f"ok: {len(novas)} venda(s) nova(s) copiada(s) para a planilha")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth")
    pp = sub.add_parser("publicar")
    pp.add_argument("n", type=int)
    pp.add_argument("--url")
    pp.add_argument("--quando", help="horário UTC ISO, ex.: 2026-11-10T01:00:00Z (padrão: data da fila)")
    pp.add_argument("--forcar", action="store_true")
    pe = sub.add_parser("pedidos")
    pe.add_argument("--dias", type=int, default=3)
    a = p.parse_args()
    if a.cmd == "auth":
        auth()
    elif a.cmd == "publicar":
        publicar(a.n, a.url, a.quando, a.forcar)
    else:
        pedidos(a.dias)
