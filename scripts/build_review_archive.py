"""Build and check a local review package from an explicit list; no network."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIST = "packaging/stage1_files.json"
MANIFEST = "PACKAGE_MANIFEST.json"
DENIED = {"tmp", ".git", ".aws", "private", "raw", ".venv", "__pycache__", "output", "delivery"}


def check(condition, message):
    if not condition:
        raise ValueError(message)


def permitted(name):
    check(isinstance(name, str) and "\\" not in name, "Only relative POSIX member names allowed")
    path = PurePosixPath(name)
    check(not path.is_absolute() and bool(path.parts) and all(x not in {".", ".."} for x in path.parts), "Unsafe archive path")
    check(not any(x.lower() in DENIED for x in path.parts), "Private/generated path in package")
    check(not any(":" in x for x in path.parts), "Drive/stream path in package")
    check(not path.name.lower().startswith(".env"), "Environment files excluded")
    check(path.suffix.lower() in {".md", ".json", ".py", ".txt"} or name == ".gitignore", "Unapproved file type")
    return path


def members():
    names = json.loads((ROOT / LIST).read_text(encoding="utf-8"))
    check(isinstance(names, list) and names and len(set(names)) == len(names), "Invalid or duplicate allowlist")
    for name in names:
        permitted(name)
    return sorted(names)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(archive, expected_names=None):
    names = expected_names if expected_names is not None else members()
    with zipfile.ZipFile(archive) as handle:
        all_names = handle.namelist()
        check(len(all_names) == len(set(all_names)), "Duplicate ZIP members")
        check(set(all_names) == set(names) | {MANIFEST}, "Unexpected/missing ZIP member")
        check(handle.testzip() is None, "ZIP CRC failure")
        manifest = json.loads(handle.read(MANIFEST))
        check(manifest["format"] == "stage1-review-v1", "Unsupported package format")
        records = manifest["files"]
        check(set(records) == set(names), "Manifest does not describe the exact allowed list")
        for name in names:
            permitted(name)
            info = handle.getinfo(name)
            check(not info.is_dir() and (info.external_attr >> 16) & 0o170000 != 0o120000, "Symlink/directory excluded")
            data = handle.read(name)
            check(records[name] == {"bytes": len(data), "sha256": digest(data)}, "Checksum mismatch: " + name)
        check(json.loads(handle.read(LIST)) == json.loads((ROOT / LIST).read_text(encoding="utf-8")), "Embedded allowlist differs")
        return manifest


def build():
    names = members()
    contents = {}
    for name in names:
        path = ROOT / name
        check(path.is_file() and not path.is_symlink(), "Missing/symlink source: " + name)
        check(path.resolve().is_relative_to(ROOT.resolve()), "Source escapes project")
        contents[name] = path.read_bytes()
    manifest = {"format": "stage1-review-v1", "scope": "single user with Codex; technical snapshot without source PDFs",
                "files": {n: {"bytes": len(d), "sha256": digest(d)} for n, d in contents.items()}}
    contents[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target = ROOT / "delivery/stage1-local-v2-2026-11-09.zip"
    target.parent.mkdir(exist_ok=True)
    # Refuse to overwrite an existing review version with different bytes.
    candidate = target.with_suffix(".building.zip")
    with zipfile.ZipFile(candidate, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for name in sorted(contents):
            info = zipfile.ZipInfo(name, (2026, 11, 9, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            handle.writestr(info, contents[name])
    verify(candidate, names)
    if target.exists():
        check(target.read_bytes() == candidate.read_bytes(), "Existing review version differs: choose a new package version before rebuilding")
        candidate.unlink()
    else:
        candidate.rename(target)
    runs = []
    temp_parent = ROOT / "tmp/transfer-check"
    temp_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="stage1-", dir=temp_parent) as folder:
        extracted = Path(folder)
        check(extracted.resolve().is_relative_to(temp_parent.resolve())
              and temp_parent.resolve().is_relative_to(ROOT.resolve()), "Temporary cleanup target escapes workspace")
        # Only after exact paths, membership, CRC and hashes have passed.
        with zipfile.ZipFile(target) as handle:
            handle.extractall(extracted)
        for args in (["scripts/check_stage1.py"], ["-m", "unittest", "discover", "-s", "tests", "-v"]):
            command = [sys.executable, "-I", *args]
            result = subprocess.run(command, cwd=extracted, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
            runs.append({"command": ["python", "-I", *args], "exit_code": result.returncode,
                         "stdout": result.stdout, "stderr": result.stderr})
            check(result.returncode == 0, "Isolated check failed: " + str(args))
    receipt = {"checked_at": datetime.now(timezone.utc).isoformat(), "archive": target.name,
               "sha256": digest(target.read_bytes()), "bytes": target.stat().st_size,
               "payload_files": len(names), "zip_members": len(names) + 1,
               "exact_members_and_hashes_verified": True, "source_documents_included": False,
               "test_environment": "new directory, isolated Python, same computer and interpreter",
               "workflow": "single_user_with_codex",
               "fact_verification_provenance": "assistant_checked_not_a_claim_of_user_review",
               "storage": "local_folder_and_archive_selected_by_user",
               "runs": runs}
    receipt_path = target.with_suffix(".receipt.json")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Archive: {target.name}; payload={len(names)}; bytes={receipt['bytes']}")
    print("SHA256: " + receipt["sha256"])
    print("Exact file list, CRC and SHA256: passed; isolated checks: 2/2 passed")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", type=Path)
    args = parser.parse_args()
    if args.verify_only:
        manifest = verify(args.verify_only)
        print(f"Verified {len(manifest['files'])} payload files; exact membership, CRC and SHA256 passed")
    else:
        build()
