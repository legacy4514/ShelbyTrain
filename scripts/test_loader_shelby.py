import os
from dotenv import load_dotenv
from torch.utils.data import DataLoader

from shelbytrain.client import ShelbyHTTPClient
from shelbytrain.dataset import ShelbyImageDataset

load_dotenv()


def main():
    client = ShelbyHTTPClient(
        account=os.environ["SHELBY_ACCOUNT"],
        api_key=os.getenv("SHELBY_API_KEY"),
        rpc_base_url=os.getenv("SHELBY_RPC_BASE_URL", "https://api.shelbynet.shelby.xyz/shelby"),
    )

    dataset = ShelbyImageDataset(
        manifest_path="data/shelbytrain_mnist/manifest.uploaded.json",
        client=client,
        cache_dir=".shelby-cache",
        max_shards=2,
    )

    loader = DataLoader(dataset, batch_size=32, shuffle=True)
    images, labels = next(iter(loader))

    print("Images shape:", images.shape)
    print("Labels shape:", labels.shape)
    print("First labels:", labels[:10].tolist())


if __name__ == "__main__":
    main()
