"""SPL Token operations — burn tokens after buyback."""

import logging

from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from solders.message import Message
from solders.hash import Hash
import struct

logger = logging.getLogger(__name__)

TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
ASSOCIATED_TOKEN_PROGRAM_ID = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")


def derive_ata(owner: Pubkey, mint: Pubkey, token_program: Pubkey = TOKEN_PROGRAM_ID) -> Pubkey:
    """Derive the Associated Token Account address."""
    seeds = [bytes(owner), bytes(token_program), bytes(mint)]
    ata, _bump = Pubkey.find_program_address(seeds, ASSOCIATED_TOKEN_PROGRAM_ID)
    return ata


def build_burn_instruction(
    owner: Pubkey,
    mint: Pubkey,
    amount: int,
    token_program: Pubkey = TOKEN_PROGRAM_ID,
) -> Instruction:
    """
    Build an SPL Token Burn instruction.
    Layout: instruction index 8 (Burn), then u64 amount (little-endian).
    """
    ata = derive_ata(owner, mint, token_program)

    # Burn instruction data: [8] + amount as u64 LE
    data = struct.pack("<Bq", 8, amount)

    accounts = [
        AccountMeta(pubkey=ata, is_signer=False, is_writable=True),
        AccountMeta(pubkey=mint, is_signer=False, is_writable=True),
        AccountMeta(pubkey=owner, is_signer=True, is_writable=False),
    ]

    return Instruction(token_program, data, accounts)


async def build_burn_tx(
    owner_pubkey: str,
    mint: str,
    amount_raw: int,
    token_program: str = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    recent_blockhash: str | None = None,
) -> bytes | None:
    """
    Build a complete burn transaction ready for signing.
    Returns serialized transaction message bytes.
    """
    try:
        owner = Pubkey.from_string(owner_pubkey)
        mint_pk = Pubkey.from_string(mint)
        prog = Pubkey.from_string(token_program)

        ix = build_burn_instruction(owner, mint_pk, amount_raw, prog)

        if not recent_blockhash:
            from app.services.solana_rpc import get_latest_blockhash
            recent_blockhash = await get_latest_blockhash()

        blockhash = Hash.from_string(recent_blockhash)
        msg = Message.new_with_blockhash([ix], owner, blockhash)
        tx = Transaction.new_unsigned(msg)
        return bytes(tx)

    except Exception:
        logger.exception("build_burn_tx failed: owner=%s mint=%s amount=%d", owner_pubkey, mint, amount_raw)
        return None
