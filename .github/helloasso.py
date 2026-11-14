# Amicale des Sapeurs-Pompiers de Gerzat
# Lancé par GitHub (.github/workflows/inscrits.yml), toutes les heures en journée.
# Pour chaque inscription de index.html dont le lien est sur HelloAsso et qui a
#   inscrits: "agenda/inscrits-....json"
# on lit la liste des inscrits sur HelloAsso et on l'écrit dans ce fichier,
# chiffrée avec le code de l'appli : le dépôt est public, les noms n'y sont jamais en clair.
# Secrets GitHub : HELLOASSO_ID, HELLOASSO_SECRET (HelloAsso, Mon compte, Intégrations et API)
# et CODE_AMICALE (le code de l'appli).
import base64, datetime, json, os, pathlib, re, sys, urllib.error, urllib.parse, urllib.request
from zoneinfo import ZoneInfo
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

API = os.environ.get("HELLOASSO_API", "https://api.helloasso.com")   # changé seulement pour les essais
ID = os.environ.get("HELLOASSO_ID", "").strip()
SECRET = os.environ.get("HELLOASSO_SECRET", "").strip()
CODE = os.environ.get("CODE_AMICALE", "").strip()
TOURS = 200000
TYPES = {"evenements": "Event", "adhesions": "Membership", "boutiques": "Shop",
         "formulaires": "PaymentForm", "collectes": "CrowdFunding", "paiements": "PaymentForm"}

page = pathlib.Path("index.html").read_text(encoding="utf-8")


def tableau(nom):
    m = re.search(r"const " + nom + r" = \[(.*?)\n\];", page, re.S)
    if not m:
        return []
    return [dict(re.findall(r'(\w+):\s*"((?:[^"\\]|\\.)*)"', o)) for o in re.findall(r"\{(.*?)\}", m.group(1), re.S)]


a_faire = []
for e in tableau("INSCRIPTIONS"):
    fichier = e.get("inscrits", "")
    m = re.search(r"helloasso\.com/associations/([^/]+)/([^/]+)/([^/?#]+)", e.get("lien", ""))
    if m and re.fullmatch(r"agenda/inscrits-[a-z0-9-]+\.json", fichier):
        a_faire.append((e, m.group(1), TYPES.get(m.group(2), "Event"), m.group(3), pathlib.Path(fichier)))

if not a_faire:
    print("Aucune inscription HelloAsso avec liste des inscrits.")
    sys.exit(0)
if not (ID and SECRET and CODE):
    print("Secrets manquants (HELLOASSO_ID, HELLOASSO_SECRET, CODE_AMICALE) : rien n'est fait.")
    sys.exit(0)


def demande(url, donnees=None, jeton=None):
    entetes = {"Accept": "application/json", "User-Agent": "AmicaleSPGerzat/1.0 (amicale.spgerzat@gmail.com)"}
    if jeton:
        entetes["Authorization"] = "Bearer " + jeton
    if donnees is not None:
        donnees = urllib.parse.urlencode(donnees).encode()
        entetes["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=donnees, headers=entetes), timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as err:
        print("HelloAsso a refusé :", err.code, url.split("?")[0], (err.read() or b"").decode("utf-8", "replace")[:300])
        sys.exit(1)


jeton = demande(API + "/oauth2/token", {"grant_type": "client_credentials", "client_id": ID, "client_secret": SECRET})["access_token"]


def articles(orga, type_, slug):
    tout, page_ = [], 1
    while True:
        q = urllib.parse.urlencode({"pageSize": 100, "pageIndex": page_})
        rep = demande(f"{API}/v5/organizations/{orga}/forms/{type_}/{slug}/items?{q}", jeton=jeton)
        tout += rep.get("data") or []
        pag = rep.get("pagination") or {}
        if page_ >= (pag.get("totalPages") or 1) or not rep.get("data"):
            return tout
        page_ += 1


def nom(p):
    p = p or {}
    return " ".join(x for x in [(p.get("lastName") or "").strip().upper(), (p.get("firstName") or "").strip().title()] if x)


def cle(sel):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sel, iterations=TOURS).derive(CODE.encode())


def lire_ancien(f):
    try:
        c = json.loads(f.read_text(encoding="utf-8"))
        b = lambda x: base64.b64decode(c[x])
        return json.loads(AESGCM(cle(b("s"))).decrypt(b("i"), b("d"), None).decode("utf-8"))
    except Exception:
        return None


def ecrire(f, contenu):
    sel, iv = os.urandom(16), os.urandom(12)
    d = AESGCM(cle(sel)).encrypt(iv, json.dumps(contenu, ensure_ascii=False).encode("utf-8"), None)
    b = lambda x: base64.b64encode(x).decode()
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps({"s": b(sel), "i": b(iv), "n": TOURS, "d": b(d)}) + "\n", encoding="utf-8")


for e, orga, type_, slug, fichier in a_faire:
    familles, totaux = {}, {}
    for it in articles(orga, type_, slug):
        if it.get("state") in ("Canceled", "Refunded", "Refused", "Abandoned", "Deleted", "Contested"):
            continue
        if it.get("type") not in (None, "Registration", "Membership", "Product"):
            continue
        commande = (it.get("order") or {}).get("id") or it.get("id")
        qui = nom(it.get("payer")) or nom(it.get("user")) or "Sans nom"
        tarif = (it.get("name") or "Place").strip()
        f = familles.setdefault(commande, {"nom": qui, "tarifs": {}})
        f["tarifs"][tarif] = f["tarifs"].get(tarif, 0) + 1
        totaux[tarif] = totaux.get(tarif, 0) + 1
    lignes = sorted(([f["nom"], ", ".join(f"{t} : {n}" for t, n in sorted(f["tarifs"].items()))] for f in familles.values()),
                    key=lambda l: l[0].lower())
    if lignes:
        compte = f"{len(lignes)} inscription(s). " + ", ".join(f"{t} : {n}" for t, n in sorted(totaux.items())) + "."
    else:
        compte = "Pas encore d'inscrit."
    contenu = {"titre": e.get("titre", ""), "compte": compte, "lignes": lignes}
    ancien = lire_ancien(fichier)
    if ancien and {k: v for k, v in ancien.items() if k != "maj"} == contenu:
        print(e.get("titre"), ": liste inchangée,", len(lignes), "inscription(s).")
        continue
    contenu["maj"] = datetime.datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m à %H h %M")
    ecrire(fichier, contenu)
    print(e.get("titre"), ": liste mise à jour,", len(lignes), "inscription(s).")
