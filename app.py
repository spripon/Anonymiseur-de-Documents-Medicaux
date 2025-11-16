import streamlit as st
import re
from io import BytesIO
import fitz  # PyMuPDF
from docx import Document
from docx.shared import RGBColor
import pandas as pd
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import pytesseract
import numpy as np
import cv2

# Configuration de la page

st.set_page_config(
page_title=“Anonymiseur de Documents Medicaux”,
page_icon=“🏥”,
layout=“wide”
)

# Titre de l’application

st.title(“🏥 Anonymiseur de Documents Medicaux”)
st.markdown(”—”)

# Definition des patterns de detection

PATTERNS = {
‘dates’: r’\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b’,
‘numeros_longs’: r’\b\d{6,}\b’,
‘noms_propres’: r’\b[A-ZÉÈÊËÀÂÄÔÖÛÜÇ][a-zéèêëàâäôöûüç]+(?:\s+[A-ZÉÈÊËÀÂÄÔÖÛÜÇ][a-zéèêëàâäôöûüç]+)*\b’,
‘email’: r’\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+.[A-Z|a-z]{2,}\b’,
‘telephone’: r’\b(?:+33|0)[1-9](?:[\s.-]?\d{2}){4}\b’,
‘numero_secu’: r’\b[12]\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{3}\s?\d{3}\s?\d{2}\b’
}

# Labels personnalisables

LABELS_COMMUNS = [
“Nom”, “Prenom”, “N° patient”, “Numero patient”, “Patient”,
“Age”, “Date de naissance”, “Ne(e) le”,
“Etablissement”, “Hopital”, “Clinique”,
“Date etude”, “Date d’etude”, “Date examen”,
“Effectue par”, “Realise par”, “Medecin”, “Docteur”, “Dr”,
“Adresse”, “Telephone”, “Tel”, “Email”, “N°SS”, “Securite sociale”
]

def anonymize_text(text, labels_to_remove):
“”“Anonymise le texte en fonction des patterns et labels”””
anonymized = text
replacements = []

```
# Anonymiser les dates
for match in re.finditer(PATTERNS['dates'], text):
    original = match.group()
    anonymized = anonymized.replace(original, "[DATE ANONYMISEE]")
    replacements.append(("Date", original, "[DATE ANONYMISEE]"))

# Anonymiser les numeros longs
for match in re.finditer(PATTERNS['numeros_longs'], text):
    original = match.group()
    # Eviter de remplacer les numeros qui font partie d'une date
    if not re.search(r'\d{1,2}[/-]' + re.escape(original), text):
        anonymized = anonymized.replace(original, "[NUMERO ANONYMISE]")
        replacements.append(("Numero", original, "[NUMERO ANONYMISE]"))

# Anonymiser les emails
for match in re.finditer(PATTERNS['email'], text):
    original = match.group()
    anonymized = anonymized.replace(original, "[EMAIL ANONYMISE]")
    replacements.append(("Email", original, "[EMAIL ANONYMISE]"))

# Anonymiser les telephones
for match in re.finditer(PATTERNS['telephone'], text):
    original = match.group()
    anonymized = anonymized.replace(original, "[TEL ANONYMISE]")
    replacements.append(("Telephone", original, "[TEL ANONYMISE]"))

# Anonymiser les numeros de securite sociale
for match in re.finditer(PATTERNS['numero_secu'], text):
    original = match.group()
    anonymized = anonymized.replace(original, "[N°SS ANONYMISE]")
    replacements.append(("N°SS", original, "[N°SS ANONYMISE]"))

# Anonymiser selon les labels
for label in labels_to_remove:
    # Pattern pour trouver "Label : valeur" ou "Label: valeur"
    pattern = rf'{re.escape(label)}\s*:?\s*([^\n]+)'
    for match in re.finditer(pattern, anonymized, re.IGNORECASE):
        full_match = match.group(0)
        value = match.group(1).strip()
        if value and len(value) > 0:
            replacement = f"{label}: [ANONYMISE]"
            anonymized = anonymized.replace(full_match, replacement)
            replacements.append((label, value, "[ANONYMISE]"))

return anonymized, replacements
```

def anonymize_pdf(pdf_bytes, labels_to_remove):
“”“Anonymise un fichier PDF”””
doc = fitz.open(stream=pdf_bytes, filetype=“pdf”)
all_replacements = []

