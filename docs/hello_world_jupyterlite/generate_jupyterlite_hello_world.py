#!/usr/bin/env python3
"""
Generate a JupyterLite notebook with specified code blocks.

This script:
1. Copies a Jupyter notebook from files/hello_world.ipynb
2. Copies jupyter_lite_config.json and requirements.txt
3. Builds the JupyterLite environment
4. Outputs to docs/extra-html/example_notebooks/hello_world

Options:
    --build: Build JupyterLite after preparing files
    --recreate-venv: Recreate the .venv-jupyterlite virtual environment
    --serve: Build and automatically serve the site (implies --build)
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent.parent
OUTPUT_DIR = ROOT_DIR / "docs" / "extra-html" / "example_notebooks" / "hello_world"
NOTEBOOK_DIR = OUTPUT_DIR / "files"

# Source files in the hello_world_jupyterlite directory
SOURCE_NOTEBOOK = SCRIPT_DIR / "files" / "hello_world.ipynb"
SOURCE_JUPYTERLITE_CONFIG = SCRIPT_DIR / "jupyter_lite_config.json"
SOURCE_REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
BUILD_CONFIG = SCRIPT_DIR / "jupyterlite_build_config.json"

# Destination paths in output directory
JUPYTERLITE_CONFIG_PATH = OUTPUT_DIR / "jupyter_lite_config.json"
REQUIREMENTS_PATH = OUTPUT_DIR / "requirements.txt"
WHEEL_DIR = OUTPUT_DIR / "wheels"


def copy_notebook():
    """Copy the Jupyter notebook from source to output directory."""
    if not SOURCE_NOTEBOOK.exists():
        raise FileNotFoundError(f"Source notebook not found: {SOURCE_NOTEBOOK}")
    
    # Create files directory
    NOTEBOOK_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy notebook
    notebook_path = NOTEBOOK_DIR / "hello_world.ipynb"
    shutil.copy2(SOURCE_NOTEBOOK, notebook_path)
    
    print(f"✅ Copied notebook: {notebook_path}")
    return notebook_path


def copy_requirements():
    """Copy requirements.txt from source to output directory."""
    if not SOURCE_REQUIREMENTS.exists():
        raise FileNotFoundError(f"Source requirements.txt not found: {SOURCE_REQUIREMENTS}")
    
    shutil.copy2(SOURCE_REQUIREMENTS, REQUIREMENTS_PATH)
    print(f"✅ Copied requirements.txt: {REQUIREMENTS_PATH}")


def download_wheel(package_name, version, output_dir):
    """Download a wheel file from PyPI if it doesn't exist locally."""
    wheel_name = f"{package_name}-{version}-py3-none-any.whl"
    wheel_path = output_dir / wheel_name
    
    if wheel_path.exists():
        print(f"✅ Wheel already exists: {wheel_path}")
        return wheel_path
    
    print(f"📥 Downloading {package_name} {version}...")
    try:
        import urllib.request
        # PyPI wheel URL format
        url = f"https://files.pythonhosted.org/packages/py3/{package_name[0]}/{package_name}/{package_name.replace('-', '_')}-{version}-py3-none-any.whl"
        
        # Try alternative URL patterns
        urls_to_try = [
            url,
            f"https://pypi.org/simple/{package_name}/#files",
            f"https://files.pythonhosted.org/packages/source/{package_name[0]}/{package_name}/{package_name.replace('-', '_')}-{version}.tar.gz"
        ]
        
        # For now, just create a placeholder - user will need to download manually
        # or we can use pip download
        print(f"⚠️  Need to download {wheel_name}")
        print(f"   Run: pip download {package_name}=={version} -d {output_dir}")
        return None
    except Exception as e:
        print(f"⚠️  Could not download {package_name}: {e}")
        return None


