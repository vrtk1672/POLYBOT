import os
import json
import getpass
from pathlib import Path

try:
    from py_clob_client_v2 import ClobClient
except ImportError as e:
    raise SystemExit(
        "Missing package. Run: pip install py-clob-client-v2 python-dotenv"
    ) from e


ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = ROOT / "secrets"
OUT_PATH = SECRETS_DIR / ".env.polymarket.clob.generated"

SECRETS_DIR.mkdir(exist_ok=True)


def ask(prompt: str, default: str | None = None, secret: bool = False) -> str:
    label = prompt
    if default:
        label += f" [{default}]"
    label += ": "

    value = getpass.getpass(label) if secret else input(label)
    value = value.strip()

    if not value and default is not None:
        return default

    return value


def safe_shape(obj):
    print("")
    print("DEBUG SHAPE, no secrets printed:")
    print("type:", type(obj))

    if isinstance(obj, dict):
        print("dict keys:", list(obj.keys()))
        for k, v in obj.items():
            if isinstance(v, str):
                print(f"{k}: string length {len(v)}")
            else:
                print(f"{k}: {type(v)}")
        return

    attrs = [a for a in dir(obj) if not a.startswith("_")]
    print("attrs:", attrs)

    for a in attrs:
        try:
            v = getattr(obj, a)
        except Exception:
            continue

        if callable(v):
            continue

        if isinstance(v, str):
            print(f"{a}: string length {len(v)}")
        else:
            print(f"{a}: {type(v)}")


def obj_to_dict(obj):
    if isinstance(obj, dict):
        return obj

    if hasattr(obj, "model_dump"):
        return obj.model_dump()

    if hasattr(obj, "dict"):
        return obj.dict()

    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)

    return {}


def pick(data: dict, names: list[str]):
    lowered = {str(k).lower(): v for k, v in data.items()}

    for name in names:
        if name in data and data[name]:
            return data[name]

    for name in names:
        key = name.lower()
        if key in lowered and lowered[key]:
            return lowered[key]

    return None


print("")
print("POLYMARKET CLOB CREDENTIAL CREATOR")
print("----------------------------------")
print("Private key is hidden while typing/pasting.")
print("")

host = ask("CLOB host", "https://clob.polymarket.com")
chain_id = int(ask("Chain ID", "137"))

print("")
print("Choose wallet type:")
print("0 = External wallet / EOA, usually MetaMask or Rabby")
print("3 = Polymarket deposit/proxy wallet, often for newer API users")
print("")
signature_type = int(ask("Signature type", "0"))

wallet_address = ask("Wallet / funder address, starts with 0x")
private_key = ask("Private key, starts with 0x", secret=True)

if not wallet_address.startswith("0x") or len(wallet_address) != 42:
    raise SystemExit("Invalid wallet address. It should look like 0x... and be 42 chars.")

if len(private_key) not in (64, 66):
    raise SystemExit("Invalid private key length. Check that you copied the private key correctly.")

print("")
print("Creating / deriving CLOB API credentials...")
print(f"Host: {host}")
print(f"Chain ID: {chain_id}")
print(f"Wallet/Funder: {wallet_address}")
print(f"Signature type: {signature_type}")
print("")

client = ClobClient(
    host=host,
    key=private_key,
    chain_id=chain_id,
    signature_type=signature_type,
    funder=wallet_address,
)

creds = client.create_or_derive_api_key()
data = obj_to_dict(creds)

safe_shape(creds)

api_key = pick(data, ["api_key", "apiKey", "key", "clob_api_key"])
secret = pick(data, ["api_secret", "apiSecret", "secret", "clob_secret"])
passphrase = pick(data, ["api_passphrase", "apiPassphrase", "passphrase", "clob_passphrase"])

if not api_key or not secret or not passphrase:
    print("")
    print("Could not parse credentials.")
    print("This means the SDK returned a different object shape.")
    print("Send me ONLY the DEBUG SHAPE above, not the raw values.")
    raise SystemExit(1)

content = f"""# Generated locally. Do not commit. Do not share.
POLYMARKET_CLOB_HOST={host}
POLYMARKET_CHAIN_ID={chain_id}
POLYMARKET_SIGNATURE_TYPE={signature_type}
POLYMARKET_FUNDER_ADDRESS={wallet_address}
POLYMARKET_CLOB_API_KEY={api_key}
POLYMARKET_CLOB_SECRET={secret}
POLYMARKET_CLOB_PASSPHRASE={passphrase}
"""

OUT_PATH.write_text(content, encoding="utf-8")

print("")
print("SUCCESS")
print(f"Saved to: {OUT_PATH}")
print("")
print("Fields saved:")
print("POLYMARKET_CLOB_API_KEY=***")
print("POLYMARKET_CLOB_SECRET=***")
print("POLYMARKET_CLOB_PASSPHRASE=***")
