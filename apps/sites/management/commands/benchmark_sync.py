from math import ceil
import statistics
import time

from django.core.management.base import BaseCommand, CommandError

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on some platforms
    resource = None


def transform_document(document):
    """Minify one document in the current process."""
    from .html_transform import minify_html

    process_started = time.process_time()
    html = minify_html(document["html"])
    cpu_time = time.process_time() - process_started

    return {
        "kind": document["kind"],
        "slug": document.get("slug"),
        "html": html,
        "cpu_time": cpu_time,
    }


class Command(BaseCommand):
    help = "Benchmark CPU-heavy HTML processing synchronously."

    def add_arguments(self, parser):
        parser.add_argument(
            "--site-id",
            type=int,
            required=True,
            help="Site ID to benchmark.",
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
        runs = options["runs"]
        warmups = options["warmups"]

        if runs < 1:
            raise CommandError("--runs must be at least 1.")
        if warmups < 0:
            raise CommandError("--warmups cannot be negative.")

        try:
            site = Site.objects.get(pk=site_id)
        except Site.DoesNotExist as exc:
            raise CommandError(f"Site {site_id} does not exist.") from exc

        documents = self._load_documents(site)
        page_count = sum(document["kind"] == "page" for document in documents)
        self.stdout.write(
            f"Loaded {len(documents)} documents ({page_count} pages + header + footer).",
        )

        for warmup_number in range(1, warmups + 1):
            try:
                self._transform_documents(documents)
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
            try:
                results = self._transform_documents(documents)
            except Exception as exc:
                failures += 1
                self.stderr.write(f"Run {run_number} failed: {exc}")
                continue

            samples.append(time.perf_counter() - started)
            cpu_samples.append(sum(result["cpu_time"] for result in results))
            memory = self._memory_usage()
            if memory is not None:
                memory_samples.append(memory)

        total_wall_time = time.perf_counter() - benchmark_started

        if not samples:
            raise CommandError("All measured runs failed.")

        self._write_results(
            site_id=site_id,
            page_count=page_count,
            document_count=len(documents),
            runs=runs,
            warmups=warmups,
            samples=samples,
            cpu_samples=cpu_samples,
            memory_samples=memory_samples,
            failures=failures,
            total_wall_time=total_wall_time,
        )

    def _transform_documents(self, documents):
        return [transform_document(document) for document in documents]

    def _load_documents(self, site):
        documents = []
        for kind, file_field in (
            ("header", site.header),
            ("footer", site.footer),
        ):
            if not file_field:
                raise CommandError(f"Site has no {kind} file.")
            documents.append(
                {"kind": kind, "slug": None, "html": self._read(file_field)},
            )

        pages = list(
            site.pages.filter(
                is_enabled=True,
                html_file__isnull=False,
            ).exclude(html_file=""),
        )
        if not pages:
            raise CommandError("Site has no enabled pages with HTML files.")

        for page in pages:
            documents.append(
                {
                    "kind": "page",
                    "slug": page.slug,
                    "html": self._read(page.html_file),
                },
            )
        return documents

    def _read(self, file_field):
        with file_field.open("r") as file:
            return file.read()

    def _memory_usage(self):
        if resource is None:
            return None
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024

    def _write_results(
        self,
        *,
        site_id,
        page_count,
        document_count,
        runs,
        warmups,
        samples,
        cpu_samples,
        memory_samples,
        failures,
        total_wall_time,
    ):
        ordered_samples = sorted(samples)
        p95_index = min(
            len(ordered_samples) - 1,
            ceil(len(ordered_samples) * 0.95) - 1,
        )

        self.stdout.write("")
        self.stdout.write("=== Synchronous Benchmark ===")
        self.stdout.write("Operation: CPU-heavy HTML processing")
        self.stdout.write(f"Site ID: {site_id}")
        self.stdout.write(f"Documents: {document_count}")
        self.stdout.write(f"Pages: {page_count}")
        self.stdout.write("Workers: 1")
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
            f"Average CPU: {statistics.mean(cpu_samples):.6f}s",
        )
        self.stdout.write("")
        self.stdout.write("--- Memory ---")
        if memory_samples:
            self.stdout.write(
                f"Maximum RSS observed: {max(memory_samples):.2f} MB",
            )
        else:
            self.stdout.write("Memory: unavailable")


# python3 manage.py benchmark_sync \
#   --site-id 1 \
#   --warmups 3 \
#   --runs 20
