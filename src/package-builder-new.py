import argparse
# import docker
import hashlib
import json
import os
import requests
import shutil
import subprocess
from pathlib import Path
from rich.prompt import Confirm

class PackageBuilder:
    def __init__(self, working_dir: Path, recipe: Path, status_callback=print):
        self._parse_recipe(recipe_file=recipe, status_callback=status_callback)
        self._configure_working_dir(working_dir, status_callback)
        self.status_callback = status_callback

    def _configure_working_dir(self, working_dir: str, status_callback):
        self.working_dir = Path(working_dir)
        self.project_dir = Path(working_dir) / self.recipe_name.replace(" ", "-")
        self.source_dir = self.project_dir / "source"
        self.cache_dir = self.project_dir / "cache"

        # Create directories
        self.source_dir.mkdir(exist_ok=True, parents=True)
        self.cache_dir.mkdir(exist_ok=True)
        self.download_path =  self.cache_dir / self.recipe_install["name"]
        
        status_callback({
            "status": "Working directory initialized",
            "message": f"Project directory: {self.project_dir}"
        })

    def _parse_recipe(self, recipe_file: Path, status_callback):
        with open(recipe_file, "r") as f:
            build_recipe = json.load(f)
        
        self.recipe_name = build_recipe["name"]
        self.recipe_version = build_recipe["version"]
        self.recipe_build_deps = build_recipe["build_deps"]
        self.recipe_env_vars = build_recipe.get("env_vars")
        self.recipe_install = build_recipe["install"]
        self.recipe_build_cmd = build_recipe["build_cmd"]
        self.recipe_clean_cmd = build_recipe.get("clean_cmd")
        self.recipe_export_files = build_recipe["export_files"]

        self.source_subdir = self.recipe_install.get("subdir") # project archives which created by git includes a parent directory which needs to apply patches in it
        
        status_callback({
            "status": "Initialized",
            "message": f"Recipe {recipe_file} parsed succesfully. Building Package: {self.recipe_name} {self.recipe_version}"
        })

    def _download_file(self, url: str, destination: Path, status_callback, progress_callback):
        temporary_download_path = Path(str(destination) + ".part")
        temporary_download_path.touch() # Write function wants a file even if its empty

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get("content-length", 0))
            downloaded_size = 0
            chunk_size = 8192

            status_callback({
                "status": "Downloading...",
                "message": f"Downloading: {url}",
                "size": total_size
            })

            with open(temporary_download_path, "wb") as f:
                latest_percent = 0
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)

                        if total_size > 0:
                            percent = int((downloaded_size / total_size) * 100)

                            if percent != latest_percent:
                                latest_percent = percent
                                progress_callback({
                                    "percentage": percent,
                                    "downloaded": downloaded_size
                                })
            
            status_callback({
                "status": "Renaming...",
                "message": "Download is done. Renaming the file..."
            })

            temporary_download_path.rename(destination)

            status_callback({
                "status": "Done",
                "message": f"Download successful. File {destination} is downloaded"
            })
            return True
            
        except Exception as e:
            if temporary_download_path.exists():
                temporary_download_path.unlink()

            status_callback({
                "status": "Failed",
                "message": f"Download failed: {e}"
            })
            return False

    def prepare_source(self, progress_callback, status_callback=None):
        
        if status_callback is None:
            status_callback = self.status_callback

        expected_sha256 = self.recipe_install["sha256"]
        
        if self.source_dir.exists():
            shutil.rmtree(self.source_dir)
        self.source_dir.mkdir(exist_ok=True, parents=True)
        
        # Check the cache for past downloads
        if not self._is_cached_and_valid(file=self.download_path, expected_sha256=expected_sha256, status_callback=status_callback):
            download_result = self._download_file(url=self.recipe_install["url"], destination=self.download_path, status_callback=status_callback, progress_callback=progress_callback)
            if not download_result:
                return False

        verify_result = self._verify_sha256(file=self.download_path, expected_sha256=expected_sha256, status_callback=status_callback)
        if verify_result:
            if self.recipe_install["type"] == "archive":
                extract_result = self._extract_archive(status_callback=status_callback)
                if extract_result:
                    return True
            else:
                shutil.copy2(src=self.download_path, dst=self.source_dir)
                return True
        return False

    def prepare_patches(self, status_callback=None):
        
        if status_callback is None:
            status_callback = self.status_callback

        patches= self.recipe_install.get("patches")
        if patches:
            for patch in patches:
                patch_download_path = self.cache_dir / patch["name"]
                patch_expected_sha256 = patch["sha256"]

                # Check the cache for past downloads
                if not self._is_cached_and_valid(file=patch_download_path, expected_sha256=patch_expected_sha256, status_callback=status_callback):
                    download_result = self._download_file(url=patch["url"], destination=patch_download_path, status_callback=status_callback, progress_callback=lambda data: None) # Create a dummy function with lambda. patch files are generally so smal that progress callback is not even needed. status is enough
                    if not download_result:
                        return False
                
                if self.source_subdir:
                    patch_destination = self.source_dir / self.source_subdir
                else:
                    patch_destination = self.source_dir
                
                patch_result = self.apply_patch(file=patch_download_path, destination=patch_destination, status_callback=status_callback)
                if not patch_result:
                    return False
        return True

    def _verify_sha256(self, file: Path, expected_sha256: str, status_callback):
        sha256_hash = hashlib.sha256()

        status_callback({
            "status": "Calculating...",
            "message": f"Calculating SHA-256 of {file}, expected result: {expected_sha256}"
        })

        with open(file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        
        calculated_sha256 = sha256_hash.hexdigest()

        if calculated_sha256.lower() == expected_sha256.lower():
            status_callback({
                "status": "Done",
                "message": f"SHA-256 checksum of {file} match."
            })
            return True
        
        status_callback({
            "status": "Failed",
            "message": f"SHA-256 checksum of {file} does not match with expected. Calculated: {calculated_sha256} Expected: {expected_sha256}"
        })
        return False

    def _is_cached_and_valid(self, file: Path, expected_sha256: str, status_callback):
        if file.exists():
            status_callback({
                "status": "Found on cache",
                "message": f"{file.name} found on cache, checking SHA-256..."
            })

            verify_result = self._verify_sha256(file, expected_sha256=expected_sha256, status_callback=status_callback)

            if verify_result:
                status_callback({
                    "status": "Done",
                    "message": "Verify SHA-256 successful, passing download..."
                })
                return True
            
            status_callback({
                "status": "Failed",
                "message": "Verify SHA-256 failed. Downloading..."
            })

    def _extract_archive(self, status_callback):
        source_archive = self.download_path
        status_callback({
            "status": "Extracting...",
            "message": f"Extracting {source_archive} to {self.source_dir}"
        })

        try:
            shutil.unpack_archive(str(source_archive), str(self.source_dir))
            status_callback({
                "status": "Done",
                "message": "Extracted succesfully."
            })
            return True
        
        except Exception as e:
            status_callback({
                "status": "Failed",
                "message": f"Extraction failed: {e}"
            })
            return False
    
    def apply_patch(self, file: Path, destination: Path, status_callback=None):

        if status_callback is None:
            status_callback = self.status_callback
        status_callback({
            "status": "Patching...",
            "message": f"Applying patch {file.name} to {destination.name}"  
        })

        try:
            command = ["patch", "-p1", "-i", str(file.resolve())]
            result = subprocess.run(
                command,
                cwd=str(destination.resolve()),
                capture_output=True,
                text=True,
                check=True
            )

            status_callback({
                "status": "Done",
                "message": "Patch applied succesfully."
            })
            return True
        
        except subprocess.CalledProcessError as e:
            status_callback({
                "status": "Failed",
                "message": f"Apply patch failed: {e.stderr}"
            })
            return False
    
    def open_source_dir(self, mode: str = "bash", use_cwd: bool = True, status_callback=None):
        
        if status_callback is None:
            status_callback = self.status_callback

        # some programs needs to get directory as workingdir and some needs as parameters
        if self.source_subdir:
            source_dir = self.source_dir / self.source_subdir
        else:
            source_dir = self.source_dir

        try:
            if use_cwd:
                subprocess.run([mode], cwd=source_dir)
            else:
                subprocess.run([mode, source_dir])
            return True

        except subprocess.CalledProcessError:
            return False
        
        except FileNotFoundError:
            status_callback({
                "status": "Program not found",
                "message": f"Program {mode} not found."
            })
            return False

if __name__ == "__main__":    
    argparser = argparse.ArgumentParser(description="Pardus Automatized Unofficial Package Builder")
    argparser.add_argument("recipe", help="Build configuration recie (json)")
    argparser.add_argument("-p", "--no-prompt", action="store_true", help="Build package directly without interactive prompts")

    args = argparser.parse_args()
    edit_source_flag = args.no_prompt

    if edit_source_flag:
        print("Warning! build without interactive prompts selected. Build process will fail directly in case any errors.")

    package_builder = PackageBuilder(working_dir="/tmp/ppb", recipe=args.recipe, status_callback=print)

    package_builder.prepare_source(progress_callback=print)
    patch_result = package_builder.prepare_patches()

    # Open a terminal inside source directory in case if an error happens while doing patches.
    if not edit_source_flag:
        if not patch_result:
            package_builder.open_source_dir(mode="xdg-open", use_cwd=False)
