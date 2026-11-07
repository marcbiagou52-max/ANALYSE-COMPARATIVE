

import json
import random
import re
import sys
import unicodedata
from difflib import get_close_matches
from pathlib import Path
from time import perf_counter

import pandas as pd

DATA_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data"
OUT_DIR = Path(__file__).parent / "sorties"

PANIER = {"P04": 1, "P12": 1, "P14": 2, "P15": 1, "P28": 1}
BF_DEBUT, BF_FIN = pd.Timestamp("2025-11-24"), pd.Timestamp("2025-11-30")
SEUIL_RAPPROCHEMENT = 0.50
BONUS_MARQUE = 0.25

# Synonymes FR/abréviations -> forme commune (les enseignes n'écrivent pas pareil)
SYNONYMES = {
    "moniteur": "monitor", "ecran": "monitor", "refrigerateur": "fridge", "frigo": "fridge",
    "climatiseur": "air conditioner", "clim": "air conditioner", "routeur": "router",
    "imprimante": "printer", "souris": "mouse", "bouilloire": "kettle", "electrique": "electric",
    "mixeur": "blender", "fer": "iron", "micro": "microwave", "ondes": "microwave",
    "ventilateur": "fan", "ventilo": "fan", "dd": "disque dur", "televiseur": "tv",
    "television": "tv",
    # mots sans valeur discriminante : supprimés
    "telephone": "", "smartphone": "", "ordinateur": "", "pc": "", "portable": "", "laptop": "",
    "core": "", "ssd": "", "pouces": "", "pouce": "", "repasser": "", "vapeur": "", "steam": "",
    "cle": "", "sur": "", "pied": "", "de": "", "du": "", "la": "", "le": "", "a": "",
}


# ---------------------------------------------------------------- utilitaires
def normaliser(texte):
    """minuscules, sans accents, sans ponctuation, unités homogènes (128 Go = 128GB)."""
    t = unicodedata.normalize("NFKD", str(texte)).encode("ascii", "ignore").decode().lower()
    t = t.replace("sans fil", "wireless")
    t = re.sub(r"(?<=\d)[.,](?=\d)", "", t)           # 1.5L -> 15l
    t = re.sub(r"(\d+)\s*(go|gb|g)\b", r"\1gb", t)    # 128 Go -> 128gb
    t = re.sub(r"(\d+)\s*(to|tb)\b", r"\1tb", t)      # 1 To -> 1tb
    t = re.sub(r"(\d+)\s*(cv|hp)\b", r"\1hp", t)      # 1 CV = 1HP
    t = re.sub(r"(\d+)\s*l\b", r"\1l", t)             # 205 L -> 205l
    t = re.sub(r"[^a-z0-9]+", " ", t)
    mots = []
    for m in t.split():
        mots.extend(SYNONYMES.get(m, m).split())
    return " ".join(mots)


def en_entier(valeur):
    """'102 900 FCFA' -> 102900 ; vide / illisible -> None."""
    if valeur is None or (isinstance(valeur, float) and pd.isna(valeur)):
        return None
    chiffres = re.sub(r"[^\d]", "", str(valeur).split(",")[0].split(".")[0])
    return int(chiffres) if chiffres else None


# ---------------------------------------------------------------- 1. collecter
def charger_lagune(chemin):
    df = pd.read_csv(chemin, sep=";", encoding="utf-8-sig", dtype=str)
    df.columns = df.columns.str.strip()
    dispo = df["disponibilite"].fillna("").str.strip().str.lower()
    return pd.DataFrame({
        "enseigne": "Marché Lagune",
        "nom_brut": df["designation"],
        "prix": df["prix"].map(en_entier),          # livraison déjà incluse
        "ancien_prix": df["ancien_prix"].map(en_entier),
        "dispo": ~dispo.eq("rupture") & dispo.ne(""),
    })


