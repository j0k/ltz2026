# -*- coding: utf-8 -*-
"""Codellake — команда у штурвала. Трое на поле: капитан, инженер и агент."""
import json
import math
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

F = "/usr/share/fonts/truetype/noto/"
pdfmetrics.registerFont(TTFont("NS", F + "NotoSans-Regular.ttf"))
pdfmetrics.registerFont(TTFont("NS-B", F + "NotoSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("ND-B", F + "NotoSansDisplay-Bold.ttf"))

W, H = 760.0, 780.0
BG = HexColor("#f7f6f3")
INK = HexColor("#0b0b0b")
INK2 = HexColor("#52514e")
INK3 = HexColor("#8a8983")
BLUE = HexColor("#2a78d6")
DEEP = HexColor("#104281")
MID = HexColor("#1c5cab")
PALE = HexColor("#cde2fb")
ACCENT = HexColor("#eb6834")
CARD = HexColor("#ffffff")

INST = {i["cwd"]: i for i in json.load(open("/home/jk/.codellake/instances.json"))["instances"]}
LTZ = INST["/home/jk/exp/LTZ2026"]
FLEET = [i["cwd"].rstrip("/").split("/")[-1] for i in INST.values() if i["cwd"] != "/home/jk/exp/LTZ2026"]

CREW = [
    dict(ang=135, name="Юрий Коноплёв", tag="@bimodaling · капитан",
         role="курс", helm=False,
         lines=["ставит курс: какую задачу берём",
                "и что показываем на защите",
                "владелец репозитория j0k/ltz2026"]),
    dict(ang=45, name="Алексей", tag="второй на поле", role="борт", helm=False,
         lines=["роль впишем, как скажете:",
                "модель, бэкенд или демо",
                "пока свободная рукоять"]),
    dict(ang=270, name="Claude", tag="codellake · инстанс LTZ · " + LTZ["model"],
         role="у руля", helm=True,
         lines=["разбор задач, инфографика, репозиторий",
                "и план на две недели",
                "на вахте с " + LTZ["started"][8:10] + "." + LTZ["started"][5:7] + " · рядом " + " и ".join(f.split(".")[0] for f in FLEET)]),
]

c = canvas.Canvas("/home/jk/exp/LTZ2026/codellake_crew.pdf", pagesize=(W, H))
c.setTitle("Codellake — команда у штурвала")

c.setFillColor(BG)
c.rect(0, 0, W, H, stroke=0, fill=1)

c.setFont("ND-B", 34)
c.setFillColor(INK)
c.drawCentredString(W / 2, H - 58, "CODELLAKE")
c.setFont("NS", 11)
c.setFillColor(INK2)
c.drawCentredString(W / 2, H - 78, "трое на поле · ЛЦТ 2026 · стендап 10 сентября")

CX, CY, R = W / 2, 398.0, 150.0

c.setStrokeColor(BLUE)
c.setLineWidth(9)
c.setLineCap(1)
for k in range(6):
    a = math.radians(k * 60 + 30)
    c.line(CX, CY, CX + R * math.cos(a), CY + R * math.sin(a))

c.setStrokeColor(DEEP)
c.setLineWidth(15)
c.circle(CX, CY, R, stroke=1, fill=0)
c.setStrokeColor(PALE)
c.setLineWidth(3)
c.circle(CX, CY, R - 11, stroke=1, fill=0)

for k in range(6):
    a = math.radians(k * 60 + 30)
    c.saveState()
    c.translate(CX + (R + 5) * math.cos(a), CY + (R + 5) * math.sin(a))
    c.rotate(k * 60 + 30)
    c.setFillColor(MID)
    c.roundRect(0, -7.0, 32, 14, 7, stroke=0, fill=1)
    c.setFillColor(DEEP)
    c.circle(30, 0, 8.5, stroke=0, fill=1)
    c.restoreState()

c.setFillColor(DEEP)
c.circle(CX, CY, 60, stroke=0, fill=1)
c.setFillColor(BG)
c.circle(CX, CY, 50, stroke=0, fill=1)
c.setFillColor(DEEP)
c.setFont("ND-B", 15)
c.drawCentredString(CX, CY + 8, "ЛЦТ")
c.setFont("NS", 8)
c.setFillColor(INK2)
c.drawCentredString(CX, CY - 7, "до заявки")
c.setFillColor(ACCENT)
c.setFont("NS-B", 11)
c.drawCentredString(CX, CY - 24, "4 дня")

CW_, CH_ = 252.0, 104.0
for m in CREW:
    a = math.radians(m["ang"])
    if m["ang"] == 270:
        x, yb = (W - CW_) / 2, 56.0
        hx, hy = x + CW_ / 2, yb + CH_
    else:
        left = math.cos(a) < 0
        x = 24 if left else W - 24 - CW_
        yb = H - 150 - CH_
        hx = x + CW_ if left else x
        hy = yb + CH_ / 2
    ax, ay = CX + (R + 40) * math.cos(a), CY + (R + 40) * math.sin(a)
    c.setStrokeColor(HexColor("#c9d4e4"))
    c.setLineWidth(1.6)
    c.line(hx, hy, ax, ay)
    c.setFillColor(HexColor("#c9d4e4"))
    c.circle(ax, ay, 3.4, stroke=0, fill=1)

    c.setFillColor(CARD)
    c.roundRect(x, yb, CW_, CH_, 8, stroke=0, fill=1)
    c.setFillColor(ACCENT if m["helm"] else BLUE)
    c.roundRect(x, yb, 3.4, CH_, 1.7, stroke=0, fill=1)

    c.setFillColor(INK)
    c.setFont("ND-B", 15)
    c.drawString(x + 16, yb + CH_ - 26, m["name"])
    label = m["role"]
    c.setFont("NS-B", 8)
    lw = pdfmetrics.stringWidth(label, "NS-B", 8)
    c.setFillColor(HexColor("#fdece3") if m["helm"] else HexColor("#eef4fd"))
    c.roundRect(x + CW_ - 20 - lw, yb + CH_ - 28, lw + 14, 15, 7.5, stroke=0, fill=1)
    c.setFillColor(ACCENT if m["helm"] else DEEP)
    c.drawCentredString(x + CW_ - 13 - lw / 2, yb + CH_ - 24, label)

    c.setFont("NS", 7.6)
    c.setFillColor(INK3)
    c.drawString(x + 16, yb + CH_ - 39, m["tag"])
    c.setFont("NS", 8.2)
    c.setFillColor(INK2)
    for i, ln in enumerate(m["lines"]):
        size = 8.2
        while pdfmetrics.stringWidth(ln, "NS", size) > CW_ - 30 and size > 6.0:
            size -= 0.2
        c.setFont("NS", size)
        c.drawString(x + 16, yb + CH_ - 55 - i * 12.5, ln)

c.setFont("NS", 8.4)
c.setFillColor(INK3)
c.drawCentredString(W / 2, 30, "заявки до 14 сентября · разработка 15–29 сентября · защита 23 октября")
c.showPage()
c.save()
print("ok")
