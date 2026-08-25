import asyncio
from math import ceil
from pathlib import Path
import statistics
import time

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on some platforms
    resource = None


async def read_document(path, semaphore):
    """Read one local file without blocking the async event loop."""
    async with semaphore:
        content = await asyncio.to_thread(path.read_bytes)
    return len(content)


async def read_documents(paths, concurrency):
    semaphore = asyncio.Semaphore(concurrency)
    return await asyncio.gather(
        *(read_document(path, semaphore) for path in paths),
    )


class Command(BaseCommand):
    help = "Benchmark concurrent local-file I/O using asyncio."

    def add_arguments(self, parser):
        parser.add_argument(
            "--site-id",
            type=int,
            required=True,
            help="Site ID whose published source files should be read.",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=10,
            help="Maximum concurrent file reads (default: 10).",
        )
        parser.add_argument(
            "--runs",
            type=int,
            default=10,
            help="Measured runs after warmups (default: 10).",
        )
        parser.add_argument(
            "--warmups",
            type=int,
            default=3,
            help="Warm-up runs excluded from results (default: 3).",
        )

    def handle(self, *args, **options):
        from apps.sites.models import Site

        site_id = options["site_id"]
        concurrency = options["concurrency"]
        runs = options["runs"]
        warmups = options["warmups"]

        if concurrency < 1:
            raise CommandError("--concurrency must be at least 1.")
        if runs < 1:
            raise CommandError("--runs must be at least 1.")
        if warmups < 0:
            raise CommandError("--warmups cannot be negative.")

        try:
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist as exc:
            raise CommandError(f"Site {site_id} does not exist.") from exc

        paths, page_count = self._load_paths(site)
        self.stdout.write(
            f"Loaded {len(paths)} files ({page_count} pages + header + footer).",
        )

        result = asyncio.run(
            self._benchmark(
                paths=paths,
                concurrency=concurrency,
                runs=runs,
                warmups=warmups,
            ),
        )
        self._write_results(
            site_id=site_id,
            page_count=page_count,
            file_count=len(paths),
            concurrency=concurrency,
            runs=runs,
            warmups=warmups,
            **result,
        )

    def _load_paths(self, site):
        paths = []
        for kind, file_field in (
            ("header", site.header),
            ("footer", site.footer),
        ):
            if not file_field:
                raise CommandError(f"Site has no {kind} file.")
            paths.append(self._storage_path(file_field.name))

        pages = list(
            site.pages.filter(
                is_enabled=True,
                html_file__isnull=False,
            ).exclude(html_file=""),
        )
        if not pages:
            raise CommandError("Site has no enabled pages with HTML files.")

        for page in pages:
            paths.append(self._storage_path(page.html_file.name))

        if site.global_css:
            paths.append(self._storage_path(site.global_css.name))
        return paths, len(pages)

    def _storage_path(self, name):
        try:
            return Path(default_storage.path(name))
        except (AttributeError, NotImplementedError, ValueError) as exc:
            raise CommandError(
                "benchmark_async requires local filesystem storage.",
            ) from exc

    async def _benchmark(self, *, paths, concurrency, runs, warmups):
        for warmup_number in range(1, warmups + 1):
            try:
                await read_documents(paths, concurrency)
            except Exception as exc:
                raise CommandError(
                    f"Warm-up {warmup_number} failed: {exc}",
                ) from exc

        samples = []
        cpu_samples = []
        memory_samples = []
        failures = 0
        benchmark_started = time.perf_counter()

        for run_number in range(1, runs + 1):
            started = time.perf_counter()
            cpu_started = time.process_time()
            try:
                sizes = await read_documents(paths, concurrency)
            except Exception as exc:
                failures += 1
                self.stderr.write(f"Run {run_number} failed: {exc}")
                continue

            samples.append(time.perf_counter() - started)
            cpu_samples.append(time.process_time() - cpu_started)
            memory = self._memory_usage()
            if memory is not None:
                memory_samples.append(memory)

            if sum(sizes) <= 0:
                failures += 1
                samples.pop()
                cpu_samples.pop()

        return {
            "samples": samples,
            "cpu_samples": cpu_samples,
            "memory_samples": memory_samples,
            "failures": failures,
            "total_wall_time": time.perf_counter() - benchmark_started,
        }

    def _memory_usage(self):
        if resource is None:
            return None
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    def _write_results(
        self,
        *,
        site_id,
        page_count,
        file_count,
        concurrency,
        runs,
        warmups,
        samples,
        cpu_samples,
        memory_samples,
        failures,
        total_wall_time,
    ):
        if not samples:
            raise CommandError("All measured runs failed.")

        ordered_samples = sorted(samples)
        p95_index = min(
            len(ordered_samples) - 1,
            ceil(len(ordered_samples) * 0.95) - 1,
        )

        self.stdout.write("")
        self.stdout.write("=== Async I/O Benchmark ===")
        self.stdout.write("Operation: concurrent local-file reads")
        self.stdout.write(f"Site ID: {site_id}")
        self.stdout.write(f"Files: {file_count}")
        self.stdout.write(f"Pages: {page_count}")
        self.stdout.write(f"Concurrency: {concurrency}")
        self.stdout.write(f"Warm-ups: {warmups}")
        self.stdout.write(f"Measured runs: {runs}")
        self.stdout.write(f"Successful runs: {len(samples)}")
        self.stdout.write(f"Failures: {failures}")
        self.stdout.write("")
        self.stdout.write("--- Wall Time ---")
        self.stdout.write(f"Min: {min(samples):.6f}s")
        self.stdout.write(f"Max: {max(samples):.6f}s")
        self.stdout.write(f"Average: {statistics.mean(samples):.6f}s")
        self.stdout.write(f"Median: {statistics.median(samples):.6f}s")
        self.stdout.write(f"P95: {ordered_samples[p95_index]:.6f}s")
        self.stdout.write(f"Total benchmark time: {total_wall_time:.6f}s")
        self.stdout.write("")
        self.stdout.write("--- CPU ---")
        self.stdout.write(
            f"Average parent CPU: {statistics.mean(cpu_samples):.6f}s",
        )
        self.stdout.write("")
        self.stdout.write("--- Memory ---")
        if memory_samples:
            self.stdout.write(
                f"Maximum RSS observed: {max(memory_samples):.2f} MB",
            )
        else:
            self.stdout.write("Memory: unavailable")


# python3 manage.py benchmark_async \
#   --site-id 1 \
#   --concurrency 4 \
#   --warmups 3 \
#   --runs 20
