#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile

import streamlit as st
from PIL import Image

from anonymizer import anonymize_document_to_pdf


st.set_page_config(
    page_title="Anonymiseur de documents médicaux",
    page_icon="🩺",
    layout="centered",
)

st.title("🩺 Anonymiseur de documents médicaux")
st.write(
    """
Téléverse un document médical **(PDF ou photo : PNG, JPG, JPEG, GIF, TIFF)**.

L'application :
- lit le texte par OCR,
- masque automatiquement :
  - les noms/prénoms après *Monsieur/Madame/Docteur/Dr*,
  - les noms d'établissements de santé (*Hôpital de..., CHU..., Centre hospitalier de...*),
  - les adresses (ex. **“644 route de Toulouse ...”**),
  - **toutes les dates** au format JJ/MM/AAAA ou JJ.MM.AAAA,
  - les numéros de téléphone et **tous les numéros ≥ 7 chiffres**,
  - les codes-barres / QR-codes détectés sur l'image.

Le PDF résultant est visuellement identique mais avec des rectangles blancs serrés sur les zones anonymisées.
"""
)

uploaded_file = st.file_uploader(
    "Choisis un document à anonymiser",
    type=["pdf", "png", "jpg", "jpeg", "gif", "tif", "tiff"],
)


def save_uploaded_as_temp_pdf_or_png(uploaded_file) -> str:
    """
    Enregistre le fichier uploadé dans un fichier temporaire.
    - Si PDF -> écrit tel quel, suffix='.pdf'
    - Si image -> ouvre avec PIL et force une conversion en PNG (suffix='.png')
    Retourne le chemin du fichier temporaire.
    """
    original_name = uploaded_file.name
    ext = os.path.splitext(original_name)[1].lower()

    # Cas PDF : on écrit le contenu brut dans un .pdf
    if ext == ".pdf":
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(uploaded_file.getbuffer())
        tmp.close()
        return tmp.name

    # Cas image : on passe obligatoirement par PIL -> PNG
    try:
        img = Image.open(uploaded_file)
        img = img.convert("RGB")  # standardiser le mode

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        img.save(tmp.name, format="PNG")
        tmp.close()
        return tmp.name
    except Exception as e:
        raise RuntimeError(f"Impossible de lire l'image : {e}")


if uploaded_file is not None:
    file_ext = os.path.splitext(uploaded_file.name)[1].lower()
    st.write(f"**Fichier chargé :** `{uploaded_file.name}`")

    # Aperçu si c'est une image
    if file_ext in [".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff"]:
        try:
            img_preview = Image.open(uploaded_file)
            st.image(img_preview, caption="Aperçu du document original", use_column_width=True)
        except Exception:
            st.info("Prévisualisation image impossible, mais le fichier sera quand même traité.")

    st.markdown("---")
    if st.button("Anonymiser le document"):
        with st.spinner("Anonymisation en cours..."):
            input_path = None
            output_path = None
            try:
                # 1) On convertit le fichier uploadé en :
                #    - PDF brut, ou
                #    - PNG (image convertie)
                input_path = save_uploaded_as_temp_pdf_or_png(uploaded_file)

                # 2) Fichier de sortie temporaire (toujours PDF)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_out:
                    output_path = tmp_out.name

                # 3) Anonymisation (via anonymizer.py)
                anonymize_document_to_pdf(input_path, output_path)

                # 4) Lecture du PDF anonymisé pour le proposer en téléchargement
                with open(output_path, "rb") as f:
                    pdf_bytes = f.read()

                st.success("Anonymisation terminée.")

                st.download_button(
                    label="📥 Télécharger le PDF anonymisé",
                    data=pdf_bytes,
                    file_name=f"anonymise_{os.path.splitext(uploaded_file.name)[0]}.pdf",
                    mime="application/pdf",
                )

            except Exception as e:
                st.error(f"Erreur lors de l'anonymisation : {e}")

            finally:
                # Nettoyage des fichiers temporaires
                try:
                    if input_path and os.path.exists(input_path):
                        os.remove(input_path)
                except Exception:
                    pass
                try:
                    if output_path and os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass
else:
    st.info("Téléverse un fichier pour commencer.")
