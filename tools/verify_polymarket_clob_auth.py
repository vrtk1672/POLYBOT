import os
import getpass
from pathlib import Path
from dotenv import load_dotenv

try:
    from py_clob_client_v2 import ClobClient, ApiCreds
except ImportError as e:
    raise SystemExit("Missing package. Run: pip install py-clob-client-v2 python-dotenv") from e

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / "secrets" / ".env.polymarket.clob.generated"

if not ENV_PATH.exists():
    raise SystemExit(f"Missing file: {ENV_PATH}")

load_dotenv(ENV_PATH, override=True)

host = os.getenv("POLYMARKET_CLOB_HOST")
chain_id = int(os.getenv("POLYMARKET_CHAIN_ID", "137"))
signature_type = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0"))
funder = os.getenv("POLYMARKET_FUNDER_ADDRESS")

api_key = os.getenv("POLYMARKET_CLOB_API_KEY")
secret = os.getenv("POLYMARKET_CLOB_SECRET")
passphrase = os.getenv("POLYMARKET_CLOB_PASSPHRASE")

missing = []
for name, value in {
    "POLYMARKET_CLOB_HOST": host,
    "POLYMARKET_CLOB_API_KEY": api_key,
    "POLYMARKET_CLOB_SECRET": secret,
    "POLYMARKET_CLOB_PASSPHRASE": passphrase,
}.items():
    if not value:
        missing.append(name)

if missing:
    raise SystemExit("Missing: " + ", ".join(missing))

print("Loaded generated CLOB credentials.")
print(f"Host: {host}")
print(f"Chain ID: {chain_id}")
print(f"Signature type: {signature_type}")
print(f"Funder: {funder}")
print("CLOB API credentials: PRESENT, hidden")
print("")

private_key = getpass.getpass("Private key for verification only, hidden and NOT saved: ").strip()
if not private_key:
    raise SystemExit("Private key missing.")

creds = ApiCreds(
    api_key=api_key,
    api_secret=secret,
    api_passphrase=passphrase,
)

client = ClobClient(
    host=host,
    key=private_key,
    chain_id=chain_id,
    creds=creds,
    signature_type=signature_type,
    funder=funder,
)

print("SDK client initialized.")

try:
    keys = client.get_api_keys()
    print("AUTH TEST OK: get_api_keys worked.")
    print("Raw keys were NOT printed.")
except Exception as e:
    print("AUTH TEST FAILED.")
    print(str(e))
    raise SystemExit(1)

print("")
print("SUCCESS: Polymarket CLOB credentials are valid.")
print("No orders were created. No trading action was sent.")
