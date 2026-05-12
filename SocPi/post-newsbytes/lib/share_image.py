"""Share-image wrapper — the narrow target for the Bash permission rule.

The skill needs to:
  1. Set anyone-with-link reader permission on the row's source image
     (already in the team's Drive folder).
  2. Upload the IG-resized image to the staging Shared Drive folder.
  3. Set anyone-with-link reader permission on the staged copy.
  4. Write both public URLs back to cache/row-<N>.json.

All of these are Drive write operations that the harness flags for
permission. By isolating them to this one script (rather than inlining
the heredoc into run.py), the user can whitelist exactly:

    Bash(python ~/.claude/post-newsbytes/lib/share_image.py *)

…and the rest of run.py stays free of write-side Drive calls.

Usage:
    python lib/share_image.py --row N
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make sibling modules importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import auth, drive as drive_mod  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(prog="share_image.py")
    parser.add_argument("--row", type=int, required=True, help="Sheet row number whose cache to update")
    args = parser.parse_args()

    secrets = auth.load_secrets()
    cache_path = auth.cache_dir() / f"row-{args.row}.json"
    if not cache_path.exists():
        print(f"row cache not found: {cache_path}. Run `collect` and `fetch-doc` first.", file=sys.stderr)
        return 2
    cached = json.loads(cache_path.read_text(encoding="utf-8"))

    source_image_id = cached.get("drive_image_id") or ""
    ig_local = cached.get("image_path_ig") or ""
    staging_folder = secrets.get("image_staging_folder_id") or ""

    if not source_image_id and not ig_local:
        print("[share-image] no image data in row cache — caption-only post.")
        return 0

    drive_api = drive_mod.build_drive_api(secrets, full_scope=True)

    # 1. Share the source image (in the team's folder) anyone-with-link.
    if source_image_id:
        drive_mod.share_anyone_with_link(drive_api, source_image_id)
        cached["public_image_url"] = drive_mod.public_url(source_image_id)
        print(f"[share-image] source image shared: {cached['public_image_url']}")

    # 2. Upload IG-resized image to staging Shared Drive folder.
    if ig_local and Path(ig_local).exists():
        if not staging_folder:
            print("[share-image] no image_staging_folder_id in secrets — falling back to source image for IG.")
            cached["public_image_url_ig"] = cached.get("public_image_url", "")
        else:
            target_name = f"row-{args.row}-ig.jpg"
            try:
                staged_id = drive_mod.upload_to_staging(drive_api, Path(ig_local), staging_folder, name=target_name)
                drive_mod.share_anyone_with_link(drive_api, staged_id)
                cached["drive_image_id_ig"] = staged_id
                cached["public_image_url_ig"] = drive_mod.public_url(staged_id)
                print(f"[share-image] IG-resized image staged: {cached['public_image_url_ig']}")
            except Exception as exc:
                msg = str(exc)
                if "storageQuotaExceeded" in msg or "storage quota" in msg.lower():
                    print(
                        "[share-image] WARNING: image_staging_folder_id is not a Shared Drive — "
                        "service accounts have zero personal-Drive quota. See INSTALL.md Step 4b. "
                        "Falling back to source image for IG."
                    )
                else:
                    print(f"[share-image] WARNING: IG-staging upload failed ({type(exc).__name__}): {exc}. "
                          "Falling back to source image for IG.")
                cached["public_image_url_ig"] = cached.get("public_image_url", "")
                cached["ig_staging_fallback"] = True
    else:
        cached["public_image_url_ig"] = cached.get("public_image_url", "")

    cache_path.write_text(json.dumps(cached, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote: {cache_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