```
for page_num in range(len(doc)):
    page = doc[page_num]
    text = page.get_text()
    
    # Anonymiser le texte
    anonymized_text, replacements = anonymize_text(text, labels_to_remove)
    all_replacements.extend(replacements)
    
    # Rechercher et masquer les informations sur la page
    for label in labels_to_remove:
        areas = page.search_for(label, flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for area in areas:
            # Etendre la zone pour couvrir la valeur apres le label
            extended_area = fitz.Rect(area.x0, area.y0, area.x0 + 300, area.y1)
            page.add_redact_annot(extended_area, fill=(0, 0, 0))
    
    # Masquer les dates
    for match in re.finditer(PATTERNS['dates'], text):
        areas = page.search_for(match.group())
        for area in areas:
            page.add_redact_annot(area, fill=(0, 0, 0))
    
    # Masquer les numeros longs
    for match in re.finditer(PATTERNS['numeros_longs'], text):
        areas = page.search_for(match.group())
        for area in areas:
            page.add_redact_annot(area, fill=(0, 0, 0))
    
    # Masquer les emails
    for match in re.finditer(PATTERNS['email'], text):
        areas = page.search_for(match.group())
        for area in areas:
            page.add_redact_annot(area, fill=(0, 0, 0))
    
    # Masquer les telephones
    for match in re.finditer(PATTERNS['telephone'], text):
        areas = page.search_for(match.group())
        for area in areas:
            page.add_redact_annot(area, fill=(0, 0, 0))
    
    page.apply_redactions()

# Sauvegarder le PDF anonymise
output_bytes = doc.write()
doc.close()

return output_bytes, all_replacements
```

def anonymize_docx(docx_bytes, labels_to_remove):
“”“Anonymise un fichier Word”””
doc = Document(BytesIO(docx_bytes))
all_replacements = []

```
# Anonymiser les paragraphes
for para in doc.paragraphs:
    if para.text.strip():
        anonymized_text, replacements = anonymize_text(para.text, labels_to_remove)
        all_replacements.extend(replacements)
        para.text = anonymized_text

# Anonymiser les tableaux
for table in doc.tables:
    for row in table.rows:
        for cell in row.cells:
            if cell.text.strip():
                anonymized_text, replacements = anonymize_text(cell.text, labels_to_remove)
                all_replacements.extend(replacements)
                cell.text = anonymized_text

# Sauvegarder le document
output_buffer = BytesIO()
doc.save(output_buffer)
output_buffer.seek(0)

return output_buffer.getvalue(), all_replacements
```

def anonymize_txt(txt_bytes, labels_to_remove):
“”“Anonymise un fichier texte”””
text = txt_bytes.decode(‘utf-8’, errors=‘ignore’)
anonymized_text, replacements = anonymize_text(text, labels_to_remove)
return anonymized_text.encode(‘utf-8’), replacements

def anonymize_image(image_bytes, labels_to_remove, use_ocr=True):
“”“Anonymise une image medicale”””
# Charger l’image
image = Image.open(BytesIO(image_bytes))