def copy_wheel():
    """Copy the buckaroo wheel to the output directory for JupyterLite to access."""
    # Read requirements.txt to find the wheel path
    with open(SOURCE_REQUIREMENTS, "r") as f:
        lines = f.readlines()
    
    wheel_path = None
    for line in lines:
        line = line.strip()
        if line.endswith(".whl") and "buckaroo" in line:
            # Handle relative path from requirements.txt
            # Path in requirements.txt is relative to OUTPUT_DIR (where it will be copied)
            if line.startswith("../"):
                # Resolve relative to OUTPUT_DIR
                wheel_path = (OUTPUT_DIR / line).resolve()
            else:
                # Absolute or relative to script dir
                wheel_path = Path(line)
                if not wheel_path.is_absolute():
                    wheel_path = (SCRIPT_DIR / wheel_path).resolve()
            break
    
    if not wheel_path or not wheel_path.exists():
        print(f"⚠️  Warning: Could not find buckaroo wheel")
        print(f"   Looked for: {wheel_path}")
        print(f"   Requirements.txt content: {lines}")
        # Try to find any buckaroo wheel in dist/
        dist_dir = ROOT_DIR / "dist"
        if dist_dir.exists():
            wheels = list(dist_dir.glob("buckaroo-*.whl"))
            if wheels:
                wheel_path = wheels[0]
                print(f"   Found wheel in dist/: {wheel_path}")
            else:
                print(f"   No buckaroo wheels found in {dist_dir}")
                return None
        else:
            return None
    
    # Create wheels directory in output
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy wheel to output directory
    dest_wheel = WHEEL_DIR / wheel_path.name
    shutil.copy2(wheel_path, dest_wheel)
    print(f"✅ Copied wheel: {dest_wheel}")
    print(f"   Wheel will be accessible at: ./wheels/{wheel_path.name}")
    return dest_wheel


