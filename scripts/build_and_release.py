"""
SoundFlow Studio — Automated Build and GitHub Release Publisher.
Supports:
1. Local compilation of SoundFlow.exe via PyInstaller.
2. Verification and validation of the built binary.
3. Automatic GitHub Release creation and binary asset uploading via GitHub REST API.
4. Git tagging and syncing with origin.
"""

import os
import sys
import time
import argparse
import subprocess
import urllib.request
import urllib.parse
import json
import shutil
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_git_credential_token() -> str:
    """Attempts to retrieve the GitHub OAuth/PAT token from Git Credential Manager."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        return token
    try:
        proc = subprocess.Popen(
            ["git", "credential", "fill"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        out, _ = proc.communicate(input="protocol=https\nhost=github.com\n", timeout=5)
        for line in out.splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def get_git_remote_repo() -> str:
    """Extracts 'owner/repo' from 'git remote get-url origin'."""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=str(PROJECT_ROOT),
            text=True
        ).strip()
        # https://github.com/owner/repo.git or git@github.com:owner/repo.git
        if url.endswith(".git"):
            url = url[:-4]
        if "github.com/" in url:
            return url.split("github.com/", 1)[1]
        elif "github.com:" in url:
            return url.split("github.com:", 1)[1]
    except Exception:
        pass
    return "MrPanica/SoundFlow"


def cleanup_temp_and_build(clean_build: bool = True, clean_temp: bool = True, clean_dist: bool = False):
    """
    Cleans up past compilation debris:
    1. Removes workspace 'build/' directory (hundreds of MB of temporary object files).
    2. Cleans orphaned PyInstaller extraction folders (_MEI*) in OS Temp directory.
    3. Optionally removes 'dist/' directory.
    """
    print("[CLEANUP] Cleaning temporary files and build artifacts...")
    freed_bytes = 0

    # 1. Clean workspace build directory
    build_dir = PROJECT_ROOT / "build"
    if clean_build and build_dir.exists():
        try:
            for p in build_dir.rglob("*"):
                if p.is_file():
                    freed_bytes += p.stat().st_size
            shutil.rmtree(build_dir, ignore_errors=True)
            print(f"[CLEANUP] Removed workspace build directory: {build_dir}")
        except Exception as e:
            print(f"[CLEANUP] Warning removing build dir: {e}")

    # 2. Clean dist directory if requested
    if clean_dist:
        dist_dir = PROJECT_ROOT / "dist"
        if dist_dir.exists():
            try:
                for p in dist_dir.rglob("*"):
                    if p.is_file():
                        freed_bytes += p.stat().st_size
                shutil.rmtree(dist_dir, ignore_errors=True)
                print(f"[CLEANUP] Removed workspace dist directory: {dist_dir}")
            except Exception as e:
                print(f"[CLEANUP] Warning removing dist dir: {e}")

    # 3. Clean orphaned _MEI* temp folders in tempfile.gettempdir()
    if clean_temp:
        temp_dir = Path(tempfile.gettempdir())
        try:
            for item in temp_dir.glob("_MEI*"):
                if item.is_dir():
                    try:
                        item_size = sum(f.stat().st_size for f in item.rglob('*') if f.is_file())
                        shutil.rmtree(item, ignore_errors=False)
                        freed_bytes += item_size
                        print(f"[CLEANUP] Removed orphaned temp folder: {item.name}")
                    except Exception:
                        # Folder is currently locked by an active running process
                        pass
        except Exception as e:
            print(f"[CLEANUP] Warning scanning temp dir: {e}")

    mb_freed = freed_bytes / (1024 * 1024)
    print(f"[CLEANUP] Completed. Freed approximately {mb_freed:.2f} MB of disk space.")


def build_binary(keep_build: bool = False) -> Path:
    """Builds SoundFlow.exe using PyInstaller, copies to root, and cleans temporary artifacts."""
    print("=" * 60)
    print(">>> [1/3] Building SoundFlow.exe via PyInstaller...")
    print("=" * 60)

    # 1. Clean previous build artifacts and orphaned temp before compilation
    cleanup_temp_and_build(clean_build=True, clean_temp=True, clean_dist=False)

    # Stop any existing running instance
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/IM", "SoundFlow.exe"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
    except Exception:
        pass

    spec_path = PROJECT_ROOT / "SoundFlow.spec"
    if not spec_path.exists():
        raise FileNotFoundError(f"SoundFlow.spec not found at {spec_path}")

    cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--noconfirm", "--log-level", "WARN"]
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if res.returncode != 0:
        raise RuntimeError(f"PyInstaller build failed with exit code {res.returncode}")

    exe_path = PROJECT_ROOT / "dist" / "SoundFlow.exe"
    if not exe_path.exists():
        raise FileNotFoundError(f"dist/SoundFlow.exe not found at {exe_path}")

    # Copy binary to PROJECT_ROOT for direct execution
    root_exe = PROJECT_ROOT / "SoundFlow.exe"
    try:
        shutil.copy2(exe_path, root_exe)
        print(f"[SUCCESS] Copied executable to root: {root_exe}")
    except Exception as e:
        print(f"[WARNING] Could not copy {exe_path.name} to {root_exe}: {e}")

    # 2. Clean temporary build directory unless user explicitly asked to keep it
    if not keep_build:
        cleanup_temp_and_build(clean_build=True, clean_temp=True, clean_dist=False)

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[SUCCESS] Built: {exe_path.name} ({size_mb:.2f} MB)")
    return exe_path


def create_github_release(token: str, repo: str, tag: str, title: str, notes: str, draft: bool = False, prerelease: bool = False) -> dict:
    """Creates a new release on GitHub using REST API."""
    print(f"\n>>> [2/3] Creating GitHub Release {tag} on {repo}...")
    url = f"https://api.github.com/repos/{repo}/releases"
    payload = json.dumps({
        "tag_name": tag,
        "name": title,
        "body": notes,
        "draft": draft,
        "prerelease": prerelease,
        "generate_release_notes": not bool(notes)
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "SoundFlow-Publisher",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[SUCCESS] Release created: {data.get('html_url')}")
            return data
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        # If release already exists, fetch it
        if e.code == 422:
            print(f"[INFO] Release {tag} might already exist. Fetching existing release...")
            get_req = urllib.request.Request(
                f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "SoundFlow-Publisher",
                    "Accept": "application/vnd.github+json"
                }
            )
            with urllib.request.urlopen(get_req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        raise RuntimeError(f"GitHub API error {e.code}: {err}")


def upload_release_asset(token: str, upload_url: str, file_path: Path):
    """Uploads binary asset to the release."""
    print(f"\n>>> [3/3] Uploading {file_path.name} to release...")
    # upload_url format: https://uploads.github.com/repos/:owner/:repo/releases/:id/assets{?name,label}
    clean_upload_url = upload_url.split("{")[0]
    full_url = f"{clean_upload_url}?name={urllib.parse.quote(file_path.name)}"

    file_size = file_path.stat().st_size
    print(f"Uploading {file_path.name} ({file_size / 1024 / 1024:.2f} MB)...")

    with open(file_path, "rb") as f:
        file_data = f.read()

    req = urllib.request.Request(
        full_url,
        data=file_data,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "SoundFlow-Publisher",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/octet-stream",
            "Content-Length": str(file_size)
        }
    )

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            download_url = data.get("browser_download_url")
            print(f"[SUCCESS] Asset uploaded successfully!")
            print(f"Download URL: {download_url}")
            return data
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        raise RuntimeError(f"Failed to upload asset (HTTP {e.code}): {err}")


def main():
    parser = argparse.ArgumentParser(description="SoundFlow Automated Build & GitHub Release Publisher")
    parser.add_argument("--tag", default="v1.0.0", help="Git release tag (e.g. v1.0.0)")
    parser.add_argument("--title", default="", help="Release title (default: SoundFlow Studio <tag>)")
    parser.add_argument("--notes", default="", help="Release notes markdown content")
    parser.add_argument("--build-only", action="store_true", help="Only build binary without publishing to GitHub")
    parser.add_argument("--no-build", action="store_true", help="Skip build step and use existing dist/SoundFlow.exe")
    parser.add_argument("--push-tag", action="store_true", help="Also create and push local git tag to origin")
    parser.add_argument("--clean", action="store_true", help="Only clean temporary build files, dist, and OS temp debris without building")
    parser.add_argument("--keep-build", action="store_true", help="Do not delete intermediate build/ directory after compilation")
    args = parser.parse_args()

    if args.clean:
        cleanup_temp_and_build(clean_build=True, clean_temp=True, clean_dist=True)
        print("[DONE] Cleanup finished.")
        return

    tag = args.tag
    title = args.title or f"SoundFlow Studio {tag}"

    if not args.no_build:
        exe_path = build_binary(keep_build=args.keep_build)
    else:
        exe_path = PROJECT_ROOT / "dist" / "SoundFlow.exe"
        if not exe_path.exists():
            raise FileNotFoundError(f"Binary {exe_path} does not exist. Run without --no-build.")

    if args.build_only:
        print(f"\n[DONE] Build completed successfully at: {exe_path}")
        return

    # GitHub Publishing
    token = get_git_credential_token()
    if not token:
        print("[ERROR] GitHub token not found! Set GITHUB_TOKEN environment variable or configure git credential manager.")
        sys.exit(1)

    repo = get_git_remote_repo()
    print(f"Target Repository: {repo}")

    if args.push_tag:
        try:
            print(f"Tagging commit with {tag}...")
            subprocess.run(["git", "tag", "-a", tag, "-m", title], cwd=str(PROJECT_ROOT), check=False)
            print(f"Pushing tag {tag} to origin...")
            subprocess.run(["git", "push", "origin", tag], cwd=str(PROJECT_ROOT), check=False)
        except Exception as e:
            print(f"Tag push warning: {e}")

    notes = args.notes or (
        f"### SoundFlow Studio {tag}\n\n"
        f"#### Features & Improvements:\n"
        f"- **YouTube Recommendation Autoplay**: Seamless next video playback with dedicated 'Next Video' controls.\n"
        f"- **Acoustically Tuned Voice FX**: WSOLA phase-aligned granular pitch shifter eliminates metallic comb-filtering.\n"
        f"- **Butterworth LPF & Damped Echo**: Warm physical studio acoustics and realistic vocal tract models.\n"
        f"- **Modern Windows 11 Fluent UI**: Soundboard, real-time Voice Changer, Edge-TTS, and Virtual Mic Cable integration.\n\n"
        f"**Download `SoundFlow.exe` below to run immediately.**"
    )

    release_info = create_github_release(token, repo, tag, title, notes)
    upload_url = release_info.get("upload_url", "")
    if not upload_url:
        raise ValueError(f"No upload_url found in release response: {release_info}")

    upload_release_asset(token, upload_url, exe_path)

    print("\n" + "=" * 60)
    print(f">>> RELEASE PUBLISHED SUCCESSFULLY!")
    print(f"Release Page: {release_info.get('html_url')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
