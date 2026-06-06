from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from blockchain import Blockchain
import os
import csv
import io

app = Flask(__name__)
blockchain = Blockchain()

ADMIN_PASSWORD = "admin123"

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

# ---------- Voting endpoint ----------
@app.route('/vote', methods=['POST'])
def vote():
    data = request.get_json()
    voter_id = data.get('voter_id', '').strip()
    candidate = data.get('candidate', '').strip()
    signature = data.get('signature', '')
    public_key = data.get('public_key', '')

    if not all([voter_id, candidate, signature, public_key]):
        return jsonify({"success": False, "message": "Missing fields"}), 400

    success = blockchain.add_transaction(voter_id, candidate, signature, public_key)
    if success:
        return jsonify({"success": True, "message": "Vote recorded (pending mining)"})
    else:
        return jsonify({"success": False, "message": "Not eligible, already voted, or invalid signature"}), 400

# ---------- Mining (admin only) ----------
@app.route('/mine', methods=['POST'])
def mine():
    data = request.get_json()
    password = data.get('password', '')
    if password != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    try:
        new_block = blockchain.mine_pending_transactions()
        return jsonify({
            "success": True,
            "message": f"Block {new_block.index} mined",
            "block_hash": new_block.hash
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

# ---------- Upload eligible voters CSV (admin only) ----------
@app.route('/admin/upload_eligible', methods=['POST'])
def upload_eligible():
    password = request.form.get('password')
    if password != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    if 'file' not in request.files:
        return jsonify({"success": False, "message": "No file provided"}), 400

    file = request.files['file']
    if not file.filename.endswith('.csv'):
        return jsonify({"success": False, "message": "Only CSV files allowed"}), 400

    stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
    reader = csv.reader(stream)
    voters = [row[0].strip() for row in reader if row and row[0].strip()]
    blockchain.add_eligible_voters_bulk(voters)
    return jsonify({"success": True, "message": f"Added {len(voters)} eligible voters"})

# ---------- Reset everything (admin only) ----------
@app.route('/admin/reset', methods=['POST'])
def reset_system():
    data = request.get_json()
    password = data.get('password', '')
    if password != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    # Reset blockchain data
    blockchain.reset()
    return jsonify({"success": True, "message": "All votes, pending transactions, and eligible voters have been deleted. Blockchain reset to genesis block."})

# ---------- Export results as CSV ----------
@app.route('/export_results')
def export_results():
    results = blockchain.get_vote_results()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Candidate', 'Votes'])
    for cand, votes in results.items():
        writer.writerow([cand, votes])
    output.seek(0)
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=election_results.csv"}
    )

# ---------- Utility endpoints ----------
@app.route('/eligible', methods=['GET'])
def get_eligible():
    return jsonify({"eligible_voters": list(blockchain.eligible_voters)})

@app.route('/chain', methods=['GET'])
def get_chain():
    return jsonify({
        "chain": blockchain.get_full_chain(),
        "length": len(blockchain.chain),
        "valid": blockchain.is_chain_valid()
    })

@app.route('/results', methods=['GET'])
def results():
    return jsonify(blockchain.get_vote_results())

@app.route('/voters', methods=['GET'])
def voters():
    blockchain._rebuild_voted_set()
    return jsonify({"voted_voters": list(blockchain.voted_voters)})

@app.route('/pending', methods=['GET'])
def pending():
    return jsonify({"pending_transactions": blockchain.pending_transactions})

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, port=5000)