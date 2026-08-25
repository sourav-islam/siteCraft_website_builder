from math import ceil
import multiprocessing
import statistics
import time

from django.core.management.base import BaseCommand, CommandError

try:
    import resource
except ImportError:  # pragma: no cover
    resource = None


def transform_document(document):
    """
    CPU-heavy operation executed inside a worker process.

    IMPORTANT:
    HTMLMinifier must be Django-independent.
    """

    from .html_transform import minify_html

    process_started = time.process_time()

    html = minify_html(document["html"])

    cpu_time = time.process_time() - process_started
    memory = get_worker_memory()

    return {
        "kind": document["kind"],
        "slug": document.get("slug"),
        "html": html,
        "cpu_time": cpu_time,
        "memory": memory,
    }


def get_worker_memory():
    """
    Return the worker process maximum RSS in MB.
    """

    if resource is None:
        return None

    usage = resource.getrusage(resource.RUSAGE_SELF)

    # Linux reports ru_maxrss in KB.
    return usage.ru_maxrss / 1024


class Command(BaseCommand):
    help = "Benchmark CPU-heavy HTML processing using multiprocessing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--site-id",
            type=int,
            required=True,
            help="Site ID to benchmark.",
        )

        parser.add_argument(
            "--workers",
            type=int,
            default=max(1, multiprocessing.cpu_count() - 1),
            help=("Number of worker processes (default: CPU count minus one)."),
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
            help=("Warm-up runs excluded from results (default: 3)."),
        )

    def handle(self, *args, **options):
        from apps.sites.models import Site

        site_id = options["site_id"]
        workers = options["workers"]
        runs = options["runs"]
        warmups = options["warmups"]

        self._validate_arguments(
            workers=workers,
            runs=runs,
            warmups=warmups,
        )

        try:
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist as exc:
            raise CommandError(
                f"Site {site_id} does not exist.",
            ) from exc

        documents = self._load_documents(site)

        page_count = sum(1 for document in documents if document["kind"] == "page")

        document_count = len(documents)

        self.stdout.write(
            f"Loaded {document_count} documents ({page_count} pages + header + footer).",
        )

        context = multiprocessing.get_context("spawn")

        with context.Pool(processes=workers) as pool:
            # --------------------------------------------------
            # Warm-up
            # --------------------------------------------------

            for warmup_number in range(1, warmups + 1):
                try:
                    pool.map(
                        transform_document,
                        documents,
                    )
                except Exception as exc:
                    raise CommandError(
                        f"Warm-up {warmup_number} failed: {exc}",
                    ) from exc

            # --------------------------------------------------
            # Benchmark
            # --------------------------------------------------

            samples = []
            worker_cpu_samples = []
            worker_memory_samples = []
            failures = 0

            benchmark_started = time.perf_counter()

            for run_number in range(1, runs + 1):
                started = time.perf_counter()

                try:
                    results = pool.map(
                        transform_document,
                        documents,
                    )

                except Exception as exc:
                    failures += 1

                    self.stderr.write(
                        f"Run {run_number} failed: {exc}",
                    )

                    continue

                elapsed = time.perf_counter() - started

                samples.append(elapsed)

                # ----------------------------------------------
                # Worker CPU
                # ----------------------------------------------

                run_cpu = sum(result["cpu_time"] for result in results)

                worker_cpu_samples.append(run_cpu)

                # ----------------------------------------------
                # Worker memory
                # ----------------------------------------------

                memory_values = [result["memory"] for result in results if result["memory"] is not None]

                if memory_values:
                    worker_memory_samples.append(
                        max(memory_values),
                    )

            total_wall_time = time.perf_counter() - benchmark_started

        if not samples:
            raise CommandError(
                "All measured runs failed.",
            )

        self._write_results(
            site_id=site_id,
            page_count=page_count,
            document_count=document_count,
            workers=workers,
            runs=runs,
            warmups=warmups,
            samples=samples,
            worker_cpu_samples=worker_cpu_samples,
            worker_memory_samples=worker_memory_samples,
            failures=failures,
            total_wall_time=total_wall_time,
        )

    # ==========================================================
    # Validation
    # ==========================================================

    def _validate_arguments(
        self,
        *,
        workers,
        runs,
        warmups,
    ):
        if workers < 1:
            raise CommandError(
                "--workers must be at least 1.",
            )

        if runs < 1:
            raise CommandError(
                "--runs must be at least 1.",
            )

        if warmups < 0:
            raise CommandError(
                "--warmups cannot be negative.",
            )

    # ==========================================================
    # Load documents
    # ==========================================================

    def _load_documents(self, site):
        """
        Load the same workload that will be used by every
        multiprocessing benchmark run.

        Django/database/file access happens in the parent process.

        Workers receive only plain Python data.
        """

        documents = []

        # ------------------------------------------------------
        # Header
        # ------------------------------------------------------

        if not site.header:
            raise CommandError(
                "Site has no header file.",
            )

        documents.append(
            {
                "kind": "header",
                "slug": None,
                "html": self._read(site.header),
            },
        )

        # ------------------------------------------------------
        # Footer
        # ------------------------------------------------------

        if not site.footer:
            raise CommandError(
                "Site has no footer file.",
            )

        documents.append(
            {
                "kind": "footer",
                "slug": None,
                "html": self._read(site.footer),
            },
        )

        # ------------------------------------------------------
        # Pages
        # ------------------------------------------------------

        pages = site.pages.filter(
            is_enabled=True,
            html_file__isnull=False,
        ).exclude(
            html_file="",
        )

        pages = list(pages)

        if not pages:
            raise CommandError(
                "Site has no enabled pages with HTML files.",
            )

        for page in pages:
            documents.append(
                {
                    "kind": "page",
                    "slug": page.slug,
                    "html": self._read(page.html_file),
                },
            )

        return documents

    # ==========================================================
    # File reading
    # ==========================================================

    def _read(self, file_field):
        """
        Read the HTML in the parent process.

        This is intentionally outside the worker because the
        benchmark is targeting CPU-heavy HTML processing.
        """

        with file_field.open("r") as file:
            return file.read()

    # ==========================================================
    # Results
    # ==========================================================

    def _write_results(
        self,
        *,
        site_id,
        page_count,
        document_count,
        workers,
        runs,
        warmups,
        samples,
        worker_cpu_samples,
        worker_memory_samples,
        failures,
        total_wall_time,
    ):
        ordered_samples = sorted(samples)

        average = statistics.mean(samples)
        median = statistics.median(samples)

        p95_index = min(
            len(ordered_samples) - 1,
            ceil(
                len(ordered_samples) * 0.95,
            )
            - 1,
        )

        p95 = ordered_samples[p95_index]

        # ------------------------------------------------------
        # Worker CPU statistics
        # ------------------------------------------------------

        average_worker_cpu = statistics.mean(worker_cpu_samples) if worker_cpu_samples else None

        # ------------------------------------------------------
        # Worker memory statistics
        # ------------------------------------------------------

        max_worker_memory = max(worker_memory_samples) if worker_memory_samples else None

        # ------------------------------------------------------
        # Output
        # ------------------------------------------------------

        self.stdout.write("")
        self.stdout.write(
            "=== Multiprocessing Benchmark ===",
        )

        self.stdout.write(
            "Operation: CPU-heavy HTML processing",
        )

        self.stdout.write(
            f"Site ID: {site_id}",
        )

        self.stdout.write(
            f"Documents: {document_count}",
        )

        self.stdout.write(
            f"Pages: {page_count}",
        )

        self.stdout.write(
            f"Workers: {workers}",
        )

        self.stdout.write(
            f"Warm-ups: {warmups}",
        )

        self.stdout.write(
            f"Measured runs: {runs}",
        )

        self.stdout.write(
            f"Successful runs: {len(samples)}",
        )

        self.stdout.write(
            f"Failures: {failures}",
        )

        # ------------------------------------------------------
        # Wall time
        # ------------------------------------------------------

        self.stdout.write("")
        self.stdout.write("--- Wall Time ---")

        self.stdout.write(
            f"Min: {min(samples):.6f}s",
        )

        self.stdout.write(
            f"Max: {max(samples):.6f}s",
        )

        self.stdout.write(
            f"Average: {average:.6f}s",
        )

        self.stdout.write(
            f"Median: {median:.6f}s",
        )

        self.stdout.write(
            f"P95: {p95:.6f}s",
        )

        self.stdout.write(
            f"Total benchmark time: {total_wall_time:.6f}s",
        )

        # ------------------------------------------------------
        # CPU
        # ------------------------------------------------------

        self.stdout.write("")
        self.stdout.write("--- Worker CPU ---")

        if average_worker_cpu is not None:
            self.stdout.write(
                f"Average worker CPU: {average_worker_cpu:.6f}s",
            )
        else:
            self.stdout.write(
                "Worker CPU: unavailable",
            )

        # ------------------------------------------------------
        # Memory
        # ------------------------------------------------------

        self.stdout.write("")
        self.stdout.write("--- Worker Memory ---")

        if max_worker_memory is not None:
            self.stdout.write(
                f"Maximum worker RSS observed: {max_worker_memory:.2f} MB",
            )
        else:
            self.stdout.write(
                "Worker memory: unavailable",
            )

        self.stdout.write("")


# python3 manage.py benchmark_multiprocessing \
#   --site-id 1 \
#   --workers 2 \
#   --warmups 3 \
#   --runs 20
