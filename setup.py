from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="pinkml",
    version="0.1.0",
    description="A library for working with InkML files (.inkml)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Coderik/pinkml",
    author="Vadim Fedorov",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    packages=["inkml"],
    include_package_data=True,
    install_requires=[],
)
