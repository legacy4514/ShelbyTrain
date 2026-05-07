from pathlib import Path
from torchvision.datasets import MNIST
import csv

OUT = Path("data/raw_mnist")
IMG_DIR = OUT / "images"
LABELS = OUT / "labels.csv"


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    dataset = MNIST(root="data/mnist", train=True, download=True)

    with LABELS.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["filename", "label"])

        for i, (img, label) in enumerate(dataset):
            name = f"{i:06d}.png"
            img.save(IMG_DIR / name)
            writer.writerow([name, label])

    print(f"Saved dataset to {OUT}")


if __name__ == "__main__":
    main()
