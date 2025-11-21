#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
from typing import List, Tuple

from PIL import Image, ImageDraw
import pytesseract
from pytesseract import Output
from pdf2image import convert_from_path


# ---------- REGEX & CONSTANTES ----------

# Dates : 01/02/2023, 1.2.23, etc.
DATE_REGEX = re.compile(
    r"\b([0-3]?\d)[./]([0-1]?\d)[./](\d{2}|\d{4})\b"
)

# Nombres longs (N° sécu, FINESS, IPP, etc.)
LONG_NUMBER_REGEX = re.compile(r"\b\d{7,}\b")

# Titres de civilité pour les patients
TITLE_PATIENT = {
    "monsieur", "mr", "m.", "madame", "mme", "mlle", "mademoiselle"
}

# Titres pour les médecins
TITLE_DOCTOR = {
    "docteur", "dr", "dr.", "drs"
}

# Types de voies pour détecter les adresses
ROAD_TYPES = {
    "rue", "route", "rte", "boulevard", "bd", "blv", "av", "av.",
    "avenue", "impasse", "allee", "allée", "chemin", "place"
}


# ---------- UTILITAIRES ----------

def normalize_word(w: str) -> str:
    """Supprime la ponctuation autour du mot."""
    return w.strip().strip(".,;:()[]{}<>/\\\"'«»!?")


def is_capitalized(word: str) -> bool:
    """
    Nom propre de type "Candelier", "Serrano", "Lannemezan" ou "CANDELIER".
    On considère qu'un mot est "nom propre" s'il commence par une majuscule
    (ou est tout en majuscules), longueur >= 2.
    """
    w = normalize_word(word)
    if len(w) < 2:
        return False
    return w[0].isupper()


def count_digits(text: str) -> int:
    return sum(ch.isdigit() for ch in text)


def _bbox_word(w: dict) -> Tuple[int, int, int, int]:
    x1 = w["left"]
    y1 = w["top"]
    x2 = x1 + w["width"]
    y2 = y1 + w["height"]
    return (x1, y1, x2, y2)


def _bbox_range(words: List[dict], i_start: int, i_end: int) -> Tuple[int, int, int, int]:
    xs1, ys1, xs2, ys2 = [], [], [], []
    for i in range(i_start, i_end + 1):
        w = words[i]
        x1 = w["left"]
        y1 = w["top"]
        x2 = x1 + w["width"]
        y2 = y1 + w["height"]
        xs1.append(x1)
        ys1.append(y1)
        xs2.append(x2)
        ys2.append(y2)
    return (min(xs1), min(ys1), max(xs2), max(ys2))


# ---------- DÉTECTION DES ZONES À MASQUER ----------

