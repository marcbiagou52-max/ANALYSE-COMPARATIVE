"""Point d'entrée unique : lance les programmes du projet d'analyse comparative.

"""
import os
import subprocess
import sys


DOSSIER = os.path.dirname(os.path.abspath(__file__))

# Pour ajouter un programme : une ligne (libellé, nom du fichier).
PROGRAMMES = [
    ("Analyse comparative (comparateur)", "comparateur.py"),
    ("Application console (menu interactif)", "app_console.py"),
]


def lancer(fichier):
    """Exécute un script avec le même Python que main.py (celui du venv)."""
    chemin = os.path.join(DOSSIER, fichier)
    if not os.path.exists(chemin):
        print(f"  [!] Fichier introuvable : {fichier}")
        return False
    print(f"\n=== Lancement de {fichier} ===\n")
    resultat = subprocess.run([sys.executable, chemin], cwd=DOSSIER)
    if resultat.returncode != 0:
        print(f"\n  [!] {fichier} s'est terminé avec une erreur (code {resultat.returncode}).")
        return False
    print(f"\n=== {fichier} terminé ===")
    return True


def afficher_menu():
    print("\n" + "=" * 46)
    print("  ANALYSE COMPARATIVE DE MARCHÉ")
    print("=" * 46)
    for i, (libelle, fichier) in enumerate(PROGRAMMES, start=1):
        etat = "" if os.path.exists(os.path.join(DOSSIER, fichier)) else "  (fichier absent)"
        print(f"  {i}. {libelle}{etat}")
    print(f"  {len(PROGRAMMES) + 1}. Tout lancer dans l'ordre")
    print("  0. Quitter")


def main():
    while True:
        afficher_menu()
        try:
            choix = input("\nVotre choix : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaisie interrompue. Au revoir.")
            return

        if choix == "0":
            print("Au revoir.")
            return
        if not choix.isdigit():
            print("  Entrez un numéro du menu.")
            continue

        n = int(choix)
        if 1 <= n <= len(PROGRAMMES):
            lancer(PROGRAMMES[n - 1][1])
        elif n == len(PROGRAMMES) + 1:
            for _, fichier in PROGRAMMES:
                if not lancer(fichier):
                    print("  Arrêt de la séquence.")
                    break
        else:
            print("  Choix hors menu.")


if __name__ == "__main__":
    main()
