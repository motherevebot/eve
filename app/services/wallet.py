"""Custodial wallet creation, key management, and transaction signing."""

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import MessageV0

from app.services.encryption import encrypt, decrypt


def create_custodial_wallet() -> tuple[str, str]:
    """
    Generate a new Solana ed25519 keypair.
    Returns (base58_public_key, encrypted_private_key_bytes_hex).
    """
    kp = Keypair()
    pubkey = str(kp.pubkey())
    secret_hex = bytes(kp).hex()
    encrypted = encrypt(secret_hex)
    return pubkey, encrypted


def get_keypair(encrypted_private_key: str) -> Keypair:
    """Decrypt stored key and reconstruct Keypair."""
    secret_hex = decrypt(encrypted_private_key)
    return Keypair.from_bytes(bytes.fromhex(secret_hex))


def sign_transaction(raw_tx_bytes: bytes, encrypted_private_key: str) -> bytes:
    """
    Deserialize a transaction (base64-decoded bytes from Jupiter/PumpPortal),
    sign it with the custodial keypair, and return signed serialized bytes.
    """
    kp = get_keypair(encrypted_private_key)
    tx = VersionedTransaction.from_bytes(raw_tx_bytes)
    signed = VersionedTransaction(tx.message, [kp])
    return bytes(signed)


def sign_versioned_transaction_multi(
    raw_tx_bytes: bytes,
    encrypted_private_key: str,
    extra_keypairs: list[Keypair] | None = None,
) -> bytes:
    """
    Sign a VersionedTransaction with the custodial keypair AND any extra keypairs
    (e.g. a mint keypair for token creation).
    """
    kp = get_keypair(encrypted_private_key)
    tx = VersionedTransaction.from_bytes(raw_tx_bytes)

    signers = [kp]
    if extra_keypairs:
        signers.extend(extra_keypairs)

    signed = VersionedTransaction(tx.message, signers)
    return bytes(signed)
