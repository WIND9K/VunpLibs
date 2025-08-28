import argparse, getpass, keyring

SERVICE_FMT = "OnusLibs:{profile}"

def main():
    p = argparse.ArgumentParser(description="Set wallet credentials into OS Keyring")
    p.add_argument("--profile", default="default", help="Profile name per project")
    p.add_argument("--base", help="WALLET_BASE (if omitted, you will be prompted)")
    p.add_argument("--token", help="ACCESS_CLIENT_TOKEN (if omitted, you will be prompted securely)")
    args = p.parse_args()

    base  = args.base  or input("WALLET_BASE: ").strip()
    token = args.token or getpass.getpass("ACCESS_CLIENT_TOKEN: ")

    if not base or not token:
        raise SystemExit("Missing WALLET_BASE or ACCESS_CLIENT_TOKEN")

    svc = SERVICE_FMT.format(profile=args.profile)
    keyring.set_password(svc, "WALLET_BASE", base)
    keyring.set_password(svc, "ACCESS_CLIENT_TOKEN", token)
    print(f"Saved to keyring profile={args.profile}")

if __name__ == "__main__":
    main()
