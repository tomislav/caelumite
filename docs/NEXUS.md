# Nexus Mods

Nexus's [API Acceptable Use Policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy)
requires every app to identify itself honestly. It also allows personal API
keys only for testing and personal use, not in a public-facing app. Upstream
ships Amethyst's registered OAuth client. Caelumite must not use that client,
so on macOS:

- API and image requests send `Application-Name: Caelumite` and Caelumite's
  version.
- OAuth login uses Caelumite's own client. Its ID and secret are
  `NEXUS_CLIENT_ID` and `NEXUS_CLIENT_SECRET` in `src/Utils/macos/app.py`.
  Both are empty until Nexus registers Caelumite, and while they are empty
  OAuth is off. Saved upstream OAuth logins are ignored.
- The personal API key is stored under Caelumite's own keyring entry.

## Testing with a personal API key

Turn the testing switch on in
`~/Library/Application Support/Caelumite/amethyst.ini`:

```ini
[dev]
nexus_personal_key = true
```

You can use the environment variable `CAELUMITE_NEXUS_PERSONAL_KEY=1`
instead. Then, in Settings → Connections, **Log in with API key…** opens your
Nexus API Keys page and asks for the key.

Without the switch, Nexus stays logged out. The login button explains why.
Installing from downloaded archives, deploying, LOOT and the wizards all work
without Nexus.

## Registering Caelumite

1. Email support@nexusmods.com and ask to register Caelumite as an
   application. Include the app name, the repository URL and what it uses the
   API for: downloads, update checks and mod metadata.
2. Nexus issues an application slug and OAuth credentials. Put them in
   `NEXUS_CLIENT_ID` and `NEXUS_CLIENT_SECRET`. If the slug isn't
   `Caelumite`, set `APPLICATION_NAME` in `src/Utils/macos/nexus.py` to it.
3. OAuth login then turns back on. The personal-key path stays available for
   testing setups.
