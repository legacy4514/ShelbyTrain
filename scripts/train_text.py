"""
ShelbyTrain — Text Language Model Training Demo
Trains a next-word prediction model on text from Shelby.
No labels required — the model learns to predict the next word.
"""
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from dotenv import load_dotenv
from shelbytrain import ShelbyTextDataset, ShelbyHTTPClient
from collections import Counter

load_dotenv()

# ── Step 1: Connect to Shelby ─────────────────────────────────────────────────
client = ShelbyHTTPClient(
    account=os.environ["SHELBY_ACCOUNT"],
    api_key=os.getenv("SHELBY_API_KEY"),
    rpc_base_url=os.getenv("SHELBY_RPC_BASE_URL",
                           "https://api.shelbynet.shelby.xyz/shelby"),
)

# ── Step 2: Load dataset from Shelby ─────────────────────────────────────────
print("Loading dataset from Shelby...")
shelby_dataset = ShelbyTextDataset(
    manifest_path="data/shelbytrain_bitcoinos/manifest.uploaded.json",
    client=client,
    cache_dir=".shelby-cache",
)
print(f"Dataset ready: {len(shelby_dataset)} samples")

# ── Step 3: Build vocabulary ──────────────────────────────────────────────────
print("Building vocabulary...")
all_words = []
for i in range(len(shelby_dataset)):
    text, _ = shelby_dataset[i]
    all_words.extend(text.lower().split())

counter = Counter(all_words)
vocab = {"<pad>": 0, "<unk>": 1}
for word, count in counter.most_common(2000):
    if count >= 2:
        vocab[word] = len(vocab)

idx_to_word = {v: k for k, v in vocab.items()}
print(f"Vocabulary size: {len(vocab)} words")
print(f"Total words in corpus: {len(all_words)}")

# ── Step 4: Create sequence dataset ──────────────────────────────────────────
# For language modeling we create (input_sequence, next_word) pairs
# Example: "bitcoin is a" → predicts "decentralized"

SEQ_LEN = 10

class SequenceDataset(Dataset):
    def __init__(self, words, vocab, seq_len):
        self.seq_len = seq_len
        self.vocab = vocab
        # Convert all words to token ids
        self.tokens = [vocab.get(w.lower(), 1) for w in words]

    def __len__(self):
        return max(0, len(self.tokens) - self.seq_len - 1)

    def __getitem__(self, idx):
        x = torch.tensor(self.tokens[idx:idx + self.seq_len], dtype=torch.long)
        y = torch.tensor(self.tokens[idx + self.seq_len], dtype=torch.long)
        return x, y

seq_dataset = SequenceDataset(all_words, vocab, SEQ_LEN)
print(f"Training sequences: {len(seq_dataset)}")

loader = DataLoader(seq_dataset, batch_size=32, shuffle=True)

# ── Step 5: Define language model ────────────────────────────────────────────
class LanguageModel(nn.Module):
    def __init__(self, vocab_size, embed_dim, hidden_dim):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.lstm = nn.LSTM(embed_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)
        self.dropout = nn.Dropout(0.3)

    def forward(self, x):
        embedded = self.embedding(x)          # [batch, seq, embed]
        out, _ = self.lstm(embedded)          # [batch, seq, hidden]
        out = self.dropout(out[:, -1, :])     # take last timestep
        return self.fc(out)                   # [batch, vocab_size]

model = LanguageModel(
    vocab_size=len(vocab),
    embed_dim=64,
    hidden_dim=128,
)

optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
criterion = nn.CrossEntropyLoss(ignore_index=0)

total_params = sum(p.numel() for p in model.parameters())
print(f"Model parameters: {total_params:,}")

# ── Step 6: Train ─────────────────────────────────────────────────────────────
print("\nStarting training...")
print("─" * 50)

for epoch in range(5):
    total_loss = 0
    correct = 0
    total = 0
    batches = 0

    for x, y in loader:
        outputs = model(x)
        loss = criterion(outputs, y)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        predicted = outputs.argmax(dim=1)
        correct += (predicted == y).sum().item()
        total += y.size(0)
        total_loss += loss.item()
        batches += 1

    avg_loss = total_loss / batches if batches else 0
    accuracy = correct / total if total else 0
    perplexity = torch.exp(torch.tensor(avg_loss)).item()

    print(f"Epoch {epoch+1}/5 | "
          f"Loss: {avg_loss:.4f} | "
          f"Accuracy: {accuracy:.2%} | "
          f"Perplexity: {perplexity:.1f}")

print("─" * 50)

# ── Step 7: Test the model ────────────────────────────────────────────────────
print("\nTesting model — next word prediction:")
print("─" * 50)

def predict_next(text, model, vocab, idx_to_word, seq_len=10):
    model.eval()
    words = text.lower().split()[-seq_len:]
    tokens = [vocab.get(w, 1) for w in words]
    # pad if needed
    tokens = [0] * (seq_len - len(tokens)) + tokens
    x = torch.tensor([tokens], dtype=torch.long)
    with torch.no_grad():
        output = model(x)
        top5 = output[0].topk(5).indices.tolist()
    return [idx_to_word.get(i, "<unk>") for i in top5]

test_phrases = [
    "bitcoin is a decentralized",
    "the blockchain network",
    "transactions are verified by",
]

for phrase in test_phrases:
    predictions = predict_next(phrase, model, vocab, idx_to_word)
    print(f"Input:      '{phrase}'")
    print(f"Predicted:  {predictions}")
    print()

# ── Step 8: Save model ────────────────────────────────────────────────────────
torch.save({
    "model_state": model.state_dict(),
    "vocab": vocab,
    "config": {
        "vocab_size": len(vocab),
        "embed_dim": 64,
        "hidden_dim": 128,
        "seq_len": SEQ_LEN,
    }
}, "trained_model.pt")

print("✓ Model saved to trained_model.pt")
print("✓ Training complete")
print(f"✓ Trained on {len(all_words):,} words from BitcoinOS.txt via Shelby")
