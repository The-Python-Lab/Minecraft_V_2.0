# --- src/text_generator.py ---
from PIL import Image, ImageDraw, ImageFont
from OpenGL.GL import *
import ctypes
import os


def create_number_texture():
    """Erstellt eine hochauflösende Zahlen-Textur (0-9) mit schwarzer Umrandung."""

    # Textur-Auflösung (Hoch)
    char_width = 64
    char_height = 64
    img_width = char_width * 10

    img = Image.new('RGBA', (img_width, char_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    font = None
    font_size = 56  # Groß für den Rand

    # Versuch, einen fetten Font zu laden
    font_candidates = ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "FreeSansBold.ttf"]

    for font_name in font_candidates:
        try:
            font = ImageFont.truetype(font_name, font_size)
            print(f"🔠 Font geladen: {font_name}")
            break
        except OSError:
            continue

    if font is None:
        try:
            font = ImageFont.load_default()
        except:
            pass

    for i in range(10):
        text = str(i)

        base_x = i * char_width + (char_width / 2)
        base_y = char_height / 2

        # Text-Größe ermitteln für exakte Zentrierung
        if font:
            bbox = draw.textbbox((0, 0), text, font=font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            x = base_x - (w / 2)
            y = base_y - (h / 2) - 5
        else:
            x = base_x
            y = base_y

        # --- UMRAUNDUNG ZEICHNEN ---
        outline_width = 3
        if font:
            # Schwarz (Schatten/Rand)
            for ox in range(-outline_width, outline_width + 1):
                for oy in range(-outline_width, outline_width + 1):
                    if ox == 0 and oy == 0: continue
                    draw.text((x + ox, y + oy), text, font=font, fill=(0, 0, 0, 255))

            # Weiß (Haupttext) oben drauf
            draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
        else:
            draw.text((x, y), text, fill=(255, 255, 255, 255))

    # In OpenGL Textur umwandeln
    img_data = img.tobytes()
    tex_id = glGenTextures(1)
    glBindTexture(GL_TEXTURE_2D, tex_id)
    # Filterung für Skalierung: GL_LINEAR
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.width, img.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, img_data)

    print(f"🔠 Zahlen-Textur generiert (ID: {tex_id}, High-Res mit Outline).")
    return tex_id