def charger_baobab(chemin):
    with open(chemin, encoding="utf-8") as f:
        items = json.load(f)["items"]
    lignes = []
    for it in items:
        p = it.get("pricing", {})
        montant = p.get("amount")
        prix = None if montant is None else montant + (p.get("delivery_fee") or 0)
        lignes.append({
            "enseigne": "Baobab Shop",
            "nom_brut": it.get("title"),
            "prix": prix,
            "dispo": (it.get("stock") or 0) > 0,
        })
    return pd.DataFrame(lignes)


def charger_comptoir(chemin):
    try:
        df = pd.read_excel(chemin, sheet_name="Tarifs octobre 2026", header=2)
    except ValueError:                                  # feuille renommée : on prend la première
        df = pd.read_excel(chemin, sheet_name=0, header=2)
    df.columns = df.columns.astype(str).str.strip()
    cat = df["Prix catalogue (FCFA)"].map(en_entier)
    remise = pd.to_numeric(df["Remise (%)"], errors="coerce").fillna(0)
    prix = (cat.astype("Float64") * (1 - remise / 100)).round().astype("Int64")
    qte = pd.to_numeric(df["Quantité en rayon"], errors="coerce").fillna(0)
    return pd.DataFrame({
        "enseigne": "Comptoir Ivoire",
        "nom_brut": df["Article"],
        "prix": prix,
        "dispo": qte > 0,
    })


# ---------------------------------------------------------------- 2. nettoyer
def nettoyer(df, journal):
    n0 = len(df)
    df = df.copy()
    df["nom_brut"] = df["nom_brut"].astype("string").str.strip()
    vides = df["nom_brut"].isna() | df["nom_brut"].eq("")
    for enseigne, k in df[vides].groupby("enseigne").size().items():
        journal.append(f"[{enseigne}] {k} ligne(s) sans nom supprimée(s)")
    df = df[~vides].copy()

    df["prix"] = pd.to_numeric(df["prix"], errors="coerce")
    if "ancien_prix" not in df:
        df["ancien_prix"] = pd.NA
    ancien = pd.to_numeric(df["ancien_prix"], errors="coerce")
    incoherent = df["prix"].notna() & ancien.notna() & (df["prix"] > ancien)
    for _, r in df[incoherent].iterrows():
        journal.append(f"[{r.enseigne}] prix {int(r.prix)} supérieur au prix barré {int(r.ancien_prix)} "
                       f"(faute de frappe probable) -> ligne ignorée : {r.nom_brut}")
    invalides = df["prix"].isna() | (df["prix"] <= 0) | incoherent
    for _, r in df[invalides & ~incoherent].iterrows():
        journal.append(f"[{r.enseigne}] prix manquant/invalide -> ligne ignorée : {r.nom_brut}")
    df.loc[invalides, "prix"] = pd.NA

    df["nom_norm"] = df["nom_brut"].map(normaliser)
    doublons = df.duplicated(["enseigne", "nom_norm"], keep="first")
    for _, r in df[doublons].iterrows():
        journal.append(f"[{r.enseigne}] doublon supprimé : {r.nom_brut}")
    df = df[~doublons].reset_index(drop=True)
    for _, r in df[~df["dispo"] & df["prix"].notna()].iterrows():
        journal.append(f"[{r.enseigne}] rupture de stock -> exclue du comparatif : {r.nom_brut}")
    journal.append(f"Nettoyage : {n0} lignes lues, {len(df)} conservées")
    return df


# ---------------------------------------------------------------- 3. rapprocher
def score(article, produit, marque):
    """Similarité cosinus sur les mots + bonus si la marque du catalogue est dans l'article."""
    ta, tb = set(article), set(produit)
    if not ta or not tb:
        return 0.0
    cos = len(ta & tb) / (len(ta) * len(tb)) ** 0.5
    return cos + (BONUS_MARQUE if marque and set(marque) <= ta else 0.0)


