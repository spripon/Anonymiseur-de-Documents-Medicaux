import streamlit as st
import spacy
import re
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageDraw
import io
import numpy as np
import os
from docx import Document
from fpdf import FPDF

# Configuration de la page
st.set_page_config(page_title="Anonymiseur Médical", page_icon="🏥", layout="wide")

# -----------------------------------------------------------------------------
# 1. CHARGEMENT DU MODÈLE NLP
# -----------------------------------------------------------------------------
@st.cache_resource
def load_nlp_model():
    # Le modèle est installé via requirements.txt, on le charge simplement.
    # On utilise 'fr_core_news_md' (Medium) qui est installé.
    try:
        return spacy.load("fr_core_news_md")
    except OSError:
        # Fallback de sécurité si le nom exact diffère légèrement
        import fr_core_news_md
        return fr_core_news_md.load()

try:
    nlp = load_nlp_model()
except Exception as e:
    st.error(f"Erreur : Le modèle Spacy n'a pas pu être chargé. Détails: {e}")
    st.stop()

# -----------------------------------------------------------------------------
# 2. FONCTIONS DE DÉTECTION (REGEX + NLP)
# -----------------------------------------------------------------------------
def get_sensitive_entities(text):
    """
    Analyse un texte et retourne une liste de mots/segments à censurer.
    """
    sensitive_words = set()
    
    # A. NLP avec Spacy (Noms, Organisations, Lieux)
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ in ["PER", "LOC", "ORG"]:
            sensitive_words.add(ent.text.lower())
            for token in ent:
                if len(token.text) > 2: 
                    sensitive_words.add(token.text.lower())

    # B. Regex pour motifs structurés
    
    # 1. Dates (JJ/MM/AAAA, JJ.MM.AAAA, JJ-MM-AAAA)
    date_pattern = r'\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b'
    dates = re.findall(date_pattern, text)
    sensitive_words.update([d.lower() for d in dates])

    # 2. Numéros de téléphone
    phone_pattern = r'\b(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}\b'
    phones = re.findall(phone_pattern, text)
    for p in phones:
        sensitive_words.add(p) 
        parts = re.split(r'[\s.-]', p)
        for part in parts:
            if len(part) > 1:
                sensitive_words.add(part)

    # 3. Sécurité Sociale (NIR)
    ssn_pattern = r'\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}(?:\s?\d{2})?\b'
    ssns = re.findall(ssn_pattern, text)
    sensitive_words.update([s.replace(" ", "") for s in ssns])

    # 4. Emails
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    sensitive_words.update([e.lower() for e in emails])

    return sensitive_words

def should_redact(word, sensitive_set):
    """Vérifie si un mot spécifique doit être masqué."""
    clean_word = word.lower().strip('.,:;()[]"\'')
    
    if clean_word in sensitive_set:
        return True
    
    if re.match(r'^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$', clean_word): 
        return True
    
    return False

# -----------------------------------------------------------------------------
# 3. MOTEUR D'ANONYMISATION VISUELLE
# -----------------------------------------------------------------------------
def anonymize_image_page(image):
    full_text = pytesseract.image_to_string(image, lang='fra')
    sensitive_entities = get_sensitive_entities(full_text)
    
    data = pytesseract.image_to_data(image, lang='fra', output_type=pytesseract.Output.DICT)
    draw = ImageDraw.Draw(image)
    n_boxes = len(data['text'])
    
    for i in range(n_boxes):
        word = data['text'][i]
        conf = int(data['conf'][i])
        
        if conf > 0 and word.strip():
            if should_redact(word, sensitive_entities):
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                draw.rectangle([x, y, x + w, y + h], fill="black", outline="black")
    
    return image

# -----------------------------------------------------------------------------
# 4. GESTION DES DOCX
# -----------------------------------------------------------------------------
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Document Anonymisé', 0, 1, 'C')

def process_docx(file_bytes):
    source_stream = io.BytesIO(file_bytes)
    doc = Document(source_stream)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    
    text_content = "\n".join(full_text)
    sensitive_entities = get_sensitive_entities(text_content)
    
    anonymized_text = text_content
    sorted_entities = sorted(list(sensitive_entities), key=len, reverse=True)
    
    for entity in sorted_entities:
        pattern = re.compile(re.escape(entity), re.IGNORECASE)
        anonymized_text = pattern.sub("█" * len(entity), anonymized_text)

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    safe_text = anonymized_text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, safe_text)
    
    return pdf.output(dest='S').encode('latin-1')

# -----------------------------------------------------------------------------
# 5. INTERFACE UTILISATEUR
# -----------------------------------------------------------------------------
st.title("🛡️ Anonymiseur de Documents Médicaux")
st.markdown("""
Cette application détecte et masque automatiquement :
* Noms de patients et médecins
* Dates de naissance et dates d'examens
* Numéros de téléphone et de Sécurité Sociale
* Noms d'établissements
""")

uploaded_file = st.file_uploader("Téléverser un document (PDF, DOCX, PNG, JPG)", type=["pdf", "docx", "png", "jpg", "jpeg"])

if uploaded_file is not None:
    file_type = uploaded_file.type
    st.info(f"Fichier chargé : {uploaded_file.name}")
    
    if st.button("Lancer l'anonymisation"):
        with st.spinner('Traitement en cours...'):
            output_pdf_bytes = None
            
            if file_type in ["image/png", "image/jpeg", "image/jpg"]:
                image = Image.open(uploaded_file)
                processed_image = anonymize_image_page(image.convert("RGB"))
                processed_image.save("temp.pdf", "PDF", resolution=100.0)
                with open("temp.pdf", "rb") as f:
                    output_pdf_bytes = f.read()
                st.image(processed_image, caption="Aperçu anonymisé", use_column_width=True)

            elif file_type == "application/pdf":
                images = convert_from_bytes(uploaded_file.read())
                processed_images = []
                progress_bar = st.progress(0)
                for i, img in enumerate(images):
                    processed_images.append(anonymize_image_page(img))
                    progress_bar.progress((i + 1) / len(images))
                
                if processed_images:
                    img_list = [img.convert('RGB') for img in processed_images]
                    img_list[0].save("temp.pdf", save_all=True, append_images=img_list[1:])
                    with open("temp.pdf", "rb") as f:
                        output_pdf_bytes = f.read()
            
            elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                output_pdf_bytes = process_docx(uploaded_file.read())
            
            if output_pdf_bytes:
                st.success("Terminé !")
                st.download_button(
                    label="📥 Télécharger le résultat",
                    data=output_pdf_bytes,
                    file_name=f"anonymise_{uploaded_file.name.split('.')[0]}.pdf",
                    mime="application/pdf"
                )


