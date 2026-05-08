> 🇬🇧 English · [🇫🇷 Français](Discord-ToS-fr)

# Discord ToS Notice

Read this **before** running the project on any account you care about.

## What this project does

It logs in to Discord using **your** user token, sends `sd` on a timer in
a channel, reads SOFI's reply, and clicks one of the response buttons. It
runs entirely from your machine.

## Why that's a problem

Discord's [Terms of Service](https://discord.com/terms) explicitly forbid:

- Automating any user account ("selfbot")
- Logging in via API as anything other than the official client

Running this project violates both. Discord enforces irregularly:
sometimes accounts run for years undetected, sometimes new accounts get
banned in days. It is not predictable.

## What can happen

- **Warning** — rare, but possible.
- **Temporary suspension** — hours to days.
- **Permanent ban** — the account is gone, including its servers, friends,
  Nitro, and purchased content.

There is no appeal process worth banking on. Discord support's standard
reply is "Terms violated, ban upheld."

## How to reduce — not eliminate — risk

The defaults in this project already do most of these:

- **Jittered intervals** — `interval_min`/`interval_max` make the cadence
  random. Don't shorten the range.
- **Random extra cooldown** — adds 30s–2.5min after SOFI's announced
  cooldown. Don't zero this.
- **Night pause** — random sleep window between 22:00 and 01:00.
- **Random click delay** — 0–5.5s before clicking the heart button.

What this project does **not** do — and you shouldn't add — is anything
that disguises itself: proxies, fingerprint spoofing, fake user-agents,
bypass of rate limits. Detection-evasion features will not be merged.

## Safer ways to interact with SOFI

- A **real bot** application (Application → Bot, with its own token) is
  ToS-compliant. SOFI's API may not allow third-party bots, but **your own**
  account script does not need to be one — it just needs to be operated by a
  human in real time.
- If you're a server owner who wants a SOFI assistant, ask SOFI's developers
  about supported integrations.

## tl;dr

This project is provided as-is for **education**. By using it on a Discord
account you accept that **the account may be permanently banned**. The
authors and contributors are not liable for that outcome.