def rapprocher(df, catalogue, journal):
    cat = [(r.produit_id, normaliser(r.nom + " " + r.marque).split(), normaliser(r.marque).split())
           for r in catalogue.itertuples()]
    vocab = sorted({m for _, mots, _ in cat for m in mots if m.isalpha() and len(m) >= 4})
    ids = []
    for r in df.itertuples():
        mots = []
        for m in r.nom_norm.split():          # corrige les fautes de frappe (samsun -> samsung)
            if m.isalpha() and len(m) >= 4 and m not in vocab:
                proche = get_close_matches(m, vocab, n=1, cutoff=0.85)
                if proche:
                    journal.append(f"[{r.enseigne}] faute corrigée : {m} -> {proche[0]} ({r.nom_brut})")
                    m = proche[0]
            mots.append(m)
        scores = sorted(((score(mots, pm, mq), pid) for pid, pm, mq in cat), reverse=True)
        (s1, p1), (s2, p2) = scores[0], scores[1]
        if s1 < SEUIL_RAPPROCHEMENT:
            journal.append(f"[{r.enseigne}] non rapproché (meilleur score {s1:.2f}) : {r.nom_brut}")
            ids.append(None)
            continue
        if s1 - s2 < 0.05:
            journal.append(f"[{r.enseigne}] rapprochement ambigu {p1}/{p2} (à vérifier) : {r.nom_brut}")
        ids.append(p1)
    df = df.copy()
    df["produit_id"] = ids
    journal.append(f"Rapprochement : {df.produit_id.notna().sum()}/{len(df)} articles associés")
    return df


