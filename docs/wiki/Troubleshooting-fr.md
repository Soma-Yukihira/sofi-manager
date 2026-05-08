> [🇬🇧 English](Troubleshooting) · 🇫🇷 Français

# Dépannage

L'outil le plus utile quand ça casse : les lignes **`📥 SOFI:`** dans les
logs. Elles montrent ce que SOFI a réellement envoyé dans le salon que le
bot écoute. La plupart des "le bot ne réagit pas" sont visibles là.

---

## Installation

### `python: command not found` / `'python' is not recognized`

Python n'est pas dans le PATH. Réinstalle en cochant *"Add Python to PATH"*,
ou appelle-le explicitement : `C:\Chemin\Vers\Python\python.exe`.

### `ModuleNotFoundError: No module named 'discord'`

Le venv n'est pas activé, ou `pip install -r requirements.txt` n'a pas été
lancé dedans. Réactive (`.\env\Scripts\activate`) et réinstalle.

### `ModuleNotFoundError: No module named 'customtkinter'`

Même cause. `pip install -r requirements.txt` dans le venv actif.

---

## Authentification

### `Token invalide`

Le token est vide, expiré, ou collé avec des espaces parasites. Re-récupère-le
(voir [Installation › Récupérer un token](Installation-fr#récupérer-un-token))
et recolle.

### Compte verrouillé / demande 2FA

Discord peut flag un nouveau login depuis l'IP du selfbot. Connecte-toi une
fois depuis un navigateur sur la même machine, valide la 2FA, puis ré-essaie.

---

## Détection de drop

### "Drop envoyé" s'affiche mais rien après

Vérifie qu'une ligne `📥 SOFI:` suit. Si absente, SOFI n'a pas répondu (rare)
ou le message n'était pas dans un salon écouté. Vérifie le champ **Salons
écoutés** dans l'onglet Configuration.

Si `📥 SOFI:` est présente mais pas de `🎴 Drop détecté` ensuite : le
message n'a pas matché `_DROP_TRIGGER_RE`. Ouvre une issue avec la ligne
`📥 SOFI:` — il faudra peut-être étendre le regex pour un nouveau format
SOFI.

### `Drop ignoré (pas le tien)`

Un autre utilisateur a droppé dans le même salon. Comportement attendu.

### `Aucune carte parsée`

Le format de drop a changé. La ligne `📥 SOFI:` au-dessus montre ce qui est
arrivé — colle-la dans une issue.

### `Boutons toujours disabled`

Le bot a attendu 10× 0.5s pour que les boutons s'activent mais ça n'est
jamais arrivé. Rare, généralement un hoquet Discord. Le drop est perdu
pour ce cycle. Si c'est chronique, augmente le nombre de retries dans
[`bot_core.py`](../../blob/main/bot_core.py) (`for attempt in range(10)`).

---

## GUI

### Le toggle de thème tout casse en gris

Probablement un override custom qui clashe avec le nouveau preset. Ouvre la
modale 🎨 Couleurs et **Réinitialiser**.

### `bots.json` grossit ou contient des doublons

Un crash en plein save peut laisser le fichier sale. Arrête l'app, ouvre
`bots.json`, dédoublonne par champ `_id`, sauvegarde, redémarre.

### CPU élevé avec plusieurs bots

Chaque bot = un thread + une loop asyncio + un client Discord. 5+ bots sur
une seule machine reste OK ; au-delà, envisage un petit VPS avec un bot
par process.

---

## Autre

Ouvre une [issue](../../issues/new) avec :

- Le message exact depuis le GUI (barre de statut + lignes de log).
- Les lignes `📥 SOFI:` autour du fail.
- OS, version Python, versions des paquets.
