"""Gera banner, foto de perfil e marca d'água do canal."""
import os
from PIL import Image, ImageDraw
import motor

A = os.path.join(motor.RAIZ, "assets"); os.makedirs(A, exist_ok=True)

def fundo(W, H):
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        k = y / H; d.rectangle([0, y, W, y + 4], fill=(int(120 + 100 * k), int(200 + 40 * k), 255))
    return img, d

# banner 2560x1440 (área segura central 1546x423)
img, d = fundo(2560, 1440)
d.rectangle([0, 860, 2560, 1440], fill=(110, 200, 90))
for i, (_, cor, _) in enumerate(motor.PERSONAGENS):
    motor.personagem(d, 1010 + i * 180, 905, 150, cor, 0, False, True)
fnt = motor.fonte(110); t = "TURMINHA DO BLOQUINHO"
d.text(((2560 - d.textlength(t, font=fnt)) / 2, 520), t, font=fnt, fill=(230, 57, 70), stroke_width=8, stroke_fill="white")
f2 = motor.fonte(48); t2 = "Músicas infantis novas todos os dias!"
d.text(((2560 - d.textlength(t2, font=f2)) / 2, 660), t2, font=f2, fill=(40, 40, 60))
img.save(os.path.join(A, "banner.png"))

# foto de perfil 800x800
img, d = fundo(800, 800)
d.rectangle([0, 600, 800, 800], fill=(110, 200, 90))
motor.personagem(d, 400, 640, 430, motor.PERSONAGENS[0][1], 0, False, True)
img.save(os.path.join(A, "perfil.png"))

# marca d'água 150x150
img = Image.new("RGBA", (150, 150), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
motor.personagem(d, 75, 140, 110, motor.PERSONAGENS[0][1], 0, False, True)
img.save(os.path.join(A, "marca.png"))
print("ok")
