"""Robô do canal: autoriza, configura o canal e publica os episódios.

  python youtube_bot.py auth          # 1x: gera token.json a partir do client_secret.json
  python youtube_bot.py configurar    # descrição, palavras-chave, país, "feito para crianças", playlists, banner, marca d'água
  python youtube_bot.py publicar 1    # publica o próximo episódio pendente (+ o Short dele)
  python youtube_bot.py status
"""
import json, os, sys
import motor
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

RAIZ = motor.RAIZ
ESCOPOS = ["https://www.googleapis.com/auth/youtube"]
SEGREDO = os.path.join(RAIZ, "client_secret.json")
TOKEN = os.path.join(RAIZ, "token.json")
PUBLICADOS = os.path.join(RAIZ, "conteudo", "publicados.json")
CANAL = json.load(open(os.path.join(RAIZ, "canal.json"), encoding="utf-8"))


def auth():
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")  # redirect para localhost
    flow = Flow.from_client_secrets_file(SEGREDO, ESCOPOS, redirect_uri="http://localhost:8080/")
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    print("1) Abra este link, entre com a conta DONA do canal e autorize:\n\n" + url)
    print("\n2) O navegador vai abrir uma página que NÃO carrega (localhost). Copie o endereço inteiro dela e cole aqui:")
    resposta = input("> ").strip()
    flow.fetch_token(authorization_response=resposta)
    open(TOKEN, "w").write(flow.credentials.to_json())
    print("ok: token.json salvo")


def cliente():
    cred = Credentials.from_authorized_user_file(TOKEN, ESCOPOS)
    if not cred.valid:
        cred.refresh(Request())
        open(TOKEN, "w").write(cred.to_json())
    return build("youtube", "v3", credentials=cred)


def playlists(yt):
    existentes, req = {}, yt.playlists().list(part="snippet", mine=True, maxResults=50)
    while req:
        r = req.execute()
        existentes.update({p["snippet"]["title"]: p["id"] for p in r["items"]})
        req = yt.playlists().list_next(req, r)
    return existentes


def configurar():
    yt = cliente()
    canal = yt.channels().list(part="brandingSettings,status", mine=True).execute()["items"][0]
    print("canal:", canal["id"], canal["brandingSettings"]["channel"].get("title"))
    b = canal["brandingSettings"]
    b["channel"].update({
        "description": CANAL["descricao"],
        "keywords": " ".join(f'"{k}"' if " " in k else k for k in CANAL["palavras_chave"]),
        "country": CANAL["pais"],
        "defaultLanguage": CANAL["idioma"],
    })
    banner = os.path.join(RAIZ, "assets", "banner.png")
    if os.path.exists(banner):
        r = yt.channelBanners().insert(media_body=MediaFileUpload(banner)).execute()
        b.setdefault("image", {})["bannerExternalUrl"] = r["url"]
    yt.channels().update(part="brandingSettings", body={"id": canal["id"], "brandingSettings": b}).execute()
    yt.channels().update(part="status", body={"id": canal["id"], "status": {
        "selfDeclaredMadeForKids": CANAL["feito_para_criancas"]}}).execute()
    print("ok: descrição, palavras-chave, país, idioma, banner e 'feito para crianças'")

    marca = os.path.join(RAIZ, "assets", "marca.png")
    if os.path.exists(marca):
        try:
            yt.watermarks().set(channelId=canal["id"], media_body=MediaFileUpload(marca), body={
                "timing": {"type": "offsetFromStart", "offsetMs": 0}, "position": {"type": "corner", "cornerPosition": "bottomRight"}}).execute()
            print("ok: marca d'água")
        except HttpError as e:
            print("aviso: marca d'água não aplicada:", e.reason)
        except ValueError:  # resposta vazia (204) quebra o httplib2; o envio já foi aceito
            print("ok: marca d'água")

    existentes = playlists(yt)
    for p in CANAL["playlists"]:
        if p["titulo"] not in existentes:
            yt.playlists().insert(part="snippet,status", body={
                "snippet": {"title": p["titulo"], "description": p["descricao"], "defaultLanguage": CANAL["idioma"]},
                "status": {"privacyStatus": "public"}}).execute()
            print("ok: playlist criada:", p["titulo"])


