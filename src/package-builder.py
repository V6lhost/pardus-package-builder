import argparse
import docker
import hashlib
import json
import os
import requests
import shutil
import sys
import subprocess
from pathlib import Path
from rich.prompt import Prompt, Confirm

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

        if self.source_subdir:
            self.recipe_export_full_path = self.source_dir / self.source_subdir / self.recipe_export_file
        else:
            self.recipe_export_full_path = self.source_dir / self.recipe_export_file
        
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
        self.recipe_export_file = build_recipe["export_file"]

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
    
    def open_application_with_path(self, mode: str = "bash", path: Path = None, use_cwd: bool = True, status_callback=None):
        # some programs needs to get directory as workingdir and some needs as parameters
        
        if status_callback is None:
            status_callback = self.status_callback

        open_path = self.source_dir
        if self.source_subdir:
            open_path.join(self.source_subdir)

        if path is not None:
            open_path = path

        try:
            if use_cwd:
                subprocess.run([mode], cwd=open_path.parent)
            else:
                subprocess.run([mode, open_path])
            return True

        except subprocess.CalledProcessError:
            return False
        
        except FileNotFoundError:
            status_callback({
                "status": "Program not found",
                "message": f"Program {mode} not found."
            })
            return False

    def clean_cache_and_source(self, status_callback=None):
        if status_callback is None:
            status_callback = self.status_callback
        
        shutil.rmtree(self.working_dir)
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self.source_dir.mkdir(exist_ok=True, parents=True)

    # Docker functions
    def initialize_container(self, image: str = "pardus/yirmibes", status_callback=None):
        
        if status_callback is None:
            status_callback = self.status_callback
        
        if self.source_subdir:
            source_path = self.source_dir / self.source_subdir
        else:
            source_path = self.source_dir

        status_callback({
            "status": "Starting container...",
            "message": f"Starting container with image: {image} volume: {source_path}"
        })

        try:
            self.docker_client = docker.from_env()

            volume_config = {
                str(source_path.resolve()): {
                    'bind': '/app/build',
                    'mode': 'rw'
                }
            }

            container = self.docker_client.containers.run(
                image=image,
                command="sleep infinity",
                detach=True,
                volumes=volume_config,
                auto_remove=True
            )

            self.container_id = container.id

            status_callback({
                "status": "Done",
                "message": f"Container started successfully. ID: {self.container_id}"
            })
            return True
        
        except Exception as e:
            status_callback({
                "status": "Failed",
                "message": f"Failed to start container: {e}"
            })
            return False
    
    def _exec_in_container(self, command: str, status_callback, stdout_callback, as_root: bool = False):
        user_str = "root" if as_root else f"{os.getuid()}:{os.getgid()}" # get current user permissions and run with them if as_root=False

        status_callback({
            "status": "Executing",
            "message": f"Running as [{user_str}]: {command}"
        })

        try:
            # get container id
            container = self.docker_client.containers.get(self.container_id)

            # run command inside container and send logs with stdout callback
            exec_log = container.exec_run(
                cmd=["bash", "-c", command],
                user=user_str,
                workdir="/app/build",
                stream=True,
                demux=False
            )

            # send logs
            for chunk in exec_log.output:
                if chunk:
                    line = chunk.decode("utf-8", errors="ignore").strip()
                    if line:
                        stdout_callback(line)

            return True

        except Exception as e:
            status_callback({
                "status": "Failed",
                "message": f"Execution failed: {e}"
            })
            return False

    def _install_dependecies(self, status_callback, stdout_callback=None):
        status_callback({
            "status": "Installing dependecies",
            "message": "Installing dependecies into container"
        })

        if not self.recipe_build_deps:
            status_callback({
                "status": "Passed",
                "message": "No build dependecies"
            })
            return True
        
        deps_list = " ".join(self.recipe_build_deps)
        command = f"export DEBIAN_FRONTEND=noninteractive && apt-get update && apt-get install -y {deps_list}"
        return self._exec_in_container(command, as_root=True, status_callback=status_callback, stdout_callback=stdout_callback)

    def _build_package(self, status_callback, stdout_callback=None):
        status_callback({
            "status": "Building...",
            "message": f"Building package {self.recipe_name} inside container"
        })

        return self._exec_in_container(command=self.recipe_build_cmd, status_callback=status_callback, stdout_callback=stdout_callback)

    def clean_source(self, status_callback, stdout_callback=None):
        status_callback({
            "status": "Cleaning...",
            "message": f"Cleaning the source directory"
        })

        if not self.recipe_clean_cmd:
            status_callback({
                "status": "Passed",
                "message": "No clean command specified"
            })
            return True

        return self._exec_in_container(command=self.recipe_clean_cmd, status_callback=status_callback, stdout_callback=stdout_callback)

    def stop_container(self, status_callback=None):
        if status_callback is None:
            status_callback = self.status_callback

        if hasattr(self, "container_id") and self.container_id:
            status_callback({
                "status": "Docker",
                "message": "Stopping and removing container..."
            })

            try:
                container = self.docker_client.containers.get(self.container_id)
                container.remove(force=True)
                
                self.container_id = None
                status_callback({
                    "status": "Done",
                    "message": "Container cleaned up successfully."
                })
                return True

            except Exception as e:
                status_callback({
                    "status": "Failed",
                    "message": f"Failed to stop container: {e}"
                })
                return False
        else:
            status_callback({
                "status": "Skipped",
                "message": "No active container to stop."
            })
            return True

    def run_build_process(self, status_callback=None, stdout_callback=None):
        if status_callback is None:
            status_callback = self.status_callback
        if stdout_callback is None:
            stdout_callback = lambda data: None
        if self._install_dependecies(status_callback=status_callback, stdout_callback=stdout_callback):
            if self._build_package(status_callback=status_callback, stdout_callback=stdout_callback):
                return True
            
        else:
            status_callback({
                "status": "Failed",
                "message": "Run build process failed"
            })
        return False

