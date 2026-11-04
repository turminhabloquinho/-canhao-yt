"""Voz da Turminha do Bloquinho com a API de fala do Gemini (plano gratuito, sem cartão).

Cada verso vira um áudio separado, guardado em cache (voz/epXX_lYY.wav), e é encaixado no
compasso em que a letra aparece na tela. Sem chave (gemini_key.txt) o vídeo sai só com música.
"""
import base64, json, os, subprocess, time, urllib.error, urllib.request, wave
import numpy as np

RAIZ = os.path.dirname(os.path.abspath(__file__))
CHAVE = os.path.join(RAIZ, "gemini_key.txt")
PASTA = os.path.join(RAIZ, "voz")
MODELO = "gemini-3.8-flash-tts"
VOZ = "Leda"
ESTILO = ""  # instrução de estilo no texto é lida em voz alta; a voz "Leda" já é jovem e alegre


def disponivel():
    return os.path.exists(CHAVE)


def _tts(texto):
    body = {"contents": [{"parts": [{"text": ESTILO + texto}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOZ}}}}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO}:generateContent",
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": open(CHAVE).read().strip(), "Content-Type": "application/json"})
    for tentativa in range(6):
        try:
            parte = json.load(urllib.request.urlopen(req, timeout=120))["candidates"][0]["content"]["parts"][0]
            return base64.b64decode(parte["inlineData"]["data"])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and tentativa < 5:
                time.sleep(30 * (tentativa + 1))  # limite por minuto do plano gratuito
                continue
            raise


def _ler(caminho, sr):
    """Lê o wav do cache já convertido para mono na taxa do motor."""
    pcm = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", caminho, "-f", "s16le", "-ac", "1",
                          "-ar", str(sr), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(pcm, dtype=np.int16).astype(float) / 32767


def _segmentos(som, sr, linhas):
    """Divide a narração em um trecho por verso. Cada corte cai na pausa mais próxima de onde o verso
    deveria terminar, estimado pelo número de letras de cada verso (pausas longas têm preferência)."""
    n = len(linhas)
    janela = int(0.02 * sr)
    energia = np.sqrt(np.convolve(som ** 2, np.ones(janela) / janela, mode="same"))
    falando = np.where(energia >= 0.02)[0]
    if len(falando) == 0:
        return None
    ini, fim = falando[0], falando[-1]
    calado = energia < 0.02
    pausas, k = [], ini
    while k < fim:
        if calado[k]:
            j = k
            while j < fim and calado[j]:
                j += 1
            if j - k >= int(0.08 * sr):
                pausas.append(((k + j) // 2, (j - k) / sr))
            k = j
        else:
            k += 1
    letras = np.cumsum([len(l) for l in linhas])
    alvos = [ini + (fim - ini) * letras[v] / letras[-1] for v in range(n - 1)]
    m = len(pausas)
    if m < n - 1:
        return None
    # programação dinâmica: n-1 cortes em ordem, valorizando pausas longas perto do ponto esperado
    nota = lambda v, q: 4 * pausas[q][1] - abs(pausas[q][0] - alvos[v]) / sr
    melhor = np.full((n - 1, m), -1e9)
    veio = np.zeros((n - 1, m), dtype=int)
    for q in range(m):
        melhor[0, q] = nota(0, q)
    for v in range(1, n - 1):
        acum, arg = -1e9, -1
        for q in range(m):
            if q > 0 and melhor[v - 1, q - 1] > acum:
                acum, arg = melhor[v - 1, q - 1], q - 1
            if arg >= 0:
                melhor[v, q] = acum + nota(v, q)
                veio[v, q] = arg
    q = int(np.argmax(melhor[n - 2]))
    cortes = []
    for v in range(n - 2, -1, -1):
        cortes.append(pausas[q][0]); q = veio[v, q]
    cortes.reverse()
    limites = [0] + cortes + [len(som)]
    return [som[a:b] for a, b in zip(limites, limites[1:])]


def faixa(ep_id, linhas, inicio, slot, sr, total, usar=None):
    """Faixa de voz do episódio: verso i começa em inicio + i*slot e é acelerado se não couber.
    Um único pedido à API por música (o plano gratuito tem limite diário de pedidos)."""
    os.makedirs(PASTA, exist_ok=True)
    cache = os.path.join(PASTA, f"ep{ep_id:02d}_gemini.wav")
    if not os.path.exists(cache):
        dados = _tts("\n".join(linhas))
        open(cache, "wb").write(dados)
    som = _ler(cache, sr)
    partes = _segmentos(som, sr, linhas)
    if partes is None:
        raise RuntimeError("narração não pôde ser dividida em versos")
    buf = np.zeros(int(total * sr))
    tempos = []  # quanto dura a fala de cada verso: a letra na tela acende nesse ritmo
    cabe = slot - 0.3
    for i, parte in enumerate(partes[:usar]):
        dur = len(parte) / sr
        if dur > cabe:  # acelera até caber no compasso (no máximo 1,6x)
            fator = min(dur / cabe, 1.6)
            idx = np.linspace(0, len(parte) - 1, int(len(parte) / fator))
            parte = np.interp(idx, np.arange(len(parte)), parte)[: int(cabe * sr)]
        a = int((inicio + i * slot + 0.15) * sr)
        buf[a: a + len(parte)] += parte[: max(0, len(buf) - a)]
        tempos.append(0.15 + len(parte) / sr)
    return buf, tempos