def descricao(ep, short=False):
    letra = ep.get("letra") or ""
    tags = " ".join("#" + t.replace(" ", "").replace("-", "") for t in ep["tags"][:3])
    return (f"{ep['titulo'].split('|')[0].strip()} 🎶\n\n"
            f"Cante junto com a Turminha do Bloquinho! Música infantil educativa para bebês e crianças de 1 a 5 anos.\n\n"
            f"🎵 LETRA:\n{letra}\n\n"
            f"🧱 Turminha do Bloquinho: vídeo novo todos os dias!\n"
            f"Música e animação originais. Conteúdo criado com auxílio de ferramentas digitais.\n\n"
            f"{tags} #musicainfantil {'#shorts' if short else '#desenhoinfantil'}")[:4900]


def enviar(yt, caminho, titulo, desc, tags, miniatura=None):
    corpo = {
        "snippet": {"title": titulo[:100], "description": desc, "tags": tags, "categoryId": "27",
                    "defaultLanguage": "pt-BR", "defaultAudioLanguage": "pt-BR"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": True, "containsSyntheticMedia": False},
    }
    req = yt.videos().insert(part="snippet,status", body=corpo,
                             media_body=MediaFileUpload(caminho, chunksize=8 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if miniatura and os.path.exists(miniatura):
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(miniatura)).execute()
        except HttpError as e:
            print("aviso: miniatura não aplicada (verifique o telefone do canal):", e.reason)
    print("publicado:", titulo, "https://youtu.be/" + vid)
    return vid


def publicar(qtd=1):
    yt = cliente()
    cal = json.load(open(motor.CAL, encoding="utf-8"))
    pub = json.load(open(PUBLICADOS)) if os.path.exists(PUBLICADOS) else {}
    lista_pl = playlists(yt)
    feitos = 0
    for ep in cal:
        if feitos >= qtd:
            break
        chave = str(ep["id"])
        if chave in pub or not (ep.get("letra") or "compila" in ep["tema"]):
            continue
        base = os.path.join(RAIZ, "saida", f"ep{ep['id']:02d}")
        if not os.path.exists(base + ".mp4"):
            if "compila" in ep["tema"]:
                motor.compilar(ep, cal, 60 if "ninar" in ep["tema"] else 30)
            else:
                motor.render(ep)
                motor.render(ep, vertical=True, limite=6)
        vid = enviar(yt, base + ".mp4", ep["titulo"], descricao(ep), ep["tags"], base + ".jpg")
        if ep["playlist"] in lista_pl:
            yt.playlistItems().insert(part="snippet", body={"snippet": {
                "playlistId": lista_pl[ep["playlist"]], "resourceId": {"kind": "youtube#video", "videoId": vid}}}).execute()
        registro = {"video": vid}
        if os.path.exists(base + "_short.mp4"):
            titulo_s = ep["titulo"].split("|")[0].strip() + " #shorts"
            registro["short"] = enviar(yt, base + "_short.mp4", titulo_s, descricao(ep, True), ep["tags"])
        pub[chave] = registro
        json.dump(pub, open(PUBLICADOS, "w"), indent=2)
        feitos += 1
    if not feitos:
        print("nada pendente: adicione novos episódios em conteudo/calendario.json")


def status():
    cal = json.load(open(motor.CAL, encoding="utf-8"))
    pub = json.load(open(PUBLICADOS)) if os.path.exists(PUBLICADOS) else {}
    print(f"episódios: {len(cal)} | publicados: {len(pub)} | restam: {len(cal) - len(pub)} dias de conteúdo")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"auth": auth, "configurar": configurar, "status": status,
     "publicar": lambda: publicar(int(sys.argv[2]) if len(sys.argv) > 2 else 1)}[cmd]()
