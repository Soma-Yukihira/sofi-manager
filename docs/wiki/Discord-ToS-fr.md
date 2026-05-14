> [🇬🇧 English](Discord-ToS) · 🇫🇷 Français

# Avis ToS Discord

À lire **avant** de lancer le projet sur un compte auquel tu tiens.

## Ce que fait ce projet

Il se connecte à Discord avec **ton** token utilisateur, envoie `sd` à
intervalles régulières dans un salon, lit la réponse de SOFI et clique sur l'un des
boutons de réponse. Tout tourne depuis ta machine.

## Pourquoi c'est un problème

Les [Conditions d'utilisation](https://discord.com/terms) interdisent
explicitement :

- Automatiser un compte utilisateur ("selfbot")
- Se connecter via l'API autrement qu'avec le client officiel

Ce projet viole les deux. Discord applique de façon irrégulière : parfois
des comptes tournent pendant des années sans détection, parfois des comptes
neufs sont bannis en quelques jours. Pas prévisible.

## Ce qui peut arriver

- **Avertissement** — rare, mais possible.
- **Suspension temporaire** — heures à jours.
- **Ban définitif** — le compte disparaît, avec ses serveurs, amis, Nitro
  et achats.

Pas de procédure d'appel sur laquelle compter. La réponse standard du
support Discord est "ToS violés, ban maintenu".

## Comment réduire — pas éliminer — le risque

Les défauts du projet font déjà la plupart de ces choses :

- **Intervalles aléatoires** — `interval_min`/`interval_max` rendent la
  cadence randomisée. Ne raccourcis pas la fourchette.
- **Cooldown extra aléatoire** — ajoute 30s–2.5min après le cooldown
  annoncé par SOFI. Ne mets pas zéro.
- **Pause nocturne** — fenêtre de sommeil aléatoire entre 22h et 01h.
- **Délai de click aléatoire** — 0–5.5s avant de cliquer le bouton coeur.

Ce que le projet **ne fait pas** — et que tu ne dois pas ajouter — c'est
tout ce qui se déguise : proxies, spoofing de fingerprint, fake user-agents,
contournement de rate limits. Les features d'évasion de détection ne seront
pas mergées.

## Façons plus sûres d'interagir avec SOFI

- Un **vrai bot** application (Application → Bot, avec son propre token)
  respecte les ToS. L'API SOFI ne permet peut-être pas les bots tiers, mais
  **ton propre** script de compte n'a pas besoin d'en être un — il suffit
  qu'il soit piloté par un humain en temps réel.
- Si tu es propriétaire d'un serveur et veux un assistant SOFI, demande
  aux devs SOFI les intégrations supportées.

## tl;dr

Ce projet est fourni tel quel à des fins **éducatives**. En l'utilisant sur
un compte Discord, tu acceptes que **le compte puisse être banni
définitivement**. Auteurs et contributeurs ne sont pas responsables de
cette issue.
