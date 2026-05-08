> [🇬🇧 English](Installation) · 🇫🇷 Français

# Installation

## Prérequis

- **Python 3.10 ou plus récent** — [télécharger](https://www.python.org/downloads/).
  Sur Windows, coche *"Add Python to PATH"* dans l'installeur.
- **pip** — fourni avec Python.
- Un compte Discord et son token.

Vérifie dans un terminal :

```bash
python --version
pip --version
```

## Étape par étape

### 1. Cloner

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
```

Ou télécharge le ZIP depuis la page GitHub et extrais-le.

### 2. Créer un environnement virtuel

Fortement recommandé — isole les dépendances du reste du système.

```bash
python -m venv env
```

Active-le :

| OS              | Commande                 |
| --------------- | ------------------------ |
| Windows (CMD)   | `env\Scripts\activate`   |
| Windows (PS)    | `.\env\Scripts\activate` |
| macOS / Linux   | `source env/bin/activate` |

Tu dois voir `(env)` apparaître devant ton prompt.

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

Ça installe :

- `discord.py-self` — client Discord (fork selfbot de `discord.py`)
- `customtkinter` — widgets Tk modernes thémés

### 4. Lancer

```bash
python main.py
```

La fenêtre s'ouvre. Le premier run ne crée aucun fichier — `bots.json` et
`settings.json` apparaissent quand tu ajoutes un bot ou changes un réglage.

## Récupérer un token

1. Ouvre Discord dans un navigateur. Connecte-toi.
2. Ouvre les DevTools → onglet **Network**.
3. Envoie un message quelconque. Cherche une requête vers `messages`.
4. Dans **Request Headers**, copie la valeur de `Authorization`. C'est ton token.

> [!CAUTION]
> Traite ton token comme un mot de passe. N'importe qui qui l'a a un accès
> complet à ton compte.

## Suite

- [Configuration](Configuration-fr) — champs du GUI expliqués.
- [Avis ToS Discord](Discord-ToS-fr) — à lire avant de lancer.