```
# Convertir en RGB si necessaire
if image.mode != 'RGB':
    image = image.convert('RGB')

# Creer une copie pour l'anonymisation
anonymized_image = image.copy()
draw = ImageDraw.Draw(anonymized_image)

all_replacements = []

if use_ocr:
    try:
        # Extraire le texte avec OCR
        ocr_data = pytesseract.image_to_data(image, lang='fra+eng', output_type=pytesseract.Output.DICT)
        
        n_boxes = len(ocr_data['text'])
        for i in range(n_boxes):
            text = ocr_data['text'][i].strip()
            
            if text:  # Si du texte est detecte
                conf = int(ocr_data['conf'][i])
                
                # Ne traiter que le texte avec une confiance > 30
                if conf > 30:
                    # Verifier si le texte correspond aux patterns
                    should_anonymize = False
                    replacement_type = ""
                    
                    # Verifier les dates
                    if re.match(PATTERNS['dates'], text):
                        should_anonymize = True
                        replacement_type = "Date"
                    
                    # Verifier les numeros longs
                    elif re.match(PATTERNS['numeros_longs'], text):
                        should_anonymize = True
                        replacement_type = "Numero"
                    
                    # Verifier les emails
                    elif re.match(PATTERNS['email'], text):
                        should_anonymize = True
                        replacement_type = "Email"
                    
                    # Verifier les telephones
                    elif re.match(PATTERNS['telephone'], text):
                        should_anonymize = True
                        replacement_type = "Telephone"
                    
                    # Verifier les labels personnalises
                    else:
                        for label in labels_to_remove:
                            if label.lower() in text.lower():
                                should_anonymize = True
                                replacement_type = label
                                break
                    
                    if should_anonymize:
                        # Obtenir les coordonnees du rectangle
                        x, y, w, h = (ocr_data['left'][i], 
                                    ocr_data['top'][i], 
                                    ocr_data['width'][i], 
                                    ocr_data['height'][i])
                        
                        # Agrandir legerement la zone pour couvrir tout le texte
                        padding = 5
                        x -= padding
                        y -= padding
                        w += padding * 2
                        h += padding * 2
                        
                        # Dessiner un rectangle noir pour masquer
                        draw.rectangle([x, y, x + w, y + h], fill='black')
                        
                        all_replacements.append((replacement_type, text, "[ANONYMISE]"))
    
    except Exception as e:
        st.warning(f"⚠️ OCR non disponible ou erreur: {str(e)}. Anonymisation manuelle appliquee.")

# Methode alternative : detection de texte avec OpenCV (plus robuste)
try:
    # Convertir en numpy array pour OpenCV
    img_array = np.array(image)
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    
    # Appliquer un seuillage adaptatif
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                   cv2.THRESH_BINARY, 11, 2)
    
    # Detecter les contours (zones de texte potentielles)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filtrer les contours par taille (probablement du texte)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        
        # Filtrer les petits contours (bruit) et les tres grands (pas du texte)
        if 20 < w < image.width * 0.8 and 10 < h < 100:
            # Extraire la region d'interet
            roi = gray[y:y+h, x:x+w]
            
            # Verifier si c'est probablement du texte (densite de pixels)
            white_pixel_ratio = np.sum(roi > 200) / (w * h)
            
            if 0.3 < white_pixel_ratio < 0.95:
                # Masquer cette zone si elle est dans les zones superieures de l'image
                # (ou se trouvent generalement les en-tetes avec infos patient)
                if y < image.height * 0.3:  # 30% superieur de l'image
                    draw.rectangle([x, y, x + w, y + h], fill='black')
                    all_replacements.append(("Zone detectee", f"Position ({x},{y})", "[MASQUE]"))

except Exception as e:
    st.warning(f"⚠️ Detection automatique de zones limitee: {str(e)}")

# Sauvegarder l'image anonymisee
output_buffer = BytesIO()
anonymized_image.save(output_buffer, format=image.format if image.format else 'PNG')
output_buffer.seek(0)

return output_buffer.getvalue(), all_replacements, image.format if image.format else 'PNG'
```

# Interface utilisateur

st.sidebar.header(“⚙️ Configuration”)

# Selection des labels a anonymiser

st.sidebar.subheader(“Labels a anonymiser”)
selected_labels = st.sidebar.multiselect(
“Selectionnez les champs a anonymiser:”,
LABELS_COMMUNS,
default=[“Nom”, “Prenom”, “N° patient”, “Age”, “Date de naissance”,
“Etablissement”, “Date etude”, “Effectue par”]
)

# Option pour ajouter des labels personnalises

custom_labels = st.sidebar.text_area(
“Labels personnalises (un par ligne):”,
help=“Ajoutez des labels supplementaires a anonymiser”
)

if custom_labels:
custom_labels_list = [label.strip() for label in custom_labels.split(’\n’) if label.strip()]
selected_labels.extend(custom_labels_list)

# Options pour les images

st.sidebar.subheader(“Options pour les images”)
use_ocr = st.sidebar.checkbox(
“Utiliser l’OCR (reconnaissance de texte)”,
value=True,
help=“Active la detection automatique de texte dans les images”
)

st.sidebar.markdown(”—”)
st.sidebar.info(
“ℹ️ **Information**\n\n”
“Cette application anonymise automatiquement:\n”
“- Les dates (JJ/MM/AAAA)\n”
“- Les numeros longs (6+ chiffres)\n”
“- Les emails\n”
“- Les numeros de telephone\n”
“- Les numeros de securite sociale\n”
“- Les champs selectionnes\n”
“- Le texte dans les images (OCR)”
)

# Zone de telechargement de fichier

st.subheader(“📤 Charger le document medical”)
uploaded_file = st.file_uploader(
“Choisissez un fichier (PDF, Word, TXT ou Image)”,
type=[‘pdf’, ‘docx’, ‘doc’, ‘txt’, ‘png’, ‘jpg’, ‘jpeg’, ‘gif’, ‘bmp’, ‘tiff’],
help=“Formats acceptes: PDF, DOCX, TXT, PNG, JPG, JPEG, GIF, BMP, TIFF”
)