def detect_pii_boxes_from_ocr(ocr: dict) -> List[Tuple[int, int, int, int]]:
    """
    Analyse le résultat de pytesseract.image_to_data et renvoie
    une liste de rectangles à masquer (x1, y1, x2, y2) autour des mots ciblés.
    AUCUNE règle "ligne entière".
    Pas de détection QR-code.
    """
    boxes: List[Tuple[int, int, int, int]] = []

    n = len(ocr["text"])
    line_dict = {}

    # Regroupement par ligne
    for i in range(n):
        text = ocr["text"][i]
        conf = float(ocr["conf"][i])

        if not text or text.strip() == "" or conf < 0:
            continue

        page = ocr["page_num"][i]
        block = ocr["block_num"][i]
        par = ocr["par_num"][i]
        line = ocr["line_num"][i]
        key = (page, block, par, line)

        left = ocr["left"][i]
        top = ocr["top"][i]
        width = ocr["width"][i]
        height = ocr["height"][i]

        if key not in line_dict:
            line_dict[key] = {"words": []}

        line_dict[key]["words"].append(
            {
                "text": text,
                "left": left,
                "top": top,
                "width": width,
                "height": height,
                "conf": conf,
            }
        )

    # Parcours ligne par ligne
    for key, line in line_dict.items():
        words = line["words"]

        # 1) DATES & NOMBRES LONGS (par mot)
        for w in words:
            t = w["text"].strip()
            if DATE_REGEX.search(t):
                boxes.append(_bbox_word(w))
                continue
            if LONG_NUMBER_REGEX.search(t):
                boxes.append(_bbox_word(w))
                continue

        # 2) GROUPES NUMÉRIQUES CONSÉCUTIFS (numéros de téléphone, etc.)
        i = 0
        while i < len(words):
            txt = normalize_word(words[i]["text"])
            # Groupe de tokens purement numériques (ex : "05 62 99 55 55")
            if txt.isdigit():
                j = i
                total_digits = 0
                while j < len(words):
                    txtj = normalize_word(words[j]["text"])
                    if txtj.isdigit():
                        total_digits += len(txtj)
                        j += 1
                    else:
                        break
                if total_digits >= 7:
                    boxes.append(_bbox_range(words, i, j - 1))
                i = j
            else:
                i += 1

        # 3) NOMS DE PATIENTS après Monsieur/Madame/etc.
        for i, w in enumerate(words):
            low = normalize_word(w["text"]).lower()
            if low in TITLE_PATIENT:
                j = i + 1
                cap_count = 0
                while j < len(words) and cap_count < 3:
                    if is_capitalized(words[j]["text"]):
                        boxes.append(_bbox_word(words[j]))
                        cap_count += 1
                        j += 1
                    else:
                        break

        # 4) NOMS DE MÉDECINS après Docteur/Dr
        for i, w in enumerate(words):
            low = normalize_word(w["text"]).lower()
            if low in TITLE_DOCTOR:
                j = i + 1
                cap_count = 0
                while j < len(words) and cap_count < 3:
                    if is_capitalized(words[j]["text"]):
                        boxes.append(_bbox_word(words[j]))
                        cap_count += 1
                        j += 1
                    else:
                        break

        # 5) ADRESSES : "<num> rue/route/boulevard/..."
        for i, w in enumerate(words):
            txt = normalize_word(w["text"])
            if txt.isdigit():
                if i + 1 < len(words):
                    next_txt = normalize_word(words[i + 1]["text"]).lower()
                    if next_txt in ROAD_TYPES:
                        boxes.append(_bbox_range(words, i, len(words) - 1))
                        break

        # 6) ÉTABLISSEMENTS : Hôpital/Hopital/Hôpitaux de X, Centre hospitalier de X, CHU X
        for i, w in enumerate(words):
            txt_norm = normalize_word(w["text"])
            low = txt_norm.lower()

            # Hopital / Hôpital / Hôpitaux de X...
            if low in {"hopital", "hôpital", "hopitaux"}:
                start = i
                end = i
                if i + 1 < len(words):
                    low_next = normalize_word(words[i + 1]["text"]).lower()
                    if low_next in {"de", "d'"}:
                        end = i + 1
                j = end + 1
                cap_count = 0
                while j < len(words) and cap_count < 3:
                    if is_capitalized(words[j]["text"]):
                        end = j
                        cap_count += 1
                        j += 1
                    else:
                        break
                boxes.append(_bbox_range(words, start, end))

            # Centre hospitalier de X...
            if low == "centre" and i + 1 < len(words):
                low_next = normalize_word(words[i + 1]["text"]).lower()
                if low_next.startswith("hospitalier"):
                    start = i
                    end = i + 1
                    j = i + 2
                    if j < len(words):
                        low_j = normalize_word(words[j]["text"]).lower()
                        if low_j in {"de", "d'"}:
                            end = j
                            j += 1
                    cap_count = 0
                    while j < len(words) and cap_count < 3:
                        if is_capitalized(words[j]["text"]):
                            end = j
                            cap_count += 1
                            j += 1
                        else:
                            break
                    boxes.append(_bbox_range(words, start, end))

            # CHU X...
            if low == "chu":
                start = i
                end = i
                j = i + 1
                cap_count = 0
                while j < len(words) and cap_count < 3:
                    if is_capitalized(words[j]["text"]):
                        end = j
                        cap_count += 1
                        j += 1
                    else:
                        break
                boxes.append(_bbox_range(words, start, end))

    return boxes


# ---------- PIPELINE IMAGE / PDF ----------

def anonymize_image(img: Image.Image) -> Image.Image:
    """
    OCR + détection PII + masquage (rectangles blancs serrés).
    """
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    ocr_data = pytesseract.image_to_data(
        img, output_type=Output.DICT, lang="fra+eng"
    )

    boxes = detect_pii_boxes_from_ocr(ocr_data)

    draw = ImageDraw.Draw(img)
    margin = 2  # petite marge pour couvrir le mot sans manger la ligne voisine

    for (x1, y1, x2, y2) in boxes:
        draw.rectangle(
            [(x1 - margin, y1 - margin), (x2 + margin, y2 + margin)],
            fill="white",
        )

    return img


def process_pdf(input_path: str):
    pages = convert_from_path(input_path, dpi=300)
    processed = []
    for page in pages:
        anon = anonymize_image(page)
        processed.append(anon)
    return processed


def process_image_file(input_path: str):
    img = Image.open(input_path)
    anon = anonymize_image(img)
    return [anon]


def save_images_as_pdf(images, output_path: str) -> None:
    if not images:
        raise ValueError("Aucune image à sauvegarder.")

    images_rgb = []
    for im in images:
        if im.mode != "RGB":
            images_rgb.append(im.convert("RGB"))
        else:
            images_rgb.append(im)

    first, *rest = images_rgb
    first.save(
        output_path,
        "PDF",
        save_all=True,
        append_images=rest,
        resolution=300.0,
    )


def anonymize_document_to_pdf(input_path: str, output_path: str) -> None:
    """
    Fonction utilisée par Streamlit : lit un PDF ou une image et écrit un PDF anonymisé.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Fichier introuvable : {input_path}")

    ext = os.path.splitext(input_path)[1].lower()

    if ext == ".pdf":
        images = process_pdf(input_path)
    elif ext in [".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff"]:
        images = process_image_file(input_path)
    else:
        raise ValueError("Format non supporté (PDF ou image).")

    save_images_as_pdf(images, output_path)


# Option : usage en ligne de commande (facultatif, mais pratique en local)
def main():
    if len(sys.argv) != 3:
        print("Usage : python anonymizer.py input_file output_pdf")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    anonymize_document_to_pdf(input_path, output_path)


if __name__ == "__main__":
    main()
