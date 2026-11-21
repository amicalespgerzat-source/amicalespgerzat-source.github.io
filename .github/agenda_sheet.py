# Amicale des Sapeurs-Pompiers de Gerzat
# Lecture de l'agenda dans le Google Sheets « Agenda de l'amicale » (onglet Agenda, partagé en lecture par lien).
# Une ligne = une date. Colonnes, dans l'ordre : Titre, Date, Heure, Lieu, Texte, Tarif, Pour qui,
# Dernier jour d'inscription, Lien d'inscription, Liste des inscrits, Affiche, Cacher heure et lieu.
# Avec un dernier jour d'inscription, la ligne est une inscription ; sinon, une simple date.
# Renvoie (AGENDA, INSCRIPTIONS) au même format que les tableaux de index.html, ou None si le tableau est illisible.
import csv, io, re, urllib.request

FEUILLE = "1-ANd1ryleo8jOcjUr5rnV2J7HfhO6sL6G3bcjBg8ZNg"
URL = "https://docs.google.com/spreadsheets/d/" + FEUILLE + "/gviz/tq?tqx=out:csv&headers=1&sheet=Agenda"
CLES = ["titre", "date", "heure", "lieu", "detail", "tarif", "public", "dernierJour", "lien", "inscrits", "affiche", "cacherHeure"]


def iso(t):
    t = (t or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    return t if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t) else ""


def lire_agenda():
    try:
        with urllib.request.urlopen(URL, timeout=30) as r:
            texte = r.read().decode("utf-8")
    except Exception as err:
        print("Tableau Agenda illisible :", err)
        return None
    lignes = list(csv.reader(io.StringIO(texte)))
    if not lignes or not lignes[0] or lignes[0][0].strip().lower() != "titre":
        print("Tableau Agenda : en-tête inattendu, on garde index.html.")
        return None
    agenda, inscriptions = [], []
    for l in lignes[1:]:
        l = (l + [""] * len(CLES))[:len(CLES)]
        e = {k: v.strip() for k, v in zip(CLES, l) if v.strip()}
        e["date"] = iso(e.get("date"))
        if not e.get("titre") or not e["date"]:
            continue
        if e.get("dernierJour"):
            e["dernierJour"] = iso(e["dernierJour"])
        if e.get("cacherHeure", "").lower() != "oui":
            e.pop("cacherHeure", None)
        if e.get("dernierJour"):
            inscriptions.append(e)
        else:
            e.pop("dernierJour", None)
            agenda.append(e)
    return agenda, inscriptions
