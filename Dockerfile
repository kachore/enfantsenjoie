# Utilisation de l'image Python officielle
FROM python:3.11-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# Copier le fichier requirements.txt et installer les dépendances
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copier tout le code de l’application
COPY . .

# Commande de démarrage avec Gunicorn
CMD ["gunicorn", "eej_site.wsgi:application", "--bind", "0.0.0.0:8000"]
