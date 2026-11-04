FROM python:3.11-slim
WORKDIR /app
# LightGBM (modèle de prévision) a besoin de la bibliothèque OpenMP, absente de l'image « slim »
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# Délais et reprises élevés : les connexions lentes coupent sinon le téléchargement des paquets
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt
COPY app ./app
# Code du pipeline : le service réutilise le calcul des caractéristiques du modèle
COPY pipeline/*.py ./pipeline/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
