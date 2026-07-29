import json
import argparse
import requests
from pathlib import Path

cache_dir = Path("/tmp/ppb/.cache")
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

if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Pardus Automatized Unofficial Package Builder")
    argparser.add_argument("config", help="Build configuration file (json)")
    argparser.add_argument("-p", "--no-prompt", action="store_true", help="Build package directly without interactive prompts")

    args = argparser.parse_args()
    edit_source_flag = args.no_prompt
    build_configuration = parse_config_json(args.config)
    for resource in build_configuration["install"]:
        download_file(resource["url"], cache_dir / resource["name"], print, print)