if __name__ == "__main__":    
    argparser = argparse.ArgumentParser(description="Pardus Automatized Unofficial Package Builder")
    argparser.add_argument("recipe", help="Build configuration recie (json)")
    argparser.add_argument("-p", "--no-prompt", action="store_true", help="Build package directly without interactive prompts")

    args = argparser.parse_args()
    edit_source_flag = args.no_prompt

    downloads_dir = subprocess.run( # Get download directory using xdg-user-dir command. localization will rename these directories so this is needed
            ["xdg-user-dir", "DOWNLOAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        ).stdout.strip()

    if edit_source_flag:
        print("Warning! build without interactive prompts selected. Build process will fail directly in case any errors.")

    package_builder = PackageBuilder(working_dir="/tmp/ppb", recipe=args.recipe, status_callback=print)

    if not package_builder.prepare_source(progress_callback=print):
        package_builder.clean_cache_and_source()
        sys.exit(1)

    if not package_builder.prepare_patches():
        package_builder.clean_cache_and_source()
        sys.exit(1)

    # Open given application inside source directory in case if you want to edit source before building
    if not edit_source_flag:
        open_source_dir = Confirm.ask("[bold Green]Do you want to open source directory before building?[/]", default=False)
        if open_source_dir:
            package_builder.open_application_with_path(mode="xdg-open", use_cwd=False)
            input("Press enter to continue")
    
    if not package_builder.initialize_container():
        package_builder.stop_container()
        package_builder.clean_cache_and_source()
        sys.exit(1)
    
    if not package_builder.run_build_process(stdout_callback=print):
        package_builder.stop_container()
        package_builder.clean_cache_and_source()
        sys.exit(1)
    
    package_builder.stop_container()
    
    install_app = Confirm.ask("[bold green]Do you want to install the package now? If you want to export the package, select 'n'. New prompt will ask you for exporting directory.[/]", default=True)
    if install_app:
        package_builder.open_application_with_path(mode="xdg-open", path=package_builder.recipe_export_full_path, use_cwd=False)
        package_builder.clean_cache_and_source()
        sys.exit(0)
    export_path = Prompt.ask("[bold orange]Please type package export path[/]", default=downloads_dir)
    if export_path:
        shutil.copy(src=str(package_builder.recipe_export_full_path), dst=str(export_path))

    package_builder.clean_cache_and_source()
    sys.exit(0)