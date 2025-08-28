from setuptools import setup, find_packages

setup(
    name="onuslibs",
    version="1.0.0",  # bump major vì BREAKING CHANGE (bỏ onuslibs)
    packages=find_packages(include=["onuslibs", "onuslibs.*"]),
    include_package_data=True,
    install_requires=[
        "cryptography",
        "python-dotenv",
        "keyring",
    ],
    extras_require={
        "ui": ["streamlit>=1.35"],
        "cli": ["typer>=0.12"],
    },
    entry_points={
        "console_scripts": [
            "onus=onuslibs.cli:app",
        ]
    },
    author="Nguyen Vu",
    description="OnusLibs: DB từ .env (thư mục cha), token ví nhập UI/CLI (keyring)",
)
