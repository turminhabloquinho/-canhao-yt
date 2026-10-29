"""Motor de vídeo da Turminha do Bloquinho — custo zero.

Gera música original (síntese) + animação dos personagens + letra karaokê,
em 16:9 (vídeo longo) e 9:16 (Short), mais a miniatura.

Uso:  python motor.py 1            # renderiza o episódio 1
      python motor.py 1 2 3 --short
      python motor.py todos
Voz opcional: coloque voz/ep01.wav (gravada no ritmo de 100 BPM) e ela é mixada.
"""
import json, math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(RAIZ, "conteudo", "calendario.json")
SR, FPS, BPM = 44100, 30, 100
BEAT = 60 / BPM
LINHA_BEATS = 8                     # cada verso dura 2 compassos
INTRO_BEATS, OUTRO_BEATS = 8, 8
FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

PERSONAGENS = [  # nome, cor, palavras que o colocam em destaque
    ("Bloquinho", (230, 57, 70), ("vermelh", "bloquinho", "morango", "maçã", "papai")),
    ("Amarelinha", (255, 196, 0), ("amarel", "sol", "banana", "mamãe", "estrel")),
    ("Azulzinho", (40, 120, 230), ("azul", "céu", "mar", "irmão", "lua", "peix")),
    ("Verdinho", (46, 184, 92), ("verd", "grama", "floresta", "sapo", "irmã", "bebê")),
]

# ---------------------------------------------------------------- música ----
NOTAS = {n: i for i, n in enumerate("C C# D D# E F F# G G# A A# B".split())}

def freq(nome, oit):
    return 440.0 * 2 ** ((NOTAS[nome] + 12 * (oit + 1) - 69) / 12)

PROGRESSAO = [("C", "E", "G"), ("G", "B", "D"), ("A", "C", "E"), ("F", "A", "C")]  # I V vi IV
PENTA = ["C", "D", "E", "G", "A"]

def env(n, a=0.01, r=0.25):
    t = np.arange(n) / SR
    e = np.minimum(1, t / a) * np.exp(-t / r)
    return e

def tom(f, dur, forma="tri", vol=0.3, r=0.25):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if forma == "tri":
        w = 2 * np.abs(2 * ((t * f) % 1) - 1) - 1
    elif forma == "sq":
        w = np.sign(np.sin(2 * np.pi * f * t)) * 0.5
    else:
        w = np.sin(2 * np.pi * f * t)
    return w * env(n, r=r) * vol

def kick():
    n = int(0.25 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * (120 * np.exp(-t * 20) + 40) * t) * np.exp(-t * 12) * 0.9

def ruido(dur, decai, vol):
    n = int(dur * SR); rng = np.random.default_rng(7)
    return rng.uniform(-1, 1, n) * np.exp(-np.arange(n) / SR * decai) * vol

def somar(buf, sinal, inicio):
    i = int(inicio * SR); j = min(len(buf), i + len(sinal))
    if i < len(buf):
        buf[i:j] += sinal[: j - i]

