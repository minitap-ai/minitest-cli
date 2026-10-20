"""Explain a run refused because its Android build has no arm ABI for physical phones."""

import httpx

from minitest_cli.commands._response_errors import extract_detail
from minitest_cli.utils.output import err_console, print_error

# testing-service answers 422 with "This Android build only contains x86_64
# native libraries and cannot run on physical devices (needs arm64-v8a ...)".
_ANDROID_ABI_MISMATCH_MARKER = "cannot run on physical device"
# testing-service#1671 words the rejection of a bundle member this way: the .aab
# itself has no arm64 code, so "upload the .aab" would be the wrong advice.
_BUNDLE_WITHOUT_ARM_MARKER = "the .aab ships no"


def try_handle_android_abi_mismatch(resp: httpx.Response) -> bool:
    """Explain a run refused because its Android build has no arm ABI for physical phones."""
    detail = extract_detail(resp)
    if _ANDROID_ABI_MISMATCH_MARKER not in detail.lower():
        return False
    print_error(detail)
    if _BUNDLE_WITHOUT_ARM_MARKER in detail.lower():
        err_console.print(
            "  [yellow]Hint:[/yellow] this .aab has no arm64 native code, so only its"
            " emulator build exists. Rebuild the app with arm64-v8a libraries (for example"
            " [bold]abiFilters[/bold] / [bold]ndk.abiFilters[/bold] in Gradle), upload the"
            " new .aab, or run on emulators."
        )
        return True
    err_console.print(
        "  [yellow]Hint:[/yellow] upload the [bold].aab[/bold] instead: it converts into a"
        " build for cloud emulators and one for physical phones, and either id works with"
        " [bold]--android-physical[/bold]. Or upload an arm64-v8a build for physical devices."
    )
    return True
