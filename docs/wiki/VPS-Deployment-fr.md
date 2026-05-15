> [🇬🇧 English](VPS-Deployment) · 🇫🇷 Français

# Déploiement VPS

Faire tourner Selfbot Manager **en headless** sur un serveur Linux —
aucun GUI requis.

## Pourquoi un CLI ?

Le repo embarque deux points d'entrée qui partagent le même cœur
(`sofi_manager.bot_core`) :

| Point d'entrée | Quand l'utiliser                                       |
| -------------- | ------------------------------------------------------ |
| `main.py`      | Desktop local — GUI complet, thèmes, multi-panneaux    |
| `cli.py`       | VPS, container, serveur headless — logs terminal uniq. |

Les deux lisent le même `bots.json` — tu peux configurer tes bots dans le
GUI sur ton laptop, push le fichier sur le VPS, le CLI le prend.

## Cheatsheet CLI

```bash
python cli.py list                       # liste les bots configurés
python cli.py show "Nom bot"             # config complète (token masqué)
python cli.py add                        # wizard interactif
python cli.py rm "Nom bot"               # supprime un bot
python cli.py run                        # lance tous les bots au premier plan
python cli.py run "Bot A" "Bot B"        # lance ceux-là seulement
python cli.py --no-color run             # supprime ANSI pour fichiers de logs
```

`Ctrl+C` arrête proprement : chaque bot draine ses logs restants et se
déconnecte avant la sortie.

## Déploiement rapide sur VPS frais

Testé Debian 12 / Ubuntu 22.04. À adapter selon ta distro.

```bash
# 1. dépendances système
sudo apt update
sudo apt install -y python3 python3-venv git

# 2. clone & venv
git clone https://github.com/Soma-Yukihira/sofi-manager.git
cd sofi-manager
python3 -m venv env
./env/bin/pip install --upgrade pip
./env/bin/pip install -r requirements.txt

# 3. configurer
./env/bin/python cli.py add        # interactif — répéter pour chaque bot
./env/bin/python cli.py list       # vérifier

# 4. test run
./env/bin/python cli.py run        # Ctrl+C quand satisfait
```

## Modes de lancement

### Foreground (test)

```bash
./env/bin/python cli.py run
```

Les logs sortent direct dans le terminal. Fermer la session SSH tue les
bots.

### Persistant via `tmux` (interactif)

```bash
tmux new -s selfbot
./env/bin/python cli.py run
# Détacher : Ctrl+B puis D
# Rattacher : tmux attach -t selfbot
```

Survit aux disconnects SSH mais meurt au reboot.

### Persistant via `systemd` (production · recommandé)

Un installateur clé en main est fourni :

```bash
sudo ./tools/install-systemd.sh
sudo systemctl start sofi-manager
journalctl -u sofi-manager -f         # logs en direct
```

Le script génère `/etc/systemd/system/sofi-manager.service` configuré avec
ton user, ton chemin d'install et ton venv. Le service :

- démarre au boot (activé par l'installateur)
- redémarre en cas de crash (backoff 10 s)
- drop les privilèges et isole `/home`, `/etc`, `/var` (`ProtectSystem`,
  `PrivateTmp`, `NoNewPrivileges`)
- redirige stdout/stderr vers le journal — pas de fichiers de logs à
  rotater

Commandes utiles :

```bash
sudo systemctl status sofi-manager
sudo systemctl restart sofi-manager
sudo systemctl stop sofi-manager
sudo systemctl disable --now sofi-manager      # désinstall complète
```

## Configurer les bots sur le VPS

Trois manières, choisis :

1. **Interactive sur le VPS** — `python cli.py add`, déroule le wizard.
   Te demande nom, token, drop channel, salons écoutés. Les défauts sont
   sensés pour tout le reste.

2. **Éditer `bots.json` directement** — même schéma que la version GUI.
   Voir [Configuration](Configuration-fr) pour chaque champ.

3. **Configurer sur ton desktop puis pousser** — ouvre le GUI sur ton
   laptop, configure les bots à fond (wishlist · les prefs de thème
   n'ont aucun effet côté VPS), puis :

   ```bash
   scp bots.json user@vps:/home/user/sofi-manager/bots.json
   sudo systemctl restart sofi-manager
   ```

## Mettre à jour

```bash
./env/bin/python tools/update.py
sudo systemctl restart sofi-manager   # si tu tournes en service
```

Le CLI fait `git pull`, rafraîchit les deps `pip` si
`requirements.txt` a changé, et imprime un résumé propre. Voir
[Mise à jour](Updating-fr) pour le modèle complet (updater intégré
GUI + fallback codeload pour les installs ZIP).

## Consommation ressources

Par bot : ~30–40 Mo RAM, quasi-zéro CPU (le bot dort entre les drops).
Un VPS 512 Mo / 1 vCPU tient 5+ bots tranquille.

Bande passante négligeable — WebSocket Discord + quelques REST par drop.

## Pistes hardening

- **Fail2ban** anti brute-force SSH : `sudo apt install fail2ban` (défauts
  OK).
- **User non-root** pour le service : l'installateur utilise déjà ton
  user sudo, jamais root. Ne change pas ça.
- **Stockage du token** : `bots.json` est `0644` par défaut. Resserre
  avec `chmod 600 bots.json` si tu te méfies des autres comptes sur la
  machine.
- **2FA Discord backup** : si Discord flag l'IP, tu devras peut-être
  confirmer la 2FA depuis un navigateur avant que le bot puisse se
  reconnecter.

## Dépannage

Voir la page dédiée [Dépannage](Troubleshooting-fr). Le CLI imprime les
mêmes lignes diagnostiques `📥 SOFI:` que le GUI — c'est le meilleur
indice quand un drop est raté.