def musica(n_linhas, seed):
    total_beats = INTRO_BEATS + n_linhas * LINHA_BEATS + OUTRO_BEATS
    dur = total_beats * BEAT
    buf = np.zeros(int(dur * SR) + SR)
    rng = np.random.default_rng(seed)
    # motivo melódico original por episódio (2 compassos), repetido com variações
    motivos = [[PENTA[rng.integers(0, 5)] for _ in range(8)] for _ in range(2)]
    for b in range(total_beats):
        t = b * BEAT
        compasso = b // 4
        acorde = PROGRESSAO[compasso % 4]
        somar(buf, kick(), t) if b % 2 == 0 else somar(buf, ruido(0.18, 25, 0.25), t)
        somar(buf, ruido(0.05, 80, 0.08), t + BEAT / 2)                     # chimbal
        somar(buf, tom(freq(acorde[0], 2), BEAT * 0.9, "sin", 0.35, 0.4), t)  # baixo
        if b % 4 == 0:
            for nota in acorde:
                somar(buf, tom(freq(nota, 4), BEAT * 4, "sin", 0.07, 1.2), t)  # pad
        if INTRO_BEATS <= b < total_beats - OUTRO_BEATS:
            mot = motivos[(compasso // 2) % 2]
            nota = mot[b % 8]
            if (b + compasso) % 7 == 6:
                nota = acorde[0]
            somar(buf, tom(freq(nota, 5), BEAT * 0.45, "tri", 0.16, 0.18), t)
            somar(buf, tom(freq(mot[(b + 3) % 8], 5), BEAT * 0.4, "tri", 0.10, 0.15), t + BEAT / 2)
        else:  # intro/final: arpejo
            for k, nota in enumerate(acorde):
                somar(buf, tom(freq(nota, 5), BEAT * 0.3, "sq", 0.05, 0.1), t + k * BEAT / 3)
    return buf[: int(dur * SR)], dur

def salvar_wav(caminho, sinal):
    sinal = sinal / (np.max(np.abs(sinal)) + 1e-9) * 0.85
    pcm = (sinal * 32767).astype(np.int16)
    with wave.open(caminho, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())

def mixar_voz(sinal, caminho_voz):
    with wave.open(caminho_voz) as w:
        voz = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float) / 32767
        if w.getnchannels() == 2:
            voz = voz.reshape(-1, 2).mean(axis=1)
        if w.getframerate() != SR:
            idx = np.linspace(0, len(voz) - 1, int(len(voz) * SR / w.getframerate()))
            voz = np.interp(idx, np.arange(len(voz)), voz)
    sinal = sinal / (np.max(np.abs(sinal)) + 1e-9) * 0.45
    somar(sinal, voz * 0.9, 0)
    return sinal

# ----------------------------------------------------------------- vídeo ----
def fonte(px):
    return ImageFont.truetype(FONTE, px)

def quebrar(texto, fnt, largura, d):
    palavras, linhas, atual = texto.split(), [], ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        if d.textlength(teste, font=fnt) <= largura:
            atual = teste
        else:
            linhas.append(atual); atual = p
    return linhas + [atual] if atual else linhas

def personagem(d, cx, base, lado, cor, pulo, piscando, feliz):
    lado = int(lado)
    y = base - lado - pulo
    sombra = max(10, lado * 0.45 - pulo * 0.3)
    d.ellipse([cx - sombra, base - 8, cx + sombra, base + 8], fill=(60, 120, 60))
    d.rounded_rectangle([cx - lado / 2, y, cx + lado / 2, y + lado], radius=lado * 0.18,
                        fill=cor, outline=(40, 40, 60), width=max(3, lado // 40))
    # pinos de bloco de montar
    for k in (-1, 1):
        px = cx + k * lado * 0.22
        d.rounded_rectangle([px - lado * 0.12, y - lado * 0.1, px + lado * 0.12, y + 4],
                            radius=6, fill=cor, outline=(40, 40, 60), width=max(3, lado // 40))
    ey = y + lado * 0.38
    for k in (-1, 1):
        ex = cx + k * lado * 0.2
        if piscando:
            d.line([ex - lado * 0.08, ey, ex + lado * 0.08, ey], fill=(30, 30, 40), width=max(4, lado // 30))
        else:
            r = lado * 0.11
            d.ellipse([ex - r, ey - r, ex + r, ey + r], fill="white", outline=(30, 30, 40), width=3)
            r2 = r * 0.55
            d.ellipse([ex - r2, ey - r2 + 2, ex + r2, ey + r2 + 2], fill=(30, 30, 40))
            d.ellipse([ex - r2 * 0.3, ey - r2 * 0.6, ex + r2 * 0.3, ey], fill="white")
    boca = lado * (0.22 if feliz else 0.14)
    d.arc([cx - boca, y + lado * 0.5, cx + boca, y + lado * 0.5 + boca * 1.3], 10, 170,
          fill=(30, 30, 40), width=max(4, lado // 28))
    for k in (-1, 1):  # bochechas
        bx = cx + k * lado * 0.33
        d.ellipse([bx - lado * 0.06, y + lado * 0.55, bx + lado * 0.06, y + lado * 0.62], fill=(255, 150, 170))

def destaque(linha, idx):
    l = linha.lower()
    for i, (_, _, chaves) in enumerate(PERSONAGENS):
        if any(c in l for c in chaves):
            return i
    return idx % 4

def quadro(W, H, t, linhas, dur, titulo, nuvens):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 4):  # céu em degradê
        k = y / H
        d.rectangle([0, y, W, y + 4], fill=(int(120 + 100 * k), int(200 + 40 * k), 255))
    s = min(W, H)
    d.ellipse([W * 0.82, H * 0.05, W * 0.82 + s * 0.16, H * 0.05 + s * 0.16], fill=(255, 220, 60))
    for (nx, ny, nv) in nuvens:
        x = (nx * W + t * nv * 40) % (W + 400) - 200
        for dx, dy, r in ((0, 0, 50), (55, -20, 60), (115, 0, 48)):
            rr = r * s / 1080
            d.ellipse([x + dx * s / 1080 - rr, ny * H + dy - rr, x + dx * s / 1080 + rr, ny * H + dy + rr], fill="white")
    chao = H * (0.72 if W > H else 0.62)
    d.rectangle([0, chao, W, H], fill=(110, 200, 90))
    d.rectangle([0, chao, W, chao + 12], fill=(80, 170, 70))

    b = t / BEAT
    ini = INTRO_BEATS * BEAT
    i_linha = int((t - ini) // (LINHA_BEATS * BEAT)) if t >= ini else -1
    em_letra = 0 <= i_linha < len(linhas)
    ativo = destaque(linhas[i_linha], i_linha) if em_letra else int(b // 4) % 4

    lado = int(s * (0.2 if W > H else 0.17))
    for i, (_, cor, _) in enumerate(PERSONAGENS):
        cx = W * (0.2 + 0.2 * i)
        fase = (b + i * 0.5) % 1
        pulo = abs(math.sin(math.pi * fase)) * lado * (0.55 if i == ativo else 0.08)
        piscando = ((t + i * 0.7) % 3.3) < 0.12
        personagem(d, cx, chao + lado * 0.15, lado * (1.15 if i == ativo else 1.0), cor, pulo, piscando, i == ativo)

    # texto: título na intro, letra karaokê no meio, chamada no final
    caixa_y = H * (0.05 if W > H else 0.1)
    if em_letra:
        texto = linhas[i_linha]
        prog = ((t - ini) % (LINHA_BEATS * BEAT)) / (LINHA_BEATS * BEAT * 0.85)
    elif t < ini:
        texto, prog = titulo, 1.0
    else:
        texto, prog = "Tchau, tchau! Até o próximo vídeo! 👋".replace(" 👋", ""), 1.0
    fnt = fonte(int(s * (0.075 if W > H else 0.065)))
    partes = quebrar(texto, fnt, W * 0.86, d)
    alt = fnt.size * 1.25
    total = sum(len(p.split()) for p in partes)
    acesas = int(total * min(1, prog) + 0.999)
    bx0, by1 = W * 0.05, caixa_y + alt * len(partes) + 30
    d.rounded_rectangle([bx0, caixa_y, W - bx0, by1], radius=30, fill=(255, 255, 255), outline=(40, 40, 60), width=5)
    cont = 0
    for k, p in enumerate(partes):
        x = (W - d.textlength(p, font=fnt)) / 2
        y = caixa_y + 15 + k * alt
        for palavra in p.split():
            cor = PERSONAGENS[ativo][1] if cont < acesas else (60, 60, 80)
            d.text((x, y), palavra, font=fnt, fill=cor, stroke_width=2, stroke_fill=(40, 40, 60) if cont < acesas else (60, 60, 80))
            x += d.textlength(palavra + " ", font=fnt)
            cont += 1
    return img

def render(ep, vertical=False, limite=None):
    letra = ep.get("letra")
    if not letra:
        print(f"ep{ep['id']:02d}: sem letra ainda, pulando"); return None
    linhas = [l.strip() for l in letra.splitlines() if l.strip()]
    if limite:
        linhas = linhas[:limite]
    W, H = (1080, 1920) if vertical else (1920, 1080)
    sufixo = "_short" if vertical else ""
    os.makedirs(os.path.join(RAIZ, "saida"), exist_ok=True)
    base = os.path.join(RAIZ, "saida", f"ep{ep['id']:02d}{sufixo}")
    audio, dur = musica(len(linhas), seed=ep["id"])
    voz = os.path.join(RAIZ, "voz", f"ep{ep['id']:02d}.wav")
    if os.path.exists(voz) and not vertical:
        audio = mixar_voz(audio, voz)
    salvar_wav(base + ".wav", audio)
    titulo = re.sub(r"[^\w\sÀ-ú,!?.-]", "", ep["titulo"].split("|")[0]).strip()
    rng = np.random.default_rng(ep["id"])
    nuvens = [(rng.random(), 0.12 + rng.random() * 0.2, 0.5 + rng.random()) for _ in range(4)]
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", base + ".wav", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", base + ".mp4"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(int(dur * FPS)):
        proc.stdin.write(quadro(W, H, f / FPS, linhas, dur, titulo, nuvens).tobytes())
    proc.stdin.close(); proc.wait()
    os.remove(base + ".wav")
    if not vertical:
        miniatura(ep, titulo, nuvens, base + ".jpg")
    print(f"ok: {base}.mp4 ({dur:.0f}s)")
    return base + ".mp4"

def miniatura(ep, titulo, nuvens, caminho):
    W, H = 1280, 720
    img = quadro(W, H, INTRO_BEATS * BEAT + 1.0, ["x"], 1, "", nuvens)  # personagens em pose
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, H * 0.4], fill=(255, 255, 255))
    palavras = titulo.split()
    curto = " ".join(palavras[:3]).upper()
    fnt = fonte(120)
    while d.textlength(curto, font=fnt) > W * 0.92 and fnt.size > 40:
        fnt = fonte(fnt.size - 4)
    x = (W - d.textlength(curto, font=fnt)) / 2
    d.text((x, 60), curto, font=fnt, fill=(230, 57, 70), stroke_width=6, stroke_fill=(40, 40, 60))
    img.save(caminho, quality=92)

def compilar(ep, cal, minutos=30):
    """Junta os episódios já renderizados num vídeo longo (gera horas de exibição)."""
    eps = [e for e in cal if e["id"] != ep["id"] and "compila" not in e["tema"] and e.get("letra") and
           ("ninar" not in ep["tema"] or "ninar" in e["tema"] or "dominio publico: brilha" in e["tema"])]
    fontes = []
    for e in eps:
        f = os.path.join(RAIZ, "saida", f"ep{e['id']:02d}.mp4")
        if os.path.exists(f) or render(e):
            fontes.append(f)
    if not fontes:
        print("compilação: renderize os episódios antes"); return None
    durs = [float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", f]).decode()) for f in fontes]
    lista, total, i = [], 0.0, 0
    while total < minutos * 60:
        lista.append(fontes[i % len(fontes)]); total += durs[i % len(fontes)]; i += 1
    txt = os.path.join(RAIZ, "saida", f"lista{ep['id']:02d}.txt")
    open(txt, "w").write("".join(f"file '{f}'\n" for f in lista))
    saida = os.path.join(RAIZ, "saida", f"ep{ep['id']:02d}.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", txt,
                    "-c", "copy", saida], check=True)
    os.remove(txt)
    rng = np.random.default_rng(ep["id"])
    nuvens = [(rng.random(), 0.12 + rng.random() * 0.2, 0.5 + rng.random()) for _ in range(4)]
    miniatura(ep, "Compilação " + str(minutos) + " min", nuvens, saida[:-4] + ".jpg")
    print(f"ok: {saida} ({total / 60:.0f} min)")
    return saida

if __name__ == "__main__":
    cal = json.load(open(CAL, encoding="utf-8"))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    ids = [e["id"] for e in cal] if args == ["todos"] else [int(a) for a in args]
    for ep in cal:
        if ep["id"] in ids:
            if "compila" in ep["tema"]:
                compilar(ep, cal, 60 if "ninar" in ep["tema"] else 30)
            elif render(ep):
                if "--short" in sys.argv:
                    render(ep, vertical=True, limite=6)
