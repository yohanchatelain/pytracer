import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

included_packages = ("pytracer*", "significantdigits")

setuptools.setup(
    name="pytracer-pkg",
    version="0.0.1",
    author="Yohan Chatelain",
    author_email="yohan.chatelain@gmail.com",
    description="Pytracer",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yohanchatelain/pytracer",
    packages=setuptools.find_namespace_packages(include=included_packages),
    package_data={
        "pytracer": [
            "data/config/*.txt",
            "data/config/*.json"
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3.8",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires='>=3.8',
    scripts=["pytracer/scripts/pytracer"]
)
