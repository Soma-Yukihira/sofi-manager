# Mise à jour

Selfbot Manager **suit `main` en continu**. Pas d'artefact de release :
chaque commit sur `main` est ce que les utilisateurs exécutent, à
l'instant où il arrive. L'updater intégré fonctionne comme Discord —
vérif silencieuse en arrière-plan, bandeau doré quand c'est prêt,
appliqué au redémarrage.

## Auto-update intégré (clones git)

Au démarrage de la GUI, un thread daemon lance `git fetch origin
main`. Si le clone local est en retard, un bandeau doré apparaît en
haut de la fenêtre :

> Mise à jour disponible — N commit(s) en attente. Redémarrez pour appliquer.

Clic sur **Redémarrer** et l'app :

1. Sauvegarde le formulaire / les settings (même chemin qu'à la
   fermeture normale).
2. Arrête tous les bots en cours.
3. Lance `git pull --ff-only origin main`.
4. Relance l'interpréteur Python avec le même `argv`.

`bots.json` et `settings.json` sont gitignorés, donc jamais touchés par
le pull.

## Garde-fous (chemin git-pull)

Le chemin git-pull **refuse de toucher l'arbre** quand :

- La branche courante n'est pas `main`.
- Tu as des commits locaux en avance sur `origin/main`.
- Des fichiers suivis ont des modifications non commitées.

Dans ces cas, aucun bandeau n'apparaît — ce sont des états dev, le
check à la demande dans le menu les remonte quand il le faut. Les cas
`.git/`-absent et `.exe` gelé suivent leurs propres chemins,
ci-dessous.

## Alternative CLI

La même opération, verbeuse, depuis un terminal :

```bash
python tools/update.py
```

Rafraîchit les dépendances pip si `requirements.txt` a changé et
imprime un résumé propre. Pratique sur un VPS, dans `tmux`, ou comme
fallback quand la GUI ne peut pas accéder au réseau.

## Installs ZIP (pas de `.git/`)

L'updater bascule sur un chemin codeload. Il récupère le SHA `main`
courant depuis `api.github.com`, télécharge le ZIP correspondant
depuis `codeload.github.com`, et écrase les fichiers suivis en place
(garde zip-slip, baseline SHA persistée en `zip_install_sha` dans
`settings.json`). Le bandeau doré et le flux de redémarrage sont
identiques au chemin git. Les fichiers gitignorés (`bots.json`,
`settings.json`, `grabs.db`) survivent intacts.

## `.exe` gelé

Les bundles PyInstaller ne peuvent pas swap atomiquement leurs propres
fichiers sources à l'exécution, donc l'updater court-circuite avec le
skip reason `frozen` et la GUI affiche un bandeau ambre passif.
Action : recompile depuis un clone frais via `python tools/build.py`,
ou bascule sur une install source.