# ---------------------------------------------------------------- 4. indexer
def indexer(df, journal):
    """index[produit_id][enseigne] = prix payé (offres achetables uniquement). Accès O(1)."""
    offres = df[df.produit_id.notna() & df.prix.notna() & df.dispo]
    index = {}
    for r in offres.itertuples():
        actuel = index.setdefault(r.produit_id, {}).get(r.enseigne)
        if actuel is not None:
            journal.append(f"[{r.enseigne}] {r.produit_id} associé à 2 articles, prix le plus bas gardé")
        index[r.produit_id][r.enseigne] = int(min(r.prix, actuel) if actuel is not None else r.prix)
    # prix aberrant : > 3x ou < 1/3 de la médiane des autres enseignes (si au moins 2 autres)
    for pid, offres in index.items():
        for e in list(offres):
            autres = sorted(p for k, p in offres.items() if k != e)
            if len(autres) >= 2:
                med = autres[len(autres) // 2] if len(autres) % 2 else sum(autres[len(autres)//2-1:len(autres)//2+1]) / 2
                if offres[e] > 3 * med or offres[e] < med / 3:
                    journal.append(f"[{e}] {pid} : prix {int(offres[e])} aberrant (médiane des autres {med:.0f}) -> exclu")
                    del offres[e]
    return index


# ---------------------------------------------------------------- 5. comparer
def comparer(index, catalogue, journal):
    noms = dict(zip(catalogue.produit_id, catalogue.nom))
    enseignes = sorted({e for offres in index.values() for e in offres})
    lignes = []
    for pid in sorted(index):
        offres = index[pid]
        if len(offres) < 2:
            journal.append(f"{pid} ({noms.get(pid)}) : une seule enseigne -> comparaison impossible")
            continue
        pmin, pmax = min(offres.values()), max(offres.values())
        moins_chere = " / ".join(sorted(e for e, p in offres.items() if p == pmin))
        ligne = {"produit_id": pid, "nom": noms.get(pid)}
        for e in enseignes:
            ligne[f"prix_{e}"] = offres.get(e)
        ligne.update({
            "moins_chere": moins_chere,
            "prix_min": pmin,
            "prix_moyen": round(sum(offres.values()) / len(offres)),
            "ecart_fcfa": pmax - pmin,
            "ecart_pct": round((pmax - pmin) / pmin * 100, 1),
        })
        lignes.append(ligne)
    return pd.DataFrame(lignes)


# ---------------------------------------------------------------- 6. décider
def synthese(comp, index):
    print("\n=== SYNTHÈSE ===")
    victoires = {}
    for cell in comp["moins_chere"]:
        for e in cell.split(" / "):
            victoires[e] = victoires.get(e, 0) + 1
    print(f"Produits comparés : {len(comp)}")
    for e, v in sorted(victoires.items(), key=lambda x: -x[1]):
        print(f"  {e} : moins chère {v} fois sur {len(comp)}")

    print("\nÉcart moyen par rapport au prix le plus bas :")
    ecarts = {}
    for pid in comp.produit_id:
        offres = index[pid]
        pmin = min(offres.values())
        for e, p in offres.items():
            ecarts.setdefault(e, []).append((p - pmin) / pmin * 100)
    for e, l in sorted(ecarts.items(), key=lambda x: sum(x[1]) / len(x[1])):
        print(f"  {e} : +{sum(l) / len(l):.1f} %")

    print("\nTop 3 des produits où comparer rapporte le plus :")
    for r in comp.nlargest(3, "ecart_fcfa").itertuples():
        print(f"  {r.produit_id} {r.nom} : {r.ecart_fcfa:,} FCFA ({r.ecart_pct} %) "
              f"-> {r.moins_chere}".replace(",", " "))


def panier(index, catalogue):
    noms = dict(zip(catalogue.produit_id, catalogue.nom))
    enseignes = sorted({e for o in index.values() for e in o})
    lignes, totaux = [], {}
    print("\n=== PANIER DE RENTRÉE ===")
    for e in enseignes:
        manquants = [pid for pid in PANIER if e not in index.get(pid, {})]
        if manquants:
            totaux[e] = None
            print(f"  {e} : panier incomplet (indisponible : {', '.join(manquants)})")
        else:
            totaux[e] = sum(index[pid][e] * q for pid, q in PANIER.items())
            print(f"  {e} : {totaux[e]:,} FCFA".replace(",", " "))
    optimal, manque_opt = 0, []
    for pid, q in PANIER.items():
        offres = index.get(pid, {})
        if not offres:
            manque_opt.append(pid)
            continue
        e = min(offres, key=offres.get)
        optimal += offres[e] * q
        lignes.append({"produit_id": pid, "nom": noms.get(pid), "quantite": q,
                       "enseigne": e, "prix_unitaire": offres[e], "total": offres[e] * q})
    if manque_opt:
        print(f"  Panier optimal impossible : {manque_opt} introuvable(s) partout")
    else:
        print(f"  Meilleur de chaque enseigne : {optimal:,} FCFA".replace(",", " "))
        complets = [t for t in totaux.values() if t]
        if complets:
            print(f"  Économie vs meilleure enseigne unique : {min(complets) - optimal:,} FCFA".replace(",", " "))
    pd.DataFrame(lignes).to_csv(OUT_DIR / "panier.csv", index=False, sep=";", encoding="utf-8-sig")


# ---------------------------------------------------------------- 7. historique
def analyser_historique(hist):
    print("\n=== HISTORIQUE : BLACK FRIDAY (24-30 nov. 2025) ===")
    moy_annee = hist.groupby(["source", "produit_id"])["prix_fcfa"].mean()
    bf = hist[(hist.date >= BF_DEBUT) & (hist.date <= BF_FIN)]
    moy_bf = bf.groupby(["source", "produit_id"])["prix_fcfa"].mean()
    ecart = ((moy_bf / moy_annee - 1) * 100).dropna()           # % par (source, produit)
    res = ecart.groupby("source").agg(ecart_moyen_pct="mean", produits="count").round(1)
    print(res.to_string())
    res.to_csv(OUT_DIR / "black_friday.csv", sep=";", encoding="utf-8-sig")
    print("(Comptoir Ivoire : prix catalogue, sans la remise)")

    # Meilleur mois d'achat : prix relatif au prix moyen annuel du même produit
    h = hist.copy()
    h["indice"] = h["prix_fcfa"] / h.groupby(["source", "produit_id"])["prix_fcfa"].transform("mean")
    h["mois"] = h["date"].dt.to_period("M")
    mois = h.groupby(["source", "mois"])["indice"].mean()
    print("\nMois le moins cher (indice 1.00 = prix moyen annuel) :")
    for source, serie in mois.groupby(level=0):
        m = serie.idxmin()[1]
        print(f"  {source} : {m} (indice {serie.min():.3f})")


# ---------------------------------------------------------------- 8. complexité
def benchmark(hist, n_requetes=200):
    print("\n=== COMPLEXITÉ ===")
    lignes = list(hist[["date", "source", "produit_id", "prix_fcfa"]].itertuples(index=False, name=None))
    t = perf_counter()
    dico = {(d, s, p): prix for d, s, p, prix in lignes}
    t_build = perf_counter() - t
    cles = random.sample(list(dico), min(n_requetes, len(dico)))

    t = perf_counter()
    for k in cles:
        next(prix for d, s, p, prix in lignes if (d, s, p) == k)
    t_liste = perf_counter() - t

    t = perf_counter()
    for k in cles:
        dico[k]
    t_dict = perf_counter() - t

    print(f"n = {len(lignes)} lignes, {len(cles)} recherches")
    print(f"  Construction du dictionnaire : {t_build * 1000:.1f} ms  -> O(n)")
    print(f"  Recherche liste (balayage)   : {t_liste * 1000:.1f} ms  -> O(n) par requête")
    print(f"  Recherche dictionnaire       : {t_dict * 1000:.3f} ms  -> O(1) en moyenne")
    if t_dict > 0:
        print(f"  Gain : x{t_liste / t_dict:,.0f}".replace(",", " "))


# ---------------------------------------------------------------- main
def main():
    OUT_DIR.mkdir(exist_ok=True)
    journal = []
    chrono = {}

    t = perf_counter()
    catalogue = pd.read_csv(DATA_DIR / "catalogue_reference.csv", encoding="utf-8-sig")
    brut = pd.concat([
        charger_lagune(DATA_DIR / "marche_lagune.csv"),
        charger_baobab(DATA_DIR / "baobab_shop.json"),
        charger_comptoir(DATA_DIR / "comptoir_ivoire.xlsx"),
    ], ignore_index=True)
    chrono["collecte"] = perf_counter() - t
    print(f"Collecte : {len(brut)} lignes ({brut.groupby('enseigne').size().to_dict()})")

    t = perf_counter()
    propre = nettoyer(brut, journal)
    chrono["nettoyage"] = perf_counter() - t

    t = perf_counter()
    rapproche = rapprocher(propre, catalogue, journal)
    chrono["rapprochement"] = perf_counter() - t

    t = perf_counter()
    index = indexer(rapproche, journal)
    comp = comparer(index, catalogue, journal)
    chrono["indexation + comparaison"] = perf_counter() - t

    comp.to_csv(OUT_DIR / "comparatif.csv", index=False, sep=";", encoding="utf-8-sig")
    print(f"Comparatif exporté : {len(comp)} produits -> sorties/comparatif.csv")

    synthese(comp, index)
    panier(index, catalogue)

    t = perf_counter()
    hist = pd.read_csv(DATA_DIR / "historique_prix.csv", parse_dates=["date"])
    analyser_historique(hist)
    chrono["historique"] = perf_counter() - t

    benchmark(hist)

    print("\n=== TEMPS D'EXÉCUTION ===")
    for k, v in chrono.items():
        print(f"  {k} : {v * 1000:.1f} ms")

    (OUT_DIR / "journal.txt").write_text("\n".join(journal), encoding="utf-8")
    print(f"\nJournal : {len(journal)} entrées -> sorties/journal.txt")


if __name__ == "__main__":
    main()