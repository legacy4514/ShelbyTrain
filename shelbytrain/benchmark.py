import time
from typing import Any, Dict

from torch.utils.data import DataLoader


def benchmark_loader(dataset, batch_size: int = 32, batches: int = 50) -> Dict[str, Any]:
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    start = time.perf_counter()
    first_batch_time = None
    total_samples = 0
    actual_batches = 0

    for i, (_images, labels) in enumerate(loader):
        now = time.perf_counter()
        if first_batch_time is None:
            first_batch_time = now - start

        total_samples += len(labels)
        actual_batches += 1

        if i + 1 >= batches:
            break

    total_time = time.perf_counter() - start
    return {
        "batches": actual_batches,
        "batch_size": batch_size,
        "samples": total_samples,
        "time_to_first_batch_sec": round(first_batch_time or 0, 4),
        "total_time_sec": round(total_time, 4),
        "samples_per_sec": round(total_samples / total_time, 2) if total_time else 0,
    }
