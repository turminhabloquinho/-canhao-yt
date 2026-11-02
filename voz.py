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


def _segmentos(som, sr, n):
    """Divide a narração da música inteira em n versos, cortando nas n-1 maiores pausas."""
    janela = int(0.02 * sr)
    energia = np.sqrt(np.convolve(som ** 2, np.ones(janela) / janela, mode="same"))
    calado = energia < 0.02
    pausas, k = [], 0
    while k < len(calado):
        if calado[k]:
            j = k
            while j < len(calado) and calado[j]:
                j += 1
            if k > 0 and j < len(calado):
                pausas.append((j - k, (k + j) // 2))
            k = j
        else:
            k += 1
    cortes = sorted(c for _, c in sorted(pausas, reverse=True)[: n - 1])
    if len(cortes) < n - 1:
        return None
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
    partes = _segmentos(som, sr, len(linhas))
    if partes is None:
        raise RuntimeError("narração não pôde ser dividida em versos")
    buf = np.zeros(int(total * sr))
    cabe = slot - 0.3
    for i, parte in enumerate(partes[:usar]):
        dur = len(parte) / sr
        if dur > cabe:  # acelera até caber no compasso (no máximo 1,6x)
            fator = min(dur / cabe, 1.6)
            idx = np.linspace(0, len(parte) - 1, int(len(parte) / fator))
            parte = np.interp(idx, np.arange(len(parte)), parte)[: int(cabe * sr)]
        a = int((inicio + i * slot + 0.15) * sr)
        buf[a: a + len(parte)] += parte[: max(0, len(buf) - a)]
    return buf
