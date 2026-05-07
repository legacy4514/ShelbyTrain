def main():
    import os
    import json
    import shutil
    import time
    from dotenv import load_dotenv

    from shelbytrain.client import ShelbyHTTPClient
    from shelbytrain.dataset import ShelbyImageDataset
    from shelbytrain.benchmark import benchmark_loader

    load_dotenv()

    def run_case(name, dataset):
        print(f"\nRunning: {name}")
        result = benchmark_loader(dataset, batch_size=32, batches=50)
        print(json.dumps(result, indent=2))
        return result

    results = {}

    # LOCAL TEST
    local_dataset = ShelbyImageDataset(
        manifest_path="data/shelbytrain_mnist/manifest.json",
        client=None,
        max_shards=5,
    )

    results["local"] = run_case("Local shards", local_dataset)

    # SHELBY COLD TEST
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

    cold_result = run_case("Shelby cold read", cold_dataset)
    cold_result["dataset_init_download_sec"] = round(cold_init_time, 4)

    results["shelby_cold"] = cold_result

    # SHELBY CACHED TEST
    cached_start = time.perf_counter()

    cached_dataset = ShelbyImageDataset(
        manifest_path="data/shelbytrain_mnist/manifest.uploaded.json",
        client=client,
        cache_dir=".shelby-cache",
        max_shards=5,
    )

    cached_init_time = time.perf_counter() - cached_start

    cached_result = run_case("Shelby cached read", cached_dataset)
    cached_result["dataset_init_cache_sec"] = round(cached_init_time, 4)

    results["shelby_cached"] = cached_result

    # SAVE RESULTS
    with open("benchmark-results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\nSaved benchmark-results.json")
if __name__ == "__main__":
    main()
