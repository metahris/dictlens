#!/usr/bin/env python
"""Development setup script for dictlens."""

import subprocess
import sys

def install_dev_dependencies():
    """Install development dependencies."""
    dev_packages = [
        "pytest>=7.0",
        "pytest-cov>=4.0",
        "coverage>=7.0",
        "black>=23.0",
        "isort>=5.12",
        "flake8>=6.0",
        "mypy>=1.0",
    ]

    print("📦 Installing development dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install"] + dev_packages)
    print("✅ Development dependencies installed!")

def install_package():
    """Install package in editable mode."""
    print("\n📦 Installing dictlens in editable mode...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])
    print("✅ Package installed in editable mode!")

def run_tests():
    """Run test suite."""
    print("\n🧪 Running tests...")
    subprocess.check_call([sys.executable, "-m", "pytest", "tests/", "-v"])
    print("✅ All tests passed!")

def main():
    """Main setup function."""
    print("=" * 60)
    print("🚀 dictlens Development Setup")
    print("=" * 60)

    try:
        install_dev_dependencies()
        install_package()
        run_tests()

        print("\n" + "=" * 60)
        print("✨ Setup complete! You're ready to contribute!")
        print("=" * 60)
        print("\nNext steps:")
        print("  • Run tests: pytest tests/ -v")
        print("  • Check coverage: pytest --cov=dictlens --cov-report=html")
        print("  • Format code: black dictlens/ tests/")
        print("  • Sort imports: isort dictlens/ tests/")
        print("  • Lint code: flake8 dictlens/ tests/")
        print("  • Type check: mypy dictlens/")
        print()

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
