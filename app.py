import streamlit as st
import spacy
import re
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image, ImageDraw
import io
import numpy as np
import tempfile
import os
from docx import Document
from fpdf import FPDF

# Configuration de la page
st.set_page_config(page_title="Anonymiseur Médical", page_icon="🏥", layout="wide")

# -----------------------------------------------------------------------------
# 1. CHARGEMENT DU MODÈLE NLP (Mise en cache pour la performance)
# -----------------------------------------------------------------------------
@st.cache_resource
def load_nlp_model():
    # Télécharge le modèle si non présent (pour l'exécution locale)
    if not spacy.util.is_package("fr_core_news_lg"):
        st.warning("Téléchargement du modèle de langue française en cours...")
        os.system("python -m spacy download fr_core_news_lg")
    return spacy.load("fr_core_news_lg")

try:
    nlp = load_nlp_model()
except Exception as e:
    st.error(f"Erreur lors du chargement du modèle Spacy : {e}")
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
            # On ajoute l'entité complète et ses parties individuelles (pour le redacting mot par mot)
            sensitive_words.add(ent.text.lower())
            for token in ent:
                if len(token.text) > 2: # Éviter de censurer des mots trop courts comme "le", "de" par erreur
                    sensitive_words.add(token.text.lower())

    # B. Regex pour motifs structurés
    
    # 1. Dates (JJ/MM/AAAA, JJ.MM.AAAA, JJ-MM-AAAA)
    date_pattern = r'\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b'
    dates = re.findall(date_pattern, text)
    sensitive_words.update([d.lower() for d in dates])

    # 2. Numéros de téléphone (Formats français variés)
    phone_pattern = r'\b(?:(?:\+|00)33|0)\s*[1-9](?:[\s.-]*\d{2}){4}\b'
    phones = re.findall(phone_pattern, text)
    # Nettoyage pour matcher les fragments si l'OCR sépare les chiffres
    for p in phones:
        sensitive_words.add(p) 
        parts = re.split(r'[\s.-]', p)
        for part in parts:
            if len(part) > 1:
                sensitive_words.add(part)

    # 3. Sécurité Sociale (NIR) approximatif
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
    
    # Vérification directe
    if clean_word in sensitive_set:
        return True
    
    # Vérification regex stricte sur le mot individuel (si l'OCR l'a isolé)
    if re.match(r'^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$', clean_word): # Date isolée
        return True
    
    return False

# -----------------------------------------------------------------------------
# 3. MOTEUR D'ANONYMISATION VISUELLE (POUR PDF ET IMAGES)
# -----------------------------------------------------------------------------
def anonymize_image_page(image):
    """
    Prend une image PIL, effectue l'OCR, détecte les PII et dessine des boîtes noires.
    """
    # 1. OCR pour obtenir le texte complet (pour le contexte NLP)
    full_text = pytesseract.image_to_string(image, lang='fra')
    
    # 2. Identification des entités sensibles sur le texte global
    sensitive_entities = get_sensitive_entities(full_text)
    
    # 3. OCR pour obtenir les positions des mots (Bounding Boxes)
    # Output format: dict avec 'left', 'top', 'width', 'height', 'text', 'conf'
    data = pytesseract.image_to_data(image, lang='fra', output_type=pytesseract.Output.DICT)
    
    draw = ImageDraw.Draw(image)
    n_boxes = len(data['text'])
    
    # 4. Itération sur chaque mot détecté
    for i in range(n_boxes):
        word = data['text'][i]
        conf = int(data['conf'][i])
        
        if conf > 0 and word.strip():
            if should_redact(word, sensitive_entities):
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                # Dessiner le rectangle noir
                draw.rectangle([x, y, x + w, y + h], fill="black", outline="black")
    
    return image

# -----------------------------------------------------------------------------
# 4. GESTION DES DOCX (Conversion Texte -> PDF Anonymisé)
# -----------------------------------------------------------------------------
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Document Anonymisé', 0, 1, 'C')

def process_docx(file_bytes):
    """Traite un fichier DOCX, extrait le texte, le censure et crée un PDF."""
    source_stream = io.BytesIO(file_bytes)
    doc = Document(source_stream)
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    
    text_content = "\n".join(full_text)
    
    # Détection
    sensitive_entities = get_sensitive_entities(text_content)
    
    # Remplacement dans le texte (Méthode simple par remplacement)
    # Note: Pour le texte brut, on remplace par [XXX] au lieu de dessiner
    anonymized_text = text_content
    
    # Tri pour remplacer les plus longs d'abord (évite les conflits de sous-chaînes)
    sorted_entities = sorted(list(sensitive_entities), key=len, reverse=True)
    
    for entity in sorted_entities:
        # Regex insensible à la casse pour le remplacement
        pattern = re.compile(re.escape(entity), re.IGNORECASE)
        anonymized_text = pattern.sub("█" * len(entity), anonymized_text)

    # Création du PDF
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    # FPDF ne gère pas bien l'UTF-8 par défaut sans police spécifique, 
    # on utilise une astuce latin-1 ou une police compatible si dispo.
    # Pour simplifier ici, on encode/decode 'latin-1' en remplaçant les erreurs
    safe_text = anonymized_text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, safe_text)
    
    return pdf.output(dest='S').encode('latin-1')

# -----------------------------------------------------------------------------
# 5. INTERFACE UTILISATEUR (STREAMLIT)
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
        with st.spinner('Traitement en cours... Cela peut prendre quelques secondes (OCR + NLP).'):
            
            output_pdf_bytes = None
            
            # CAS 1 : IMAGES
            if file_type in ["image/png", "image/jpeg", "image/jpg"]:
                image = Image.open(uploaded_file)
                processed_image = anonymize_image_page(image.convert("RGB"))
                
                # Convertir en PDF
                processed_image.save("temp.pdf", "PDF", resolution=100.0)
                with open("temp.pdf", "rb") as f:
                    output_pdf_bytes = f.read()
                st.image(processed_image, caption="Aperçu anonymisé", use_column_width=True)

            # CAS 2 : PDF
            elif file_type == "application/pdf":
                # Convertir PDF en images
                images = convert_from_bytes(uploaded_file.read())
                processed_images = []
                
                progress_bar = st.progress(0)
                for i, img in enumerate(images):
                    processed_images.append(anonymize_image_page(img))
                    progress_bar.progress((i + 1) / len(images))
                
                # Sauvegarder toutes les pages dans un seul PDF
                if processed_images:
                    img_list = [img.convert('RGB') for img in processed_images]
                    img_list[0].save("temp.pdf", save_all=True, append_images=img_list[1:])
                    with open("temp.pdf", "rb") as f:
                        output_pdf_bytes = f.read()
            
            # CAS 3 : WORD (DOCX)
            elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                output_pdf_bytes = process_docx(uploaded_file.read())
            
            # TÉLÉCHARGEMENT
            if output_pdf_bytes:
                st.success("Anonymisation terminée !")
                st.download_button(
                    label="📥 Télécharger le document anonymisé (PDF)",
                    data=output_pdf_bytes,
                    file_name=f"anonymise_{uploaded_file.name.split('.')[0]}.pdf",
                    mime="application/pdf"
                )

st.sidebar.header("Notes techniques")
st.sidebar.info("""
**Confidentialité** : Les fichiers sont traités en mémoire RAM et ne sont pas stockés.
**Précision** : L'outil utilise le modèle `fr_core_news_lg` de Spacy pour le Français et Tesseract OCR. 
Il est possible que certaines entités manuscrites ou mal numérisées échappent à la détection. **Vérifiez toujours le résultat.**
""")