if uploaded_file is not None:
st.success(f”✅ Fichier charge: {uploaded_file.name}”)

```
# Afficher un apercu pour les images
file_extension = uploaded_file.name.split('.')[-1].lower()
if file_extension in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff']:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📷 Image originale")
        st.image(uploaded_file, use_container_width=True)

# Bouton pour lancer l'anonymisation
if st.button("🔒 Anonymiser le document", type="primary"):
    with st.spinner("Anonymisation en cours..."):
        try:
            file_bytes = uploaded_file.read()
            file_extension = uploaded_file.name.split('.')[-1].lower()
            
            # Anonymiser selon le type de fichier
            if file_extension == 'pdf':
                anonymized_bytes, replacements = anonymize_pdf(file_bytes, selected_labels)
                mime_type = "application/pdf"
                output_extension = "pdf"
                
            elif file_extension in ['docx', 'doc']:
                anonymized_bytes, replacements = anonymize_docx(file_bytes, selected_labels)
                mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                output_extension = "docx"
                
            elif file_extension == 'txt':
                anonymized_bytes, replacements = anonymize_txt(file_bytes, selected_labels)
                mime_type = "text/plain"
                output_extension = "txt"
            
            elif file_extension in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff']:
                anonymized_bytes, replacements, img_format = anonymize_image(
                    file_bytes, selected_labels, use_ocr
                )
                mime_type = f"image/{img_format.lower()}"
                output_extension = img_format.lower()
            
            st.success("✅ Anonymisation terminee!")
            
            # Afficher l'image anonymisee si c'est une image
            if file_extension in ['png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff']:
                with col2:
                    st.subheader("🔒 Image anonymisee")
                    st.image(anonymized_bytes, use_container_width=True)
            
            # Afficher les statistiques
            col_stat1, col_stat2 = st.columns(2)
            with col_stat1:
                st.metric("Elements anonymises", len(replacements))
            with col_stat2:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Tableau des remplacements
            if replacements:
                st.subheader("📊 Details des anonymisations")
                df_replacements = pd.DataFrame(
                    replacements,
                    columns=["Type", "Valeur originale", "Remplacement"]
                )
                st.dataframe(df_replacements, use_container_width=True)
            else:
                st.info("ℹ️ Aucune donnee sensible detectee automatiquement.")
            
            # Bouton de telechargement
            st.subheader("💾 Telecharger le document anonymise")
            original_name = uploaded_file.name.rsplit('.', 1)[0]
            output_filename = f"{original_name}_anonymise_{timestamp}.{output_extension}"
            
            st.download_button(
                label=f"📥 Telecharger {output_filename}",
                data=anonymized_bytes,
                file_name=output_filename,
                mime=mime_type,
                type="primary"
            )
            
            st.warning(
                "⚠️ **Attention**: Verifiez toujours manuellement le document anonymise "
                "avant de le partager pour vous assurer que toutes les donnees sensibles "
                "ont ete correctement supprimees."
            )
            
        except Exception as e:
            st.error(f"❌ Erreur lors de l'anonymisation: {str(e)}")
            st.exception(e)
```

else:
# Instructions
st.info(
“👈 **Pour commencer:**\n\n”
“1. Selectionnez les champs a anonymiser dans la barre laterale\n”
“2. Telechargez votre document medical (PDF, Word, TXT ou Image)\n”
“3. Cliquez sur ‘Anonymiser le document’\n”
“4. Telechargez le document anonymise”
)

```
# Exemples d'utilisation
with st.expander("📖 Types de fichiers supportes"):
    st.markdown("""
    **Documents texte:**
    - PDF (avec masquage visuel des donnees)
    - Word (.docx)
    - Fichiers texte (.txt)
    
    **Images medicales:**
    - PNG
    - JPG / JPEG
    - GIF
    - BMP
    - TIFF
    
    Pour les images, l'OCR detecte automatiquement le texte et masque:
    - Les informations d'en-tete (nom, date, numero)
    - Les dates et numeros dans l'image
    - Les zones de texte personnalisees
    """)
```

# Footer

st.markdown(”—”)
st.markdown(
“<div style='text-align: center; color: gray;'>”
“🔒 Application d’anonymisation de documents medicaux | “
“Developpe pour la protection des donnees patients | “
“Support: PDF, Word, TXT, Images”
“</div>”,
unsafe_allow_html=True
)
