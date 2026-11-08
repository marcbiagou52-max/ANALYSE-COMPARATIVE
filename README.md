# Analyse comparative de marché

Projet Python qui compare les prix de produits électroniques et électroménagers proposés par trois enseignes fictives à Abidjan : Marché Lagune, Baobab Shop et Comptoir Ivoire.

Les données sont fictives et servent uniquement à l'exercice. Pour plus de détails sur les sources, les formats et les objectifs, consultez [data/LISEZ-MOI.md](data/LISEZ-MOI.md).

## Prérequis

- Python 3
- Les dépendances listées dans `requirements.txt` : `pandas` et `openpyxl`

Installation des dépendances :

```powershell
python -m pip install -r requirements.txt
```

## Lancer le projet

Depuis le dossier du projet :

```powershell
python main.py
```

Le menu propose de lancer le comparateur, l'application console ou les deux. Vous pouvez aussi exécuter directement :

```powershell
python comparateur.py
python app_console.py
```

Le comparateur charge les données, nettoie les articles, les rapproche du catalogue de référence, compare les prix et affiche une synthèse. L'application console permet également de rechercher un produit, de calculer le panier de rentrée et d'analyser l'historique des prix.

Par défaut, les données sont lues dans `data/`. Pour utiliser un autre dossier de données avec le comparateur :

```powershell
python comparateur.py chemin\vers\les\donnees
```

## Données et résultats

- `data/catalogue_reference.csv` : catalogue commun des produits.
- `data/marche_lagune.csv`, `data/baobab_shop.json` et `data/comptoir_ivoire.xlsx` : offres des trois enseignes.
- `data/historique_prix.csv` : historique des prix.
- `sorties/` : résultats générés à l'exécution, notamment le comparatif, le journal de nettoyage, le panier et l'analyse Black Friday.

Les fichiers générés dans `sorties/` ne sont pas suivis par Git.
