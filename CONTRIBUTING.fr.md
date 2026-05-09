# Contribuer

Merci de considérer une contribution. C'est un petit projet — garde tes PR
petites et ciblées.

> [English](CONTRIBUTING.md) · [Français]

---

## 🐛 Signaler un bug

Ouvre une [issue](../../issues/new) avec :

1. **Ce que tu as fait** — l'action effectuée dans le GUI.
2. **Ce qui s'est passé** — le comportement réel, en incluant les **lignes
   `📥 SOFI:`** au moment de l'erreur. Ces lignes sont l'info diagnostique la
   plus utile — colle-les telles quelles.
3. **Ce que tu attendais** — le comportement souhaité.
4. **Environnement** — OS, version Python (`python --version`), versions des
   paquets (`pip list | grep -E "discord|customtkinter"`).

Ne colle jamais ton token. Masque-le en `XXX.YYY.ZZZ` s'il apparaît quelque part.

---

## 💡 Proposer une feature

Ouvre une issue décrivant le cas d'usage avant de coder. Une proposition en
3 lignes ("aujourd'hui X est pénible, j'aimerais Y") fait gagner du temps à
tout le monde.

---

## 🛠 Setup dev

```bash
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
python -m venv env
.\env\Scripts\activate          # Windows
# source env/bin/activate       # macOS / Linux
pip install -r requirements.txt
python main.py
```

Lance d'abord les tests core légers :

```bash
python -m unittest
```

Puis teste manuellement les changements UI :

- Démarrer le GUI, ajouter un bot, sauvegarder, redémarrer — config persiste.
- Basculer dark/light, personnaliser une couleur, redémarrer — settings
  persistent.
- Éditer une wishlist avec doublons et casse mixte — la sauvegarde trie et
  dédoublonne.

---

## 🧱 Style de code

- Reste proche du style existant. Préfère la lisibilité à la malice.
- Pas de nouvelle dépendance sans discussion.
- Garde `bot_core.py` indépendant du GUI : il doit rester importable sans
  écran.
- Garde `gui.py` indépendant de Discord : pas de logique réseau dedans.

---

## 📜 Pull requests

1. Fork, branche depuis `main`.
2. Un sujet par PR — les petits diffs passent plus vite en review.
3. Description claire : ce qui change, pourquoi, comment tu l'as testé.
4. En soumettant une PR tu acceptes que ta contribution soit sous la licence
   [MIT](LICENSE) du projet.

---

## 🚫 Hors scope

- Tout ce qui vise à **contourner la détection Discord** (rotation de proxy,
  spoofing de fingerprint, contournement de rate limits). Le projet est
  transparent sur ce qu'il fait — l'[avertissement](README.fr.md#) se veut
  honnête, pas une checkbox à cocher.
- Features qui ciblent serveurs ou utilisateurs Discord sans consentement
  (DM en masse, scraping de membres, signalements automatisés, etc.).
