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

## Garde-fous

L'updater **refuse de toucher l'arbre** dans tous ces cas :

- `.git/` est absent (install par ZIP ou `.exe` distribué).
- La branche courante n'est pas `main`.
- Tu as des commits locaux en avance sur `origin/main`.
- Des fichiers suivis ont des modifications non commitées.

Dans tous ces cas, le bandeau n'apparaît simplement pas.

## Alternative CLI

La même opération, verbeuse, depuis un terminal :

```bash
python tools/update.py
```

Rafraîchit les dépendances pip si `requirements.txt` a changé et
imprime un résumé propre. Pratique sur un VPS, dans `tmux`, ou comme
fallback quand la GUI ne peut pas accéder au réseau.

## Utilisateurs ZIP / `.exe`

Ces installs n'ont pas de `.git/`, donc l'auto-updater est inerte. Pour
une nouvelle version, re-télécharge les sources (ou recompile
l'exécutable depuis un clone frais via `python tools/build.py`).
