from shelbytrain.sharder import create_image_shards


if __name__ == "__main__":
    create_image_shards(
        dataset_dir="data/raw_mnist",
        output_dir="data/shelbytrain_mnist",
        shard_size=1000,
        dataset_name="mnist-demo",
    )
