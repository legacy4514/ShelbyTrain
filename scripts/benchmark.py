import json
import shutil
import time
import os

from dotenv import load_dotenv

from shelbytrain.client import ShelbyHTTPClient
from shelbytrain.dataset import ShelbyImageDataset
from shelbytrain.benchmark import benchmark_loader

load_dotenv()


def run_case(name, dataset):
    result = benchmark_loader(dataset, batch_size=32, batches=50)
    return result


def run_benchmark():
    results = {}

    local_dataset = ShelbyImageDataset(
        manifest_path="data/shelbytrain_mnist/manifest.json",
        client=None,
        max_shards=5,
    )

    results["local"] = run_case("Local", local_dataset)

    shutil.rmtree(".shelby-cache", ignore_errors=True)

    client = ShelbyHTTPClient(
        account=os.environ["SHELBY_ACCOUNT"],
        api_key=os.getenv("SHELBY_API_KEY"),
    )

    cold_start = time.perf_counter()

    cold_dataset = ShelbyImageDataset(
        manifest_path="data/shelbytrain_mnist/manifest.uploaded.json",
        client=client,
        cache_dir=".shelby-cache",
        max_shards=5,
    )

    cold_init_time = time.perf_counter() - cold_start

    cold_result = run_case("Shelby Cold", cold_dataset)

    cold_result["dataset_init_download_sec"] = round(cold_init_time, 4)

    results["shelby_cold"] = cold_result

    cached_start = time.perf_counter()

    cached_dataset = ShelbyImageDataset(
        manifest_path="data/shelbytrain_mnist/manifest.uploaded.json",
        client=client,
        cache_dir=".shelby-cache",
        max_shards=5,
    )

    cached_init_time = time.perf_counter() - cached_start

    cached_result = run_case("Shelby Cached", cached_dataset)

    cached_result["dataset_init_cache_sec"] = round(cached_init_time, 4)

    results["shelby_cached"] = cached_result

    with open("benchmark-results.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    output = run_benchmark()
    print(json.dumps(output, indent=2))
