from torch.utils.data import DataLoader
from shelbytrain.dataset import ShelbyImageDataset


def main():
    dataset = ShelbyImageDataset(
        manifest_path="data/shelbytrain_mnist/manifest.json",
        client=None,
        max_shards=2,
    )

    loader = DataLoader(dataset, batch_size=32, shuffle=True)
    images, labels = next(iter(loader))

    print("Images shape:", images.shape)
    print("Labels shape:", labels.shape)
    print("First labels:", labels[:10].tolist())


if __name__ == "__main__":
    main()
