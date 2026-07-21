# Task: Stabilize Ubuntu 20.04 Packaging for Video Event Logger

## 1. Objective

Refactor and stabilize the Linux packaging workflow for **Video Event Logger** so that it produces a reproducible, installable, and debuggable application package for:

- **Ubuntu 20.04**
- **Architecture: `linux/amd64` / `x86_64`**

Ubuntu 20.04 is the only mandatory target for this task.

Compatibility with Ubuntu 22.04 and Ubuntu 24.04 is desirable, but it must not influence or weaken the Ubuntu 20.04 implementation. Do not introduce separate builds for newer Ubuntu versions in this task.

The package must be built inside an Ubuntu 20.04 Docker image and must not require Python to be installed on the target machine.

The application uses:

- Python 3.12.4
- PySide6
- `python-vlc`
- PyInstaller
- system-installed VLC/libVLC

The final application should use the VLC installation from the target Ubuntu system rather than bundle VLC libraries and plugins inside the PyInstaller package.

---

## 2. Current Problems

The current package does not start on Ubuntu 20.04.

Possible causes include:

1. Unpinned PySide6 version may resolve to a wheel requiring a newer glibc than Ubuntu 20.04 provides.
2. Native libraries bundled by PyInstaller may be incompatible with Ubuntu 20.04.
3. PyInstaller may accidentally include parts of the system VLC installation.
4. The launcher modifies `LD_LIBRARY_PATH`, which may cause Qt, VLC, Mesa, X11, or C++ runtime libraries to be loaded from incorrect locations.
5. Production builds use `console=False`, hiding startup errors.
6. The current build script responsibilities may be mixed between the host and the Docker container.
7. The package does not perform automated validation of architecture, glibc requirements, missing shared libraries, Qt plugins, or VLC availability.
8. Dependency versions are not reproducible because the application requirements use broad `>=` constraints.

---

## 3. Current Relevant Files

The implementation should inspect and update the existing packaging files rather than create a parallel unused packaging system.

Expected relevant files:

```text
requirements.txt
video_event_logger.spec
packaging/ubuntu_20_04/Dockerfile
packaging/ubuntu_20_04/build.sh
packaging/ubuntu_20_04/create_release_archive.sh
packaging/ubuntu_20_04/install_release.sh
video_event_logger/main.py
video_event_logger/app_config.py
```

File names may differ slightly in the repository. Reuse the existing structure where reasonable.

---

## 4. Scope

### In scope

- Reproducible dependency versions.
- Ubuntu 20.04 `linux/amd64` Docker build.
- Correct Python 3.12.4 compilation with shared-library support.
- PyInstaller `onedir` package.
- System VLC integration.
- Safe launcher environment.
- Debug and release build modes.
- Automated package validation.
- Improved installation diagnostics.
- Release archive creation.
- Documentation for building, installing, debugging, and testing the package.

### Out of scope

- macOS packaging.
- Windows packaging.
- ARM64 Linux packages.
- Ubuntu 22.04-specific or Ubuntu 24.04-specific build images.
- AppImage.
- Snap.
- Flatpak.
- Automatic application updates.
- Code signing.
- Bundling VLC or its plugin directory into the release.
- Replacing PyInstaller with another packaging framework.
- Changing application functionality unrelated to startup and packaging.
- Creating a `.deb` package unless it is already partially implemented in the repository.

A `.deb` package may be mentioned as a future improvement, but the required artifact for this task remains the existing release archive workflow.

---

## 5. Required Dependency Changes

### 5.1 Pin runtime dependencies

Replace broad runtime constraints such as:

```text
PySide6>=6.5
python-vlc>=3.0
```

with exact tested versions.

Use the following initial versions unless repository constraints prove that they are incompatible:

```text
PySide6==6.7.3
python-vlc==3.0.21203
```

PySide6 must remain compatible with:

- Python 3.12
- Ubuntu 20.04 glibc 2.31
- `linux/amd64`

Do not upgrade PySide6 to a wheel with a glibc baseline newer than Ubuntu 20.04.

### 5.2 Pin build dependencies

Create or update a separate build requirements file, for example:

```text
requirements-build.txt
```

