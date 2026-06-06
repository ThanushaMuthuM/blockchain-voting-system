import hashlib
import json
import os
import base64
from time import time
from typing import List, Dict, Set
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

CHAIN_FILE = "blockchain.json"
ELIGIBLE_FILE = "eligible_voters.json"

class Block:
    def __init__(self, index: int, transactions: List[Dict], timestamp: float,
                 previous_hash: str, nonce: int = 0):
        self.index = index
        self.transactions = transactions
        self.timestamp = timestamp
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        block_string = json.dumps({
            "index": self.index,
            "transactions": self.transactions,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce
        }, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def mine_block(self, difficulty: int) -> None:
        target = "0" * difficulty
        while self.hash[:difficulty] != target:
            self.nonce += 1
            self.hash = self.compute_hash()

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "transactions": self.transactions,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash
        }

    @staticmethod
    def from_dict(data: Dict) -> 'Block':
        block = Block(data["index"], data["transactions"], data["timestamp"],
                      data["previous_hash"], data["nonce"])
        block.hash = data["hash"]
        return block


class Blockchain:
    def __init__(self, difficulty: int = 4):
        self.difficulty = difficulty
        self.chain: List[Block] = []
        self.pending_transactions: List[Dict] = []
        self.voted_voters: Set[str] = set()
        self.candidates = ["Alice", "Bob", "Charlie"]
        self.eligible_voters: Set[str] = set()

        self._load_eligible_voters()
        if os.path.exists(CHAIN_FILE):
            self.load_from_file()
        else:
            self.create_genesis_block()
            self.save_to_file()

    # ---------- Eligible voters management ----------
    def _load_eligible_voters(self):
        if os.path.exists(ELIGIBLE_FILE):
            with open(ELIGIBLE_FILE, "r") as f:
                data = json.load(f)
                self.eligible_voters = set(data.get("voters", []))
        else:
            self.eligible_voters = set()

    def save_eligible_voters(self):
        with open(ELIGIBLE_FILE, "w") as f:
            json.dump({"voters": list(self.eligible_voters)}, f)

    def add_eligible_voters_bulk(self, voter_ids: List[str]):
        for vid in voter_ids:
            self.eligible_voters.add(vid.strip())
        self.save_eligible_voters()

    # ---------- Blockchain persistence ----------
    def create_genesis_block(self):
        genesis_block = Block(0, [], time(), "0")
        genesis_block.mine_block(self.difficulty)
        self.chain.append(genesis_block)

    def save_to_file(self):
        data = {
            "chain": [block.to_dict() for block in self.chain],
            "pending_transactions": self.pending_transactions,
            "voted_voters": list(self.voted_voters)
        }
        with open(CHAIN_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def load_from_file(self):
        with open(CHAIN_FILE, "r") as f:
            data = json.load(f)
        self.chain = [Block.from_dict(block_data) for block_data in data["chain"]]
        self.pending_transactions = data["pending_transactions"]
        self.voted_voters = set(data["voted_voters"])

    # ---------- Signature verification ----------
    def verify_signature(self, voter_id: str, candidate: str, signature_b64: str, public_key_pem: str) -> bool:
        try:
            message = f"{voter_id}:{candidate}".encode()
            pub_key = serialization.load_pem_public_key(public_key_pem.encode())
            pub_key.verify(
                base64.b64decode(signature_b64),
                message,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
        except (InvalidSignature, Exception):
            return False

    # ---------- Add vote ----------
    def add_transaction(self, voter_id: str, candidate: str, signature: str, public_key_pem: str) -> bool:
        if voter_id not in self.eligible_voters:
            return False
        self._rebuild_voted_set()
        if voter_id in self.voted_voters:
            return False
        if candidate not in self.candidates:
            return False
        if not self.verify_signature(voter_id, candidate, signature, public_key_pem):
            return False

        transaction = {
            "voter_id": voter_id,
            "candidate": candidate,
            "public_key": public_key_pem,
            "signature": signature,
            "timestamp": time()
        }
        self.pending_transactions.append(transaction)
        self.voted_voters.add(voter_id)
        self.save_to_file()
        return True

    def _rebuild_voted_set(self):
        voted = set()
        for block in self.chain:
            for tx in block.transactions:
                voted.add(tx["voter_id"])
        for tx in self.pending_transactions:
            voted.add(tx["voter_id"])
        self.voted_voters = voted

    # ---------- Mining ----------
    def mine_pending_transactions(self) -> Block:
        if not self.pending_transactions:
            raise Exception("No pending transactions to mine.")
        new_block = Block(
            index=len(self.chain),
            transactions=self.pending_transactions.copy(),
            timestamp=time(),
            previous_hash=self.chain[-1].hash
        )
        new_block.mine_block(self.difficulty)
        self.chain.append(new_block)
        self.pending_transactions = []
        self.save_to_file()
        return new_block

    # ---------- Reset everything ----------
    def reset(self):
        """Delete all votes, pending transactions, and eligible voters."""
        self.chain = []
        self.pending_transactions = []
        self.voted_voters = set()
        self.eligible_voters = set()
        self.create_genesis_block()
        self.save_to_file()
        self.save_eligible_voters()   # clears the file

    # ---------- Results & chain ----------
    def get_vote_results(self) -> Dict[str, int]:
        results = {c: 0 for c in self.candidates}
        for block in self.chain:
            for tx in block.transactions:
                candidate = tx["candidate"]
                if candidate in results:
                    results[candidate] += 1
        return results

    def is_chain_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            cur = self.chain[i]
            prev = self.chain[i-1]
            if cur.hash != cur.compute_hash():
                return False
            if cur.previous_hash != prev.hash:
                return False
            if cur.hash[:self.difficulty] != "0" * self.difficulty:
                return False
        return True

    def get_full_chain(self) -> List[Dict]:
        return [block.to_dict() for block in self.chain]