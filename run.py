"""
Point d’entrée de développement : instancie l’application Flask via `create_app`
et lance le serveur en mode debug.
"""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