It should include the application requirements and an exact PyInstaller version:

```text
-r requirements.txt
PyInstaller==6.14.2
```

If the repository already separates production and development dependencies, integrate this requirement into the existing structure instead of duplicating it.

### 5.3 Record resolved versions

The build process must write the resolved dependency list into the release metadata or build logs:

```bash
python -m pip freeze
```

The generated package should include a text file such as:

```text
BUILD_INFO.txt
```

It should contain at least:

- application version;
- build date in UTC;
- target platform;
- target architecture;
- Ubuntu base version;
- Python version;
- PyInstaller version;
- PySide6 version;
- `python-vlc` version;
- Git commit hash when Git metadata is available.

Failure to obtain the Git commit hash must not fail the build.

---

## 6. Docker Build Requirements

## 6.1 Base image

Continue using:

```dockerfile
FROM ubuntu:20.04
```

The resulting image must be explicitly built for:

```text
linux/amd64
```

Do not rely on the host architecture, especially when building on Apple Silicon.

The host build command must include:

```bash
docker build --platform linux/amd64 ...
```

The container run command must include:

```bash
docker run --platform linux/amd64 ...
```

### 6.2 Architecture validation

The Docker build must fail early unless all of the following are true:

```text
uname -m == x86_64
dpkg --print-architecture == amd64
```

Example validation:

```bash
test "$(uname -m)" = "x86_64"
test "$(dpkg --print-architecture)" = "amd64"
```

After PyInstaller finishes, validate the generated executable with `file`.

The executable must be identified as an x86-64 ELF binary.

### 6.3 Python compilation

Continue compiling Python 3.12.4 from source inside Ubuntu 20.04.

Required configure options:

```bash
./configure \
  --enable-shared \
  --enable-optimizations \
  --with-ensurepip=install
```

The Docker build must verify:

```bash
python3.12 --version
ldd "$(command -v python3.12)"
ldconfig -p | grep libpython3.12
```

No dependency reported by `ldd` may contain:

```text
not found
```

Register `/usr/local/lib` through `ldconfig`.

Do not copy a Python installation from a newer Ubuntu image or another build stage with a newer glibc.

### 6.4 Required diagnostic packages

The build image should contain tools required for validation:

```text
binutils
file
patchelf
```

Keep other currently required compiler and Python development packages.

### 6.5 VLC in the builder

VLC may remain installed in the Docker builder because the application imports and analyzes `python-vlc`.

However, system VLC binaries, libVLC libraries, and VLC plugins must not be distributed in the final PyInstaller package.

---

## 7. Separate Host and Container Build Responsibilities

The packaging workflow must have a clear split.

### Host-side script

The host-side script may:

- read the application version;
- create the release output directory;
- build the Docker image;
- run the Docker container;
- mount the release directory;
- print the resulting archive path.

The host-side script must not execute PyInstaller directly.

Suggested name:

```text
packaging/ubuntu_20_04/build_release.sh
```

The existing `build.sh` may keep its name if it is already used externally, but its role must be unambiguous.

### Container-side script

Create or clearly identify a separate script that runs only inside the Docker container.

Suggested name:

```text
packaging/ubuntu_20_04/build_in_container.sh
```

It must:

1. create a temporary virtual environment;
2. upgrade packaging tooling to pinned or controlled versions;
3. install build requirements;
4. print resolved dependency versions;
5. clean previous PyInstaller output;
6. build the application;
7. run package validation;
8. create release metadata;
9. create the release archive.

The container-side script must never call:

```text
docker build
docker run
docker compose
```

The Dockerfile `CMD` must invoke the container-side script, not the host-side Docker orchestration script.

---

## 8. PyInstaller Specification Changes

Continue using a PyInstaller `onedir` build.

Do not switch to `onefile` during this task.

### 8.1 Exclude system libraries

After creating `Analysis`, call:

```python
a.exclude_system_libraries()
```

The goal is to avoid bundling arbitrary libraries from:

```text
/lib
/lib64
/usr/lib
/usr/lib64
```

PySide6 libraries installed inside the Python environment must remain included.

After the build, explicitly verify that the output does not contain:

```text
libvlc.so
libvlc.so.5
libvlccore.so
libvlccore.so.*
vlc/plugins
```

If PyInstaller still includes these files, remove them from the collected binaries through an explicit filtering step in the `.spec` file.

Do not blindly remove every library with `vlc` in its name without first confirming that it belongs to the system VLC runtime.

### 8.2 Keep VLC Python import

Retain:

```python
hiddenimports=["vlc"]
```

unless PyInstaller's current hook resolves it correctly and a test proves the explicit hidden import is unnecessary.

Keeping it is acceptable.

### 8.3 Application assets

Ensure the application icon remains included at:

```text
video_event_logger/assets/app_icon.svg
```

Verify that the runtime application resolves the asset relative to the PyInstaller bundle correctly.

### 8.4 Debug and release modes

Support two packaging modes.

#### Debug mode

Debug mode must use:

```python
console=True
debug=True
```

It should preserve stdout and stderr for diagnosing startup failures.

#### Release mode

Release mode may use:

```python
console=False
debug=False
```

The release launcher must redirect stdout and stderr to a persistent log file.

The mode may be selected using an environment variable such as:

```text
BUILD_MODE=debug
BUILD_MODE=release
```

Avoid maintaining two largely duplicated `.spec` files. Prefer conditional configuration in one spec file or a small shared configuration layer.

### 8.5 PyInstaller output cleanup

Before every build, delete stale build outputs:

```text
build/
dist/
```

Do not allow files from an older PyInstaller run to leak into the current release.

---

## 9. Launcher Requirements

The installed application must be started through a launcher script.

### 9.1 Do not override `LD_LIBRARY_PATH`

Remove logic that prepends the complete architecture library directory:

```bash
export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu:..."
```

Do not set a global `LD_LIBRARY_PATH` for the application.

Standard Ubuntu library locations are already handled by the dynamic linker. Overriding them may cause incompatible Qt, Mesa, VLC, X11, or C++ runtime libraries to be loaded.

### 9.2 Locate system libVLC

The launcher should detect `libvlc.so.5` in known Ubuntu architecture-specific locations.

For the mandatory target, prioritize:

```text
/usr/lib/x86_64-linux-gnu/libvlc.so.5
/usr/lib/x86_64-linux-gnu/vlc/plugins
```

Fallback paths for other architectures are unnecessary in this task because only `linux/amd64` is supported.

Set only the VLC-specific environment variables needed by `python-vlc`, for example:

```bash
export PYTHON_VLC_LIB_PATH="/usr/lib/x86_64-linux-gnu/libvlc.so.5"
export VLC_PLUGIN_PATH="/usr/lib/x86_64-linux-gnu/vlc/plugins"
```

Do not set `PYTHON_VLC_MODULE_PATH` unless the application demonstrably requires it. Document the reason if it is retained.

### 9.3 Fail clearly when VLC is missing

VLC is a required runtime dependency, not an optional warning.

The installer or launcher must stop with a clear error when VLC/libVLC is unavailable.

The message must include the installation command:

```bash
sudo apt update
sudo apt install vlc
```

Check both:

```bash
command -v vlc
```

and:

```text
/usr/lib/x86_64-linux-gnu/libvlc.so.5
```

A `vlc` executable alone is not enough if libVLC cannot be loaded.

### 9.4 Persistent logs

Create a log directory using:

```text
${XDG_STATE_HOME:-$HOME/.local/state}/video-event-logger
```

The release launcher must append stdout and stderr to:

```text
application.log
```

The application log must remain available when the application is launched through the Ubuntu application menu.

Use log rotation only if the repository already has a logging solution. Otherwise, a single append-only file is acceptable for this task.

### 9.5 Qt debugging

Support optional Qt plugin diagnostics without editing the launcher.

For example, users must be able to run:

```bash
QT_DEBUG_PLUGINS=1 ~/.local/opt/video-event-logger/video-event-logger-launcher
```

Do not force `QT_DEBUG_PLUGINS=1` during normal startup.

---

## 10. Installer Requirements

Continue supporting user-local installation without `sudo`.

Default installation locations:

