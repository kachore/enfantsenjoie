# EEJ - Enfants En Joie (Django)

Ce dépôt contient un scaffold minimal pour le site web de l'ONG EEJ en Django.

Pré-requis:
- Python 3.10+
- pip
- DB Browser for SQLite (optionnel pour ouvrir db.sqlite3)

Installation locale (PowerShell):

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Notes:
1. Logo:
	 - Le fichier `logo.jpg` est à la racine du workspace.
	 - Copier (ou déplacer) ce fichier vers `eej_site/static/logo.jpg` (ou créer un lien) pour qu'il s'affiche dans la barre de navigation.
	 - Sous PowerShell:
		 ```powershell
		 Copy-Item ..\logo.jpg .\static\logo.jpg
		 ```
2. Base de données SQLite:
	 - Le fichier est `db.sqlite3` à la racine du projet Django (`eej_site/db.sqlite3`).
	 - Pour l'ouvrir dans DB Browser for SQLite:
		 - Lancer DB Browser for SQLite.
		 - Cliquer sur "Ouvrir une base de données".
		 - Sélectionner le fichier `db.sqlite3`.
		 - Explorer les tables (ex: website_newsitem, website_center, website_contactmessage, auth_user, etc.).
	 - Éviter d'éditer directement les contenus critiques pendant que le serveur Django tourne.