def download_pyodide_wheels():
    """Download pyarrow and fastparquet wheels for Pyodide."""
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    
    print("📥 Downloading Pyodide-compatible wheels...")
    
    # Check if wheels already exist (try both 2024.5.0 and 2024.11.0 for fastparquet)
    pyarrow_wheels = list(WHEEL_DIR.glob("pyarrow-18.1.0*.whl"))
    fastparquet_wheels = list(WHEEL_DIR.glob("fastparquet-2024.5.0*.whl"))
    if not fastparquet_wheels:
        fastparquet_wheels = list(WHEEL_DIR.glob("fastparquet-2024.11.0*.whl"))
    
    if pyarrow_wheels and fastparquet_wheels:
        print(f"✅ Wheels already exist:")
        print(f"   {pyarrow_wheels[0].name}")
        print(f"   {fastparquet_wheels[0].name}")
        return True
    
    # Try to download using pip
    print("   Attempting to download with pip...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "download", 
             "pyarrow==18.1.0", "fastparquet==2024.11.0",  # Note: 2024.5.0 doesn't exist on PyPI, using 2024.11.0
             "-d", str(WHEEL_DIR),
             "--only-binary", ":all:"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ Downloaded wheels to", WHEEL_DIR)
        
        # Find the downloaded wheels (try both 2024.5.0 and 2024.11.0 for fastparquet)
        pyarrow_wheels = list(WHEEL_DIR.glob("pyarrow-18.1.0*.whl"))
        fastparquet_wheels = list(WHEEL_DIR.glob("fastparquet-2024.5.0*.whl"))
        if not fastparquet_wheels:
            fastparquet_wheels = list(WHEEL_DIR.glob("fastparquet-2024.11.0*.whl"))
        
        if pyarrow_wheels:
            print(f"✅ Found pyarrow wheel: {pyarrow_wheels[0].name}")
        else:
            print("⚠️  pyarrow wheel not found after download")
            
        if fastparquet_wheels:
            print(f"✅ Found fastparquet wheel: {fastparquet_wheels[0].name}")
        else:
            print("⚠️  fastparquet wheel not found after download")
            
        return len(pyarrow_wheels) > 0 and len(fastparquet_wheels) > 0
    except subprocess.CalledProcessError as e:
        print(f"⚠️  pip download failed")
        if e.stderr:
            stderr_text = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
            print(f"   Error: {stderr_text[:200]}")
        if e.stdout:
            stdout_text = e.stdout if isinstance(e.stdout, str) else e.stdout.decode()
            if "ERROR" in stdout_text or "Could not find" in stdout_text:
                print(f"   Details: {stdout_text[:300]}")
        print("   You may need to manually download the wheels:")
        print(f"   cd {WHEEL_DIR}")
        print("   pip download pyarrow==18.1.0 fastparquet==2024.11.0 --only-binary :all:")
        print("   Note: fastparquet 2024.5.0 doesn't exist on PyPI, using 2024.11.0")
        print("   Or download from PyPI and place in the wheels/ directory")
        return False


def copy_jupyterlite_config():
    """Copy JupyterLite configuration from source to output directory."""
    if not SOURCE_JUPYTERLITE_CONFIG.exists():
        raise FileNotFoundError(f"Source jupyter_lite_config.json not found: {SOURCE_JUPYTERLITE_CONFIG}")
    
    shutil.copy2(SOURCE_JUPYTERLITE_CONFIG, JUPYTERLITE_CONFIG_PATH)
    print(f"✅ Copied JupyterLite config: {JUPYTERLITE_CONFIG_PATH}")


def load_build_config():
    """Load build configuration from jupyterlite_build_config.json."""
    if not BUILD_CONFIG.exists():
        raise FileNotFoundError(f"Build config not found: {BUILD_CONFIG}")
    
    with open(BUILD_CONFIG, 'r') as f:
        config = json.load(f)
    
    return config.get("build", {})


def setup_jupyterlite_venv(recreate=False):
    """Set up the JupyterLite build virtual environment based on config.
    
    Args:
        recreate: If True, delete existing venv and recreate it.
    """
    config = load_build_config()
    python_version = config.get("python_version", "3.12")
    venv_name = config.get("venv_name", ".venv-jupyterlite")
    packages = config.get("packages", ["jupyterlite", "jupyterlite-pyodide-kernel", "jupyter-server"])
    
    venv_path = ROOT_DIR / venv_name
    venv_python = venv_path / "bin" / "python"
    
    # Check if venv already exists
    if venv_python.exists():
        if recreate:
            print(f"🗑️  Removing existing {venv_name}...")
            shutil.rmtree(venv_path)
            print(f"✅ Removed {venv_name}")
        else:
            # Verify the existing venv is using the correct Python version
            try:
                result = subprocess.run(
                    [str(venv_python), "--version"],
                    capture_output=True,
                    text=True,
                    check=True
                )
                actual_version = result.stdout.strip()
                print(f"✅ Using existing {venv_name}")
                print(f"   Python version: {actual_version}")
                # Check if it matches the expected version
                if python_version in actual_version:
                    print(f"   ✅ Venv Python version matches expected {python_version}")
                else:
                    print(f"   ⚠️  Venv Python version ({actual_version}) doesn't match expected {python_version}")
                    print(f"   Consider using --recreate-venv to rebuild with Python {python_version}")
            except subprocess.CalledProcessError:
                print(f"⚠️  Could not verify Python version in existing {venv_name}")
            return str(venv_python)
    
    # Create venv with specified Python version
    print(f"🔧 Setting up {venv_name} with Python {python_version}...")
    
    # Try to find Python with the specified version
    python_cmd = f"python{python_version}"
    try:
        # Check if the specific Python version is available
        result = subprocess.run(
            [python_cmd, "--version"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            raise FileNotFoundError
    except (FileNotFoundError, subprocess.CalledProcessError):
        # Try python3.12, python3, etc.
        for py_cmd in [f"python{python_version}", "python3", "python"]:
            try:
                result = subprocess.run(
                    [py_cmd, "--version"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    python_cmd = py_cmd
                    actual_version = result.stdout.strip()
                    print(f"   Found {python_cmd}: {actual_version}")
                    break
            except FileNotFoundError:
                continue
        else:
            print(f"❌ Could not find Python {python_version}")
            print("   Please install Python 3.12 or update jupyterlite_build_config.json")
            return None
    
    # Create venv using uv (preferred) or venv module
    try:
        print(f"   Creating virtual environment with {python_cmd}...")
        # Try uv first
        subprocess.run(
            ["uv", "venv", str(venv_path), "--python", python_cmd],
            check=True,
            capture_output=True
        )
        print(f"✅ Created {venv_name} with uv")
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall back to standard venv module
        try:
            subprocess.run(
                [python_cmd, "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True
            )
            print(f"✅ Created {venv_name} with venv module")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to create virtual environment: {e}")
            return None
    
    # Verify the created venv is using the correct Python version
    if venv_python.exists():
        try:
            result = subprocess.run(
                [str(venv_python), "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            actual_version = result.stdout.strip()
            print(f"   Verified venv Python version: {actual_version}")
            if python_version not in actual_version:
                print(f"   ⚠️  WARNING: Venv Python version ({actual_version}) doesn't match expected {python_version}")
                print(f"   This may cause issues. The venv was created with {python_cmd}")
        except subprocess.CalledProcessError:
            print(f"   ⚠️  Could not verify Python version in created venv")
    
    # Install packages in the venv
    print(f"   Installing packages: {', '.join(packages)}...")
    try:
        # Try uv pip first
        subprocess.run(
            ["uv", "pip", "install", "--python", str(venv_python)] + packages,
            check=True,
            capture_output=True
        )
        print(f"✅ Installed packages with uv")
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall back to pip
        try:
            subprocess.run(
                [str(venv_python), "-m", "pip", "install"] + packages + ["--quiet"],
                check=True,
                capture_output=True
            )
            print(f"✅ Installed packages with pip")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install packages: {e}")
            return None
    
    return str(venv_python)


def build_jupyterlite(recreate_venv=False):
    """Build the JupyterLite environment.
    
    Args:
        recreate_venv: If True, recreate the venv before building.
    """
    print("🔨 Building JupyterLite...")
    
    # Set up venv based on config
    python_cmd = setup_jupyterlite_venv(recreate=recreate_venv)
    if not python_cmd:
        return False
    
    if python_cmd != sys.executable:
        print(f"   Using Python from venv: {python_cmd}")
    
    # Build JupyterLite
    # Note: JupyterLite build process will:
    # 1. Copy notebooks from files/ directory
    # 2. Include packages from requirements.txt via micropip (packages available at runtime)
    # 3. Generate the static site in build/ directory
    try:
        # Try using python -m jupyterlite first
        print("   Building JupyterLite with Pyodide 0.27.0 (Python 3.12)...")
        print("   Note: Pyodide 0.27.0 includes Python 3.12.x")
        # Pyodide 0.27.0 has Python 3.12.x
        result = subprocess.run(
            [python_cmd, "-m", "jupyterlite", "build", "--pyodide", "https://github.com/pyodide/pyodide/releases/download/0.27.0/pyodide-0.27.0.tar.bz2"],
            cwd=OUTPUT_DIR,
            check=True,
            capture_output=True,
            text=True
        )
        # Only show last few lines of output to avoid clutter
        if result.stdout:
            lines = result.stdout.strip().split('\n')
            if len(lines) > 10:
                print("   ...")
                for line in lines[-5:]:
                    print(f"   {line}")
            else:
                print(result.stdout)
        print("✅ JupyterLite build completed")
        print(f"   Build output: {OUTPUT_DIR / 'build'}")
        print(f"   Serve from: {OUTPUT_DIR / 'build'}")
    except subprocess.CalledProcessError as e:
        # Try with jupyter command if available
        try:
            subprocess.run(
                [python_cmd, "-m", "jupyter", "lite", "build"],
                cwd=OUTPUT_DIR,
                check=True
            )
            print("✅ JupyterLite build completed")
            print(f"   Build output: {OUTPUT_DIR / 'build'}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"❌ JupyterLite build failed: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                stderr_text = e.stderr if isinstance(e.stderr, str) else e.stderr.decode()
                print(f"   Error: {stderr_text[:500]}")
            print("   You may need to install: pip install jupyterlite jupyterlite-pyodide-kernel jupyter-server")
            print("   Or create .venv-jupyterlite: uv venv .venv-jupyterlite")
            return False
    
    return True


def main():
    """Main function to generate JupyterLite notebook."""
    print("🚀 Generating JupyterLite hello world notebook...")
    print(f"   Source directory: {SCRIPT_DIR}")
    print(f"   Output directory: {OUTPUT_DIR}")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy notebook
    copy_notebook()
    
    # Copy requirements.txt
    copy_requirements()
    
    # Copy wheel to output directory
    wheel_path = copy_wheel()
    
    # Copy JupyterLite config first
    copy_jupyterlite_config()
    
    # Download pyarrow and fastparquet wheels for Pyodide
    wheels_downloaded = download_pyodide_wheels()
    
    # Update config with actual wheel names if they exist
    if wheels_downloaded:
        pyarrow_wheels = list(WHEEL_DIR.glob("pyarrow-18.1.0*.whl"))
        fastparquet_wheels = list(WHEEL_DIR.glob("fastparquet-2024.5.0*.whl"))
        if not fastparquet_wheels:
            fastparquet_wheels = list(WHEEL_DIR.glob("fastparquet-2024.11.0*.whl"))
        if pyarrow_wheels and fastparquet_wheels:
            # Update the config file with actual wheel names
            import json
            with open(JUPYTERLITE_CONFIG_PATH, "r") as f:
                config = json.load(f)
            config["LiteBuildConfig"]["piplite_wheels"] = [
                f"wheels/{pyarrow_wheels[0].name}",
                f"wheels/{fastparquet_wheels[0].name}"
            ]
            with open(JUPYTERLITE_CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=2)
            print(f"✅ Updated JupyterLite config with wheel names:")
            print(f"   wheels/{pyarrow_wheels[0].name}")
            print(f"   wheels/{fastparquet_wheels[0].name}")
    
    if wheel_path:
        print(f"\n💡 Note: The wheel is available at: {wheel_path.relative_to(OUTPUT_DIR)}")
        print(f"   The notebook should install it using: await micropip.install('./wheels/{wheel_path.name}')")
    
    # Build JupyterLite (optional - user can do this manually)
    print("\n📦 To build JupyterLite, run:")
    print(f"   cd {OUTPUT_DIR}")
    print("   jupyter lite build")
    print("\n🌐 To serve the built site, run:")
    print(f"   npx http-server -o {OUTPUT_DIR / 'build'}")
    print("\n   Or serve the entire directory (includes source files):")
    print(f"   npx http-server -o {OUTPUT_DIR}")
    
    # Optionally build now (skip prompt if --build flag is provided)
    import sys
    auto_build = '--build' in sys.argv or '--serve' in sys.argv
    recreate_venv = '--recreate-venv' in sys.argv
    build_now = 'y' if auto_build else input("\nBuild JupyterLite now? (y/n): ").strip().lower()
    if build_now == 'y':
        if build_jupyterlite(recreate_venv=recreate_venv):
            print("\n✅ JupyterLite build complete!")
            if '--serve' in sys.argv:
                # Auto-serve if --serve flag is provided
                print("\n🌐 Starting server...")
                import os
                os.chdir(OUTPUT_DIR / 'build')
                subprocess.Popen(['npx', 'http-server', '-p', '8080', '-o', '.'])
                print("   Server starting at http://localhost:8080")
            else:
                print(f"\n🌐 To serve the built site, run:")
                print(f"   cd {OUTPUT_DIR / 'build'}")
                print("   npx http-server -p 8080 -o .")
                print("\n   Or from the output directory:")
                print(f"   cd {OUTPUT_DIR}")
                print("   npx http-server -p 8080 -o build")
                print("\n   Or use the convenience script:")
                print("   ./docs/build_and_serve_jupyterlite.sh")
                print("\n   The build/ directory contains the static JupyterLite site.")
        else:
            print("\n⚠️  Build skipped or failed. You can build manually later.")
    else:
        print("\n⏭️  Skipping build. Run 'jupyter lite build' in the output directory when ready.")


if __name__ == "__main__":
    main()