```text
Application:
$HOME/.local/opt/video-event-logger

Desktop entry:
${XDG_DATA_HOME:-$HOME/.local/share}/applications/video-event-logger.desktop
```

### Required behavior

The installer must:

1. verify that the packaged executable exists and is executable;
2. verify that the target architecture is `x86_64`;
3. verify that VLC and libVLC are installed;
4. reject unsafe installation paths such as an empty path or `/`;
5. replace an older user-local installation safely;
6. create the desktop entry;
7. preserve the application icon;
8. create the log directory;
9. update the desktop database when available;
10. print the installed launcher path;
11. print the application log path;
12. print a terminal command for manually starting the application.

Example final output:

```text
Video Event Logger installed.

Launcher:
  ~/.local/opt/video-event-logger/video-event-logger-launcher

Application log:
  ~/.local/state/video-event-logger/application.log

Manual start:
  ~/.local/opt/video-event-logger/video-event-logger-launcher
```

Do not silently continue when VLC is missing.

### Desktop entry

The desktop entry should keep:

```ini
Terminal=false
Type=Application
Categories=AudioVideo;Video;Utility;
StartupNotify=true
```

`Exec`, `Path`, and `Icon` must use valid absolute paths generated by the installer.

---

## 11. Automated Validation Script

Create a validation script, for example:

```text
packaging/ubuntu_20_04/validate_build.sh
```

Run it automatically after PyInstaller and before creating the release archive.

The script must fail the build when a mandatory check fails.

### 11.1 Architecture check

Validate:

```bash
file dist/video-event-logger/video-event-logger
```

The result must indicate:

```text
ELF 64-bit
x86-64
```

### 11.2 Missing shared libraries

Run `ldd` against:

- the main executable;
- every ELF executable and shared object inside the PyInstaller output.

Fail if any output contains:

```text
not found
```

The script must skip non-ELF files safely.

### 11.3 glibc compatibility

Inspect all ELF files using `objdump`.

The package must not require a glibc symbol newer than:

```text
GLIBC_2.31
```

Fail the build if any file requires:

```text
GLIBC_2.32
GLIBC_2.33
GLIBC_2.34
```

or any later version.

When failing, print every offending file and the unsupported GLIBC versions it requires.

Do not only print the global maximum version; identify the files responsible.

### 11.4 Excluded VLC files

Fail if the release contains system VLC runtime files or plugin directories, including:

```text
libvlc.so*
libvlccore.so*
*/vlc/plugins/*
```

The application must use target-system VLC.

### 11.5 Qt platform plugin

Verify that the PySide6 Qt `xcb` platform plugin exists in the package.

Locate:

```text
libqxcb.so
```

Run `ldd` against it and fail if any dependency is missing.

The validation script should print the resolved path to `libqxcb.so`.

### 11.6 Python runtime

Verify that the package contains the expected Python runtime artifacts required by PyInstaller.

The validation must not assume the target machine has Python installed.

### 11.7 Smoke import test inside the builder

Before PyInstaller packaging, run:

```bash
python -c "import PySide6; import vlc; print(PySide6.__version__)"
```

Also call a minimal `python-vlc` function that does not require starting video playback, for example retrieving the wrapper or libVLC version.

This test may use the builder's system VLC.

### 11.8 Build metadata

Verify that `BUILD_INFO.txt` exists in the release directory and contains the mandatory fields.

---

## 12. Runtime Smoke Test

Add a lightweight application smoke-test mode.

Preferred interface:

```bash
video-event-logger --smoke-test
```

The smoke test should:

1. initialize the minimum required Qt application state;
2. verify that the application can import its internal modules;
3. verify that the configured icon exists;
4. verify that `python-vlc` can load system libVLC;
5. retrieve and print the libVLC version;
6. exit without opening the full GUI;
7. return exit code `0` on success;
8. return a non-zero exit code with a clear error on failure.

The smoke test must not require:

- a video file;
- user interaction;
- audio playback;
- network access.

If adding a CLI argument to the application would require excessive unrelated refactoring, create a small dedicated smoke-test entry point. However, prefer a real application argument because it validates more of the actual startup path.

The release validation process should execute the smoke test in an Ubuntu 20.04 environment with VLC installed.

---

