# Amicale des Sapeurs-Pompiers de Gerzat : espace bureau de l'appli.
# Lancé par GitHub (.github/workflows/bureau.yml) chaque nuit, ou à la main (Run workflow).
# Lit les totaux de la compta auprès du script Google du fichier « Comptabilité Amicale SP Gerzat V3 »
# (secret COMPTA_URL, adresse avec jeton), ajoute les tuiles de .github/bureau_tuiles.json,
# chiffre le tout avec le code du bureau (secret CODE_BUREAU) et l'écrit dans bureau/bureau.json.
# Le dépôt est public : rien n'y est en clair. Le fichier ne change que si les chiffres changent.
import base64, datetime, json, os, pathlib, sys, urllib.request
from zoneinfo import ZoneInfo
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

URL = os.environ.get("COMPTA_URL", "").strip()
CODE = os.environ.get("CODE_BUREAU", "").strip()
TOURS = 600000
SORTIE = pathlib.Path("bureau/bureau.json")
if not URL or not CODE:
    sys.exit("Secrets COMPTA_URL ou CODE_BUREAU manquants.")


def cle(sel):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=TOURS).derive(CODE.encode())


# 1. Les totaux de la compta
try:
    with urllib.request.urlopen(urllib.request.Request(URL, headers={"User-Agent": "amicale-bureau"}), timeout=60) as r:
        comptes = json.loads(r.read().decode("utf-8"))
except Exception as e:
    sys.exit("Script Google injoignable ou réponse illisible (" + type(e).__name__ + ").")
if not isinstance(comptes, dict) or comptes.get("erreur") or "enveloppes" not in comptes or "resultat" not in comptes:
    sys.exit("Le script Google n'a pas renvoyé les comptes (jeton refusé ou format inattendu).")
for e in comptes.get("enveloppes", []):
    if not isinstance(e, dict) or "nom" not in e:
        sys.exit("Format des enveloppes inattendu.")

tuiles = json.loads(pathlib.Path(".github/bureau_tuiles.json").read_text(encoding="utf-8"))

# 2. Comparer avec la version en ligne (sans la date) pour ne pas changer le fichier pour rien
ancien = None
try:
    c = json.loads(SORTIE.read_text(encoding="utf-8"))
    b = lambda x: base64.b64decode(c[x])
    ancien = json.loads(AESGCM(cle(b("s"))).decrypt(b("i"), b("d"), None).decode("utf-8"))
except Exception:
    pass
sans_date = lambda d: {k: v for k, v in (d or {}).items() if k != "maj"}
if ancien and ancien.get("tuiles") == tuiles and sans_date(ancien.get("comptes")) == sans_date(comptes):
    print("Comptes inchangés.")
    sys.exit(0)

comptes["maj"] = datetime.datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y")
contenu = {"tuiles": tuiles, "comptes": comptes}

# 3. Chiffrer et écrire
sel, iv = os.urandom(16), os.urandom(12)
d = AESGCM(cle(sel)).encrypt(iv, json.dumps(contenu, ensure_ascii=False).encode("utf-8"), None)
b64 = lambda x: base64.b64encode(x).decode()
SORTIE.parent.mkdir(exist_ok=True)
SORTIE.write_text(json.dumps({"s": b64(sel), "i": b64(iv), "n": TOURS, "d": b64(d)}) + "\n", encoding="utf-8")
print("Comptes mis à jour :", len(comptes.get("enveloppes", [])), "enveloppes.")
