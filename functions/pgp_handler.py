import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class PGPError(Exception):
    """Raised when a PGP operation fails."""
    pass


def _run_gpg(
    args,
    homedir,
    input_data=None,
    passphrase_file=None
):
    command = [
        "gpg",
        "--batch",
        "--no-tty",
        "--homedir", homedir
    ]

    if passphrase_file:
        command.extend([
            "--pinentry-mode", "loopback",
            "--passphrase-file", passphrase_file
        ])

    command.extend(args)

    try:
        result = subprocess.run(
            command,
            input=input_data,
            capture_output=True,
            check=False,
            timeout=120
        )

    except FileNotFoundError as exc:
        raise PGPError("GnuPG executable not found.") from exc

    except subprocess.TimeoutExpired as exc:
        raise PGPError("GnuPG operation timed out.") from exc

    if result.returncode != 0:
        error = result.stderr.decode(
            "utf-8",
            errors="replace"
        )

        raise PGPError(error)

    return result.stdout


def encrypt_and_sign(
    data: bytes,
    recipient_public_keys: list[str],
    recipient_ids: list[str],
    private_key_path: str,
    private_key_password: str,
    sign: bool = True
) -> bytes:

    if not data:
        raise ValueError("Message data is empty")

    if not recipient_public_keys:
        raise ValueError("Recipient public keys are required")

    if not recipient_ids:
        raise ValueError("Recipient email addresses are required")

    if sign and not private_key_path:
        raise ValueError("Private key path is required")

    # Password may be empty for unprotected keys (example keys).
    if sign and private_key_password is None:
        raise ValueError("Private key password is required (may be empty string)")

    for key in recipient_public_keys:
        if not Path(key).is_file():
            raise FileNotFoundError(key)

    if sign and not Path(private_key_path).is_file():
        raise FileNotFoundError(private_key_path)

    if not shutil.which("gpg"):
        raise PGPError("GnuPG is not installed or unavailable in PATH.")

    with tempfile.TemporaryDirectory(prefix="pgp_") as temp_dir:

        os.chmod(temp_dir, 0o700)

        homedir = str(Path(temp_dir) / "gnupg")
        Path(homedir).mkdir(mode=0o700)

        # Import recipient public keys.
        for key_path in recipient_public_keys:

            with open(key_path, "rb") as key_file:
                _run_gpg(
                    ["--import"],
                    homedir,
                    input_data=key_file.read()
                )

        # Import application private key.
        if sign:

            with open(private_key_path, "rb") as key_file:
                _run_gpg(
                    ["--import"],
                    homedir,
                    input_data=key_file.read()
                )

        passphrase_file = None

        try:

            if sign:

                passphrase_file = str(
                    Path(temp_dir) / "passphrase"
                )

                fd = os.open(
                    passphrase_file,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600
                )

                with os.fdopen(fd, "w") as file:
                    file.write(private_key_password)

            # Encrypt and optionally sign.
            args = [
                "--trust-model", "always",
                "--armor",
                "--encrypt",
                "--output", "-"
            ]

            if sign:
                args.append("--sign")

            for recipient in recipient_ids:
                args.extend(["--recipient", recipient])

            return _run_gpg(
                args,
                homedir,
                input_data=data,
                passphrase_file=passphrase_file
            )

        finally:

            if passphrase_file and os.path.exists(passphrase_file):
                os.remove(passphrase_file)
