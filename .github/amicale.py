# Amicale des Sapeurs-Pompiers de Gerzat
# Lancé par GitHub (.github/workflows/agenda.yml). Deux travaux :
# 1. refaire agenda/amicale.ics, l'agenda auquel les téléphones sont abonnés ;
# 2. envoyer les notifications automatiques de chaque date :
#    à l'ajout, 15 jours avant (vers 18 h) et la veille (vers 18 h).
# Ce qui a déjà été envoyé est noté dans agenda/notifications.json.
# Les dates viennent des tableaux AGENDA et INSCRIPTIONS de index.html.
import datetime, json, os, pathlib, re, sys, unicodedata, urllib.request
from zoneinfo import ZoneInfo

APP_ID = "ff8f17cb-65d5-4a47-8825-8860c79a6e52"
LIEN = "https://amicalespgerzat-source.github.io/#agenda"
ESSAI = os.environ.get("ESSAI") == "1"          # 1 : affiche sans rien envoyer
CLE = os.environ.get("ONESIGNAL_CLE", "").strip()
EVENEMENT = os.environ.get("GITHUB_EVENT_NAME", "")
maintenant = datetime.datetime.now(ZoneInfo("Europe/Paris"))
if os.environ.get("MAINTENANT"):                 # pour les essais
    maintenant = datetime.datetime.fromisoformat(os.environ["MAINTENANT"]).replace(tzinfo=ZoneInfo("Europe/Paris"))
aujourdhui = maintenant.date()

page = pathlib.Path("index.html").read_text(encoding="utf-8")


