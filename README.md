# Pardus Package Builder

**An automatized, recipe-driven `.deb` package builder for Pardus, using isolated Docker containers.**

> ⚠️ **Work in progress.** This project is unstable, actively force-pushed to, and its Git history may be rewritten at any time.

[🇹🇷 Türkçe README için tıklayın](README.tr.md)

![Status](https://img.shields.io/badge/status-work--in--progress-red.svg)
![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![Docker](https://img.shields.io/badge/build%20engine-Docker-2496ED.svg)
![Platform](https://img.shields.io/badge/platform-Pardus%20%2F%20Debian--based-orange.svg)

---

## About

**Pardus Package Builder** is a command-line tool that builds `.deb` packages from source, following a simple JSON **recipe** file — conceptually similar to `PKGBUILD`s in the AUR or `ebuild`s in Gentoo, but targeting Debian/Pardus packaging and running every build step inside a disposable **Docker container** for isolation and reproducibility.

Instead of installing build dependencies on your host system, the tool spins up a container (based on a Pardus image by default), downloads and verifies the source, applies any patches, installs only the dependencies that specific recipe needs, runs the build command, and then hands you back a ready-to-install `.deb` file — all while your host stays clean.

## How It Works

For a given recipe, the tool runs through this pipeline:

1. **Parse the recipe** — reads the JSON file describing what to build and how.
2. **Download the source** — fetches the source archive/file from the URL in the recipe.
3. **Verify integrity** — checks the downloaded file's SHA-256 hash against the one declared in the recipe.
4. **Cache** — successful downloads are cached under `~/.cache/pardus-package-builder`, so re-running a build won't re-download unchanged sources.
5. **Apply patches** (optional) — downloads and verifies any patches listed in the recipe, then applies them with `patch -p1`.
6. **Review source** (optional, interactive) — offers to open the extracted source directory in your file manager before building, so you can inspect or tweak it first.
7. **Start a Docker container** — launches a container from the specified image (defaults to `pardus/yirmibes`) with the source directory mounted as a volume.
8. **Install build dependencies** — runs `apt-get install` inside the container for the packages listed in the recipe.
9. **Run the build command** — executes the recipe's `build_cmd` inside the container, streaming output back to your terminal.
10. **Clean up** — runs the optional `clean_cmd`, then stops and removes the container.
11. **Install or export** — either opens the resulting `.deb` for direct installation, or asks where you'd like to save it.

## The Recipe Format

A recipe is a JSON file describing everything needed to reproduce a build:

```json
{
    "name": "Pardus System Services Manager",
    "version": "1.0.0",
    "build_deps": [
        "make", "binutils", "python3", "python3-venv", "dpkg",
        "libglib2.0-0", "libfontconfig1", "libfreetype6",
        "libxkbcommon0", "libx11-6", "libdbus-1-3",
        "libgssapi-krb5-2", "libbrotli1"
    ],
    "env_vars": [],
    "install": {
        "name": "pardus-system-services-manager.tar.gz",
        "url": "https://github.com/V6lhost/pardus-system-services-manager/tarball/2d00076",
        "sha256": "90dbe23cccd45c9fefbb59c831e50da626fbf9e210c9aa449c6fe28695e5a827",
        "type": "archive",
        "subdir": "V6lhost-pardus-system-services-manager-2d00076",
        "patches": [
            {
                "name": "patch1.patch",
                "url": "https://github.com/V6lhost/pardus-system-services-manager/commit/030e8c4d83ae9c1c75674b2b11ff88f550460791.patch",
                "sha256": "10ef27bd99238cdc199967891c3e68014c8a33552e80d2aece02f31c5d10dab0"
            }
        ]
    },
    "build_cmd": "make build",
    "clean_cmd": "make clean",
    "export_file": "output_deb/pardus-system-services-manager-1.0.0.deb"
}
```

| Field | Description |
|---|---|
| `name` | Human-readable package/project name |
| `version` | Version being built |
| `build_deps` | List of Debian/Pardus packages installed inside the build container before building |
| `env_vars` | Optional list of environment variables to set for the build |
| `install.name` | Filename the downloaded source is saved as |
| `install.url` | URL to download the source from |
| `install.sha256` | Expected SHA-256 checksum of the downloaded source |
| `install.type` | `"archive"` (extracted automatically) or a plain file |
| `install.subdir` | Subdirectory inside the extracted archive to build in (useful for GitHub tarballs, which nest content under a parent folder) |
| `install.patches` | Optional list of patches (each with its own `url` and `sha256`) applied before building |
| `build_cmd` | Shell command executed inside the container to build the package |
| `clean_cmd` | Optional shell command to clean up after the build |
| `export_file` | Path (relative to the build directory) to the resulting `.deb` file |

An example recipe is included at [`examples/test-pardus-system-services-manager.json`](examples/test-pardus-system-services-manager.json) — fittingly, it builds [pardus-system-services-manager](https://github.com/V6lhost/pardus-system-services-manager), another project by the same author.

## Requirements

- Python **3.11+**
- **Docker** (`docker.io`) — the build container engine
- `python3-docker`, `python3-rich` (installed automatically via `requirements.txt` / the `.deb` package)
- `xdg-user-dir` / `xdg-utils` — used to locate your Downloads folder and to open files/folders
- The `patch` utility inside the build container (add it to `build_deps` in your recipe if your build needs it)

## Installation

### Option 1 — Build and install the `.deb` package (recommended)

```bash
git clone https://github.com/V6lhost/pardus-package-builder.git
cd pardus-package-builder
make build
sudo dpkg -i output_deb/pardus-package-builder-*.deb
```

The package's post-install script will automatically add the user who ran `sudo` to the `docker` group (if the `docker` group exists), so the tool can talk to the Docker daemon without extra setup. **You'll need to log out and back in (or start a new shell session) for the group change to take effect.**

### Option 2 — Run from source (development)

```bash
git clone https://github.com/V6lhost/pardus-package-builder.git
cd pardus-package-builder
pip install -r requirements.txt
make run
```

### Cleaning build artifacts

```bash
make clean
```

## Usage

```bash
pardus-package-builder <recipe.json> [OPTIONS]
```

| Option | Description |
|---|---|
| `recipe` | Path to the JSON recipe file describing the build (required) |
| `-p`, `--no-prompt` | Build directly without interactive prompts (fails immediately on error instead of asking) |
| `-i`, `--install-directly` | Install the resulting package automatically without asking |

**Example:**

```bash
pardus-package-builder examples/test-pardus-system-services-manager.json
```

By default, the tool will interactively ask whether you want to inspect the source before building, and whether you want to install the resulting package or export it to a custom location afterward.

## Project Structure

```
pardus-package-builder/
├── debian/          # Debian packaging metadata, control file, postinst script, launcher
├── examples/         # Sample recipe files
├── src/              # Application source code (package-builder.py)
├── Makefile           # Build, run, and packaging automation
├── requirements.txt
└── LICENSE
```

## Security Notes

- A recipe's `build_cmd`, `clean_cmd`, and `build_deps` are executed as real shell commands **inside the build container** — treat recipe files the same way you'd treat a shell script from an untrusted source, and only run recipes you trust.
- Source archives and patches are integrity-checked against a SHA-256 hash declared in the recipe, but this only guarantees the file matches what the recipe *author* specified — it does not vouch for the recipe author's intentions.
- Builds run in a disposable container, isolating build dependencies from your host, but the build container does have your source directory mounted with read/write access.

## Contributing

Contributions, bug reports, and feature suggestions are welcome — keeping in mind this project is early-stage and evolving quickly.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Open a pull request describing what you changed and why

## License

This project is licensed under the **GNU General Public License v3.0**. See [`LICENSE`](LICENSE) for the full text.

## Disclaimer

This is an **unofficial, work-in-progress** tool, developed independently and not affiliated with, maintained by, or endorsed by TÜBİTAK or the official Pardus project. The `main` branch may be force-pushed and its history rewritten without notice. Use at your own discretion.


## Credits
- [Furkan Çolak](https://github.com/furkanclk3180) - Testing
- [topraklanbudev](https://github.com/Topraklanbudev) - Testing and motivation
- [ilgilenmek](https://github.com/keenon63) - Motivation