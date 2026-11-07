
import sys
from time import perf_counter

import pandas as pd

import comparateur as c

ETAT = {}   # données chargées : journal, catalogue, index, comp, hist


def pause():
    input("\nAppuyez sur Entrée pour revenir au menu...")


def fcfa(n):
    return f"{int(n):,}".replace(",", " ") + " FCFA"


def charger():
    """Étapes 1 à 4 : collecte, nettoyage, rapprochement, indexation + comparatif."""
    c.OUT_DIR.mkdir(exist_ok=True)
    t = perf_counter()
    journal = []
    catalogue = pd.read_csv(c.DATA_DIR / "catalogue_reference.csv", encoding="utf-8-sig")
    brut = pd.concat([
        c.charger_lagune(c.DATA_DIR / "marche_lagune.csv"),
        c.charger_baobab(c.DATA_DIR / "baobab_shop.json"),
        c.charger_comptoir(c.DATA_DIR / "comptoir_ivoire.xlsx"),
    ], ignore_index=True)
    propre = c.nettoyer(brut, journal)
    rapproche = c.rapprocher(propre, catalogue, journal)
    index = c.indexer(rapproche, journal)
    comp = c.comparer(index, catalogue, journal)
    comp.to_csv(c.OUT_DIR / "comparatif.csv", index=False, sep=";", encoding="utf-8-sig")
    (c.OUT_DIR / "journal.txt").write_text("\n".join(journal), encoding="utf-8")
    ETAT.update(journal=journal, catalogue=catalogue, index=index, comp=comp)
    print(f"{len(brut)} lignes lues, {len(rapproche)} conservées, {len(comp)} produits comparables "
          f"({(perf_counter() - t) * 1000:.0f} ms)")
    print(f"Journal : {len(journal)} entrées. Comparatif exporté dans sorties/comparatif.csv")


def assurer_charge():
    if not ETAT:
        print("Chargement des données...")
        charger()


def afficher_comparatif():
    assurer_charge()
    comp = ETAT["comp"]
    cols = [x for x in comp.columns if x.startswith("prix_") and x not in ("prix_min", "prix_moyen")]
    vue = comp[["produit_id", "nom"] + cols + ["moins_chere", "ecart_fcfa", "ecart_pct"]]
    with pd.option_context("display.width", 250, "display.max_columns", 20, "display.max_colwidth", 38):
        print(vue.to_string(index=False))


def rechercher():
    assurer_charge()
    terme = input("Produit à chercher (ex. samsung, clim, iphone) : ").strip()
    if not terme:
        return
    mots = set(c.normaliser(terme).split())
    trouves = [r for r in ETAT["catalogue"].itertuples() if mots <= set(c.normaliser(r.nom + " " + r.marque).split())]
    if not trouves:
        print("Aucun produit trouvé.")
        return
    for r in trouves:
        offres = ETAT["index"].get(r.produit_id, {})   # accès O(1) par dictionnaire
        print(f"\n{r.produit_id} : {r.nom}")
        if not offres:
            print("   aucune offre exploitable (rupture ou prix manquant partout)")
            continue
        pmin = min(offres.values())
        for e, p in sorted(offres.items(), key=lambda x: x[1]):
            print(f"   {e:<16} {fcfa(p):>14}   {'<- le moins cher' if p == pmin else f'+{(p - pmin) / pmin * 100:.1f} %'}")
        if len(offres) < 2:
            print("   (une seule enseigne : comparaison impossible)")


def menu_synthese():
    assurer_charge()
    c.synthese(ETAT["comp"], ETAT["index"])


def menu_panier():
    assurer_charge()
    c.panier(ETAT["index"], ETAT["catalogue"])


def menu_historique():
    if "hist" not in ETAT:
        ETAT["hist"] = pd.read_csv(c.DATA_DIR / "historique_prix.csv", parse_dates=["date"])
    c.OUT_DIR.mkdir(exist_ok=True)
    c.analyser_historique(ETAT["hist"])


def menu_complexite():
    if "hist" not in ETAT:
        ETAT["hist"] = pd.read_csv(c.DATA_DIR / "historique_prix.csv", parse_dates=["date"])
    c.benchmark(ETAT["hist"])


def afficher_journal():
    assurer_charge()
    for ligne in ETAT["journal"]:
        print(" -", ligne)


def tout_executer():
    charger()
    for f in (menu_synthese, menu_panier, menu_historique, menu_complexite):
        f()
    print("\nFichiers exportés dans le dossier sorties/")


MENU = [
    ("1", "Charger, nettoyer et rapprocher les 3 sources", charger),
    ("2", "Voir le comparatif des prix", afficher_comparatif),
    ("3", "Rechercher un produit", rechercher),
    ("4", "Synthèse (meilleure enseigne, écarts, top 3)", menu_synthese),
    ("5", "Panier de rentrée", menu_panier),
    ("6", "Historique : Black Friday et meilleur mois", menu_historique),
    ("7", "Complexité : mesure des temps", menu_complexite),
    ("8", "Journal de nettoyage", afficher_journal),
    ("9", "Tout exécuter et exporter", tout_executer),
    ("0", "Quitter", None),
]


def main():
    actions = {k: f for k, _, f in MENU}
    while True:
        print("\n" + "=" * 54)
        print("  ANALYSE COMPARATIVE DE MARCHÉ — Abidjan")
        print("=" * 54)
        for k, titre, _ in MENU:
            print(f"  {k}. {titre}")
        try:
            choix = input("\nVotre choix : ").strip()
        except EOFError:
            break
        if choix == "0":
            print("Au revoir.")
            break
        if choix not in actions:
            print("Choix invalide, tapez un chiffre du menu.")
            continue
        try:
            print()
            actions[choix]()
        except FileNotFoundError as e:
            print(f"Fichier introuvable : {e.filename}. Vérifiez le dossier data/.")
        except KeyError as e:
            print(f"Colonne attendue absente : {e}. Le format du fichier a changé ?")
        if sys.stdin.isatty():
            pause()


if __name__ == "__main__":
    main()