## 13. Ubuntu 20.04 Test Environment

The final package must be tested in a clean Ubuntu 20.04 `x86_64` environment.

Acceptable environments:

- clean virtual machine;
- disposable cloud VM;
- clean Docker container with GUI/X11 support where practical;
- CI runner based on Ubuntu 20.04.

A plain Docker container is acceptable for binary and smoke checks, but final GUI startup should be verified in a real Ubuntu 20.04 graphical session or equivalent VM.

### Mandatory test cases

#### Test 1: Clean installation

1. Install VLC.
2. Extract the release archive.
3. Run `install_release.sh`.
4. Start the application from the terminal.
5. Start the application from the Ubuntu application menu.

Expected result:

- application starts;
- no Python installation is required;
- no missing-library error occurs;
- the main window is displayed;
- application log is created.

#### Test 2: Missing VLC

1. Use an Ubuntu 20.04 environment without VLC.
2. Run `install_release.sh`.

Expected result:

- installation fails clearly;
- the exact VLC installation command is printed;
- no broken desktop entry is created.

#### Test 3: Manual launcher

Run:

```bash
~/.local/opt/video-event-logger/video-event-logger-launcher
```

Expected result:

- application starts;
- logs are written to the XDG state directory.

#### Test 4: Smoke test

Run the packaged smoke-test mode.

Expected result:

- Qt initializes;
- libVLC is loaded from the target system;
- libVLC version is printed;
- process exits with code `0`.

#### Test 5: Qt diagnostics

Run:

```bash
QT_DEBUG_PLUGINS=1 ~/.local/opt/video-event-logger/video-event-logger-launcher
```

Expected result:

- Qt finds the bundled `xcb` platform plugin;
- no missing dependency is reported for `libqxcb.so`.

#### Test 6: Video playback

Open a supported local video and verify:

- video initializes;
- playback starts;
- seek works;
- pause/resume works;
- application does not crash when closing the video or application.

Use at least one common H.264 MP4 file.

#### Test 7: Reinstallation

Install the same release twice.

Expected result:

- the second installation replaces the previous files safely;
- no duplicate desktop entries are created;
- user-generated application data outside the installation directory is not deleted.

---

## 14. Build Documentation

Create or update a packaging README, for example:

```text
packaging/ubuntu_20_04/README.md
```

It must document:

### Build prerequisites on the host

- Docker with `buildx`;
- ability to run `linux/amd64` containers;
- disk space requirements;
- Apple Silicon emulation note.

### Build command

Document the exact host-side command, for example:

```bash
bash packaging/ubuntu_20_04/build_release.sh
```

### Debug build

Document how to produce a debug package:

```bash
BUILD_MODE=debug bash packaging/ubuntu_20_04/build_release.sh
```

### Release output

Document where the archive is created.

### Installation

Document:

```bash
tar -xzf <release>.tar.gz
cd <release>
sudo apt update
sudo apt install vlc
bash install_release.sh
```

### Manual start

Document the launcher path.

### Logs

Document the application log path.

### Diagnostics

Include commands for:

```bash
file
ldd
objdump
QT_DEBUG_PLUGINS=1
```

### Supported platform

State explicitly:

```text
Supported target: Ubuntu 20.04 x86_64
```

Do not claim official support for Ubuntu 22.04 or Ubuntu 24.04 in this task.

---

## 15. Release Archive Requirements

The generated archive should have a deterministic and understandable structure.

Suggested structure:

```text
video-event-logger-v<version>-ubuntu20.04/
├── video-event-logger/
│   ├── video-event-logger
│   ├── _internal/
│   ├── video_event_logger/
│   │   └── assets/
│   │       └── app_icon.svg
│   └── ...
├── install_release.sh
├── BUILD_INFO.txt
└── README.md
```

Exact PyInstaller internal directory layout may differ depending on its version.

The archive must not include:

- virtual environments;
- Python source build directories;
- Docker cache files;
- repository `.git` directory;
- test files unrelated to installation;
- VLC libraries;
- VLC plugins;
- previous release archives;
- previous `build/` or `dist/` contents.

The archive name should include:

- application version;
- Ubuntu 20.04;
- architecture where practical.

