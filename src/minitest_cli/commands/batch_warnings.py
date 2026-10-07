from minitest_cli.models.batch import BatchResponse
from minitest_cli.utils.output import print_warning


def print_compatibility_warnings(batch: BatchResponse, seen: set[str] | None = None) -> set[str]:
    reported = seen if seen is not None else set()
    for target in batch.targets:
        for warning in target.compatibility_warnings:
            if warning not in reported:
                print_warning(warning)
                reported.add(warning)
    return reported
