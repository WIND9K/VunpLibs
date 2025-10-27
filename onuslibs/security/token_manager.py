import keyring

SERVICE = "onuslibs:{profile}"

def set_wallet_credentials(profile: str, base: str, token: str):
    keyring.set_password(SERVICE.format(profile=profile), "WALLET_BASE", base)
    keyring.set_password(SERVICE.format(profile=profile), "ACCESS_CLIENT_TOKEN", token)

def get_wallet_credentials(profile: str):
    base = keyring.get_password(SERVICE.format(profile=profile), "WALLET_BASE")
    token = keyring.get_password(SERVICE.format(profile=profile), "ACCESS_CLIENT_TOKEN")
    return base, token

def clear_wallet_credentials(profile: str):
    for key in ("WALLET_BASE","ACCESS_CLIENT_TOKEN"):
        try:
            keyring.delete_password(SERVICE.format(profile=profile), key)
        except Exception:
            pass