Example:

```text
video-event-logger-v1.2.3-ubuntu20.04-amd64.tar.gz
```

---

## 16. Error Handling Requirements

All packaging shell scripts must use:

```bash
set -euo pipefail
```

Scripts must:

- quote variables;
- reject unsafe paths;
- print the failing validation step;
- avoid swallowing mandatory errors;
- use `|| true` only for optional operations;
- clean temporary virtual environments when practical;
- avoid modifying the host system outside mounted release directories.

A failed build or validation must return a non-zero exit code.

Do not create a release archive when validation has failed.

---

## 17. Acceptance Criteria

The task is complete only when all criteria below are satisfied.

### Build

- [ ] Docker image is based on Ubuntu 20.04.
- [ ] Build platform is explicitly `linux/amd64`.
- [ ] Docker build confirms `x86_64` and `amd64`.
- [ ] Python 3.12.4 is built with `--enable-shared`.
- [ ] `libpython3.12` is resolvable.
- [ ] Runtime and build dependency versions are pinned.
- [ ] PyInstaller uses an `onedir` build.
- [ ] Host-side and container-side build responsibilities are separated.
- [ ] Build metadata is generated.

### Binary compatibility

- [ ] Main executable is an x86-64 ELF.
- [ ] No packaged ELF file requires a glibc version newer than 2.31.
- [ ] No packaged ELF dependency is reported as `not found`.
- [ ] `libqxcb.so` exists and all of its dependencies resolve.
- [ ] No system VLC libraries are bundled.
- [ ] No VLC plugin directory is bundled.

### Runtime

- [ ] Target machine does not require Python.
- [ ] VLC is detected as a mandatory system dependency.
- [ ] Launcher does not set a global `LD_LIBRARY_PATH`.
- [ ] Launcher configures only the required VLC-specific paths.
- [ ] Application starts from the terminal on clean Ubuntu 20.04.
- [ ] Application starts from the desktop menu on clean Ubuntu 20.04.
- [ ] Application log is written to the XDG state directory.
- [ ] Smoke-test mode succeeds.
- [ ] Local H.264 MP4 playback works.

### Installation

- [ ] User-local installation succeeds without `sudo`.
- [ ] Missing VLC causes a clear installation failure.
- [ ] Reinstallation is safe.
- [ ] Desktop entry uses valid absolute paths.
- [ ] Application icon is displayed.
- [ ] Installation instructions are documented.

### Release

- [ ] Release archive contains only required runtime and installation files.
- [ ] Archive name includes application version and Ubuntu 20.04.
- [ ] Archive is not created when validation fails.
- [ ] Build and installation documentation is complete.

---

## 18. Expected Deliverables

The AI agent must provide:

1. Updated pinned requirements.
2. Updated Ubuntu 20.04 Dockerfile.
3. Updated PyInstaller spec.
4. Clear host-side Docker build script.
5. Clear container-side package build script.
6. Updated installation script.
7. Safe launcher implementation.
8. Automated validation script.
9. Runtime smoke-test implementation.
10. Release metadata generation.
11. Updated release archive generation.
12. Ubuntu 20.04 packaging README.
13. Summary of all changed files.
14. Exact build command.
15. Exact installation command.
16. Test results from the available environment.
17. Any remaining limitation that could not be verified locally.

---

## 19. Implementation Rules for the AI Agent

- Inspect the existing implementation before changing it.
- Reuse existing scripts where they already have a clear responsibility.
- Do not create unused alternative packaging flows.
- Do not change application behavior unrelated to packaging.
- Do not silently upgrade dependencies.
- Do not weaken Ubuntu 20.04 compatibility to support newer systems.
- Do not bundle glibc.
- Do not bundle system VLC.
- Do not set a global `LD_LIBRARY_PATH`.
- Do not hide validation failures.
- Do not claim a test passed unless it was actually executed.
- Clearly separate verified results from assumptions.
- Preserve the existing application version source in `video_event_logger/app_config.py`.
- Keep the existing release workflow usable from the repository root.
- Keep backward compatibility for existing user data and annotation files.
- Backward compatibility for old packaging scripts is not required if the documented replacement works.
