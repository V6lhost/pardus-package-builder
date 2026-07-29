import json
import argparse
import requests
from pathlib import Path
import hashlib
import shutil
import subprocess

sources_dir = Path("/tmp/ppb")
cache_dir = sources_dir / ".cache"
cache_dir.mkdir(exist_ok=True, parents=True)

def parse_config_json(file: Path):
    with open(file, "r") as f:
        data = json.load(f)
    return data

def download_file(url: str, target_path: Path, status_callback, progress_callback):
    temp_path = Path(str(target_path) + ".part")  # save as .part file until download finishes
    temp_path.touch()

    try:
        # stream=True downloads the file as chunks
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        # get total size from file header
        total_size = int(response.headers.get("content-length", 0))
        downloaded_size = 0
        chunk_size = 8192  # 8 KB per chunk

        status_callback({
            "status": "downloading",
            "message": f"Downloading: {url}",
            "size": total_size
            })

        with open(temp_path, "wb") as f:
            latest_percent = 0
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)

                    # calculate current progress
                    if total_size > 0:
                        percent = int((downloaded_size / total_size) * 100)
                        
                        # check if the percent is same as last percent before running callback
                        if percent != latest_percent:
                            latest_percent = percent
                            progress_callback({
                                "percentage": percent,
                                "downloaded_size": downloaded_size
                            })

        status_callback({
            "status": "Renaming",
            "message": "Download is done. Renaming the file..." 
        })

        # rename the file
        if target_path.exists():
            target_path.unlink()
        temp_path.rename(target_path)

        status_callback({
            "status": "done",
            "message": "Download successful"
        })

        return target_path

    except Exception as e:
        # clean the temporary files in case of error
        if temp_path.exists():
            temp_path.unlink()
        raise Exception(f"Error while downloading file: {e}")

def verify_sha256(file: Path, expected_sha256: str, status_callback):
    sha256_hash = hashlib.sha256()

    status_callback({
        "status": "calculating",
        "message": f"Calculating SHA256 of {file}, expected result is {expected_sha256}"
    })

    with open(file, "rb") as f:
        for byte_block in iter(lambda: f.read(8192), b""): # 8kb per block to avoid filling up ram
            sha256_hash.update(byte_block)
    
    calculated_hash = sha256_hash.hexdigest()

    if calculated_hash.lower() == expected_sha256.lower():
        status_callback({
            "status": "done",
            "message": f"sha256 verify of {file} is successful. Result is {calculated_hash}"
        })
        return True
    
    status_callback({
        "status": "failed",
        "message": f"sha256 checksum of {file} does not match with {expected_sha256}"
    })
    return False

def extract_archive(file: Path, extract_dir: Path, status_callback):
    extract_dir.mkdir(exist_ok=True, parents=True)

    status_callback({
        "status": "extracting",
        "message": f"extracting {file} to {extract_dir}..."
    })

    try:
        shutil.unpack_archive(str(file), str(extract_dir))
        status_callback({
            "status": "done",
            "message": "extracted successfully."
        })
        return True
    
    except Exception as e:
        raise Exception(f"Error while extracting archive {file}: {e}")

def apply_patch(patch_file: Path, target_dir: Path, status_callback):
    status_callback({
            "status": "Patching",
            "message": f"Applying patch {patch_file.name} to {target_dir}...",
        })

    try:
        command = ["patch", "-p1", "-i", str(patch_file.resolve())]
        status_callback(command)
        result = subprocess.run(
            command,
            cwd=str(target_dir.resolve()),
            capture_output=True,
            text=True,
            check=True,
        )

        status_callback({
            "status": "Done",
            "message": "Patch applied successfully."
        })
        return True

    except subprocess.CalledProcessError as e:
        status_callback({
                "status": "Failed",
                "message": f"Failed to apply patch {patch_file} to {target_dir}.: {e}"
        })
    except FileNotFoundError:
        raise Exception(
            "The 'patch' command is not installed on the system. Please install it."
        )

if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Pardus Automatized Unofficial Package Builder")
    argparser.add_argument("config", help="Build configuration file (json)")
    argparser.add_argument("-p", "--no-prompt", action="store_true", help="Build package directly without interactive prompts")

    args = argparser.parse_args()
    edit_source_flag = args.no_prompt
    build_configuration = parse_config_json(args.config)
    