def tableau(nom):
    m = re.search(r"const " + nom + r" = \[(.*?)\n\];", page, re.S)
    if not m:
        return []
    return [dict(re.findall(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', o)) for o in re.findall(r"\{(.*?)\}", m.group(1), re.S)]


def slug(e):
    t = unicodedata.normalize("NFD", e["date"] + "-" + e["titre"])
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()


def lire(d):
    return datetime.date(*map(int, d.split("-")))


evenements = {}
for e in tableau("AGENDA") + tableau("INSCRIPTIONS"):
    try:
        e["_date"] = lire(e["date"])
        evenements[slug(e)] = e
    except Exception as err:
        print("Date ignorée, mal écrite :", e.get("titre"), e.get("date"), err)


# ---------- 1. Agenda abonné ----------

def echap(t):
    return t.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def plier(l):
    b = l.encode("utf-8"); morceaux = []
    while len(b) > 74:
        k = 74
        while (b[k] & 0xC0) == 0x80:
            k -= 1
        morceaux.append(b[:k].decode("utf-8")); b = b[k:]
    morceaux.append(b.decode("utf-8"))
    return "\r\n ".join(morceaux)


tampon = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def vevent(e):
    d = e["_date"]
    h = re.search(r"(\d{1,2})\s*h\s*(\d{2})?", e.get("heure", ""))
    f = "%Y%m%dT%H%M%S"
    if h:
        t = datetime.datetime(d.year, d.month, d.day, int(h.group(1)), int(h.group(2) or 0))
        quand = ["DTSTART:" + t.strftime(f), "DTEND:" + (t + datetime.timedelta(hours=2)).strftime(f)]
    else:
        quand = ["DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"), "DTEND;VALUE=DATE:" + (d + datetime.timedelta(days=1)).strftime("%Y%m%d")]
    desc = "\n".join(x for x in [e.get("heure", ""), e.get("detail", ""), ("Affiche : " + e["affiche"]) if e.get("affiche") else ""] if x)
    return ["BEGIN:VEVENT", "UID:" + slug(e) + "@amicalespgerzat-source.github.io", "DTSTAMP:" + tampon] + quand + [
            "SUMMARY:" + echap(e["titre"]), "LOCATION:" + echap(e.get("lieu", "")),
            "DESCRIPTION:" + echap(desc), "END:VEVENT"]


lignes = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Amicale SP Gerzat//Appli//FR", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
          "X-WR-CALNAME:Amicale SP Gerzat", "X-WR-TIMEZONE:Europe/Paris",
          "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
for k in sorted(evenements):
    lignes += vevent(evenements[k])
lignes.append("END:VCALENDAR")
nouveau = "\r\n".join(plier(l) for l in lignes) + "\r\n"
ics = pathlib.Path("agenda/amicale.ics")
sans_tampon = lambda t: re.sub(r"DTSTAMP:\S+", "", t)
ancien = ics.read_bytes().decode("utf-8") if ics.exists() else ""
if sans_tampon(ancien) == sans_tampon(nouveau):
    print("Agenda déjà à jour.")
else:
    ics.parent.mkdir(exist_ok=True)
    ics.write_bytes(nouveau.encode("utf-8"))
    print("Agenda mis à jour :", len(evenements), "dates.")


# ---------- 2. Notifications ----------

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]


def jour(d):
    return f"{JOURS[d.weekday()]} {d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]}"


def phrase(*morceaux):
    t = ", ".join(m.strip() for m in morceaux if m and m.strip())
    return t[0].upper() + t[1:] + "." if t else ""


def inscription(e):
    if e.get("dernierJour"):
        try:
            fin = lire(e["dernierJour"])
        except Exception:
            return ""
        if fin >= aujourdhui:
            return " Inscription dans l'appli avant le " + jour(fin + datetime.timedelta(days=1)) + "."
    return ""


fichier_suivi = pathlib.Path("agenda/notifications.json")
suivi = json.loads(fichier_suivi.read_text(encoding="utf-8")) if fichier_suivi.exists() else {}


def envoyer(cle_suivi, titre, texte):
    print(("[essai] " if ESSAI else "") + "Notification :", titre, "|", texte)
    if ESSAI:
        suivi[cle_suivi] = aujourdhui.isoformat()
        return True
    if not CLE:
        print("Clé OneSignal absente : rien n'est envoyé. Ajouter le secret ONESIGNAL_CLE dans GitHub.")
        return False
    corps = {"app_id": APP_ID, "target_channel": "push", "included_segments": ["Total Subscriptions"],
             "headings": {"en": titre, "fr": titre}, "contents": {"en": texte, "fr": texte}, "url": LIEN}
    req = urllib.request.Request("https://api.onesignal.com/notifications", data=json.dumps(corps).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Authorization": "Key " + CLE})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            reponse = json.loads(r.read().decode("utf-8") or "{}")
    except Exception as err:
        print("Envoi refusé :", err)
        return False
    if reponse.get("errors"):
        print("OneSignal a répondu :", reponse["errors"])
    suivi[cle_suivi] = aujourdhui.isoformat()
    return True


if os.environ.get("TEST_ENVOI") == "true":    # bouton Run workflow, case cochée
    probleme_test = not envoyer("test", "Test de l'amicale", "Les notifications automatiques marchent.")
    suivi.pop("test", None)
    if probleme_test:
        sys.exit(1)

journee = 8 <= maintenant.hour < 21          # pas de notification la nuit
soir = maintenant.hour >= 18 and EVENEMENT != "push"
probleme = False

for k in sorted(evenements, key=lambda k: evenements[k]["_date"]):
    e = evenements[k]
    n = (e["_date"] - aujourdhui).days
    if n < 0:
        continue
    deja_aujourdhui = any(suivi.get(k + ":" + q) == aujourdhui.isoformat() for q in ("nouveau", "j15", "veille"))

    # A l'ajout
    if (k + ":nouveau") not in suivi and n >= 1:
        if journee:
            ok = envoyer(k + ":nouveau", "Nouvelle date : " + e["titre"],
                         phrase(jour(e["_date"]), e.get("heure", ""), e.get("lieu", "")) + inscription(e))
            probleme |= not ok
        continue

    if deja_aujourdhui or not soir:
        continue

    # 15 jours avant, sauf si la date vient d'être annoncée
    annonce = suivi.get(k + ":nouveau", "2000-01-01")
    recente = (e["_date"] - lire(annonce)).days <= 15
    if (k + ":j15") not in suivi and 2 <= n <= 15 and not recente:
        ok = envoyer(k + ":j15", f"{e['titre']} dans {n} jours",
                     phrase(jour(e["_date"]), e.get("heure", ""), e.get("lieu", "")) + inscription(e))
        probleme |= not ok
        continue

    # La veille
    if (k + ":veille") not in suivi and n == 1:
        ok = envoyer(k + ":veille", e["titre"] + " demain",
                     phrase(e.get("heure", ""), e.get("lieu", "")) + (" " + e["detail"] if e.get("detail") else ""))
        probleme |= not ok

# On oublie les dates passées depuis plus de 30 jours
garder = {}
for cle_suivi, quand in suivi.items():
    s = cle_suivi.rsplit(":", 1)[0]
    e = evenements.get(s)
    if e and (aujourdhui - e["_date"]).days > 30:
        continue
    if not e and (aujourdhui - lire(quand)).days > 60:
        continue
    garder[cle_suivi] = quand
fichier_suivi.write_text(json.dumps(garder, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")

if probleme:
    sys.exit(1)
